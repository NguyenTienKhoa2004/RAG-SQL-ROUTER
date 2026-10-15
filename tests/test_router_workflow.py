import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from llama_index.core.llms import ChatMessage, ChatResponse
from llama_index.core.llms.llm import ToolSelection
from llama_index.core.tools import FunctionTool, ToolOutput

from backend.serialization import collect_tool_results
from backend.rag.workflow import RouterOutputAgentWorkflow


class RouterWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def make_llm(self, tool_name=None, query="question"):
        selections = [] if tool_name is None else [ToolSelection(
            tool_id="call_1", tool_name=tool_name, tool_kwargs={"query": query}
        )]
        return SimpleNamespace(
            achat_with_tools=AsyncMock(side_effect=[
                ChatResponse(message=ChatMessage(role="assistant", content="refusal")),
                ChatResponse(message=ChatMessage(role="assistant", content="finished")),
            ]),
            get_tool_calls_from_response=Mock(side_effect=[selections, []]),
        )

    async def test_shipping_question_uses_real_document_tool_and_has_no_fake_score(self):
        query = "đơn hàng có giá trị bao nhiêu được miễn phí giao hàng?"
        document = Path("data/cua_hang_mau.txt").read_text(encoding="utf-8")
        answer = next(line for line in document.splitlines() if "700.000" in line)
        lookup = Mock(return_value={"response": answer})

        def search(query: str):
            return lookup(query)

        document_tool = FunctionTool.from_defaults(search, name="document_tool")
        sql_tool = FunctionTool.from_defaults(search, name="sql_tool")
        llm = self.make_llm("document_tool", query)
        workflow = RouterOutputAgentWorkflow(tools=[document_tool, sql_tool], llm=llm)
        result = await workflow.run(message=query)
        lookup.assert_called_once_with(query)
        first, last = llm.achat_with_tools.call_args_list
        self.assertTrue(first.kwargs["tool_required"])
        self.assertFalse(last.kwargs["tool_required"])
        prompt = first.kwargs["chat_history"][0]
        self.assertEqual(prompt.role, "system")
        self.assertIn("free shipping", prompt.content)
        tools = collect_tool_results(workflow.current_turn_history)
        self.assertEqual(tools[0].name, "document_tool")
        rendered = tools[0].model_dump_json()
        self.assertIn("700.000", rendered)
        self.assertIn("document_tool", rendered)
        self.assertNotIn("Trust Score", rendered)
        self.assertNotIn("{'response':", rendered)

    async def test_sql_tool_keeps_its_identity_without_document_score(self):
        def search(query: str):
            return "Chicago population: 2,746,388"

        llm = self.make_llm("sql_tool", "Chicago population?")
        workflow = RouterOutputAgentWorkflow(
            tools=[FunctionTool.from_defaults(search, name="sql_tool")], llm=llm
        )
        result = await workflow.run(message="Chicago population?")
        tools = collect_tool_results(workflow.current_turn_history)
        self.assertEqual(tools[0].name, "sql_tool")
        rendered = tools[0].model_dump_json()
        self.assertNotIn("document_tool", rendered)
        self.assertNotIn("Trust Score", rendered)

    async def test_document_policy_can_be_followed_by_sql_in_the_same_turn(self):
        policy = Mock(return_value={"response": "September standard shipping is free from 500000 VND."})
        facts = Mock(return_value="DH1002: merchandise 600000 VND, shipping charged 30000 VND.")

        def search_policy(query: str):
            return policy(query)

        def search_sales(query: str):
            return facts(query)

        llm = self.make_llm()
        llm.achat_with_tools.side_effect = [
            ChatResponse(message=ChatMessage(role="assistant", content=value))
            for value in ("", "", "DH1002 was overcharged 30000 VND.")
        ]
        llm.get_tool_calls_from_response.side_effect = [
            [ToolSelection(tool_id="policy", tool_name="document_tool", tool_kwargs={"query": "September shipping rules?"})],
            [ToolSelection(tool_id="facts", tool_name="sql_tool", tool_kwargs={"query": "DH1002 merchandise and shipping fee?"})],
            [],
        ]
        workflow = RouterOutputAgentWorkflow(tools=[
            FunctionTool.from_defaults(search_policy, name="document_tool"),
            FunctionTool.from_defaults(search_sales, name="sql_tool"),
        ], llm=llm)
        answer = await workflow.run(message="Was DH1002 charged the correct shipping fee?")
        self.assertEqual(answer, "DH1002 was overcharged 30000 VND.")
        self.assertEqual([tool.name for tool in collect_tool_results(workflow.current_turn_history)],
                         ["document_tool", "sql_tool"])
        facts.assert_called_once()
        second_prompt = llm.achat_with_tools.call_args_list[1].kwargs["chat_history"]
        self.assertTrue(any(message.role == "tool" and "500000" in message.content for message in second_prompt))

    async def test_missing_tool_call_reports_failure_without_fabricated_metadata(self):
        def search(query: str):
            raise AssertionError("should not be called")

        llm = self.make_llm()
        workflow = RouterOutputAgentWorkflow(
            tools=[FunctionTool.from_defaults(search, name="document_tool")], llm=llm
        )
        result = await workflow.run(message="Free shipping?")
        self.assertEqual(collect_tool_results(workflow.current_turn_history), [])
        rendered = result
        self.assertIn("không gọi công cụ", rendered)
        self.assertNotIn("refusal", rendered)
        self.assertNotIn("Tool Used", rendered)
        self.assertNotIn("Trust Score", rendered)

    async def test_structured_document_response_is_unwrapped_without_score(self):
        def search(query: str):
            return {"response": "700.000 đồng"}

        llm = self.make_llm("document_tool")
        workflow = RouterOutputAgentWorkflow(
            tools=[FunctionTool.from_defaults(search, name="document_tool")], llm=llm
        )
        result = await workflow.run(message="Free shipping?")
        rendered = collect_tool_results(workflow.current_turn_history)[0].content
        self.assertIn("700.000 đồng", rendered)
        self.assertNotIn("{'response':", rendered)
        self.assertNotIn("Trust Score", rendered)

    async def test_tool_error_keeps_error_metadata(self):
        def search(query: str):
            return ToolOutput(
                tool_name="document_tool", content="Error executing tool: unavailable",
                raw_input={}, raw_output={"response": "unavailable"},
                is_error=True,
            )

        llm = self.make_llm("document_tool")
        workflow = RouterOutputAgentWorkflow(
            tools=[FunctionTool.from_defaults(search, name="document_tool",
                                              callback=lambda output: output)], llm=llm
        )
        result = await workflow.run(message="Free shipping?")
        tools = collect_tool_results(workflow.current_turn_history)
        self.assertTrue(tools[0].is_error)
        rendered = tools[0].content
        self.assertIn("unavailable", rendered)
        self.assertTrue(next(message for message in workflow.chat_history
                             if message.role == "tool").additional_kwargs["is_error"])
        self.assertNotIn("Trust Score", rendered)

    async def test_follow_up_keeps_context_and_requires_a_new_tool_call(self):
        lookup = Mock(side_effect=["Chicago population: 2,746,388", "Chicago is in Illinois"])

        def search(query: str):
            return lookup(query)

        llm = self.make_llm()
        llm.achat_with_tools.side_effect = [
            ChatResponse(message=ChatMessage(role="assistant", content=content))
            for content in ("", "Chicago population: 2,746,388", "", "Chicago is in Illinois")
        ]
        llm.get_tool_calls_from_response.side_effect = [
            [ToolSelection(tool_id="call_1", tool_name="sql_tool",
                           tool_kwargs={"query": "Dân số Chicago là bao nhiêu?"})],
            [],
            [ToolSelection(tool_id="call_2", tool_name="sql_tool",
                           tool_kwargs={"query": "Chicago thuộc bang nào?"})],
            [],
        ]
        workflow = RouterOutputAgentWorkflow(
            tools=[FunctionTool.from_defaults(search, name="sql_tool")], llm=llm
        )
        await workflow.run(message="Dân số Chicago là bao nhiêu?")
        result = await workflow.run(message="Thành phố đó thuộc bang nào?")

        calls = llm.achat_with_tools.call_args_list
        self.assertEqual([call.kwargs["tool_required"] for call in calls],
                         [True, False, True, False])
        follow_up_history = calls[2].kwargs["chat_history"]
        contents = [message.content for message in follow_up_history]
        self.assertIn("Dân số Chicago là bao nhiêu?", contents)
        self.assertIn("Chicago population: 2,746,388", contents)
        self.assertEqual(contents[-1], "Thành phố đó thuộc bang nào?")
        self.assertEqual(lookup.call_count, 2)
        rendered = collect_tool_results(workflow.current_turn_history)[0].content
        self.assertIn("Illinois", rendered)
        self.assertNotIn("2,746,388", rendered)

    async def test_old_tool_result_does_not_hide_missing_follow_up_tool_call(self):
        history = [
            ChatMessage(role="user", content="Chicago population?"),
            ChatMessage(role="tool", content="Old population result"),
            ChatMessage(role="assistant", content="Chicago population: 2,746,388"),
        ]
        llm = self.make_llm()
        workflow = RouterOutputAgentWorkflow(
            tools=[FunctionTool.from_defaults(lambda query: "unused", name="sql_tool")],
            llm=llm, chat_history=history,
        )
        result = await workflow.run(message="Which state is that city in?")
        self.assertTrue(llm.achat_with_tools.call_args.kwargs["tool_required"])
        self.assertEqual(collect_tool_results(workflow.current_turn_history), [])
        rendered = result
        self.assertIn("không gọi công cụ", rendered)
        self.assertNotIn("Old population result", rendered)
        self.assertNotIn("Tool Used", rendered)

    async def test_reset_clears_conversation_context(self):
        llm = self.make_llm()
        workflow = RouterOutputAgentWorkflow(
            tools=[], llm=llm,
            chat_history=[ChatMessage(role="user", content="Remember Chicago")],
        )
        workflow.reset()
        await workflow.run(message="Hello")
        self.assertEqual(workflow.current_turn_history, workflow.chat_history)
        contents = [message.content for message in llm.achat_with_tools.call_args.kwargs["chat_history"]]
        self.assertNotIn("Remember Chicago", contents)

    def test_plain_answer_or_error_has_no_fabricated_metadata(self):
        for result in ("OpenRouter authentication failed", "Xin chào"):
            self.assertEqual(collect_tool_results([ChatMessage(role="assistant", content=result)]), [])


if __name__ == "__main__":
    unittest.main()
