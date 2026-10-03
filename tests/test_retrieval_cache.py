import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

from backend.rag.retrieval_cache import RetrievalCache


class RetrievalCacheTests(unittest.TestCase):
    def test_repeat_skips_retrieval_and_different_query_misses(self):
        retrieve = Mock(side_effect=lambda query: [{"text": query}])
        cache = RetrievalCache(retrieve)
        self.assertEqual(cache.get("question"), cache.get("question"))
        cache.get("other question")
        self.assertEqual(retrieve.call_count, 2)

    def test_results_cannot_mutate_cached_nodes(self):
        retrieve = Mock(return_value=[{"text": "original"}])
        cache = RetrievalCache(retrieve)
        cache.get("q")[0]["text"] = "changed on miss"
        hit = cache.get("q")
        self.assertEqual(hit[0]["text"], "original")
        hit[0]["text"] = "changed on hit"
        self.assertEqual(cache.get("q")[0]["text"], "original")

    def test_expiry_triggers_new_search_without_sliding_ttl(self):
        retrieve = Mock(return_value=[])
        cache = RetrievalCache(retrieve, ttl_seconds=5)
        with patch("backend.rag.retrieval_cache.monotonic", return_value=0):
            cache.get("q")
        with patch("backend.rag.retrieval_cache.monotonic", return_value=4):
            cache.get("q")
        with patch("backend.rag.retrieval_cache.monotonic", return_value=5):
            cache.get("q")
        self.assertEqual(retrieve.call_count, 2)

    def test_least_recently_used_entry_is_evicted(self):
        retrieve = Mock(return_value=[])
        cache = RetrievalCache(retrieve, max_entries=2)
        for query in ("a", "b", "a", "c", "a", "b"):
            cache.get(query)
        self.assertEqual([call.args[0] for call in retrieve.call_args_list],
                         ["a", "b", "c", "b"])

    def test_failed_retrieval_is_retried(self):
        retrieve = Mock(side_effect=[RuntimeError("unavailable"), []])
        cache = RetrievalCache(retrieve)
        with self.assertRaises(RuntimeError):
            cache.get("q")
        self.assertEqual(cache.get("q"), [])
        self.assertEqual(retrieve.call_count, 2)

    def test_document_indexes_have_separate_caches(self):
        first = RetrievalCache(lambda query: ["first document"])
        second = RetrievalCache(lambda query: ["new document"])
        self.assertEqual(first.get("q"), ["first document"])
        self.assertEqual(second.get("q"), ["new document"])

    def test_concurrent_repeat_searches_only_once(self):
        retrieve = Mock(return_value=[{"text": "document"}])
        cache = RetrievalCache(retrieve)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(cache.get, ["q"] * 8))
        self.assertEqual(len(results), 8)
        retrieve.assert_called_once_with("q")

    def test_invalid_configuration_is_rejected(self):
        for config in ({"max_entries": 0}, {"ttl_seconds": 0}):
            with self.assertRaises(ValueError):
                RetrievalCache(Mock(), **config)

    def test_llamaindex_reuses_nodes_but_synthesizes_every_time(self):
        from llama_index.core import Document, QueryBundle, VectorStoreIndex
        from llama_index.core.embeddings import MockEmbedding
        from llama_index.core.llms import MockLLM

        index = VectorStoreIndex.from_documents(
            [Document(text="The store opens at 9 AM.")],
            embed_model=MockEmbedding(embed_dim=8),
        )
        engine = index.as_query_engine(llm=MockLLM(), similarity_top_k=3)
        with patch.object(engine, "retrieve", wraps=engine.retrieve) as retrieve:
            cache = RetrievalCache(lambda query: engine.retrieve(QueryBundle(query)))
            with patch.object(engine, "synthesize", wraps=engine.synthesize) as synthesize:
                answers = [
                    engine.synthesize(QueryBundle("Opening time?"),
                                      nodes=cache.get("Opening time?"))
                    for _ in range(2)
                ]
        self.assertEqual(retrieve.call_count, 1)
        self.assertEqual(synthesize.call_count, 2)
        for answer in answers:
            self.assertEqual(answer.source_nodes[0].node.text,
                             "The store opens at 9 AM.")


if __name__ == "__main__":
    unittest.main()
