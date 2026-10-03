"""Document indexing must keep async Milvus initialization on the active loop."""

import asyncio
import threading
import unittest
from unittest.mock import Mock, patch

from llama_index.core import Document
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.llms import MockLLM

from backend.rag.tools import setup_document_tool


class DocumentToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_milvus_connects_on_active_loop_and_indexing_stays_in_worker(self):
        loop = asyncio.get_running_loop()
        main_thread = threading.get_ident()
        query_engine = Mock()
        query_engine.retrieve.return_value = ["document context"]
        query_engine.synthesize.return_value = "Document answer"
        index = Mock()
        index.as_query_engine.return_value = query_engine

        def create_vector_store(**kwargs):
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
            tool = await setup_document_tool("unused", llm=MockLLM(), embed_model=MockEmbedding(embed_dim=8))
            first = await tool.acall(query="Policy?")
            second = await tool.acall(query="Policy?")
        self.assertEqual(first.raw_output, {"response": "Document answer"})
        self.assertEqual(second.raw_output, first.raw_output)
        query_engine.retrieve.assert_called_once()
        self.assertEqual(query_engine.synthesize.call_count, 2)


if __name__ == "__main__":
    unittest.main()
