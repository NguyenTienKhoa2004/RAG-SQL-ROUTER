"""Convert internal tool messages to public API data; presentation belongs to React."""
from .schemas import ToolResult


def collect_tool_results(chat_history):
    return [
        ToolResult(
            name=message.additional_kwargs.get("tool_used")
            or message.additional_kwargs.get("name", "tool"),
            content=message.content or "",
            is_error=bool(message.additional_kwargs.get("is_error", False)),
        )
        for message in chat_history if message.role == "tool"
    ]
