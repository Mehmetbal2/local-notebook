import logging
import os
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from paths import get_data_dir, get_milvus_uri

logger = logging.getLogger(__name__)

# Supports both local Milvus Lite file (default: local-notebook-data/milvus.db)
# and standalone Milvus server (e.g. http://localhost:19530).
MILVUS_URI = get_milvus_uri()

# These constants define the Milvus data layout. Changing any of them requires
# an explicit vector-store migration or full re-index.
TEXT_COLLECTION = "local_notebook_text_segments_v1"
IMAGE_COLLECTION = "local_notebook_image_segments_v1"
VECTOR_INDEX_TYPE = "IVF_PQ"
IVF_NLIST = 128
IVF_NPROBE = 32
PQ_M = 128
PQ_NBITS = 8

_client = None
# Milvus Lite takes an exclusive flock on the database file, so two threads that
# both see `_client is None` must not open it at the same time: the loser gets
# "Open local milvus failed" and the job drops into the retry queue. Serialize
# initialization (double-checked locking) so only one thread ever creates it.
_client_lock = threading.Lock()
# Creating a collection is not atomic: after the shared collections are dropped (model switch
# or re-index), several re-embed jobs reach ensure_collection at the same moment and would
# each try to create or drop it. One thread at a time decides.
_collection_lock = threading.Lock()


def _create_milvus_client(uri: str):
    is_remote = uri.startswith(("http://", "https://"))
    saved_env = os.environ.get("MILVUS_URI")
    try:
        if not is_remote:
            os.environ["MILVUS_URI"] = ""
            import pymilvus.settings
            pymilvus.settings.Config.MILVUS_URI = ""
            Path(uri).parent.mkdir(parents=True, exist_ok=True)
        from pymilvus import MilvusClient
        return MilvusClient(uri=uri)
    finally:
        if saved_env is not None:
            os.environ["MILVUS_URI"] = saved_env


def _is_milvus_lock_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "holds the lock" in message
        or "open local milvus failed" in message
        or "resource temporarily unavailable" in message
    )


def _create_client_with_retry(uri: str):
    """Wait briefly when the previous backend process has not released the data dir yet."""
    attempts = max(1, int(os.getenv("MILVUS_STARTUP_RETRIES", "8")))
    for attempt in range(attempts):
        try:
            return _create_milvus_client(uri)
        except Exception as exc:
            if attempt == attempts - 1 or not _is_milvus_lock_error(exc):
                raise
            delay = min(2.0, 0.25 * (2 ** attempt))
            logger.warning(
                "Milvus data directory is still locked by the previous process; "
                "retrying in %.2fs (%d/%d)",
                delay,
                attempt + 1,
                attempts,
            )
            time.sleep(delay)


def _get_client():
    global _client, MILVUS_URI
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        MILVUS_URI = get_milvus_uri()
        try:
            _client = _create_client_with_retry(MILVUS_URI)
        except Exception as exc:
            fallback_uri = (get_data_dir() / "milvus.db").resolve().as_posix()
            if MILVUS_URI.startswith(("http://", "https://")) and MILVUS_URI != fallback_uri:
                logger.warning(
                    "Milvus server at %s unavailable (%s); falling back to local Milvus Lite at %s",
                    MILVUS_URI,
                    exc,
                    fallback_uri,
                )
                os.environ["MILVUS_URI"] = fallback_uri
                MILVUS_URI = fallback_uri
                _client = _create_client_with_retry(fallback_uri)
            else:
                raise
    return _client


def _legacy_col(project_id: str) -> str:
    return "p_" + project_id.replace("-", "_")


def _legacy_img_col(project_id: str) -> str:
    return _legacy_col(project_id) + "_images"


def legacy_collection_names(project_id: str) -> tuple[str, str]:
    return _legacy_col(project_id), _legacy_img_col(project_id)


def shared_collection_names() -> tuple[str, str]:
    return TEXT_COLLECTION, IMAGE_COLLECTION


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _in_expr(field_name: str, values: Iterable[str]) -> str:
    values_quoted = ", ".join(_quote(value) for value in values)
    return f"{field_name} in [{values_quoted}]"


def _not_in_expr(field_name: str, values: Iterable[str]) -> str:
    values_quoted = ", ".join(_quote(value) for value in values)
    return f"{field_name} not in [{values_quoted}]"


def _project_filter(project_id: str) -> str:
    return f"project_id == {_quote(project_id)}"


def _project_file_filter(project_id: str, file_id: str) -> str:
    return f"{_project_filter(project_id)} and file_id == {_quote(file_id)}"


