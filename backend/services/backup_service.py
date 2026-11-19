"""Portable backup and restore for the local data store.

A backup is a zip with a consistent copy of the SQLite database, the local vector
store (a Milvus Lite directory, or a single SQLite file in older setups) and,
optionally, the uploaded source files. Restore is staged and applied on the next
start, before any database or Milvus connection is opened: replacing those files
while the process is using them would corrupt the store.

The SQLite database is copied through SQLite's online backup API. The Milvus Lite
store cannot be copied that way, so its immutable data files are copied first and
the collection manifests last: a manifest only ever points at files that already
exist on disk, so the copy is never left referencing a half-written segment.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import secrets
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from paths import PROJECT_ROOT, get_data_dir, get_database_url, get_milvus_uri, get_upload_dir

logger = logging.getLogger(__name__)

BACKUP_FORMAT = 2
MAX_RESTORE_BYTES = int(os.getenv("RESTORE_MAX_ARCHIVE_BYTES", 4 * 1024 * 1024 * 1024))
MAX_RESTORE_UNCOMPRESSED = int(
    os.getenv("RESTORE_MAX_UNCOMPRESSED_BYTES", 8 * 1024 * 1024 * 1024)
)
RESTORE_DIR_NAME = "restore"

# Files inside the Milvus Lite directory that must not be copied:
#   LOCK               - the lock held by the running process
#   .database-staging  - scratch space for database creation
VECTOR_LOCK_FILE = "LOCK"
VECTOR_STAGING_DIR = ".database-staging"
VECTOR_MANIFESTS = ("manifest.json", "manifest.json.prev")

# How many pre-restore safety copies to keep. Each one is a full copy of the database and the
# vector store, so they used to pile up until the disk was full.
KEEP_PRE_RESTORE = max(1, int(os.getenv("BACKUP_KEEP_PRE_RESTORE", "3")))
# A prepared backup the browser never fetched is deleted after this long.
DOWNLOAD_TTL_SECONDS = max(60, int(os.getenv("BACKUP_DOWNLOAD_TTL_SECONDS", "900")))
ARCHIVE_PREFIX = "local-notebook-backup-"
PRE_RESTORE_PREFIX = "pre-restore-"

# One-time download tokens: the browser fetches the archive with a plain link, so it is
# written straight to disk instead of being held in page memory first.
_downloads: dict[str, tuple[Path, float]] = {}
_downloads_lock = threading.Lock()


def database_file() -> Path | None:
    """Path of the SQLite database, or None when a non-SQLite database is configured."""
    url = get_database_url()
    if not url.startswith("sqlite") or "///" not in url:
        return None
    raw = url.split("///", 1)[1]
    if not raw or raw == ":memory:":
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


def milvus_file() -> Path | None:
    """Path of the local vector store (file or directory), or None in server mode."""
    uri = get_milvus_uri()
    if uri.startswith(("http://", "https://", "unix:")):
        return None
    return Path(uri)


def _copy_sqlite_consistent(source: Path, destination: Path) -> None:
    """Use SQLite's online backup API so the copy is valid even while the app is writing."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(source), timeout=30)
    try:
        dst = sqlite3.connect(destination)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _validate_sqlite(path: Path) -> None:
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if not result or str(result[0]).lower() != "ok":
            raise ValueError("The uploaded database failed its integrity check")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if not {"users", "files", "projects"}.issubset(tables):
            raise ValueError("The uploaded database is not a Local Notebook database")
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"The uploaded file is not a readable SQLite database: {exc}") from exc
    finally:
        conn.close()


def _flush_vector_store() -> None:
    """Ask Milvus Lite to persist pending writes before the directory is copied.

    Best effort: the client is only touched when the app already created it, and a
    failure here (for example while switching stores) must not fail the backup.
    """
    from services import vector_service

    client = getattr(vector_service, "_client", None)
    if client is None:
        return
    try:
        for name in vector_service.shared_collection_names():
            try:
                if client.has_collection(collection_name=name):
                    client.flush(collection_name=name)
            except Exception:
                logger.warning(
                    "Could not flush vector collection %s before backup; "
                    "the copy may not include its most recent writes",
                    name,
                )
    except Exception:  # pragma: no cover - defensive, client is sandboxed above
        logger.warning("Could not flush the vector store before backup", exc_info=True)


