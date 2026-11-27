# Operations Guide

Everything an operator needs for a local installation: backups, security defaults,
diagnostics, and the two Milvus modes.

## Backup and restore

Open **Settings → System status → Backup and restore** (admins only).

- **Download backup** builds the zip on the server, then hands the browser a one-time
  link (valid 15 minutes, usable once). The browser downloads it like any file, so even a
  multi-gigabyte archive goes straight to disk instead of being held in page memory.
  The zip contains:
  - `local_notebook.db` — a consistent copy made with SQLite's online backup API, so it
    is safe to run while the application is writing;
  - `milvus.db/` — the local vector index (a Milvus Lite directory, roughly as large as
    the index itself). Its data files are copied first and the collection manifests
    last, so the copy never references a half-written segment. Untick **Include the
    vector index** for a small database-only backup;
  - `uploads/` — optional; tick "Include uploaded source files" (archives can be large);
  - `manifest.json` — format version, timestamp, whether vectors were included, sizes.
- **Restore from file** uploads a zip. It is validated (integrity check, expected tables,
  safe paths, size limits) and **staged**, not applied immediately.
- On the **next application start**, the staged backup replaces the current database,
  vector store and (if included) the uploads folder. The previous data is moved to
  `local-notebook-data/backups/pre-restore-<timestamp>/` first, so a bad restore can be
  undone by copying those files back. The newest three of these copies are kept
  (`BACKUP_KEEP_PRE_RESTORE`); older ones are removed at startup, since each is a full
  copy of the data.
- A backup without vectors keeps the index that is already on disk, since deleting it
  would break search until every source is re-indexed. The Admin page warns when the
  uploaded archive has no index; re-index sources if results look wrong afterwards.
- In remote Milvus mode vectors live in the Milvus server and are **not** part of the
  archive; only the SQLite database is backed up.

Backups are deleted once downloaded. An archive whose link was never used is removed after
the link expires, and an uploaded restore that a newer upload replaced is removed too, so
nothing accumulates on disk.
For the most consistent copy, run a backup while no files are being uploaded or
re-indexed; the vector copy is retried with a clear error if a segment changes mid-copy.

## Security defaults

- **Admin password.** The old `admin/admin` default is no longer used. When
  `ADMIN_PASSWORD` is missing or equal to `admin`, a random password is generated and
  written to `local-notebook-data/admin_password.txt` (owner-only, `0600`). Read it,
  sign in, then delete the file. Set a strong `ADMIN_PASSWORD` to choose it yourself.
  An existing account still using `admin` is rotated on the next start.
- **JWT secret.** A missing or placeholder `SECRET_KEY` is replaced by a persistent key
  at `local-notebook-data/secret_key` (`0600`). Changing the key signs everyone out once.
- **CORS.** Only `localhost`, `127.0.0.1`, `[::1]` and private LAN addresses are accepted,
  on the frontend port (`FRONTEND_PORT`) and the Vite dev-server port 5173. Allow more
  ports with `CORS_ALLOW_PORTS` (comma-separated) or whole origins with
  `CORS_ALLOW_ORIGINS`.
- **Downloads.** Uploaded HTML files are served as `text/plain` attachments, never as
  renderable pages from the API origin.

## Network exposure

`start.sh` binds the backend and frontend to `0.0.0.0`, so other devices on the same
network can use the app. Keep the admin password strong. To restrict access to this
machine only, bind `127.0.0.1` in `start.sh` and set `CORS_ALLOW_ORIGINS` accordingly.

## Diagnostics

**Settings → System status** shows model usage, backup/restore and a read-only snapshot:

- application version, Python version, uptime;
- database size and row counts (projects, files, segments, messages, users);
- vector store mode and per-collection row count / dimension;
- data, uploads and free disk space;
- SearXNG reachability; the embedding source, and for the local service a live `/health`
  check (model and dimension, or "not responding"); LLM configuration;
- the most recent `WARNING`/`ERROR` lines from `local-notebook-data/logs/backend.log`.
  Milvus Lite's harmless `AllocTimestamp … Method not implemented` error is filtered out.

## User statistics

**User management** lists, under the user table, each account's projects, sources and
storage, chat messages, generated outputs, LLM calls and token share for the last 7, 30
or 90 days, and when the account was last active. Projects created before accounts
existed are grouped as "content without an owner".

## Local embedding port

The backend reaches the local embedding service at the address saved in Settings
(`embedding_local_url`). `start.sh` starts the service on that address's port, so the two
never disagree; `EMBEDDING_PORT` (default `8001`) is used only when nothing is saved.

## Milvus modes

| Mode | How | Characteristics |
|---|---|---|
| **Lite (default)** | `MILVUS_URI=./local-notebook-data/milvus.db` | Zero dependencies, single process, `IVF_FLAT` index, no scalar indexes |
| **Server** | `MILVUS_URI=http://milvus:19530` inside the Docker stack (see `docker-compose.yml`; the port is not published on the host by default) | Multi-process, `IVF_PQ` + inverted filter indexes, scales to millions of vectors |

