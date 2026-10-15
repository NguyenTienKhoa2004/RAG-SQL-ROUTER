"""Central configuration; paths are independent of the launch directory."""
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class AppConfig:
    database_path: Path
    milvus_uri: str = "http://localhost:19530"
    llm_model: str = "qwen/qwen3-30b-a3b-instruct-2507"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    query_timeout: float = 60
    max_upload_bytes: int = 20 * 1024 * 1024
    session_ttl: float = 12 * 60 * 60
    max_sessions: int = 100

    @classmethod
    def from_environment(cls):
        database = Path(os.getenv("DATABASE_PATH", "sales_database.sqlite"))
        return cls(
            database_path=database if database.is_absolute() else PROJECT_ROOT / database,
            milvus_uri=os.getenv("MILVUS_URI", "http://localhost:19530"),
            llm_model=os.getenv("LLM_MODEL", cls.llm_model),
            embedding_model=os.getenv("EMBEDDING_MODEL", cls.embedding_model),
            query_timeout=float(os.getenv("QUERY_TIMEOUT_SECONDS", "60")),
            max_upload_bytes=int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024,
        )