def _vector_store_size(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        total = 0
        for entry in path.rglob("*"):
            if entry.is_file() and not entry.is_symlink():
                total += entry.stat().st_size
        return total
    except OSError:
        return 0


def _copy_vector_store(source: Path, destination: Path) -> int:
    """Copy a Milvus Lite directory, writing the collection manifests last."""
    if not source.is_dir():
        raise ValueError(f"The vector store at {source} is not a directory")

    destination.mkdir(parents=True, exist_ok=True)
    manifests: list[tuple[Path, Path]] = []
    copied = 0

    for entry in sorted(source.rglob("*")):
        relative = entry.relative_to(source)
        if relative.parts and relative.parts[0] == VECTOR_STAGING_DIR:
            continue
        if entry.is_symlink():
            continue
        if entry.is_dir():
            (destination / relative).mkdir(parents=True, exist_ok=True)
            continue
        if relative.name == VECTOR_LOCK_FILE:
            continue
        if relative.name in VECTOR_MANIFESTS:
            # The manifest is the commit point of a collection; copy it last.
            manifests.append((entry, relative))
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry, target)
        copied += entry.stat().st_size

    for entry, relative in sorted(
        manifests, key=lambda item: (item[1].name != "manifest.json.prev", str(item[1]))
    ):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry, target)
        copied += entry.stat().st_size

    _verify_vector_copy(destination)
    return copied