def _filter_for_project_files(project_id: str, file_ids: list[str] | None = None) -> str:
    filter_expr = _project_filter(project_id)
    if file_ids:
        filter_expr += f" and {_in_expr('file_id', file_ids)}"
    return filter_expr


def _pq_m(dim: int) -> int:
    preferred = max(1, PQ_M)
    if dim % preferred == 0 and preferred <= dim:
        return preferred

    candidates = [128, 96, 64, 48, 32, 24, 16, 12, 8, 4, 2, 1]
    for candidate in candidates:
        if candidate <= dim and dim % candidate == 0:
            logger.warning(
                "PQ_M=%s is incompatible with vector dim=%s; using m=%s",
                preferred,
                dim,
                candidate,
            )
            return candidate
    return 1


def _effective_vector_index_type() -> str:
    if not MILVUS_URI.startswith(("http://", "https://")) and VECTOR_INDEX_TYPE == "IVF_PQ":
        return "IVF_FLAT"
    return VECTOR_INDEX_TYPE


def _add_vector_index(index_params, dim: int) -> None:
    index_type = _effective_vector_index_type()
    params: dict[str, int] = {"nlist": IVF_NLIST}
    if index_type == "IVF_PQ":
        params.update({"m": _pq_m(dim), "nbits": PQ_NBITS})

    index_params.add_index(
        field_name="embedding",
        index_type=index_type,
        metric_type="L2",
        params=params,
    )


def _add_filter_indexes(index_params) -> None:
    if not MILVUS_URI.startswith(("http://", "https://")):
        return
    index_params.add_index(field_name="project_id", index_type="INVERTED")
    index_params.add_index(field_name="file_id", index_type="INVERTED")


def _ensure_collection_loaded(client, name: str) -> bool:
    if not client.has_collection(name):
        return False
    try:
        client.load_collection(name)
    except Exception as exc:
        if "IVF_PQ" in str(exc) or isinstance(exc, NotImplementedError):
            try:
                client.drop_index(collection_name=name, index_name="embedding")
                index_params = client.prepare_index_params()
                _add_vector_index(index_params, dim=0)
                client.create_index(collection_name=name, index_params=index_params)
                client.load_collection(name)
                logger.info(
                    "Migrated collection '%s' vector index from IVF_PQ to %s",
                    name,
                    _effective_vector_index_type(),
                )
            except Exception as migrate_exc:
                logger.warning("Failed to migrate vector index on '%s': %s", name, migrate_exc)
    return True


# Collections already loaded by the current client, with their vector dim. search() runs on
# every chat question; without this it paid a load + describe round trip each time. Entries
# are dropped whenever this process creates or drops a collection.
_search_ready: dict[tuple[int, str], int | None] = {}
_search_ready_lock = threading.Lock()


def _forget_collection(name: str) -> None:
    with _search_ready_lock:
        for key in [key for key in _search_ready if key[1] == name]:
            _search_ready.pop(key, None)


def _search_dim(client, name: str) -> tuple[bool, int | None]:
    """(exists, dim) for a collection about to be searched, using the cache when possible."""
    key = (id(client), name)
    with _search_ready_lock:
        if key in _search_ready:
            return True, _search_ready[key]
    if not _ensure_collection_loaded(client, name):
        return False, None
    dim = _get_collection_dim(client, name)
    with _search_ready_lock:
        _search_ready[key] = dim
    return True, dim


def _get_collection_dim(client, name: str) -> int | None:
    if not client.has_collection(name):
        return None
    try:
        desc = client.describe_collection(name)
        for field in desc.get("fields", []):
            if field.get("name") == "embedding":
                params = field.get("params") or {}
                dim_val = params.get("dim") or field.get("dim")
                if dim_val is not None:
                    return int(dim_val)
    except Exception as exc:
        logger.warning("Could not inspect collection '%s' dim: %s", name, exc)
    return None


def _is_collection_empty(client, name: str) -> bool:
    try:
        rows = client.query(collection_name=name, filter='id != ""', output_fields=["id"], limit=1)
        return not bool(rows)
    except Exception:
        return False


def reset_shared_collections() -> None:
    client = _get_client()
    for name in shared_collection_names():
        if client.has_collection(name):
            client.drop_collection(collection_name=name)
            _forget_collection(name)
            logger.info("Dropped shared Milvus collection '%s' after embedding model switch", name)


