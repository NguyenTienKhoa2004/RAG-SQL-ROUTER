"""Explicitly disable embeddings for the fixed-table, standard SQL parser."""

from llama_index.core.base.embeddings.base import BaseEmbedding


class SQLOnlyEmbedding(BaseEmbedding):
    """Avoid LlamaIndex's eager default provider lookup; never produce vectors.

    NLSQLRetriever requires an embedding object at initialization, even though
    its DEFAULT SQL parser does not use one. Fail clearly if that ever changes.
    Document RAG uses its own real Hugging Face model.
    """

    def _get_query_embedding(self, query: str) -> list[float]:
        raise RuntimeError("The SQL-only tool does not support vector embeddings.")

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._get_query_embedding(text)