def _verify_vector_copy(root: Path) -> None:
    """Every data file named by a copied manifest must exist in the copy."""
    for manifest_path in root.rglob("manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        partitions = manifest.get("partitions") or {}
        if not isinstance(partitions, dict):
            continue
        for partition_name, partition in partitions.items():
            if not isinstance(partition, dict):
                continue
            base = manifest_path.parent / "partitions" / str(partition_name)
            for key in ("data_files", "delta_files"):
                for name in partition.get(key) or []:
                    if not (base / name).exists():
                        raise ValueError(
                            "The vector index is incomplete: "
                            f"{partition_name}/{name} is missing."
                        )


def _zip_entries(temp: Path) -> list[tuple[Path, str, bool]]:
    """Return (path, archive name, is_vector_data) entries for the archive.

    Directories are written too: the Milvus store keeps an empty ``wal/`` directory
    that the reader expects to exist.
    """
    entries: list[tuple[Path, str, bool]] = []
    for path in sorted(temp.rglob("*")):
        name = path.relative_to(temp).as_posix()
        if path.is_dir():
            name += "/"
        entries.append((path, name, name.startswith("milvus.db/")))
    return entries


def create_backup_archive(
    include_uploads: bool = False, include_vectors: bool = True
) -> Path:
    """Build a backup zip and return its path. The caller is responsible for deleting it."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backups_dir = get_data_dir() / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    archive_path = backups_dir / f"{ARCHIVE_PREFIX}{timestamp}.zip"

    db_path = database_file()
    vectors_path = milvus_file()
    vectors_local = vectors_path is not None

    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        copied: list[str] = []
        vector_bytes = 0
        vector_files = 0

        if db_path and db_path.exists():
            target = temp / "local_notebook.db"
            _copy_sqlite_consistent(db_path, target)
            copied.append("local_notebook.db")

        vectors_included = bool(
            vectors_local and include_vectors and vectors_path and vectors_path.exists()
        )
        if vectors_included and vectors_path is not None:
            _flush_vector_store()
            target = temp / "milvus.db"
            if vectors_path.is_dir():
                vector_bytes = _copy_vector_store(vectors_path, target)
                vector_files = sum(1 for entry in target.rglob("*") if entry.is_file())
            else:
                # Older setups stored the vector index in a single SQLite file.
                _copy_sqlite_consistent(vectors_path, target)
                vector_bytes = target.stat().st_size
                vector_files = 1
            copied.append("milvus.db/")

        if vectors_included:
            excluded_reason = None
        elif not vectors_local:
            excluded_reason = "remote vector server"
        elif not include_vectors:
            excluded_reason = "not requested"
        else:
            excluded_reason = "no local index yet"

        manifest = {
            "format": BACKUP_FORMAT,
            "app": "local-notebook",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": bool(db_path),
            "vector_store": "local" if vectors_local else "remote",
            "vectors_included": vectors_included,
            "vectors_excluded_reason": excluded_reason,
            "vector_bytes": vector_bytes,
            "vector_files": vector_files,
            "include_uploads": include_uploads,
            "files": sorted(copied) + (["uploads/"] if include_uploads else []),
        }
        manifest_path = temp / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path, name, is_vector in _zip_entries(temp):
                if is_vector:
                    # Parquet and index files are already compact; level 1 keeps the
                    # backup fast on stores that can be hundreds of megabytes.
                    archive.write(path, name, compresslevel=1)
                else:
                    archive.write(path, name)
            if include_uploads:
                uploads = get_upload_dir()
                if uploads.exists():
                    for path in uploads.rglob("*"):
                        if path.is_file():
                            archive.write(path, Path("uploads") / path.relative_to(uploads))

    logger.info(
        "Created backup archive %s (%s bytes, vectors included: %s)",
        archive_path,
        archive_path.stat().st_size,
        vectors_included,
    )
    return archive_path


def _backups_dir() -> Path:
    return get_data_dir() / "backups"


def register_download(archive_path: Path) -> str:
    """Hand out a one-time token for a prepared archive (and drop expired ones)."""
    token = secrets.token_urlsafe(32)
    now = time.time()
    expired: list[Path] = []
    with _downloads_lock:
        for key, (path, expires_at) in list(_downloads.items()):
            if expires_at <= now:
                _downloads.pop(key, None)
                expired.append(path)
        _downloads[token] = (archive_path, now + DOWNLOAD_TTL_SECONDS)
    for path in expired:
        path.unlink(missing_ok=True)
    return token


def claim_download(token: str) -> Path | None:
    """Return the archive for a token exactly once; None if unknown, used or expired."""
    with _downloads_lock:
        entry = _downloads.pop(token, None)
    if entry is None:
        return None
    path, expires_at = entry
    if expires_at <= time.time() or not path.exists():
        path.unlink(missing_ok=True)
        return None
    return path


def _pending_staging() -> Path | None:
    marker = _restore_root() / "pending.json"
    if not marker.exists():
        return None
    try:
        return Path(json.loads(marker.read_text(encoding="utf-8"))["staging"]).resolve()
    except Exception:
        return None


def prune_backups(keep_pre_restore: int | None = None) -> dict:
    """Remove backup leftovers that only use disk space.

    - pre-restore safety copies beyond the newest ``keep_pre_restore``
    - prepared backup archives older than the download window that nobody fetched
    - restore staging folders that no pending restore points to (a replaced upload)
    """
    keep = KEEP_PRE_RESTORE if keep_pre_restore is None else max(1, keep_pre_restore)
    removed: list[str] = []
    freed = 0

    def _remove(path: Path) -> None:
        nonlocal freed
        size = _vector_store_size(path) if path.is_dir() else (path.stat().st_size if path.exists() else 0)
        _remove_path(path)
        freed += size
        removed.append(path.name)

    backups = _backups_dir()
    if backups.is_dir():
        safety = sorted(
            (p for p in backups.iterdir() if p.is_dir() and p.name.startswith(PRE_RESTORE_PREFIX)),
            key=lambda p: p.name,
            reverse=True,
        )
        for path in safety[keep:]:
            _remove(path)

        with _downloads_lock:
            waiting = {path.resolve() for path, _ in _downloads.values()}
        cutoff = time.time() - DOWNLOAD_TTL_SECONDS
        for path in backups.glob(f"{ARCHIVE_PREFIX}*.zip"):
            try:
                stale = path.stat().st_mtime < cutoff
            except OSError:
                continue
            if stale and path.resolve() not in waiting:
                _remove(path)

    restore_root = _restore_root()
    if restore_root.is_dir():
        pending = _pending_staging()
        for path in restore_root.iterdir():
            if path.is_dir() and path.resolve() != pending:
                _remove(path)

    if removed:
        logger.info("Removed %d backup leftover(s), %d bytes: %s", len(removed), freed, ", ".join(removed))
    return {"removed": removed, "freed_bytes": freed}


def _restore_root() -> Path:
    return get_data_dir() / RESTORE_DIR_NAME


def _read_manifest(staging: Path) -> dict:
    manifest_path = staging / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return manifest if isinstance(manifest, dict) else {}


def stage_restore_archive(upload_path: Path) -> dict:
    """Validate an uploaded archive and mark it for the next start. Nothing is replaced yet."""
    restore_root = _restore_root()
    restore_root.mkdir(parents=True, exist_ok=True)
    staging = restore_root / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    staging.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(upload_path) as archive:
            members = archive.infolist()
            total_uncompressed = sum(member.file_size for member in members)
            if total_uncompressed > MAX_RESTORE_UNCOMPRESSED:
                raise ValueError("The archive is too large to restore")
            for member in members:
                parts = Path(member.filename).parts
                if member.filename.startswith("/") or ".." in parts:
                    raise ValueError("The archive contains an unsafe path")
            archive.extractall(staging)
    except zipfile.BadZipFile as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise ValueError("The uploaded file is not a valid zip archive") from exc
    except ValueError:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    db_file = staging / "local_notebook.db"
    if not db_file.exists():
        shutil.rmtree(staging, ignore_errors=True)
        raise ValueError("The archive does not contain local_notebook.db")

    _validate_sqlite(db_file)

    staged_vectors = staging / "milvus.db"
    if staged_vectors.is_dir():
        try:
            _verify_vector_copy(staged_vectors)
        except ValueError as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise ValueError(f"The backup's vector index is damaged: {exc}") from exc

    manifest = _read_manifest(staging)

    marker = restore_root / "pending.json"
    marker.write_text(
        json.dumps(
            {
                "staging": str(staging),
                "staged_at": datetime.now(timezone.utc).isoformat(),
                "manifest": manifest,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.warning("Restore staged at %s; it will be applied on the next start", staging)
    # An earlier upload that this one replaces is no longer needed.
    try:
        prune_backups()
    except Exception:
        logger.warning("Could not clean up older restore uploads", exc_info=True)
    return {"staging": str(staging), "manifest": manifest}


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def _move_aside(path: Path, safety_dir: Path, moved: list[tuple[Path, Path]]) -> None:
    safety_dir.mkdir(parents=True, exist_ok=True)
    backup_path = safety_dir / path.name
    if backup_path.exists():
        _remove_path(backup_path)
    shutil.move(str(path), str(backup_path))
    moved.append((path, backup_path))


def apply_pending_restore() -> dict | None:
    """Apply a staged restore. Must run at startup before the DB/Milvus are opened."""
    restore_root = _restore_root()
    marker = restore_root / "pending.json"
    if not marker.exists():
        return None

    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        staging = Path(data["staging"])
        staged_db = staging / "local_notebook.db"
        if not staged_db.exists():
            raise ValueError("staged database is missing")
    except Exception as exc:
        logger.error("Ignoring unreadable restore marker: %s", exc)
        marker.unlink(missing_ok=True)
        return None

    manifest = data.get("manifest")
    if not isinstance(manifest, dict):
        manifest = _read_manifest(staging)

    safety_dir = (
        get_data_dir()
        / "backups"
        / f"{PRE_RESTORE_PREFIX}{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )
    db_target = database_file()
    vectors_target = milvus_file()
    staged_vectors = staging / "milvus.db"
    staged_uploads = staging / "uploads"
    vectors_restored = False
    warnings: list[str] = []

    # Prepare every file next to its destination first. Only when all copies exist does
    # the commit phase move the current data aside, so a failed copy leaves the app intact.
    plan: list[tuple[Path, Path]] = []
    if db_target is not None:
        plan.append((staged_db, db_target))
    if vectors_target is not None and staged_vectors.exists():
        if vectors_target.is_dir() == staged_vectors.is_dir():
            plan.append((staged_vectors, vectors_target))
            vectors_restored = True
        else:
            warnings.append(
                "The backup vector store format does not match this installation; "
                "the current vector index was kept."
            )
            logger.warning(
                "Skipping staged vectors: %s is a %s but the backup entry is a %s",
                vectors_target,
                "directory" if vectors_target.is_dir() else "file",
                "directory" if staged_vectors.is_dir() else "file",
            )
    elif vectors_target is not None and vectors_target.exists():
        warnings.append(
            "The backup does not contain the vector index; the existing index was kept. "
            "Re-index your sources if search results look wrong."
        )
        logger.warning(
            "Restoring a backup without vectors; the existing vector store at %s was kept",
            vectors_target,
        )
    uploads_target = get_upload_dir() if staged_uploads.is_dir() else None

    prepared: list[tuple[Path, Path]] = []
    try:
        for source, target in plan:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".restoring")
            _remove_path(temporary)
            if source.is_dir():
                shutil.copytree(source, temporary)
            else:
                shutil.copy2(source, temporary)
            prepared.append((temporary, target))
        if uploads_target is not None:
            temporary_uploads = get_data_dir() / "uploads.restoring"
            shutil.rmtree(temporary_uploads, ignore_errors=True)
            shutil.copytree(staged_uploads, temporary_uploads)
            prepared.append((temporary_uploads, uploads_target))
    except Exception:
        for temporary, _target in prepared:
            _remove_path(temporary)
        logger.exception("Could not prepare the restore files; the current data is unchanged")
        raise

    moved: list[tuple[Path, Path]] = []
    installed: list[Path] = []
    try:
        for temporary, target in prepared:
            if target.is_dir() and not target.is_symlink():
                if target.exists():
                    _move_aside(target, safety_dir, moved)
                temporary.rename(target)
            else:
                for suffix in ("", "-wal", "-shm"):
                    current = Path(f"{target}{suffix}")
                    if current.exists():
                        _move_aside(current, safety_dir, moved)
                temporary.replace(target)
            installed.append(target)
    except Exception:
        logger.exception("Restore commit failed; restoring the previous data")
        for temporary, _target in prepared:
            if temporary.exists():
                _remove_path(temporary)
        for path in reversed(installed):
            _remove_path(path)
        for original, backup_path in reversed(moved):
            try:
                if backup_path.exists():
                    shutil.move(str(backup_path), str(original))
            except Exception:
                logger.exception("Could not put %s back from %s", original, backup_path)
        raise

    marker.unlink(missing_ok=True)
    shutil.rmtree(staging, ignore_errors=True)
    logger.warning(
        "Restore applied. Previous data was moved to %s; the restore source was removed.",
        safety_dir,
    )
    return {
        "safety": str(safety_dir),
        "vectors_restored": vectors_restored,
        "warnings": warnings,
    }
