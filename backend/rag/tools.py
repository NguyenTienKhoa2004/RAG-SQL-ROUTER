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
from .retrieval_cache import RetrievalCache
from .sql_embedding import SQLOnlyEmbedding


#####################################
# Define Tools for Router Agent
#####################################
def setup_sql_tool(db_path="city_database.sqlite", table_name="city_stats", *, llm=None):
    """Setup SQL query tool for querying city database."""
    # Validate database exists
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file not found: {db_path}")

    try:
        engine = create_engine(f"sqlite:///{db_path}")
        sql_database = SQLDatabase(engine)
    except Exception as e:
        print(f"Error setting up SQL database: {e}")
        raise

    # Create SQL query engine
    sql_query_engine = NLSQLTableQueryEngine(
        sql_database=sql_database,
        tables=[table_name],
        llm=llm,
        # Fixed-table text-to-SQL needs no embeddings. Supply an explicit guard
        # because NLSQLRetriever otherwise loads Settings.embed_model eagerly.
        embed_model=SQLOnlyEmbedding(),
    )

    # Create tool for SQL querying
    sql_tool = QueryEngineTool.from_defaults(
        query_engine=sql_query_engine,
        name="sql_tool",
        description=(
            "Useful for translating a natural language query into a SQL query over"
            " a table containing: city_stats, containing the population/state of"
            " each city located in the USA."
        ),
    )

    # Return the SQL tool
    return sql_tool


async def setup_document_tool(file_dir, milvus_uri="http://localhost:19530", *, llm=None, embed_model=None):
    """Setup document query tool from uploaded documents."""

    # Create a reader and load the data
    node_parser = MarkdownNodeParser()
    docs = await asyncio.to_thread(load_uploaded_documents, file_dir)

    # Creating a vector index over loaded data
    unique_collection_id = uuid.uuid4().hex
    collection_name = f"rag_with_sql_{unique_collection_id}"
    embed_model = embed_model or Settings.embed_model
    embedding_dim = len(await asyncio.to_thread(embed_model.get_text_embedding, "dimension probe"))
    # MilvusVectorStore also constructs AsyncMilvusClient. Initialize it on the
    # running event loop, rather than in an asyncio.to_thread worker.
    vector_store = MilvusVectorStore(
        uri=milvus_uri,
        dim=embedding_dim,
        overwrite=True,
        collection_name=collection_name,
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
        text_qa_template=qa_template, similarity_top_k=3, llm=llm
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
            "Useful for answering a natural language question by performing a semantic search over "
            "uploaded documents, including store policies, order values for free shipping, "
            "delivery fees, opening hours, returns and payments. Documents may contain general knowledge, reports, "
            "or domain-specific content. Returns the most relevant passages or synthesized answers. "
            "If the user query does not relate to US city statistics (population and state), use this document search tool."
        ),
    )

    # Return the document tool
    return docs_tool
