"""Public HTTP contracts; credentials and internal LLM messages stay private."""
from typing import Literal
from pydantic import BaseModel, Field, SecretStr


class SessionRequest(BaseModel):
    api_key: SecretStr | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)


class ToolResult(BaseModel):
    name: str
    content: str
    is_error: bool = False


class ChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    tools: list[ToolResult] = Field(default_factory=list)
    duration_ms: int | None = None


class DocumentInfo(BaseModel):
    name: str
    size: int


class SessionView(BaseModel):
    id: str
    model: str
    documents: list[DocumentInfo]
    messages: list[ChatMessage]
    available_tools: list[str]


class DatabaseView(BaseModel):
    table: str
    columns: list[str]
    rows: list[dict]
    total: int
    total_population: int
    states: int
    page: int
    page_size: int
