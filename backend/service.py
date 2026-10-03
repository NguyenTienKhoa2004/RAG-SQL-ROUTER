"""Session orchestration. No HTTP or UI dependencies live in this module."""
import asyncio
import os
import shutil
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory
from time import monotonic, perf_counter
from uuid import uuid4
from .config import AppConfig
from .rag.tools import setup_document_tool, setup_sql_tool
from .rag.workflow import RouterOutputAgentWorkflow
from .schemas import ChatMessage, DocumentInfo, SessionView
from .serialization import collect_tool_results


class ServiceError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@lru_cache(maxsize=2)
def get_embedding_model(model_name):
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    return HuggingFaceEmbedding(model_name=model_name)


def create_llm(api_key, model_name):
    from llama_index.llms.openrouter import OpenRouter
    return OpenRouter(model=model_name, api_key=api_key)


@dataclass
class Session:
    id: str
    llm: object
    sql_tool: object
    workflow: RouterOutputAgentWorkflow
    directory: TemporaryDirectory = field(default_factory=TemporaryDirectory)
    documents: dict[str, DocumentInfo] = field(default_factory=dict)
    messages: list[ChatMessage] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    touched: float = field(default_factory=monotonic)


class SessionService:
    def __init__(self, config: AppConfig):
        self.config = config
        self.sessions: dict[str, Session] = {}

    def prune(self):
        for session_id, session in list(self.sessions.items()):
            if monotonic() - session.touched > self.config.session_ttl and not session.lock.locked():
                self.sessions.pop(session_id)
                session.directory.cleanup()

    def create(self, api_key: str | None = None) -> SessionView:
        self.prune()
        if len(self.sessions) >= self.config.max_sessions:
            raise ServiceError("Workspace capacity reached. Close an existing session and retry.", 503)
        key = (api_key or os.getenv("OPENROUTER_API_KEY", "")).strip()
        if not key:
            raise ServiceError("Enter an OpenRouter API key to connect your workspace.")
        if not self.config.database_path.is_file():
            raise ServiceError("The configured city database is missing.", 503)
        llm = create_llm(key, self.config.llm_model)
        sql_tool = setup_sql_tool(str(self.config.database_path), llm=llm)
        session_id = uuid4().hex
        workflow = RouterOutputAgentWorkflow(tools=[sql_tool], llm=llm, timeout=self.config.query_timeout)
        self.sessions[session_id] = Session(session_id, llm, sql_tool, workflow)
        return self.view(self.sessions[session_id])

    def get(self, session_id) -> Session:
        self.prune()
        session = self.sessions.get(session_id)
        if session is None:
            raise ServiceError("This session has expired. Reconnect to start a new workspace.", 404)
        session.touched = monotonic()
        return session

    def view(self, session: Session) -> SessionView:
        return SessionView(
            id=session.id, model=self.config.llm_model,
            documents=list(session.documents.values()), messages=session.messages,
            available_tools=[tool.metadata.name for tool in session.workflow.tools],
        )

    async def chat(self, session_id, question) -> ChatMessage:
        session = self.get(session_id)
        question = question.strip()
        if not question:
            raise ServiceError("Your question cannot be empty.")
        async with session.lock:
            turn_start = len(session.workflow.chat_history)
            started = perf_counter()
            try:
                result = await asyncio.wait_for(
                    session.workflow.run(message=question), timeout=self.config.query_timeout,
                )
            except (asyncio.CancelledError, Exception) as exc:
                del session.workflow.chat_history[turn_start:]
                if isinstance(exc, asyncio.CancelledError):
                    raise
                if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
                    raise ServiceError("The query timed out. Try a simpler question.", 504) from exc
                raise ServiceError("The query could not be completed. Please retry.", 502) from exc
            tools = collect_tool_results(session.workflow.current_turn_history)
            answer = ChatMessage(
                id=uuid4().hex, role="assistant", content=str(result or "No answer was returned."),
                tools=tools, duration_ms=round((perf_counter() - started) * 1000),
            )
            session.messages.extend([
                ChatMessage(id=uuid4().hex, role="user", content=question), answer,
            ])
            session.touched = monotonic()
            return answer

    async def upload(self, session_id, files: list[tuple[str, bytes]]) -> SessionView:
        session = self.get(session_id)
        if not files:
            raise ServiceError("Choose at least one document.")
        allowed = {".pdf", ".docx", ".pptx", ".txt", ".md"}
        if sum(len(content) for _, content in files) > self.config.max_upload_bytes:
            raise ServiceError("The upload exceeds the configured size limit.", 413)
        for name, content in files:
            if (not name or Path(name).name != name or PureWindowsPath(name).name != name
                    or name in {".", ".."} or ":" in name or "\x00" in name):
                raise ServiceError("Invalid document filename.")
            if Path(name).suffix.lower() not in allowed:
                raise ServiceError("Supported formats: PDF, DOCX, PPTX, TXT and Markdown.")
            if not content:
                raise ServiceError(f"{name} is empty.")
        async with session.lock:
            staging = TemporaryDirectory()
            try:
                # Build a replacement index before touching the active session.
                shutil.copytree(session.directory.name, staging.name, dirs_exist_ok=True)
                documents = dict(session.documents)
                for name, content in files:
                    Path(staging.name, name).write_bytes(content)
                    documents[name] = DocumentInfo(name=name, size=len(content))

                embed_model = await asyncio.to_thread(get_embedding_model, self.config.embedding_model)
                document_tool = await setup_document_tool(
                    staging.name, self.config.milvus_uri, llm=session.llm,
                    embed_model=embed_model,
                )
                workflow = RouterOutputAgentWorkflow(
                    tools=[session.sql_tool, document_tool], llm=session.llm,
                    timeout=self.config.query_timeout, chat_history=session.workflow.chat_history,
                )
            except Exception as exc:
                staging.cleanup()
                raise ServiceError(
                    "Document processing failed. Check the file contents and Milvus connection.", 502,
                ) from exc
            old_directory = session.directory
            session.directory = staging
            session.documents = documents
            session.workflow = workflow
            session.touched = monotonic()
            old_directory.cleanup()
            return self.view(session)

    async def reset(self, session_id):
        session = self.get(session_id)
        async with session.lock:
            session.workflow.reset()
            session.messages.clear()
            return self.view(session)

    async def delete(self, session_id):
        session = self.get(session_id)
        async with session.lock:
            self.sessions.pop(session_id, None)
            session.directory.cleanup()

    def close(self):
        for session in self.sessions.values():
            session.directory.cleanup()
        self.sessions.clear()
