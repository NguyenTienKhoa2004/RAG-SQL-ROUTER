"""Document tool threading, hybrid retrieval, and cached context."""

import asyncio
import threading
import unittest
from unittest.mock import Mock, patch

from llama_index.core import Document
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.llms import MockLLM
from llama_index.vector_stores.milvus import MilvusVectorStore

from backend.rag.tools import delete_document_collection, setup_document_tool


class DocumentToolTests(unittest.IsolatedAsyncioTestCase):
    def test_collection_cleanup_closes_client_even_when_deletion_fails(self):
        for error in (None, RuntimeError("Milvus unavailable")):
            with self.subTest(error=error), patch("backend.rag.tools.MilvusClient") as create_client:
                client = create_client.return_value
                client.drop_collection.side_effect = error
                if error:
                    with self.assertRaises(RuntimeError):
                        delete_document_collection("http://localhost:19530", "old_collection")
                else:
                    delete_document_collection("http://localhost:19530", "old_collection")
                client.drop_collection.assert_called_once_with("old_collection", timeout=5)
                client.close.assert_called_once()

    async def test_milvus_connects_on_active_loop_and_indexing_stays_in_worker(self):
        loop = asyncio.get_running_loop()
        main_thread = threading.get_ident()
        query_engine = Mock()
        query_engine.retrieve.return_value = ["document context"]
        query_engine.synthesize.return_value = "Document answer"
        index = Mock()
        index.as_query_engine.return_value = query_engine

        def create_vector_store(**kwargs):
            self.assertEqual(kwargs["collection_name"], "requested_collection")
            self.assertIs(asyncio.get_running_loop(), loop)
            self.assertEqual(threading.get_ident(), main_thread)
            return Mock()

        def create_index(*args, **kwargs):
            self.assertNotEqual(threading.get_ident(), main_thread)
            return index

        with patch("backend.rag.tools.load_uploaded_documents", return_value=[Document(text="Policy")]), patch(
            "backend.rag.tools.MilvusVectorStore", side_effect=create_vector_store,
        ), patch("backend.rag.tools.StorageContext.from_defaults", return_value=Mock()), patch(
            "backend.rag.tools.VectorStoreIndex.from_documents", side_effect=create_index,
        ):
            tool = await setup_document_tool(
                "unused", llm=MockLLM(), embed_model=MockEmbedding(embed_dim=8),
                collection_name="requested_collection",
            )
            first = await tool.acall(query="Policy?")
            second = await tool.acall(query="Policy?")
        self.assertEqual(first.raw_output, {"response": "Document answer"})
        self.assertEqual(second.raw_output, first.raw_output)
        query_engine.retrieve.assert_called_once()
        self.assertEqual(query_engine.synthesize.call_count, 2)

    async def test_hybrid_search_sends_dense_and_bm25_requests_and_caches_context(self):
        # Exercise real indexing, retrieval, Milvus serialization, and synthesis;
        # replace only the external Milvus client and document loading.
        client = Mock()

        def create_vector_store(**kwargs):
            store = MilvusVectorStore.model_construct(search_config={}, **kwargs)
            store._milvusclient = client
            return store

        def hybrid_search(collection_name, requests, **kwargs):
            entry = client.insert.call_args.args[1][0]
            return [[{"id": entry["id"], "distance": 0.03, "entity": entry}]]

        client.hybrid_search.side_effect = hybrid_search
        text = "## Returns\nSKU-123 can be returned within 30 days."
        with patch("backend.rag.tools.load_uploaded_documents", return_value=[Document(text=text)]), patch(
            "backend.rag.tools.MilvusVectorStore", side_effect=create_vector_store,
        ):
            tool = await setup_document_tool("unused", llm=MockLLM(), embed_model=MockEmbedding(embed_dim=8))
            for _ in range(2):
                result = await tool.acall(query="What is the return period for SKU-123?")
                self.assertIn("SKU-123 can be returned within 30 days.", result.raw_output["response"])

        client.hybrid_search.assert_called_once()
        client.search.assert_not_called()
        dense, sparse = client.hybrid_search.call_args.args[1]
        self.assertEqual(len(dense.data[0]), 8)
        self.assertEqual(sparse.data, ["What is the return period for SKU-123?"])
        self.assertEqual(sparse.param["metric_type"], "BM25")
        self.assertEqual(type(client.hybrid_search.call_args.kwargs["ranker"]).__name__, "RRFRanker")


if __name__ == "__main__":
    unittest.main()
