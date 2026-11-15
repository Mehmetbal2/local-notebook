import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from utils.i18n import msg as ui_msg

logger = logging.getLogger("ocr_client")

ATX_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        return value if value > 0 else default
    except ValueError:
        return default


OCR_PDF_CHUNK_PAGES = _env_int("OCR_PDF_CHUNK_PAGES", 20)


def _make_minimal_pdf() -> bytes:
    return (
        b"%PDF-1.0\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 72 72]/Parent 2 0 R/Contents 4 0 R>>endobj\n"
        b"4 0 obj<</Length 22>>stream\nBT /F1 12 Tf (hi) Tj ET\nendstream\nendobj\n"
        b"xref\n0 5\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000210 00000 n \n"
        b"trailer<</Size 5/Root 1 0 R>>\nstartxref\n282\n%%EOF\n"
    )


def _extract_error_message(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])
            for key in ("detail", "message", "msg"):
                if data.get(key):
                    return str(data[key])
    except Exception:
        pass
    text = (resp.text or "").strip()
    return ui_msg("service_returned", status=resp.status_code) + (f": {text[:300]}" if text else "")


@dataclass
class OCRResult:
    markdown: str
    content_list: list
    success: bool
    error_message: Optional[str] = None
    page_count: int = 0
    images: dict | None = None


@dataclass(frozen=True)
class PDFChunk:
    file_path: str
    start_page: int
    end_page: int


def _safe_file_stem(file_path: str) -> str:
    stem = os.path.splitext(os.path.basename(file_path))[0]
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in stem)
    return safe[:80] or "document"


def _get_pdf_page_count_sync(file_path: str) -> int:
    try:
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        return len(reader.pages)
    except Exception:
        return 0


async def _get_pdf_page_count(file_path: str) -> int:
    return await asyncio.to_thread(_get_pdf_page_count_sync, file_path)


def _split_pdf_sync(file_path: str, output_dir: str, pages_per_chunk: int) -> list[PDFChunk]:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(file_path)
    total_pages = len(reader.pages)
    stem = _safe_file_stem(file_path)
    chunks: list[PDFChunk] = []

    for start in range(0, total_pages, pages_per_chunk):
        end = min(start + pages_per_chunk, total_pages)
        writer = PdfWriter()
        for page_index in range(start, end):
            writer.add_page(reader.pages[page_index])

        chunk_name = f"{stem}_p{start + 1:04d}-{end:04d}.pdf"
        chunk_path = os.path.join(output_dir, chunk_name)
        with open(chunk_path, "wb") as f:
            writer.write(f)

        chunks.append(PDFChunk(file_path=chunk_path, start_page=start, end_page=end))

    return chunks


async def _split_pdf(file_path: str, output_dir: str, pages_per_chunk: int) -> list[PDFChunk]:
    return await asyncio.to_thread(_split_pdf_sync, file_path, output_dir, pages_per_chunk)


def _markdown_page_to_content_list(page_text: str, page_idx: int) -> list[dict]:
    """Convert a single page of OCR markdown into structured content_list items."""
    if not page_text or not page_text.strip():
        return []

    items: list[dict] = []
    buffer: list[str] = []
    in_code_fence = False
    code_lang = ""
    in_math_block = False

    def flush_buffer() -> None:
        if not buffer:
            return
        chunk = "\n".join(buffer).strip()
        buffer.clear()
        if not chunk:
            return
        if chunk.startswith("$$") and chunk.endswith("$$"):
            items.append({"type": "equation", "text": chunk, "page_idx": page_idx})
        else:
            items.append({"type": "text", "text": chunk, "page_idx": page_idx})

    for raw_line in page_text.splitlines():
        stripped = raw_line.strip()

        if in_code_fence:
            if stripped.startswith("```"):
                code_body = "\n".join(buffer).strip("\n")
                buffer.clear()
                in_code_fence = False
                if code_body.strip():
                    item: dict = {"type": "code", "code_body": code_body, "page_idx": page_idx}
                    if code_lang:
                        item["guess_lang"] = code_lang
                    items.append(item)
                code_lang = ""
            else:
                buffer.append(raw_line.rstrip())
            continue

        if in_math_block:
            buffer.append(raw_line.rstrip())
            if stripped.endswith("$$"):
                in_math_block = False
                flush_buffer()
            continue

        if not stripped:
            flush_buffer()
            continue

        if stripped.startswith("```"):
            flush_buffer()
            in_code_fence = True
            code_lang = stripped[3:].strip()
            continue

        if stripped.startswith("$$"):
            flush_buffer()
            if len(stripped) > 4 and stripped.endswith("$$"):
                items.append({"type": "equation", "text": stripped, "page_idx": page_idx})
            else:
                in_math_block = True
                buffer.append(stripped)
            continue

        heading_match = ATX_HEADING_RE.match(stripped)
        if heading_match:
            flush_buffer()
            items.append({
                "type": "text",
                "text": heading_match.group(2).strip(),
                "text_level": len(heading_match.group(1)),
                "page_idx": page_idx,
            })
            continue

        is_table_line = stripped.startswith("|")
        if buffer and buffer[0].lstrip().startswith("|") != is_table_line:
            flush_buffer()

        buffer.append(raw_line.rstrip())

    if in_code_fence and buffer:
        code_body = "\n".join(buffer).strip("\n")
        buffer.clear()
        if code_body.strip():
            item = {"type": "code", "code_body": code_body, "page_idx": page_idx}
            if code_lang:
                item["guess_lang"] = code_lang
            items.append(item)
    else:
        flush_buffer()

    return items