def _check_or_recreate_collection_dim(client, name: str, dim: int) -> bool:
    """Return True if collection already exists with matching dim; False if it was dropped/absent and must be created."""
    if not _ensure_collection_loaded(client, name):
        return False
    existing_dim = _get_collection_dim(client, name)
    if existing_dim is None or existing_dim == dim:
        return True
    if _is_collection_empty(client, name):
        logger.info(
            "Dropping empty Milvus collection '%s' with stale dim=%s to recreate with dim=%s",
            name,
            existing_dim,
            dim,
        )
        client.drop_collection(collection_name=name)
        _forget_collection(name)
        return False
    from utils.i18n import msg as ui_msg
    raise RuntimeError(ui_msg("embedding_dim_mismatch", existing_dim=existing_dim, new_dim=dim))


def ensure_collection(project_id: str, dim: int) -> None:
    with _collection_lock:
        _ensure_collection_locked(project_id, dim)


def _ensure_collection_locked(project_id: str, dim: int) -> None:
    client = _get_client()
    name = TEXT_COLLECTION
    if _check_or_recreate_collection_dim(client, name, dim):
        return

    from pymilvus import DataType
    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("id",            DataType.VARCHAR,      max_length=200, is_primary=True)
    schema.add_field("project_id",    DataType.VARCHAR,      max_length=50)
    schema.add_field("file_id",       DataType.VARCHAR,      max_length=50)
    schema.add_field("file_name",     DataType.VARCHAR,      max_length=500)
    schema.add_field("segment_index", DataType.INT64)
    schema.add_field("content",       DataType.VARCHAR,      max_length=4096)
    schema.add_field("summary",       DataType.VARCHAR,      max_length=2048)
    schema.add_field("embedding",     DataType.FLOAT_VECTOR, dim=dim)

    index_params = client.prepare_index_params()
    _add_filter_indexes(index_params)
    _add_vector_index(index_params, dim)

    client.create_collection(
        collection_name=name,
        schema=schema,
        index_params=index_params,
    )
    _forget_collection(name)
    logger.info(
        "Created Milvus text collection '%s' dim=%s index=%s",
        name,
        dim,
        VECTOR_INDEX_TYPE,
    )


def ensure_image_collection(project_id: str, dim: int) -> None:
    with _collection_lock:
        _ensure_image_collection_locked(project_id, dim)


def _ensure_image_collection_locked(project_id: str, dim: int) -> None:
    client = _get_client()
    name = IMAGE_COLLECTION
    if _check_or_recreate_collection_dim(client, name, dim):
        return

    from pymilvus import DataType
    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("id",            DataType.VARCHAR,      max_length=200, is_primary=True)
    schema.add_field("project_id",    DataType.VARCHAR,      max_length=50)
    schema.add_field("file_id",       DataType.VARCHAR,      max_length=50)
    schema.add_field("file_name",     DataType.VARCHAR,      max_length=500)
    schema.add_field("image_index",   DataType.INT64)
    schema.add_field("description",   DataType.VARCHAR,      max_length=4096)
    schema.add_field("embedding",     DataType.FLOAT_VECTOR, dim=dim)

    index_params = client.prepare_index_params()
    _add_filter_indexes(index_params)
    _add_vector_index(index_params, dim)

    client.create_collection(
        collection_name=name,
        schema=schema,
        index_params=index_params,
    )
    _forget_collection(name)
    logger.info(
        "Created Milvus image collection '%s' dim=%s index=%s",
        name,
        dim,
        VECTOR_INDEX_TYPE,
    )


def upsert_chunks(project_id: str, chunks: list[dict]) -> None:
    if not chunks:
        return
    client = _get_client()
    _ensure_collection_loaded(client, TEXT_COLLECTION)
    data = [{**chunk, "project_id": project_id} for chunk in chunks]
    client.upsert(collection_name=TEXT_COLLECTION, data=data)


def upsert_image_chunks(project_id: str, chunks: list[dict]) -> None:
    if not chunks:
        return
    client = _get_client()
    _ensure_collection_loaded(client, IMAGE_COLLECTION)
    data = [{**chunk, "project_id": project_id} for chunk in chunks]
    client.upsert(collection_name=IMAGE_COLLECTION, data=data)


def delete_by_file(project_id: str, file_id: str) -> None:
    client = _get_client()

    if _ensure_collection_loaded(client, TEXT_COLLECTION):
        client.delete(
            collection_name=TEXT_COLLECTION,
            filter=_project_file_filter(project_id, file_id),
        )

    if _ensure_collection_loaded(client, IMAGE_COLLECTION):
        client.delete(
            collection_name=IMAGE_COLLECTION,
            filter=_project_file_filter(project_id, file_id),
        )


def delete_project_vectors(project_id: str) -> None:
    client = _get_client()

    for name in shared_collection_names():
        if _ensure_collection_loaded(client, name):
            client.delete(collection_name=name, filter=_project_filter(project_id))
            logger.info("Deleted Milvus vectors from '%s' for project %s", name, project_id)

    for name in legacy_collection_names(project_id):
        if client.has_collection(name):
            client.drop_collection(collection_name=name)
            logger.info("Dropped legacy Milvus collection '%s'", name)


