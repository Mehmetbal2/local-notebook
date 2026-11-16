import os
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from paths import get_database_url

DATABASE_URL = get_database_url()

_connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args=_connect_args,
)

if "sqlite" in DATABASE_URL:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        journal_mode = os.getenv("SQLITE_JOURNAL_MODE", "WAL").upper()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA journal_mode={journal_mode}")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


RUNTIME_SCHEMA_COLUMNS = [
    ("projects", "owner_user_id", "VARCHAR(36)"),
    ("projects", "summary", "TEXT"),
    ("projects", "color", "VARCHAR(20)"),
    ("sessions", "last_total_tokens", "INTEGER"),
    ("sessions", "title_generation_status", "VARCHAR(20)"),
    ("sessions", "compact_summary", "TEXT"),
    ("sessions", "compact_citations_json", "TEXT"),
    ("sessions", "compact_message_id", "VARCHAR(36)"),
    ("messages", "deleted_at", "TIMESTAMP"),
    ("files", "processing_current", "INTEGER"),
    ("files", "processing_total", "INTEGER"),
    ("files", "processing_message", "VARCHAR(200)"),
    ("files", "source_url", "TEXT"),
]


# Earlier versions named the OCR service after the provider it shipped with.
# These one-time renames move existing installs to the provider-neutral names.
_LEGACY_OCR_PREFIX = "mineru"
LEGACY_SETTING_KEYS = {
    f"{_LEGACY_OCR_PREFIX}_{suffix}": f"ocr_{suffix}"
    for suffix in ("api_key", "base_url", "model", "verified")
}
LEGACY_FILE_COLUMNS = (f"{_LEGACY_OCR_PREFIX}_batch_id", f"{_LEGACY_OCR_PREFIX}_batch_created")


async def _migrate_legacy_ocr_names(conn, logger=None) -> None:
    for old_key, new_key in LEGACY_SETTING_KEYS.items():
        try:
            result = await conn.execute(
                text(
                    "UPDATE settings SET key = :new WHERE key = :old "
                    "AND NOT EXISTS (SELECT 1 FROM settings WHERE key = :new)"
                ),
                {"old": old_key, "new": new_key},
            )
            await conn.execute(text("DELETE FROM settings WHERE key = :old"), {"old": old_key})
            if logger and result.rowcount:
                logger.info(f"Migration: renamed setting {old_key} -> {new_key}")
        except Exception:
            pass
    try:
        await conn.execute(
            text("UPDATE settings SET value = 'ocr' WHERE key = 'pdf_engine' AND value = :old"),
            {"old": _LEGACY_OCR_PREFIX},
        )
    except Exception:
        pass
    for col in LEGACY_FILE_COLUMNS:
        try:
            await conn.execute(text(f"ALTER TABLE files DROP COLUMN {col}"))
            if logger:
                logger.info(f"Migration: dropped unused column files.{col}")
        except Exception:
            pass


async def ensure_runtime_schema(conn, logger=None) -> None:
    await _migrate_legacy_ocr_names(conn, logger)
    for table, col, col_type in RUNTIME_SCHEMA_COLUMNS:
        try:
            await conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            )
            if logger:
                logger.info(f"Migration: added {table}.{col}")
        except Exception:
            pass
