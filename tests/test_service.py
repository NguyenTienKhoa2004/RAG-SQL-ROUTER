"""Session invariants after extracting orchestration from Streamlit."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from llama_index.core.llms import ChatMessage
from backend.config import AppConfig
from backend.service import ServiceError, SessionService


def tool(name):
    return SimpleNamespace(metadata=SimpleNamespace(name=name))


class StubWorkflow:
    def __init__(self, tools, llm, timeout, chat_history=None):
        self.tools = tools
        self.chat_history = list(chat_history or [])
        self.current_turn_history = []

    async def run(self, message):
        self.current_turn_history = [
            ChatMessage(role="user", content=message),
            ChatMessage(role="tool", content="raw tool result",
                        additional_kwargs={"tool_used": "sql_tool"}),
            ChatMessage(role="assistant", content="final synthesized answer"),
        ]
        self.chat_history.extend(self.current_turn_history)
        return "final synthesized answer"

    def reset(self):
        self.chat_history.clear()


class SessionServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        database = Path(self.directory.name, "cities.sqlite")
        database.touch()
        self.service = SessionService(AppConfig(database_path=database))
        patches = [
            patch("backend.service.create_llm", side_effect=lambda key, model: SimpleNamespace(key=key)),
            patch("backend.service.setup_sql_tool", return_value=tool("sql_tool")),
            patch("backend.service.RouterOutputAgentWorkflow", side_effect=StubWorkflow),
            patch("backend.service.get_embedding_model", return_value=object()),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.service.close)
        self.first = self.service.create("first-key")

    async def test_follow_up_preserves_history_and_returns_final_answer_with_current_tools(self):
        session = self.service.get(self.first.id)
        await self.service.chat(session.id, "Chicago population?")
        previous = list(session.workflow.chat_history)
        answer = await self.service.chat(session.id, "Which state is that city in?")
        self.assertEqual(session.workflow.chat_history[:len(previous)], previous)
        self.assertEqual(answer.content, "final synthesized answer")
        self.assertEqual(len(answer.tools), 1)
        self.assertEqual(answer.tools[0].content, "raw tool result")
        self.assertEqual(len(session.messages), 4)

    async def test_sessions_do_not_share_credentials_or_chat_history(self):
        second = self.service.create("second-key")
        await self.service.chat(self.first.id, "Remember Chicago")
        self.assertEqual(self.service.get(second.id).workflow.chat_history, [])
        self.assertNotEqual(self.service.get(second.id).llm.key,
                            self.service.get(self.first.id).llm.key)
        self.assertNotIn("first-key", self.first.model_dump_json())

    async def test_failed_turn_is_rolled_back_without_losing_previous_context(self):
        session = self.service.get(self.first.id)
        await self.service.chat(session.id, "Chicago population?")
        previous = list(session.workflow.chat_history)

        async def fail(message):
            session.workflow.chat_history.append(ChatMessage(role="user", content=message))
            raise RuntimeError("failed")

        session.workflow.run = fail
        with self.assertRaises(ServiceError):
            await self.service.chat(session.id, "Which state?")
        self.assertEqual(session.workflow.chat_history, previous)
        self.assertEqual(len(session.messages), 2)

    async def test_timeout_is_reported_and_partial_history_is_removed(self):
        session = self.service.get(self.first.id)
        previous = list(session.workflow.chat_history)

        async def fail(message):
            session.workflow.chat_history.append(ChatMessage(role="user", content=message))
            raise asyncio.TimeoutError()

        session.workflow.run = fail
        with self.assertRaises(ServiceError) as error:
            await self.service.chat(session.id, "Which state?")
        self.assertEqual(error.exception.status, 504)
        self.assertEqual(session.workflow.chat_history, previous)

    async def test_upload_rebuild_preserves_history_and_reset_keeps_documents(self):
        session = self.service.get(self.first.id)
        await self.service.chat(session.id, "Chicago?")
        history = list(session.workflow.chat_history)
        with patch("backend.service.setup_document_tool", new_callable=AsyncMock, return_value=tool("document_tool")) as build:
            view = await self.service.upload(session.id, [("policy.txt", b"Policy text")])
        self.assertEqual(session.workflow.chat_history, history)
        self.assertEqual(view.available_tools, ["sql_tool", "document_tool"])
        self.assertEqual(Path(session.directory.name, "policy.txt").read_bytes(), b"Policy text")
        self.assertIs(build.call_args.kwargs["llm"], session.llm)
        view = await self.service.reset(session.id)
        self.assertEqual(view.messages, [])
        self.assertEqual(session.workflow.chat_history, [])
        self.assertEqual(view.documents[0].name, "policy.txt")

    async def test_failed_upload_keeps_the_previous_index_and_files(self):
        session = self.service.get(self.first.id)
        previous = session.workflow
        directory = session.directory.name
        with patch("backend.service.setup_document_tool", side_effect=RuntimeError("Milvus unavailable")):
            with self.assertRaises(ServiceError):
                await self.service.upload(session.id, [("policy.txt", b"Policy text")])
        self.assertIs(session.workflow, previous)
        self.assertEqual(session.directory.name, directory)
        self.assertEqual(session.documents, {})
        self.assertFalse(Path(directory, "policy.txt").exists())

    async def test_upload_rejects_path_traversal_and_unsupported_files(self):
        for name in ("../secret.txt", "..\\secret.txt", "C:\\secret.txt", "code.exe"):
            with self.subTest(name=name), self.assertRaises(ServiceError):
                await self.service.upload(self.first.id, [(name, b"text")])

    async def test_reupload_deletes_old_collection_after_switching_workflow(self):
        session = self.service.get(self.first.id)
        with patch("backend.service.setup_document_tool", new_callable=AsyncMock,
                   return_value=tool("document_tool")) as build, patch(
            "backend.service.delete_document_collection",
        ) as delete:
            await self.service.upload(session.id, [("policy.txt", b"Old policy")])
            delete.assert_not_called()
            old_collection = session.collection_name
            old_workflow = session.workflow

            def check_active_index(uri, collection_name):
                self.assertEqual(collection_name, old_collection)
                self.assertNotEqual(session.collection_name, old_collection)
                self.assertIsNot(session.workflow, old_workflow)
                self.assertEqual(Path(session.directory.name, "policy.txt").read_bytes(), b"New policy")

            delete.side_effect = check_active_index
            await self.service.upload(session.id, [("policy.txt", b"New policy")])
            delete.assert_called_once_with(self.service.config.milvus_uri, old_collection)
            self.assertEqual(session.collection_name, build.call_args.kwargs["collection_name"])

    async def test_failed_reupload_does_not_delete_active_collection(self):
        session = self.service.get(self.first.id)
        with patch("backend.service.setup_document_tool", new_callable=AsyncMock,
                   return_value=tool("document_tool")):
            await self.service.upload(session.id, [("policy.txt", b"Old policy")])
        old_collection = session.collection_name
        old_workflow = session.workflow
        with patch("backend.service.setup_document_tool", side_effect=RuntimeError("Index failed")), patch(
            "backend.service.delete_document_collection",
        ) as delete:
            with self.assertRaises(ServiceError):
                await self.service.upload(session.id, [("policy.txt", b"New policy")])
            delete.assert_not_called()
        self.assertEqual(session.collection_name, old_collection)
        self.assertIs(session.workflow, old_workflow)
        self.assertEqual(Path(session.directory.name, "policy.txt").read_bytes(), b"Old policy")

    async def test_cleanup_failure_does_not_fail_successful_upload(self):
        session = self.service.get(self.first.id)
        with patch("backend.service.setup_document_tool", new_callable=AsyncMock,
                   return_value=tool("document_tool")):
            await self.service.upload(session.id, [("policy.txt", b"Old policy")])
            old_collection = session.collection_name
            with patch("backend.service.delete_document_collection", side_effect=RuntimeError("Milvus unavailable")), \
                    self.assertLogs("backend.service", level="ERROR") as logs:
                view = await self.service.upload(session.id, [("policy.txt", b"New policy")])
        self.assertNotEqual(session.collection_name, old_collection)
        self.assertEqual(view.available_tools, ["sql_tool", "document_tool"])
        self.assertEqual(Path(session.directory.name, "policy.txt").read_bytes(), b"New policy")
        self.assertIn(old_collection, logs.output[0])

    async def test_disconnect_removes_session_and_temporary_files(self):
        directory = self.service.get(self.first.id).directory.name
        await self.service.delete(self.first.id)
        self.assertFalse(Path(directory).exists())
        with self.assertRaises(ServiceError) as error:
            self.service.get(self.first.id)
        self.assertEqual(error.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
