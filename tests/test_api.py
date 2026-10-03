"""HTTP contracts and fixed database browsing; no paid LLM calls needed."""
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.config import AppConfig
from backend.service import SessionService
from test_service import StubWorkflow, tool


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name, "cities.sqlite")
        with closing(sqlite3.connect(path)) as database:
            database.execute("CREATE TABLE city_stats (city_name TEXT, population INTEGER, state TEXT)")
            database.executemany("INSERT INTO city_stats VALUES (?, ?, ?)", [
                ("Chicago", 2746388, "Illinois"), ("Boston", 675647, "Massachusetts"),
            ])
            database.commit()
        config = AppConfig(database_path=path, max_upload_bytes=20)
        self.service = SessionService(config)
        self.client = TestClient(create_app(config, self.service))
        for item in [
            patch("backend.service.create_llm", return_value=object()),
            patch("backend.service.setup_sql_tool", return_value=tool("sql_tool")),
            patch("backend.service.RouterOutputAgentWorkflow", side_effect=StubWorkflow),
            patch("backend.service.get_embedding_model", return_value=object()),
            patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}),
        ]:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.service.close)
        self.addCleanup(self.client.close)

    def connect(self):
        response = self.client.post("/api/sessions", json={"api_key": "test-private-key"})
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("test-private-key", response.text)
        return response.json()["id"]

    def test_health_and_database_work_before_connecting(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        response = self.client.get("/api/database?search=Chicago&page_size=1")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["rows"][0]["state"], "Illinois")
        self.assertEqual(body["states"], 2)

    def test_database_search_is_parameterized_and_pagination_is_validated(self):
        response = self.client.get("/api/database", params={"search": "' OR 1=1 --"})
        self.assertEqual(response.json()["total"], 0)
        self.assertEqual(self.client.get("/api/database?page=0").status_code, 422)
        self.assertEqual(self.client.get("/api/database?page_size=1000").status_code, 422)

    def test_chat_reset_restore_and_disconnect_contract(self):
        session_id = self.connect()
        response = self.client.post(f"/api/sessions/{session_id}/chat", json={"message": "Chicago?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], "final synthesized answer")
        self.assertEqual(response.json()["tools"][0]["name"], "sql_tool")
        self.assertEqual(len(self.client.get(f"/api/sessions/{session_id}").json()["messages"]), 2)
        self.assertEqual(self.client.post(f"/api/sessions/{session_id}/reset").json()["messages"], [])
        self.assertEqual(self.client.delete(f"/api/sessions/{session_id}").status_code, 204)
        self.assertEqual(self.client.get(f"/api/sessions/{session_id}").status_code, 404)

    def test_upload_contract_and_size_limit(self):
        session_id = self.connect()
        with patch("backend.service.setup_document_tool", new_callable=AsyncMock, return_value=tool("document_tool")):
            response = self.client.post(f"/api/sessions/{session_id}/documents", files=[
                ("files", ("policy.txt", b"Policy text", "text/plain")),
            ])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["documents"][0]["name"], "policy.txt")
        response = self.client.post(f"/api/sessions/{session_id}/documents", files=[
            ("files", ("large.txt", b"x" * 21, "text/plain")),
        ])
        self.assertEqual(response.status_code, 413)

    def test_missing_key_unknown_session_and_blank_question(self):
        self.assertEqual(self.client.post("/api/sessions", json={}).status_code, 400)
        self.assertEqual(self.client.post("/api/sessions/unknown/chat", json={"message": "Hi"}).status_code, 404)
        session_id = self.connect()
        self.assertEqual(self.client.post(f"/api/sessions/{session_id}/chat", json={"message": "  "}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
