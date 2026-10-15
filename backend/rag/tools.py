# Required imports
import os
import asyncio
import uuid
from sqlalchemy import create_engine
from llama_index.core import (
    VectorStoreIndex,
    SQLDatabase,
    PromptTemplate,
    StorageContext,
    Settings,
    QueryBundle,
)
from llama_index.core.query_engine import NLSQLTableQueryEngine
from llama_index.core.tools import QueryEngineTool, FunctionTool
from llama_index.core.node_parser import MarkdownNodeParser
from .document_loading import load_uploaded_documents
from llama_index.vector_stores.milvus import MilvusVectorStore
from llama_index.vector_stores.milvus.utils import BM25BuiltInFunction
from pymilvus import MilvusClient
from .retrieval_cache import RetrievalCache
from .sql_embedding import SQLOnlyEmbedding


#####################################
# Define Tools for Router Agent
#####################################
SALES_TABLE_CONTEXT = {
    "customers": "Synthetic customers. Names may be duplicated; identify customers by customer_id.",
    "products": "Catalog. list_price_vnd is not the historical sale price. Categories: apparel, electronics, home.",
    "orders": "ISO date strings. NULL delivered_at means missing data. membership_at_purchase and shipping_region "
              "are historical snapshots. shipping_fee_vnd is the actual charged fee, not the policy rule.",
    "order_items": "Historical sale prices in integer VND. discount_vnd is the TOTAL discount for the entire line, "
                   "not per unit. Merchandise value = quantity * unit_price_vnd - discount_vnd. "
                   "is_clearance identifies clearance items.",
    "payments": "Purchase payments, including shipping. Count only status=succeeded. An order may have failed "
                "attempts and multiple successful installments. Refunds are recorded only in returns.",
    "returns": "Return requests linked to order_items. Only status=refunded is an actual refund; "
               "refund_amount_vnd is the total refund for that request. requested_at differs from refunded_at. "
               "Reason, item_condition, quantity and dates are facts; eligibility rules require document_tool.",
}


def setup_sql_tool(db_path="sales_database.sqlite", *, llm=None):
    """Setup text-to-SQL across the six sales tables."""
    # Validate database exists
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file not found: {db_path}")

    try:
        engine = create_engine(f"sqlite:///{db_path}")
        sql_database = SQLDatabase(engine, include_tables=list(SALES_TABLE_CONTEXT))
    except Exception as e:
        print(f"Error setting up SQL database: {e}")
        raise

    # Create SQL query engine
    sql_query_engine = NLSQLTableQueryEngine(
        sql_database=sql_database,
        tables=list(SALES_TABLE_CONTEXT),
        context_query_kwargs=SALES_TABLE_CONTEXT,
        llm=llm,
        # Fixed-schema text-to-SQL needs no embeddings. Supply an explicit guard
        # because NLSQLRetriever otherwise loads Settings.embed_model eagerly.
        embed_model=SQLOnlyEmbedding(),
    )

    # Create tool for SQL querying
    sql_tool = QueryEngineTool.from_defaults(
        query_engine=sql_query_engine,
        name="sql_tool",
        description=(
            "Query the synthetic sales database: customers, products, orders, order_items, payments, returns. "
            "Use for order facts, sales totals, dates, customers, products, payments and refunds. All money is VND. "
            "Aggregate each child table before joining to avoid multiplying amounts. Net merchandise revenue "
            "for orders placed in a period counts delivered orders, subtracts actual refunds linked to those "
            "orders, and excludes shipping. Cash flow instead uses payment/refund transaction dates. "
            "Policies and eligibility rules must come from document_tool; combine both tools when needed."
        ),
    )

    # Return the SQL tool
    return sql_tool


def delete_document_collection(milvus_uri, collection_name):
    """Remove a replaced document index and close the cleanup connection."""
    client = MilvusClient(uri=milvus_uri, timeout=5)
    try:
        client.drop_collection(collection_name, timeout=5)
    finally:
        client.close()


async def setup_document_tool(
    file_dir, milvus_uri="http://localhost:19530", *, llm=None, embed_model=None, collection_name=None,
):
    """Setup document query tool from uploaded documents."""

    # Create a reader and load the data
    node_parser = MarkdownNodeParser()
    docs = await asyncio.to_thread(load_uploaded_documents, file_dir)

    # Creating a vector index over loaded data
    collection_name = collection_name or f"rag_with_sql_{uuid.uuid4().hex}"
    embed_model = embed_model or Settings.embed_model
    embedding_dim = len(await asyncio.to_thread(embed_model.get_text_embedding, "dimension probe"))
    # MilvusVectorStore also constructs AsyncMilvusClient. Initialize it on the
    # running event loop, rather than in an asyncio.to_thread worker.
    vector_store = MilvusVectorStore(
        uri=milvus_uri,
        dim=embedding_dim,
        overwrite=True,
        collection_name=collection_name,
        enable_sparse=True,
        sparse_embedding_function=BM25BuiltInFunction(),
        hybrid_ranker="RRFRanker",
    )
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    vector_index = await asyncio.to_thread(
        VectorStoreIndex.from_documents,
        docs,
        show_progress=True,
        transformations=[node_parser],
        storage_context=storage_context,
        embed_model=embed_model,
    )
    print("[Documents] Index ready; document_tool is available", flush=True)

    # Custom prompt template
    template = (
        "You are a meticulous and accurate document analyst. Your task is to answer the user's question based exclusively on the provided context. "
        "Follow these rules strictly:\n"
        "1. Your entire response must be grounded in the facts provided in the 'Context' section. Do not use any prior knowledge.\n"
        "2. If multiple parts of the context are relevant, synthesize them into a single, coherent answer.\n"
        "3. If the context does not contain the information needed to answer the question, you must state only: 'The provided context does not contain enough information to answer this question.'\n"
        "-----------------------------------------\n"
        "Context: {context_str}\n"
        "-----------------------------------------\n"
        "Question: {query_str}\n\n"
        "Answer:"
    )
    qa_template = PromptTemplate(template)

    # Create a query engine for the vector index
    docs_query_engine = vector_index.as_query_engine(
        text_qa_template=qa_template,
        similarity_top_k=3,
        vector_store_query_mode="hybrid",
        llm=llm,
    )
    # Keep the engine and retrieved nodes local to this tool's document index.
    retrieval_cache = RetrievalCache(
        lambda query: docs_query_engine.retrieve(QueryBundle(query)),
        max_entries=128,
        ttl_seconds=300,
    )

    async def document_query_tool(query: str):
        """Retrieve document context and generate a fresh answer with the LLM."""
        def query_documents():
            nodes = retrieval_cache.get(query)
            response_obj = docs_query_engine.synthesize(QueryBundle(query), nodes=nodes)
            return {"response": str(response_obj)}

        return await asyncio.to_thread(query_documents)

    # Create tool for document querying using FunctionTool
    docs_tool = FunctionTool.from_defaults(
        document_query_tool,
        name="document_tool",
        description=(
            "Useful for answering a natural language question by performing hybrid semantic and keyword search over "
            "uploaded documents, including store policies, order values for free shipping, "
            "delivery fees, opening hours, returns and payments. Documents may contain general knowledge, reports, "
            "or domain-specific content. Returns the most relevant passages or synthesized answers. "
            "Use this tool for policy rules and effective dates, not for actual sales transactions or totals. "
            "For order eligibility or shipping audits, combine document policies with facts from sql_tool."
        ),
    )

    # Return the document tool
    return docs_tool