def delete_project_collections(project_id: str) -> None:
    delete_project_vectors(project_id)


def delete_projects_vectors(project_ids: Iterable[str]) -> None:
    ids = sorted(set(project_ids))
    if not ids:
        return

    client = _get_client()
    filter_expr = _in_expr("project_id", ids)
    for name in shared_collection_names():
        if _ensure_collection_loaded(client, name):
            client.delete(collection_name=name, filter=filter_expr)


def delete_vectors_not_in_projects(active_project_ids: Iterable[str]) -> None:
    ids = sorted(set(active_project_ids))
    client = _get_client()
    filter_expr = (
        _not_in_expr("project_id", ids)
        if ids
        else 'project_id != ""'
    )
    for name in shared_collection_names():
        if _ensure_collection_loaded(client, name):
            client.delete(collection_name=name, filter=filter_expr)


def search(
    project_id: str,
    query_vector: list[float],
    file_ids: list[str] | None = None,
    top_k: int = 8,
) -> list[dict]:
    client = _get_client()
    name = TEXT_COLLECTION

    exists, existing_dim = _search_dim(client, name)
    if not exists:
        return []
    if existing_dim is not None and existing_dim != len(query_vector):
        from utils.i18n import msg as ui_msg
        raise RuntimeError(ui_msg("embedding_dim_mismatch", existing_dim=existing_dim, new_dim=len(query_vector)))

    try:
        results = client.search(
            collection_name=name,
            data=[query_vector],
            limit=top_k,
            filter=_filter_for_project_files(project_id, file_ids),
            output_fields=["file_id", "file_name", "segment_index", "content", "summary"],
            search_params={"metric_type": "L2", "params": {"nprobe": IVF_NPROBE}},
        )
    except Exception:
        # The cached state may be stale (collection dropped or released elsewhere).
        _forget_collection(name)
        if not client.has_collection(name):
            return []
        raise

    hits = []
    for hit in results[0]:
        hits.append({
            "segment_id":    hit["id"],
            "file_id":       hit["entity"]["file_id"],
            "file_name":     hit["entity"]["file_name"],
            "segment_index": hit["entity"]["segment_index"],
            "content":       hit["entity"]["content"],
            "summary":       hit["entity"].get("summary") or "",
            "score":         hit["distance"],
        })
    return hits


def search_images(
    project_id: str,
    query_vector: list[float],
    file_ids: list[str] | None = None,
    top_k: int = 5,
) -> list[dict]:
    client = _get_client()
    name = IMAGE_COLLECTION

    exists, existing_dim = _search_dim(client, name)
    if not exists:
        return []
    if existing_dim is not None and existing_dim != len(query_vector):
        from utils.i18n import msg as ui_msg
        raise RuntimeError(ui_msg("embedding_dim_mismatch", existing_dim=existing_dim, new_dim=len(query_vector)))

    try:
        results = client.search(
            collection_name=name,
            data=[query_vector],
            limit=top_k,
            filter=_filter_for_project_files(project_id, file_ids),
            output_fields=["file_id", "file_name", "image_index", "description"],
            search_params={"metric_type": "L2", "params": {"nprobe": IVF_NPROBE}},
        )
    except Exception:
        # The cached state may be stale (collection dropped or released elsewhere).
        _forget_collection(name)
        if not client.has_collection(name):
            return []
        raise

    hits = []
    for hit in results[0]:
        hits.append({
            "image_id":      hit["id"],
            "file_id":       hit["entity"]["file_id"],
            "file_name":     hit["entity"]["file_name"],
            "image_index":   hit["entity"]["image_index"],
            "description":   hit["entity"]["description"],
            "score":         hit["distance"],
        })
    return hits


def get_by_ids(project_id: str, segment_ids: list[str]) -> list[dict]:
    if not segment_ids:
        return []
    client = _get_client()
    name = TEXT_COLLECTION
    if not _ensure_collection_loaded(client, name):
        return []

    results = client.query(
        collection_name=name,
        filter=f"{_project_filter(project_id)} and {_in_expr('id', segment_ids)}",
        output_fields=["file_id", "file_name", "segment_index", "content", "summary"],
    )

    return [
        {
            "id":            r["id"],
            "file_id":       r.get("file_id", ""),
            "file_name":     r.get("file_name", ""),
            "segment_index": r.get("segment_index", 0),
            "content":       r.get("content", ""),
            "summary":       r.get("summary") or "",
        }
        for r in (results or [])
    ]