def _offset_content_list(content_list: list, page_offset: int) -> list:
    adjusted = []
    for item in content_list or []:
        if not isinstance(item, dict):
            adjusted.append(item)
            continue
        copied = dict(item)
        page_idx = copied.get("page_idx")
        if isinstance(page_idx, int):
            copied["page_idx"] = page_idx + page_offset
        for key in ("page", "start_page", "end_page"):
            value = copied.get(key)
            if isinstance(value, int):
                copied[key] = value + page_offset
        adjusted.append(copied)
    return adjusted


def _merge_chunk_results(chunk_results: list[tuple[PDFChunk, OCRResult]], page_count: int) -> OCRResult:
    markdown_parts: list[str] = []
    content_list: list = []

    for chunk, result in chunk_results:
        if result.markdown:
            markdown_parts.append(result.markdown.strip())
        content_list.extend(_offset_content_list(result.content_list or [], chunk.start_page))

    return OCRResult(
        markdown="\n\n".join(part for part in markdown_parts if part),
        content_list=content_list,
        success=True,
        page_count=page_count,
        images={},
    )


# ── Chunk cache: finished OCR chunks survive a restart or a stopped run ─────

OCR_CACHE_MAX_AGE_DAYS = _env_int("OCR_CACHE_MAX_AGE_DAYS", 14)


def _ocr_cache_root() -> str:
    from paths import get_data_dir

    return os.path.join(str(get_data_dir()), "cache", "ocr")


def _file_sha256(file_path: str) -> str:
    digest = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _ocr_cache_dir(file_path: str, model: str) -> str | None:
    """Folder for one PDF + model + chunk size; None when the cache is unusable."""
    try:
        key = f"{_file_sha256(file_path)}_{re.sub(r'[^A-Za-z0-9._-]', '_', model)}_{OCR_PDF_CHUNK_PAGES}"
        path = os.path.join(_ocr_cache_root(), key)
        os.makedirs(path, exist_ok=True)
        return path
    except OSError as exc:
        logger.warning(f"OCR cache unavailable: {exc}")
        return None


def _chunk_cache_file(cache_dir: str, chunk: "PDFChunk") -> str:
    return os.path.join(cache_dir, f"p{chunk.start_page + 1:04d}-{chunk.end_page:04d}.json")


def _load_cached_chunk(cache_dir: str | None, chunk: "PDFChunk") -> "OCRResult | None":
    if not cache_dir:
        return None
    path = _chunk_cache_file(cache_dir, chunk)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return OCRResult(
            markdown=data.get("markdown") or "",
            content_list=data.get("content_list") or [],
            success=True,
            page_count=int(data.get("page_count") or (chunk.end_page - chunk.start_page)),
            images={},
        )
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning(f"Ignoring unreadable OCR cache file {path}: {exc}")
        return None


