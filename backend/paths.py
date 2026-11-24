import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent


def _resolve_from_root(raw_path: str | Path) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (PROJECT_ROOT / path).resolve()


def safe_join(base: str | Path, *parts: str) -> Path:
    """Join untrusted path parts (an id, a file name) under `base`.

    Raises ValueError when the result would land outside `base`, e.g. through
    `..`, an absolute part or a symlink.
    """
    root = os.path.realpath(base)
    candidate = os.path.realpath(os.path.join(root, *[str(p) for p in parts]))
    if candidate != root and not candidate.startswith(root + os.sep):
        raise ValueError("path escapes its base directory")
    return Path(candidate)


def get_data_dir() -> Path:
    raw = os.getenv("LOCAL_NOTEBOOK_DATA_DIR", "").strip()
    if raw:
        data_dir = _resolve_from_root(raw)
    else:
        data_dir = (PROJECT_ROOT / "local-notebook-data").resolve()
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)  # owner-only when created
    return data_dir


def get_upload_dir() -> Path:
    raw = os.getenv("UPLOAD_DIR", "").strip()
    if raw and raw not in {"./uploads", "uploads"}:
        upload_dir = _resolve_from_root(raw)
    else:
        upload_dir = (get_data_dir() / "uploads").resolve()
    upload_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return upload_dir


def get_database_url() -> str:
    raw = os.getenv("DATABASE_URL", "").strip()
    if not raw or raw in {
        "sqlite+aiosqlite:///./local_notebook.db",
        "sqlite+aiosqlite:///local_notebook.db",
    }:
        db_file = (get_data_dir() / "local_notebook.db").resolve()
        return f"sqlite+aiosqlite:///{db_file.as_posix()}"

    if raw.startswith("sqlite") and "///" in raw:
        prefix, db_path_str = raw.split("///", 1)
        if not db_path_str.startswith("/"):
            resolved_db = _resolve_from_root(db_path_str)
            resolved_db.parent.mkdir(parents=True, exist_ok=True)
            return f"{prefix}///{resolved_db.as_posix()}"
    return raw


def get_sqlite_db_path() -> str:
    db_url = get_database_url()
    if "///" in db_url:
        raw_path = db_url.split("///", 1)[-1]
        return str(_resolve_from_root(raw_path))
    return str((get_data_dir() / "local_notebook.db").resolve())


def get_milvus_uri() -> str:
    raw = os.getenv("MILVUS_URI", "").strip()
    if not raw:
        milvus_path = (get_data_dir() / "milvus.db").resolve()
        milvus_path.parent.mkdir(parents=True, exist_ok=True)
        return milvus_path.as_posix()

    if raw.startswith(("http://", "https://", "unix:")):
        return raw

    milvus_path = _resolve_from_root(raw)
    milvus_path.parent.mkdir(parents=True, exist_ok=True)
    return milvus_path.as_posix()


def to_portable_path(path: str | Path) -> str:
    """Convert a filesystem path into a universal path relative to PROJECT_ROOT."""
    resolved = _resolve_from_root(path)
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        try:
            return Path("local-notebook-data") .joinpath(
                resolved.relative_to(get_data_dir())
            ).as_posix()
        except ValueError:
            return resolved.as_posix()


def resolve_stored_path(
    stored_path: str | Path | None,
    project_id: str | None = None,
    file_name: str | None = None,
) -> str:
    """Resolve a stored file path universally across directories and machines."""
    if not stored_path:
        if project_id and file_name:
            return (get_upload_dir() / project_id / file_name).as_posix()
        return ""

    raw_str = str(stored_path).strip().replace("\\", "/")
    candidate = Path(raw_str)

    # 1. Relative path -> resolve against PROJECT_ROOT, then DATA_DIR, then UPLOAD_DIR
    if not candidate.is_absolute():
        for base in (PROJECT_ROOT, get_data_dir(), get_upload_dir(), BACKEND_DIR):
            resolved = (base / candidate).resolve()
            if resolved.exists():
                return resolved.as_posix()
        return (PROJECT_ROOT / candidate).resolve().as_posix()

    # 2. Absolute path that exists on this machine
    if candidate.exists():
        return candidate.resolve().as_posix()

    # 3. Absolute path from a moved project directory or another machine -> rebase
    for marker in ("/local-notebook-data/", "/uploads/"):
        if marker in raw_str:
            suffix = raw_str.split(marker, 1)[1].lstrip("/")
            base = get_data_dir() if marker == "/local-notebook-data/" else get_upload_dir()
            rebased = (base / suffix).resolve()
            if rebased.exists():
                return rebased.as_posix()

    if project_id and file_name:
        fallback = (get_upload_dir() / project_id / Path(file_name).name).resolve()
        if fallback.exists():
            return fallback.as_posix()

    return candidate.as_posix()

