"""Use the actual SQL engine, not a mocked factory, to catch provider fallback."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from llama_index.core import Settings
from llama_index.core.llms import CompletionResponse, MockLLM

from backend.api import create_app
from backend.config import AppConfig
from backend.rag.sql_embedding import SQLOnlyEmbedding
from backend.rag.tools import setup_sql_tool


class SQLLLM(MockLLM):
    def complete(self, prompt, formatted=False, **kwargs):
        return CompletionResponse(
            text="SQLQuery: SELECT population FROM city_stats WHERE city_name = 'Chicago';\nSQLResult:"
        )


class SQLInitializationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name, "cities.sqlite")
        with closing(sqlite3.connect(self.path)) as database:
            database.execute("CREATE TABLE city_stats (city_name TEXT, population INTEGER, state TEXT)")
            database.execute("INSERT INTO city_stats VALUES ('Chicago', 2746388, 'Illinois')")
            database.commit()

    def test_session_creation_uses_real_sql_engine_without_any_embedding_provider(self):
        config = AppConfig(database_path=self.path)
        with patch.object(Settings, "_embed_model", None), patch(
            "llama_index.core.settings.resolve_embed_model",
            side_effect=AssertionError("Default embedding provider must not be loaded"),
        ) as resolve, patch(
            "backend.service.get_embedding_model",
            side_effect=AssertionError("Document model must remain lazy"),
        ) as documents, TestClient(create_app(config)) as client:
            # OpenRouter constructs a client locally; this is not a live API call.
            response = client.post("/api/sessions", json={"api_key": "placeholder-not-a-real-key"})
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(response.json()["available_tools"], ["sql_tool"])
            self.assertNotIn("placeholder-not-a-real-key", response.text)
            resolve.assert_not_called()
            documents.assert_not_called()
            self.assertIsNone(Settings._embed_model)
            session = client.app.state.service.get(response.json()["id"])
            session.sql_tool.query_engine.sql_retriever._sql_database.engine.dispose()

    def test_real_text_to_sql_executes_without_generating_embeddings(self):
        with patch.object(Settings, "_embed_model", None), patch(
            "llama_index.core.settings.resolve_embed_model",
            side_effect=AssertionError("Default embedding provider must not be loaded"),
        ):
            tool = setup_sql_tool(str(self.path), llm=SQLLLM())
            try:
                result = tool.call("What is Chicago's population?")
                self.assertFalse(result.is_error, result.content)
                self.assertEqual(result.raw_output.metadata["result"], [(2746388,)])
                self.assertIn("SELECT population", result.raw_output.metadata["sql_query"])
                self.assertIsNone(Settings._embed_model)
            finally:
                tool.query_engine.sql_retriever._sql_database.engine.dispose()

    def test_sql_embedding_guard_rejects_accidental_vector_use(self):
        with self.assertRaisesRegex(RuntimeError, "SQL-only"):
            SQLOnlyEmbedding().get_query_embedding("Chicago")


if __name__ == "__main__":
    unittest.main()