Switch to the server when you need multiple worker processes, hundreds of thousands of
segments or more, or when filtered queries get slow. A backup taken in Lite mode contains
the vectors; in server mode it does not.

## Environment variables added for reliability

| Variable | Default | Purpose |
|---|---|---|
| `LLM_MAX_CONCURRENCY` | `2` | Process-wide cap on background summary LLM calls |
| `WEB_DISCOVERY_QUERY_TIMEOUT` | `60` | Budget for the model's extra search queries (phase 2, runs after results are shown) |
| `EMBED_MAX_ATTEMPTS` | `3` | Attempts per embedding batch on 408/425/429/5xx and connection errors |
| `SEARXNG_SEARCH_TIMEOUT` | `12` | Per-query SearXNG timeout |
| `MILVUS_STARTUP_RETRIES` | `8` | Backoff retries while the previous process releases the data dir |
| `CORS_ALLOW_ORIGINS` | empty | Extra allowed origins, comma-separated |
| `CORS_ALLOW_PORTS` | empty | Extra allowed ports on localhost/LAN, comma-separated |
| `BACKUP_KEEP_PRE_RESTORE` | `3` | Pre-restore safety copies kept |
| `BACKUP_DOWNLOAD_TTL_SECONDS` | `900` | Lifetime of a prepared backup's one-time link |
| `USAGE_TIMEZONE` | system time zone | Time zone used to date model usage (was fixed to Asia/Shanghai) |
| `MAX_UPLOAD_MB` | `500` | Largest multipart upload; multipart requests also need a valid session before their body is read. Backup restores need an admin and are exempt from the size limit |
| `MAX_REQUEST_MB` | `20` | Largest non-upload request body (JSON, forms) |
| `MEDIA_TOKEN_EXPIRE_MINUTES` | `720` | Lifetime of the preview-only token put in image/audio URLs |
| `LOGIN_MAX_FAILURES` / `LOGIN_MAX_FAILURES_PER_ADDRESS` / `LOGIN_MAX_FAILURES_PER_USER` / `LOGIN_WINDOW_SECONDS` | `10` / `50` / `30` / `900` | Failed sign-ins allowed per user name and address, per address, per user name from any address, and the window; then 429 |
| `BACKEND_HOST` | `127.0.0.1` | Address `start.sh` binds the API to. Other devices use the API through the interface port; set `0.0.0.0` only to expose the API directly |
| `ARCHIVE_MAX_UNCOMPRESSED_MB` | `512` | Largest unpacked size of an EPUB/DOCX (zip bomb guard) |
| `PDF_MAX_PAGES` | `5000` | PDFs with more pages are refused |
| `PDF_MAX_PAGE_CONTENT_MB` | `32` | Largest expanded content of one PDF page (content streams plus every form drawing); larger pages are skipped |
| `PDF_MAX_CONTENT_MB` | `1024` | Largest expanded content of a whole PDF, a shared stream counted once per page |
| `PDF_MAX_TEXT_MB` | `64` | Most text (million characters) one PDF may yield |
| `PROJECT_SEARCH_CACHE_MB` | `128` | Memory for the in-project search cache (least recently used sources are dropped first) |
| `PARSER_MAX_MEMORY_MB` | `2048` | Document parsing (PDF, EPUB, DOCX, HTML, TXT/Markdown) runs in a child process that is stopped above this resident memory |
| `PARSER_TIMEOUT_SECONDS` | `1800` | The parsing child process is stopped after this long |
| `PARSER_ISOLATION` | on | Set to `0` to parse in the backend process (debugging only; removes the memory/time guard) |
| `WEB_FETCH_ALLOW_PRIVATE` | off | Set to `1` to let web-source import and web search read pages on loopback/private/link-local addresses (intranet). Off by default so users cannot reach server-internal services |
| `SQLITE_JOURNAL_MODE` | `WAL` | SQLite journal mode |
| `RESTORE_MAX_ARCHIVE_BYTES` | `4294967296` (4 GiB) | Upload size limit for a restore archive |
| `RESTORE_MAX_UNCOMPRESSED_BYTES` | `8589934592` (8 GiB) | Zip-bomb guard for a restore |

## Troubleshooting

- **`Open local milvus failed`** — another backend process still holds the Milvus Lite
  file lock. The client retries with backoff; make sure only one backend runs.
- **Word export has endnotes instead of footnotes** — pandoc is missing or unusable on
  this machine. Install a native build (`brew install pandoc` on macOS). The export
  logs a warning and falls back to the built-in writer.
- **429 from the LLM provider** — lower `LLM_MAX_CONCURRENCY` (the provider may allow
  fewer concurrent requests than your file concurrency implies).
- **Restore did not apply** — the zip was rejected at staging time (see the error in
  Settings → System status), or the application has not been restarted. Check the startup log for
  "Restore applied".
