"""Backend entry point: uv run uvicorn app:app --reload."""

from backend.api import app

__all__ = ["app"]
