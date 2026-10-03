"""FastAPI transport. Models, state, and agent orchestration live in service.py."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, Query, UploadFile
from fastapi.responses import JSONResponse
from .config import AppConfig
from .database import read_city_database
from .schemas import ChatMessage, ChatRequest, DatabaseView, SessionRequest, SessionView
from .service import ServiceError, SessionService

logger = logging.getLogger(__name__)


def create_app(config: AppConfig | None = None, service: SessionService | None = None):
    config = config or AppConfig.from_environment()
    service = service or SessionService(config)

    @asynccontextmanager
    async def lifespan(app):
        yield
        service.close()

    app = FastAPI(title="RAG + SQL Workspace", version="0.2.0", lifespan=lifespan)
    app.state.service = service

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        return JSONResponse(status_code=exc.status, content={"detail": str(exc)})

    @app.get("/api/health")
    def health():
        return {
            "status": "ok", "database_available": config.database_path.is_file(),
            "server_key_configured": bool(os.getenv("OPENROUTER_API_KEY", "").strip()),
            "model": config.llm_model, "max_upload_bytes": config.max_upload_bytes,
        }

    @app.post("/api/sessions", response_model=SessionView, status_code=201)
    async def connect(body: SessionRequest):
        key = body.api_key.get_secret_value() if body.api_key else None
        try:
            # Initialize in the event-loop thread; workflow locks belong to that loop.
            return service.create(key)
        except ServiceError:
            raise
        except Exception:
            logger.exception("Workspace initialization failed")
            raise ServiceError("Could not initialize the workspace. Check the backend logs and configuration.", 503)

    @app.get("/api/sessions/{session_id}", response_model=SessionView)
    async def session_info(session_id: str):
        session = service.get(session_id)
        async with session.lock:
            return service.view(session)

    @app.post("/api/sessions/{session_id}/chat", response_model=ChatMessage)
    async def chat(session_id: str, body: ChatRequest):
        return await service.chat(session_id, body.message)

    @app.post("/api/sessions/{session_id}/documents", response_model=SessionView)
    async def upload(session_id: str, files: list[UploadFile] = File(...)):
        service.get(session_id)
        documents = []
        total = 0
        try:
            for file in files:
                content = await file.read(config.max_upload_bytes - total + 1)
                total += len(content)
                if total > config.max_upload_bytes:
                    raise ServiceError("The upload exceeds the configured size limit.", 413)
                documents.append((file.filename or "", content))
            return await service.upload(session_id, documents)
        finally:
            for file in files:
                await file.close()

    @app.post("/api/sessions/{session_id}/reset", response_model=SessionView)
    async def reset(session_id: str):
        return await service.reset(session_id)

    @app.delete("/api/sessions/{session_id}", status_code=204)
    async def disconnect(session_id: str):
        await service.delete(session_id)

    @app.get("/api/database", response_model=DatabaseView)
    async def database(
        page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
        search: str = Query("", max_length=200),
    ):
        try:
            return await asyncio.to_thread(read_city_database, config.database_path, page, page_size, search)
        except Exception:
            logger.exception("Database browser failed")
            raise ServiceError("The city database is unavailable.", 503)

    return app


app = create_app()