def _save_cached_chunk(cache_dir: str | None, chunk: "PDFChunk", result: "OCRResult") -> None:
    if not cache_dir:
        return
    path = _chunk_cache_file(cache_dir, chunk)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"markdown": result.markdown, "content_list": result.content_list, "page_count": result.page_count},
                f,
                ensure_ascii=False,
            )
        os.replace(tmp, path)
    except (OSError, TypeError, ValueError) as exc:
        logger.warning(f"Could not cache OCR chunk {path}: {exc}")


def cleanup_ocr_cache(max_age_days: int = OCR_CACHE_MAX_AGE_DAYS) -> int:
    """Delete cached OCR folders not touched for max_age_days. Returns how many were removed."""
    root = _ocr_cache_root()
    if not os.path.isdir(root):
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for name in os.listdir(root):
        path = os.path.join(root, name)
        try:
            if os.path.isdir(path) and os.path.getmtime(path) < cutoff:
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed


def _build_ocr_url(base_url: str) -> str:
    clean = (base_url or "").strip().rstrip("/")
    return clean if clean.endswith("/ocr") else f"{clean}/ocr"


class PDFOCRClient:
    """Client for /ocr PDF parsing endpoints with Bearer API key and selectable model."""

    MAX_RETRIES = 5
    RETRY_BASE_DELAY = 3

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 300):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.timeout = timeout

    async def parse_pdf(self, file_path: str) -> OCRResult:
        if not os.path.exists(file_path):
            return OCRResult(
                markdown="",
                content_list=[],
                success=False,
                error_message=ui_msg("file_not_found", path=file_path),
            )

        page_count = await _get_pdf_page_count(file_path)
        if page_count > OCR_PDF_CHUNK_PAGES:
            return await self._parse_pdf_in_page_chunks(file_path=file_path, page_count=page_count)

        return await self._parse_pdf_single(file_path=file_path, page_count=page_count)

    async def _parse_pdf_in_page_chunks(self, file_path: str, page_count: int) -> OCRResult:
        logger.info(
            f"PDF has {page_count} pages, more than {OCR_PDF_CHUNK_PAGES}; calling OCR in page chunks ({self.model})"
        )

        cache_dir = await asyncio.to_thread(_ocr_cache_dir, file_path, self.model)
        with tempfile.TemporaryDirectory(prefix="pdf_ocr_chunks_") as temp_dir:
            chunks = await _split_pdf(file_path, temp_dir, OCR_PDF_CHUNK_PAGES)
            chunk_results: list[tuple[PDFChunk, OCRResult]] = []

            for index, chunk in enumerate(chunks, start=1):
                cached = _load_cached_chunk(cache_dir, chunk)
                if cached is not None:
                    logger.info(
                        f"OCR chunk {index}/{len(chunks)}: pages {chunk.start_page + 1}-{chunk.end_page} (from cache)"
                    )
                    chunk_results.append((chunk, cached))
                    continue
                logger.info(
                    f"OCR chunk {index}/{len(chunks)}: pages {chunk.start_page + 1}-{chunk.end_page}"
                )
                result = await self._parse_pdf_single(
                    file_path=chunk.file_path,
                    page_count=chunk.end_page - chunk.start_page,
                )
                if result.success:
                    _save_cached_chunk(cache_dir, chunk, result)
                if not result.success:
                    return OCRResult(
                        markdown="",
                        content_list=[],
                        success=False,
                        error_message=ui_msg(
                            "ocr_pages_failed",
                            start=chunk.start_page + 1,
                            end=chunk.end_page,
                            error=result.error_message or ui_msg("unknown_error"),
                        ),
                        page_count=page_count,
                    )
                chunk_results.append((chunk, result))

        merged = _merge_chunk_results(chunk_results, page_count)
        logger.info(
            f"OCR chunks merged: chunks={len(chunk_results)}, "
            f"markdown={len(merged.markdown)} chars, blocks={len(merged.content_list)}, pages={page_count}"
        )
        return merged

    async def _parse_pdf_single(self, file_path: str, page_count: int) -> OCRResult:
        target_url = _build_ocr_url(self.base_url)
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

        try:
            logger.info(f"calling the PDF OCR service: {target_url} model={self.model}")
            resp = None
            for attempt in range(self.MAX_RETRIES):
                with open(file_path, "rb") as f:
                    files = {"file": (os.path.basename(file_path), f, "application/pdf")}
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        resp = await client.post(
                            target_url,
                            headers=headers,
                            files=files,
                            data={"model": self.model},
                        )

                if resp.status_code not in (429, 503):
                    break

                retry_after = int(resp.headers.get("Retry-After", 0) or 0)
                delay = min(max(retry_after, self.RETRY_BASE_DELAY * (2 ** attempt)), 60)
                logger.warning(
                    f"PDF OCR service busy ({resp.status_code}), retry {attempt + 1}/{self.MAX_RETRIES}, waiting {delay}s..."
                )
                await asyncio.sleep(delay)

            assert resp is not None
            if resp.status_code not in (200, 201):
                error_msg = _extract_error_message(resp)
                logger.error(error_msg)
                return OCRResult(markdown="", content_list=[], success=False, error_message=error_msg)

            result = resp.json()
            if not isinstance(result, dict):
                return OCRResult(
                    markdown="",
                    content_list=[],
                    success=False,
                    error_message=ui_msg("ocr_non_json"),
                )

            pages = result.get("pages")
            markdown_parts: list[str] = []
            content_list: list[dict] = []

            if isinstance(pages, list) and pages:
                for idx, page_obj in enumerate(pages):
                    if not isinstance(page_obj, dict):
                        continue
                    raw_page = page_obj.get("page")
                    page_num = raw_page if isinstance(raw_page, int) and raw_page > 0 else idx + 1
                    page_text = str(page_obj.get("text") or "").strip()
                    if page_text:
                        markdown_parts.append(page_text)
                        content_list.extend(_markdown_page_to_content_list(page_text, page_num - 1))

            if not content_list:
                fallback_text = str(result.get("text") or result.get("markdown") or "").strip()
                if fallback_text:
                    markdown_parts.append(fallback_text)
                    content_list.extend(_markdown_page_to_content_list(fallback_text, 0))

            markdown = "\n\n".join(markdown_parts)
            resolved_pages = page_count or (len(pages) if isinstance(pages, list) else 0)
            logger.info(
                f"PDF OCR parsing finished: model={self.model}, markdown={len(markdown)} chars, "
                f"items={len(content_list)}, pages={resolved_pages}"
            )
            return OCRResult(
                markdown=markdown,
                content_list=content_list,
                success=True,
                page_count=resolved_pages,
                images={},
            )

        except httpx.ConnectError:
            error_msg = ui_msg("ocr_cannot_connect", url=self.base_url)
            logger.error(error_msg)
            return OCRResult(markdown="", content_list=[], success=False, error_message=error_msg)
        except httpx.TimeoutException:
            error_msg = ui_msg("ocr_timeout", seconds=self.timeout)
            logger.error(error_msg)
            return OCRResult(markdown="", content_list=[], success=False, error_message=error_msg)
        except Exception as e:
            error_msg = ui_msg("ocr_failed", error=e)
            logger.exception(error_msg)
            return OCRResult(markdown="", content_list=[], success=False, error_message=error_msg)

    async def health_check(self) -> tuple[bool, str]:
        target_url = _build_ocr_url(self.base_url)
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        pdf_bytes = _make_minimal_pdf()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    target_url,
                    headers=headers,
                    files={"file": ("probe.pdf", pdf_bytes, "application/pdf")},
                    data={"model": self.model},
                )
            if resp.status_code in (200, 201):
                return True, ui_msg("conn_ok_model", model=self.model)
            return False, _extract_error_message(resp)
        except httpx.ConnectError:
            return False, ui_msg("cannot_connect_url", url=self.base_url)
        except httpx.TimeoutException:
            return False, ui_msg("conn_timeout_url", url=self.base_url)
        except Exception as exc:
            return False, str(exc)



async def health_check(base_url: str = "", api_key: str = "", model: str = "") -> dict:
    if not api_key:
        return {"ok": False, "msg": ui_msg("missing_api_key")}
    if not base_url:
        return {"ok": False, "msg": ui_msg("missing_base_url")}
    if not model:
        return {"ok": False, "msg": ui_msg("missing_model")}

    ok, msg = await PDFOCRClient(base_url=base_url, api_key=api_key, model=model).health_check()
    if ok:
        return {"ok": True, "msg": msg, "verified": True}
    return {"ok": False, "msg": msg}
