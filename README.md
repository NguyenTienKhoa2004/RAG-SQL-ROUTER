# Forma - RAG + SQL Workspace

A minimal React workspace for asking questions across uploaded documents and a SQL database. Python handles retrieval, tools and conversation state; React handles presentation and user interactions.

## Architecture

```text
frontend/src/
  components/          Chat, sources, connection dialog, database browser
  hooks/useWorkspace   Session and request state
  lib/api              HTTP client
  App.jsx              Workspace layout
  styles.css           Responsive UI
backend/
  api.py               FastAPI routes and HTTP errors
  schemas.py           Public request/response contracts
  service.py           Session lifecycle, chat, upload and reset
  serialization.py     Tool results as structured API data
  database.py          Fixed read-only queries for the database browser
  config.py            Environment configuration
  rag/
    workflow.py        LLM tool-selection loop and conversation history
    tools.py           Document RAG and text-to-SQL tools
    document_loading.py Text extraction and OCR fallback
    retrieval_cache.py Cache of retrieved document nodes
app.py                 Alias for the FastAPI application
```

**Query flow:** React -> API -> session workflow -> SQL/document tools -> workflow final answer -> React. Tool results are returned separately and can be expanded in the chat. Each question starts a new tool lookup; prior conversation messages remain available to resolve follow-up references.

**Document flow:** upload -> validate and stage files -> text extraction / OCR -> Markdown nodes -> dense embeddings + Milvus BM25 index -> hybrid retrieval with RRF -> document tool. A successful upload replaces the index, keeps chat history, and deletes the old Milvus collection. Cleanup failures are logged without failing the successful upload; a failed upload keeps the previous documents and workflow.

## Run locally

Requirements: Python 3.12+, uv, Node.js 20+ and npm. Create the sales dataset with `python migrate/seed_sales.py`, or configure `DATABASE_PATH` to a database with the same schema. See [migration instructions, policy documents and benchmark answers](migrate/README.md).

### 1. Backend

From the project root:

```bash
uv sync
uv run python migrate/seed_sales.py
uv run uvicorn backend.api:app --reload --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/docs. `uv run uvicorn app:app --reload` is also supported. Streamlit is no longer required.

Optionally copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`. Otherwise enter your key in the React connection dialog. The browser stores only the opaque session ID in sessionStorage, never the API key. Credentials stay in backend memory for that session.

### 2. Frontend

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. Vite proxies `/api` to port 8000. On Windows, use `npm.cmd` if PowerShell blocks `npm.ps1`.

Connect the workspace, ask about sales, or add your documents through the sources panel. Enter sends a question; Shift + Enter adds a line. Starting a new conversation clears history and keeps uploaded documents. Disconnecting removes the session.

### 3. Milvus for document RAG

SQL chat and the database browser do not need Milvus or an embedding provider. The SQL tool queries six related sales tables and explicitly disables embeddings to avoid LlamaIndex's default OpenAI provider lookup. Document uploads require Milvus at `MILVUS_URI` (default `http://localhost:19530`).

With Docker Desktop running, start Milvus and Attu from the project root:

```powershell
docker compose up -d
```

Compose runs Milvus 3.0.2 with embedded etcd and local storage, and Attu 3.0.0. Attu starts after Milvus becomes healthy. Open http://localhost:3000 to inspect document text, metadata, indexes and collections; its preconfigured connection is `milvus:19530`, database `default`. Attu uses single-user mode (`ATTU_AUTH_MODE=none`), and all published ports bind to localhost for local development. Milvus's built-in monitoring UI is at http://localhost:9091/webui/.

Milvus data stays in `volumes/milvus/`, the same directory used by `standalone.bat`. Attu settings stay in a Docker volume. Stop the services with `docker compose down`; their persisted data is retained. Use `docker compose ps` for status and `docker compose logs -f` for logs. Backend and frontend still run with the commands above.

For a first-time switch from containers created by `standalone.bat` or `docker run`, stop the old containers and rename them before running Compose:

```powershell
docker stop milvus-standalone
docker rename milvus-standalone milvus-standalone-legacy
# Only if an old Attu container exists:
docker stop attu
docker rename attu attu-legacy
docker compose up -d
```

The renamed containers are stopped backups. Use Compose for subsequent starts so that a legacy Milvus container does not run against the same data directory at the same time. The existing `embedEtcd.yaml` and `user.yaml` are mounted as configuration files. First document upload may download the configured Hugging Face embedding model. Reupload documents after enabling hybrid search to create a collection containing both dense vectors and the BM25 index.

## Configuration

| Variable | Default |
| --- | --- |
| `LLM_MODEL` | `qwen/qwen3-30b-a3b-instruct-2507` |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` |
| `MILVUS_URI` | `http://localhost:19530` |
| `DATABASE_PATH` | `sales_database.sqlite` |
| `QUERY_TIMEOUT_SECONDS` | `60` |
| `MAX_UPLOAD_MB` | `20` (combined files per request) |

Supported uploads: PDF, DOCX, PPTX, TXT and Markdown. Reuploading a filename replaces its content. Each index caches up to 128 exact retrieval queries for 5 minutes; LLM answer synthesis still runs on every call.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Backend status and public configuration |
| POST | `/api/sessions` | Connect using an API key or server configuration |
| GET | `/api/sessions/{id}` | Restore chat and document metadata |
| POST | `/api/sessions/{id}/chat` | Final answer, tool results and duration |
| POST | `/api/sessions/{id}/documents` | Multipart upload, field name `files` |
| POST | `/api/sessions/{id}/reset` | Clear conversation history |
| DELETE | `/api/sessions/{id}` | Disconnect and clean up temporary files |
| GET | `/api/database` | Browse six sales tables; `table` (default `orders`), `search`, `page`, `page_size` |

## Verification

```bash
uv run python -m unittest discover -s tests -v
cd frontend
npm test
npm run build
```

Backend tests cover the workflow, history, retrieval cache, loading, session isolation, upload rollback and HTTP contracts. Frontend tests cover connection, follow-ups, tool details, failed-query retry, uploads and expired sessions. These tests mock external model/Milvus calls; a complete live RAG run needs those services.

## Current scope

This is a local development application. Sessions live in one backend process, expire after 12 hours of inactivity and are lost on restart; use one worker. There is no user authentication or durable session store yet. Milvus collections are recreated on upload and are not automatically removed when sessions end. The database browser uses fixed read-only queries; hardening LLM-generated SQL remains a separate roadmap step.

The notebooks are retained as tutorial references. The application uses the modules under `backend/rag/`.

## 📬 Stay Updated with Our Newsletter!

**Get a FREE Data Science eBook** 📖 with 150+ essential lessons in Data Science when you subscribe to our newsletter! Stay in the loop with the latest tutorials, insights, and exclusive resources. [Subscribe now!](https://join.dailydoseofds.com)

[![Daily Dose of Data Science Newsletter](https://github.com/patchy631/ai-engineering/blob/main/resources/join_ddods.png)](https://join.dailydoseofds.com)

## Contribution

Contributions are welcome! Feel free to fork this repository and submit pull requests with your improvements.
