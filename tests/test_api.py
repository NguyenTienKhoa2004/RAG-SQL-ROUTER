"""HTTP contracts and fixed database browsing; no paid LLM calls needed."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.config import AppConfig
from backend.service import SessionService
from migrate.seed_sales import migrate
from test_service import StubWorkflow, tool


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name, "sales.sqlite")
        migrate(path)
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
        response = self.client.get("/api/database?search=DH1004&page_size=1")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["rows"][0]["order_id"], "DH1004")
        self.assertEqual(body["rows"][0]["merchandise_total_vnd"], 690000)
        self.assertEqual(body["total_customers"], 120)
        self.assertEqual(body["total_products"], 12)
        self.assertEqual(body["table"], "orders")

    def test_database_pagination_and_customer_search(self):
        first = self.client.get("/api/database?page_size=10").json()
        second = self.client.get("/api/database?page_size=10&page=2").json()
        self.assertEqual(first["total"], 608)
        self.assertEqual(len(first["rows"]), 10)
        self.assertFalse({r["order_id"] for r in first["rows"]} & {r["order_id"] for r in second["rows"]})
        rows = self.client.get("/api/database?search=KH001").json()["rows"]
        self.assertTrue(rows)
        self.assertTrue(all(row["customer_id"] == "KH001" for row in rows))

    def test_database_search_is_parameterized_and_pagination_is_validated(self):
        response = self.client.get("/api/database", params={"search": "' OR 1=1 --"})
        self.assertEqual(response.json()["total"], 0)
        self.assertEqual(self.client.get("/api/database?page=0").status_code, 422)
        self.assertEqual(self.client.get("/api/database?page_size=1000").status_code, 422)

    def test_all_sales_tables_support_browsing_search_and_pagination(self):
        for table, count, primary_key, search in [
            ("orders", 608, "order_id", "DH1004"),
            ("customers", 120, "customer_id", "KH001"),
            ("products", 12, "product_id", "SP01"),
            ("order_items", 1496, "order_item_id", "DH1004"),
            ("payments", 653, "payment_id", "DH1004"),
            ("returns", 6, "return_id", "refunded"),
        ]:
            with self.subTest(table=table):
                first = self.client.get("/api/database", params={"table": table, "page_size": 2})
                self.assertEqual(first.status_code, 200, first.text)
                body = first.json()
                self.assertEqual(body["table"], table)
                self.assertEqual(body["total"], count)
                self.assertEqual(body["columns"][0], primary_key)
                self.assertEqual(set(body["columns"]), set(body["rows"][0]))
                second = self.client.get("/api/database", params={"table": table, "page_size": 2, "page": 2}).json()
                self.assertFalse({r[primary_key] for r in body["rows"]} & {r[primary_key] for r in second["rows"]})
                matches = self.client.get("/api/database", params={"table": table, "search": search}).json()
                self.assertGreater(matches["total"], 0)
                self.assertTrue(all(any(search in str(value) for value in row.values()) for row in matches["rows"]))
                injected = self.client.get("/api/database", params={"table": table, "search": "' OR 1=1 --"})
                self.assertEqual(injected.json()["total"], 0)

    def test_database_table_allowlist_and_null_values(self):
        for table in ("sqlite_master", "orders; DROP TABLE orders;--", "unknown"):
            self.assertEqual(self.client.get("/api/database", params={"table": table}).status_code, 422)
        body = self.client.get("/api/database?table=orders&search=DH1005").json()
        self.assertIsNone(body["rows"][0]["delivered_at"])

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
