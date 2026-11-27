#!/usr/bin/env bash
set -euo pipefail

# Universal project root resolution (no hardcoded paths)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Load .env if present
if [[ -f "$PROJECT_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/.env"
  set +a
fi

# Prepend project-local Python (.venv) and Node (.node) runtimes to PATH
export PATH="$PROJECT_ROOT/.venv/bin:$PROJECT_ROOT/.node/bin:$PATH"

# Resolve data, upload, model, and cache directories relative to PROJECT_ROOT
resolve_path() {
  local p="$1"
  if [[ "$p" = /* ]]; then
    printf "%s\n" "$p"
  else
    printf "%s/%s\n" "$PROJECT_ROOT" "${p#./}"
  fi
}

DATA_DIR="$(resolve_path "${LOCAL_NOTEBOOK_DATA_DIR:-./local-notebook-data}")"
UPLOAD_DIR="$(resolve_path "${UPLOAD_DIR:-$DATA_DIR/uploads}")"
LOG_DIR="$DATA_DIR/logs"
RUN_DIR="$DATA_DIR/run"
MODELS_DIR="$DATA_DIR/models"

mkdir -p "$DATA_DIR" "$UPLOAD_DIR" "$LOG_DIR" "$RUN_DIR" \
         "$MODELS_DIR/huggingface" "$MODELS_DIR/modelscope" "$MODELS_DIR/torch" \
         "$PROJECT_ROOT/.cache/uv" "$PROJECT_ROOT/.cache/pip" "$PROJECT_ROOT/.cache/npm"
# The data folder holds the database (with API keys), uploads and backups: only this
# user may open it. A folder without access for others hides everything inside it.
chmod 700 "$DATA_DIR" "$UPLOAD_DIR" 2>/dev/null || true

export LOCAL_NOTEBOOK_DATA_DIR="$DATA_DIR"
export UPLOAD_DIR="$UPLOAD_DIR"
export DATABASE_URL="sqlite+aiosqlite:///$DATA_DIR/local_notebook.db"
export MILVUS_URI="$(resolve_path "${MILVUS_URI:-$DATA_DIR/milvus.db}")"
export REDIS_URL="${REDIS_URL:-memory://}"
export HF_HOME="${HF_HOME:-$MODELS_DIR/huggingface}"
export MODELSCOPE_CACHE="${MODELSCOPE_CACHE:-$MODELS_DIR/modelscope}"
export TORCH_HOME="${TORCH_HOME:-$MODELS_DIR/torch}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PROJECT_ROOT/.cache/uv}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$PROJECT_ROOT/.cache/pip}"
export NPM_CONFIG_CACHE="${NPM_CONFIG_CACHE:-$PROJECT_ROOT/.cache/npm}"
export PYTHONPATH="$PROJECT_ROOT/backend:$PROJECT_ROOT/backend/packages:${PYTHONPATH:-}"

BACKEND_PORT="${BACKEND_PORT:-8081}"
FRONTEND_PORT="${FRONTEND_PORT:-8080}"
EMBEDDING_PORT="${EMBEDDING_PORT:-8001}"
START_EMBEDDING="${START_EMBEDDING:-auto}"
SEARXNG_PORT="${SEARXNG_PORT:-8888}"
START_SEARXNG="${LOCAL_NOTEBOOK_SEARXNG:-1}"
SEARXNG_COMPOSE="$PROJECT_ROOT/services/searxng/docker-compose.yml"
export SEARXNG_PORT

# Docker CLI locations used by OrbStack / Docker Desktop on macOS
export PATH="$PATH:/usr/local/bin:/opt/homebrew/bin:$HOME/.orbstack/bin"

PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
NODE_BIN="$PROJECT_ROOT/.node/bin/node"

BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
EMBEDDING_PID_FILE="$RUN_DIR/embedding.pid"
EMBEDDING_PORT_FILE="$RUN_DIR/embedding.port"

# Read one value from the settings table; prints nothing when the database or key is missing.
read_setting() {
  local key="$1" db_file="$DATA_DIR/local_notebook.db"
  [[ -f "$db_file" ]] || return 0
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$db_file" "SELECT value FROM settings WHERE key='$key' LIMIT 1;" 2>/dev/null || true
  elif [[ -x "$PYTHON_BIN" ]]; then
    "$PYTHON_BIN" - "$db_file" "$key" 2>/dev/null <<'PY' || true
import sqlite3, sys
row = sqlite3.connect(sys.argv[1]).execute(
    "SELECT value FROM settings WHERE key=? LIMIT 1", (sys.argv[2],)
).fetchone()
print(row[0] if row else "")
PY
  fi
}

# The backend talks to the local embedding service at the address saved in Settings
# (embedding_local_url) and would start it on that port itself. Use the same port here,
# so the two never disagree; EMBEDDING_PORT is only the fallback when nothing is saved.
resolve_embedding_port() {
  local url port
  url="$(read_setting embedding_local_url)"
  [[ -n "$url" ]] || return 0
  port="$(printf '%s' "$url" | sed -nE 's#^https?://(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)(:([0-9]+))?(/.*)?$#\3#p')"
  if [[ -n "$port" && "$port" != "$EMBEDDING_PORT" ]]; then
    echo "Using embedding port $port from Settings (EMBEDDING_PORT was $EMBEDDING_PORT)."
    EMBEDDING_PORT="$port"
  fi
}
resolve_embedding_port

is_running() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

rotate_log() {
  local log_file="$1"
  if [[ -f "$log_file" ]]; then
    local size
    size="$(wc -c < "$log_file" 2>/dev/null || echo 0)"
    if (( size > 10485760 )); then
      mv -f "$log_file" "${log_file}.1" 2>/dev/null || true
    fi
  fi
}

stop_service() {
  local name="$1"
  local pid_file="$2"
  if is_running "$pid_file"; then
    local pid
    pid="$(cat "$pid_file")"
    echo "Stopping $name (PID $pid)..."
    kill "$pid" 2>/dev/null || true
    for _ in {1..20}; do
      if ! kill -0 "$pid" 2>/dev/null; then
        break
      fi
      sleep 0.25
    done
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
}

# ── SearXNG (web search, runs in Docker) ────────────────────────────────────
embedding_enabled() {
  if [[ "$START_EMBEDDING" == "0" ]]; then
    return 1
  fi
  if [[ -z "${MODEL:-}" && ! -f "$MODELS_DIR/bge-m3/config.json" ]]; then
    return 1
  fi
  if [[ "$START_EMBEDDING" == "1" ]]; then
    return 0
  fi
  local db_file="$DATA_DIR/local_notebook.db"
  if [[ ! -f "$db_file" ]]; then
    return 0
  fi
  local src=""
  if command -v sqlite3 >/dev/null 2>&1; then
    src="$(sqlite3 "$db_file" "SELECT value FROM settings WHERE key='embedding_source' LIMIT 1;" 2>/dev/null || true)"
  else
    src="$("$PYTHON_BIN" -c "import sqlite3; c=sqlite3.connect('$db_file'); r=c.execute(\"SELECT value FROM settings WHERE key='embedding_source' LIMIT 1\").fetchone(); print(r[0] if r else '')" 2>/dev/null || true)"
  fi
  [[ -z "$src" || "$src" == "local" ]]
}

searxng_enabled() {
  [[ "$START_SEARXNG" == "1" ]] && [[ -f "$SEARXNG_COMPOSE" ]] && command -v docker >/dev/null 2>&1
}

docker_ready() {
  docker info >/dev/null 2>&1
}

start_searxng() {
  if ! searxng_enabled; then
    if [[ "$START_SEARXNG" == "1" ]] && ! command -v docker >/dev/null 2>&1; then
      echo "SearXNG skipped: Docker is not installed (web search will be unavailable)."
    fi
    return 0
  fi
  if ! docker_ready; then
    # On macOS, try to launch OrbStack / Docker Desktop in the background.
    if [[ "$(uname)" == "Darwin" ]]; then
      if [[ -d "/Applications/OrbStack.app" ]]; then
        open -ga OrbStack >/dev/null 2>&1 || true
      elif [[ -d "/Applications/Docker.app" ]]; then
        open -ga Docker >/dev/null 2>&1 || true
      fi
    fi
    for _ in {1..30}; do
      docker_ready && break
      sleep 1
    done
  fi
  if ! docker_ready; then
    echo "SearXNG skipped: Docker is not running (start OrbStack/Docker and run ./start.sh restart)."
    return 0
  fi
  # A per-install secret for SearXNG, kept in .env (ignored by git).
  if [[ -z "${SEARXNG_SECRET:-}" ]]; then
    SEARXNG_SECRET="$(openssl rand -hex 32 2>/dev/null || LC_ALL=C tr -dc 'a-f0-9' </dev/urandom | head -c 64)"
    printf '\n# SearXNG secret (generated by start.sh)\nSEARXNG_SECRET=%s\n' "$SEARXNG_SECRET" >> "$PROJECT_ROOT/.env"
  fi
  export SEARXNG_SECRET
  echo "Starting SearXNG on http://127.0.0.1:$SEARXNG_PORT ..."
  rotate_log "$LOG_DIR/searxng.log"
  if ! docker compose -f "$SEARXNG_COMPOSE" up -d >>"$LOG_DIR/searxng.log" 2>&1; then
    echo "SearXNG could not be started; see $LOG_DIR/searxng.log"
    return 0
  fi
  # On restart, reload SearXNG too so changes to its settings.yml take effect.
  if [[ "${LOCAL_NOTEBOOK_RESTART_SEARXNG:-0}" == "1" ]]; then
    echo "Restarting SearXNG to load its settings..."
    docker compose -f "$SEARXNG_COMPOSE" restart >>"$LOG_DIR/searxng.log" 2>&1 || true
  fi
}

stop_searxng() {
  if searxng_enabled && docker_ready; then
    if [[ -n "$(docker compose -f "$SEARXNG_COMPOSE" ps -q 2>/dev/null)" ]]; then
      echo "Stopping SearXNG..."
      docker compose -f "$SEARXNG_COMPOSE" stop >/dev/null 2>&1 || true
    fi
  fi
}

searxng_status() {
  if searxng_enabled && docker_ready && [[ -n "$(docker compose -f "$SEARXNG_COMPOSE" ps -q --status running 2>/dev/null)" ]]; then
    echo "  [RUNNING] SearXNG -> http://127.0.0.1:$SEARXNG_PORT"
  else
    echo "  [STOPPED] SearXNG"
  fi
}

# Install frontend packages when package-lock.json changed since the last install
# (for example after an update that added a dependency).
ensure_frontend_deps() {
  local fe="$PROJECT_ROOT/frontend"
  local stamp="$fe/node_modules/.package-lock.json"
  if [[ -f "$stamp" && ! "$fe/package-lock.json" -nt "$stamp" ]]; then
    return 0
  fi
  local npm_cli="$PROJECT_ROOT/.node/lib/node_modules/npm/bin/npm-cli.js"
  echo "Installing frontend packages (package-lock.json changed)..."
  if [[ -f "$npm_cli" ]]; then
    (cd "$fe" && "$NODE_BIN" "$npm_cli" install --no-audit --no-fund)
  elif command -v npm >/dev/null 2>&1; then
    (cd "$fe" && npm install --no-audit --no-fund)
  else
    echo "Warning: npm not found; run 'npm install' in frontend/ manually."
  fi
}

start_services() {
  local detach=false
  local build_frontend=false
  for arg in "$@"; do
    case "$arg" in
      -d|--detach) detach=true ;;
      --build) build_frontend=true ;;
      --with-embedding) START_EMBEDDING=1 ;;
    esac
  done

  ensure_frontend_deps

  if [[ "$build_frontend" == "true" ]] || [[ ! -d "$PROJECT_ROOT/frontend/dist" ]]; then
    echo "Building frontend..."
    (cd "$PROJECT_ROOT/frontend" && "$NODE_BIN" ./node_modules/vue-tsc/bin/vue-tsc.js -b && "$NODE_BIN" ./node_modules/vite/bin/vite.js build)
  fi

  start_searxng

  if embedding_enabled; then
    if is_running "$EMBEDDING_PID_FILE"; then
      echo "Embedding service is already running (PID $(cat "$EMBEDDING_PID_FILE"))."
    else
      echo "Starting Local Embedding Service on http://localhost:$EMBEDDING_PORT ..."
      rotate_log "$LOG_DIR/embedding.log"
      (
        cd "$PROJECT_ROOT/services/embedding"
        PORT="$EMBEDDING_PORT" nohup "$PYTHON_BIN" server.py \
          < /dev/null >> "$LOG_DIR/embedding.log" 2>&1 &
        echo $! > "$EMBEDDING_PID_FILE"
        echo "$EMBEDDING_PORT" > "$EMBEDDING_PORT_FILE"
      )
    fi
  fi

  if is_running "$BACKEND_PID_FILE"; then
    echo "Backend is already running (PID $(cat "$BACKEND_PID_FILE"))."
  else
    echo "Starting Backend on http://localhost:$BACKEND_PORT ..."
    rotate_log "$LOG_DIR/backend.log"
    (
      cd "$PROJECT_ROOT/backend"
      # The API listens on this computer only; the interface reaches it through vite's
      # /api proxy. BACKEND_HOST=0.0.0.0 exposes it directly.
      PORT="$BACKEND_PORT" nohup "$PYTHON_BIN" -m uvicorn main:app \
        --host "${BACKEND_HOST:-127.0.0.1}" --port "$BACKEND_PORT" \
        < /dev/null >> "$LOG_DIR/backend.log" 2>&1 &
      echo $! > "$BACKEND_PID_FILE"
    )
  fi

  if is_running "$FRONTEND_PID_FILE"; then
    echo "Frontend is already running (PID $(cat "$FRONTEND_PID_FILE"))."
  else
    echo "Starting Frontend on http://localhost:$FRONTEND_PORT ..."
    rotate_log "$LOG_DIR/frontend.log"
    (
      cd "$PROJECT_ROOT/frontend"
      # The interface is plain HTTP, so by default only this computer can open it: on a
      # network, passwords and session tokens would travel unencrypted. FRONTEND_HOST=0.0.0.0
      # opens it to other devices on a network you trust (see docs/OPERATIONS.md).
      VITE_PROXY_TARGET="http://127.0.0.1:$BACKEND_PORT" nohup "$NODE_BIN" ./node_modules/vite/bin/vite.js \
        --host "${FRONTEND_HOST:-127.0.0.1}" --port "$FRONTEND_PORT" \
        < /dev/null >> "$LOG_DIR/frontend.log" 2>&1 &
      echo $! > "$FRONTEND_PID_FILE"
    )
  fi

  echo ""
  echo "Local Notebook is running:"
  echo "  Frontend: http://localhost:$FRONTEND_PORT"
  echo "  Backend:  http://localhost:$BACKEND_PORT/health"
  if searxng_enabled && docker_ready; then
    echo "  SearXNG:  http://127.0.0.1:$SEARXNG_PORT"
  fi
  if embedding_enabled; then
    echo "  Embedding: http://localhost:$EMBEDDING_PORT/health"
  fi
  echo "  Logs:     $LOG_DIR/"

  if [[ "$detach" == "false" ]] && [[ "${1:-}" == "up" ]] && [[ "$*" != *"-d"* ]]; then
    echo "Press Ctrl+C to stop tailing logs (services will continue running, use './start.sh down' to stop)."
    tail -f "$LOG_DIR/backend.log" "$LOG_DIR/frontend.log"
  fi
}

status_services() {
  for item in "Backend:$BACKEND_PID_FILE:http://localhost:$BACKEND_PORT/health" \
              "Frontend:$FRONTEND_PID_FILE:http://localhost:$FRONTEND_PORT" \
              "Embedding:$EMBEDDING_PID_FILE:http://localhost:$EMBEDDING_PORT/health"; do
    IFS=":" read -r name pid_file url_scheme url_rest <<< "$item"
    local url="${url_scheme}:${url_rest}"
    if is_running "$pid_file"; then
      echo "  [RUNNING] $name (PID $(cat "$pid_file")) -> $url"
    else
      echo "  [STOPPED] $name"
    fi
  done
  searxng_status
}

CMD="${1:-up}"
case "$CMD" in
  up|start)
    shift || true
    start_services "up" "$@"
    ;;
  down|stop)
    stop_service "Frontend" "$FRONTEND_PID_FILE"
    stop_service "Backend" "$BACKEND_PID_FILE"
    stop_service "Embedding" "$EMBEDDING_PID_FILE"
    rm -f "$EMBEDDING_PORT_FILE"
    # A restart keeps SearXNG running (start_services makes sure it is up).
    if [[ "${LOCAL_NOTEBOOK_KEEP_SEARXNG:-0}" != "1" ]]; then
      stop_searxng
    fi
    echo "All Local Notebook services stopped."
    ;;
  restart)
    shift || true
    LOCAL_NOTEBOOK_KEEP_SEARXNG=1 "$0" down
    LOCAL_NOTEBOOK_RESTART_SEARXNG=1 start_services "up" -d "$@"
    ;;
  status|ps)
    status_services
    ;;
  logs)
    shift || true
    tail "$@" "$LOG_DIR/backend.log" "$LOG_DIR/frontend.log"
    ;;
  docker)
    shift || true
    exec docker compose "$@"
    ;;
  *)
    echo "Usage: ./start.sh [up [-d] [--build] [--with-embedding] | down | restart | status | logs [-f]]"
    exit 1
    ;;
esac
