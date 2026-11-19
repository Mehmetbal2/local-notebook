# Local Notebook · backend

FastAPI service with REST and streaming (SSE) APIs. File parsing, re-indexing and report generation run in an in-process task queue, so a local installation needs no Redis or separate worker.

## Directory

| Path | Responsibility |
|---|---|
| [routes/](./routes) | API routes: `auth`, `admin`, `project`, `file`, `session`, `chat`, `search`, `feature`, `workflow`, `web_source`, `settings` |
| [agent/](./agent) | Chat core: `chat_agent`, `citation_parser` for passage-level citations, prompts and the tools the agent can call |
| [services/](./services) | Domain services: embedding and the local bge-m3 lifecycle, `vector_service` (Milvus Lite or server), parsing helpers, summaries, web discovery, export, backup and restore, usage accounting |
| [workers/](./workers) | Background tasks: parsing, segmenting, summarizing and embedding uploads; re-embedding; project summary refresh; deep research |
| [models/](./models) | SQLAlchemy models: `user`, `project`, `file`, `segment`, `block`, `image`, `session`, `message`, `feature`, `workflow`, `usage`, `settings` |
| [schemas/](./schemas) | Pydantic request and response models |
| [packages/kosong/](./packages/kosong) | Bundled agent framework: LLM providers, tool calling and streaming |
| [tests/](./tests) | Unit and regression tests (`python -m unittest discover -s tests`) |
| `main.py` | Entry point: applies a staged restore, prepares the database, starts the queue and the routes |
| `config.py` | Settings: the database first, then environment variables, then defaults |

## Configuration

Runtime settings (LLM, embedding, OCR, ASR, TTS, web search) are stored in the SQLite `settings` table and edited on the **Settings** page; changes apply without a restart. Environment variables only provide defaults. `start.sh` sets the paths below; the full list of reliability and security variables is in [docs/OPERATIONS.md](../docs/OPERATIONS.md).

| Variable | Set by `start.sh` | Purpose |
|---|---|---|
| `LOCAL_NOTEBOOK_DATA_DIR` | `./local-notebook-data` | Data folder |
| `DATABASE_URL` | SQLite file in the data folder | SQLAlchemy URL |
| `MILVUS_URI` | `milvus.db` in the data folder | Milvus Lite path, or `http://host:19530` for a Milvus server |
| `UPLOAD_DIR` | `uploads/` in the data folder | Uploaded files |
| `REDIS_URL` | `memory://` | In-process queue; a `redis://` URL switches to an ARQ worker |
| `SECRET_KEY` | — | JWT secret; a missing or placeholder value is replaced by a persistent random key |
| `ADMIN_PASSWORD` | — | Initial admin password; when missing, a random one is written to `admin_password.txt` |

## Running the backend on its own

```bash
# from the project root
export PYTHONPATH="$PWD/backend:$PWD/backend/packages"
export LOCAL_NOTEBOOK_DATA_DIR="$PWD/local-notebook-data" REDIS_URL=memory://
cd backend && ../.venv/bin/python -m uvicorn main:app --port 8081
curl http://localhost:8081/health
```

## Data flow

1. **Upload:** `routes/file_routes.py` stores the file and queues `parse_file_task`.
2. **Parsing:** `workers/parsers/` extracts text (PyMuPDF, optional OCR, FunASR for audio); segments and their summaries are committed to SQLite before embedding, so an embedding failure never repeats the LLM work.
3. **Indexing:** `embedding_service` embeds segments with retries; `vector_service` writes them to the shared Milvus collections.
4. **Chat:** `routes/chat_routes.py` streams SSE; `agent/chat_agent.py` searches the knowledge base and `agent/citation_parser.py` turns `[citation_X]` markers into passage links.
