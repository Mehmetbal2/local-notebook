import asyncio
import json
import logging
import math
import os
from dataclasses import dataclass
from typing import Awaitable, Callable

import config
from kosong._generate import generate
from kosong.message import Message
from services.llm_provider import create_llm_chat_provider
from services.usage_service import record_model_usage

logger = logging.getLogger("service.summary")

SEGMENT_SUMMARY_PROMPT = """Generate a concise summary for the following text. The summary will be used for document retrieval and synthesis.

Requirements:
1. Preserve key entities such as names, places, technical terms, and numbers.
2. Highlight the core claim, topic, or finding.
3. Use direct declarative sentences; avoid low-information phrases such as "this text discusses".
4. Keep exact source terms, titles, names, and quoted wording unchanged when translation would lose precision.
5. Output only the summary, with no extra explanation.

Output language: {output_language}

Text:
{content}

Summary:"""

FILE_SUMMARY_PROMPT = """Using the following file information, generate an overall summary and keywords.

=== Summary Requirements ===
1. Write no more than 120 words. Combine the key information from the segment summaries and extract the file's main purpose.
2. Use concise, information-dense declarative sentences.
3. Bold marking rules (use **bold**):
   - Bold the document's **core claim** or **main conclusion**.
   - Bold **key concept definitions**, especially when a technical term first appears.
   - Do not bold names, places, or concrete examples unless they are the document's main topic.

=== Keyword Requirements ===
1. Extract 5 keywords, each 1-4 words or one short phrase.
2. Keywords should reflect the document's core themes rather than isolated examples.
3. Prefer disciplines, methods, core concepts, and main viewpoints.
4. Write keywords in the output language, unless a keyword is a source-specific proper noun or technical term.

Return strict JSON only:
{{"summary": "Overall file summary...", "keywords": ["keyword 1", "keyword 2", "keyword 3", "keyword 4", "keyword 5"]}}

Output language: {output_language}

File name: {filename}

Segment summaries:
{segment_summaries}"""

PROJECT_SUMMARY_PROMPT = """Using the following project information and file summaries, generate an overall project summary in no more than 120 words.

Requirements:
1. Combine the topics and content across all files.
2. Explain the relationships among the files.
3. Highlight the project's core value.
4. Write in the output language and output only the summary, with no extra explanation.

Output language: {output_language}

Project name: {project_name}

File summaries:
{file_summaries}

Project summary:"""

PROJECT_OVERVIEW_PROMPT = """Using the following project information and file summaries, generate an overall project summary and one theme color.

Summary requirements:
1. Write no more than 120 words in the output language.
2. Combine the topics and content across all files.
3. Explain the relationships among the files.
4. Highlight the project's core value.

Theme color requirements:
Choose exactly one color from this list:
- blue: technology, business, finance, law, academic research
- green: environment, agriculture, health, medicine, biology
- orange: creativity, design, marketing, entertainment, education
- red: history, politics, social issues
- purple: art, philosophy, psychology, religion
- cyan: science communication, children, social science
- pink: fashion, beauty, lifestyle, emotion
- brown: classics, traditional culture, archaeology, historical documents

Return strict JSON only:
{{"summary": "Project summary...", "color": "blue"}}

Output language: {output_language}

Project name: {project_name}
Project description: {project_description}

File summaries:
{file_summaries}"""

PROJECT_COLORS = {"blue", "green", "orange", "red", "purple", "cyan", "pink", "brown"}
DEFAULT_OUTPUT_LANGUAGE = "English"
SUMMARY_GENERATION_MAX_ATTEMPTS = 3
SUMMARY_RETRY_BASE_DELAY = 0.5

# Large books should stay fast, but quality must not collapse after 40 segments.
# Up to FULL_LIMIT every segment gets an LLM summary; above it a bounded,
# evenly-spaced sample including the final segment is summarized and the rest
# receive a sentence-boundary extractive snippet.
SEGMENT_SUMMARY_FULL_LIMIT = int(os.getenv("SEGMENT_SUMMARY_FULL_LIMIT", "200"))
SEGMENT_SUMMARY_SAMPLE_MIN = int(os.getenv("SEGMENT_SUMMARY_SAMPLE_MIN", "32"))
SEGMENT_SUMMARY_SAMPLE_MAX = int(os.getenv("SEGMENT_SUMMARY_SAMPLE_MAX", "64"))
SEGMENT_SUMMARY_SAMPLE_RATIO = float(os.getenv("SEGMENT_SUMMARY_SAMPLE_RATIO", "0.15"))
SNIPPET_MAX_CHARS = int(os.getenv("SEGMENT_SUMMARY_SNIPPET_CHARS", "240"))
SEGMENT_SUMMARY_CONCURRENCY = int(os.getenv("SEGMENT_SUMMARY_CONCURRENCY", "2"))
SEGMENT_SUMMARY_MAX_ATTEMPTS = int(os.getenv("SEGMENT_SUMMARY_MAX_ATTEMPTS", "5"))

SUMMARY_SENTENCE_ENDINGS = "。！？!?؛;؟۔.…"


@dataclass
class SegmentSummaryBatch:
    summaries: dict[int, str]
    llm_indices: set[int]


def _evenly_spaced_indices(total: int, count: int) -> list[int]:
    """Return ``count`` indices across ``total`` that always include the last item."""
    if total <= 0 or count <= 0:
        return []
    if count >= total:
        return list(range(total))
    if count == 1:
        return [total - 1]
    return sorted({
        round(index * (total - 1) / (count - 1))
        for index in range(count)
    })


def _extractive_snippet(content: str, limit: int = SNIPPET_MAX_CHARS) -> str:
    """Create a readable fallback snippet at a sentence or word boundary."""
    text = (content or "").strip()
    if len(text) <= limit:
        return text

    window = text[:limit]
    cut = max(window.rfind(char) for char in SUMMARY_SENTENCE_ENDINGS)
    if cut >= int(limit * 0.5):
        return text[:cut + 1].strip()

    cut = window.rfind(" ")
    if cut >= int(limit * 0.6):
        return text[:cut].rstrip() + "…"

    return text[:limit].rstrip() + "…"


def _is_retryable_llm_error(error: Exception) -> bool:
    status = getattr(error, "status_code", None)
    if status in (408, 409, 425, 429, 500, 502, 503, 504):
        return True
    message = str(error).lower()
    return any(
        marker in message
        for marker in ("rate limit", "429", "timeout", "temporarily", "connection reset")
    )


def _sample_summaries(summaries: list[str], limit: int) -> list[str]:
    usable = [summary for summary in summaries if summary]
    if not usable:
        return []
    indices = _evenly_spaced_indices(len(usable), min(limit, len(usable)))
    return [usable[index] for index in indices]


def normalize_output_language(output_language: str | None) -> str:
    value = (output_language or "").strip()
    normalized = value.lower().replace("_", "-")
    if normalized in {"zh", "zh-cn", "chinese", "中文", "简体中文"}:
        return "Chinese"
    if normalized in {"en", "en-us", "en-gb", "english"}:
        return "English"
    if normalized in {"tr", "tr-tr", "turkish", "türkçe", "turkce"}:
        return "Turkish"
    return value or DEFAULT_OUTPUT_LANGUAGE


def _strip_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return text


def _truncate_summary(text: str, limit: int = 500) -> str:
    return text.strip()[:limit] if text else ""


def _fallback_summary_from_lines(lines: list[str], limit: int = 500) -> str:
    cleaned = [line.strip() for line in lines if line and line.strip()]
    if not cleaned:
        return ""
    return _truncate_summary(" ".join(cleaned), limit)


def _retry_prompt(prompt: str, reason: str) -> str:
    return (
        f"{prompt}\n\n"
        "Previous response was invalid: "
        f"{reason}. Return the requested final answer only. "
        "Do not include markdown fences, prose, or explanations."
    )


async def _sleep_before_retry(attempt: int) -> None:
    await asyncio.sleep(SUMMARY_RETRY_BASE_DELAY * attempt)


async def _llm_complete(
    prompt: str,
    api_key: str,
    base_url: str | None,
    model: str,
    api_format: str = "openai",
    max_tokens: int = 1024,
    temperature: float = 0.2,
    user_id: str | None = None,
) -> str:
    chat_provider = create_llm_chat_provider(
        api_key=api_key,
        base_url=base_url,
        model=model,
        api_format=api_format,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=False,
    )
    result = await generate(
        chat_provider=chat_provider,
        system_prompt="",
        tools=[],
        history=[Message(role="user", content=prompt)],
    )
    await record_model_usage(user_id=user_id, model=model, usage=result.usage)
    return result.message.extract_text().strip()


async def _resolve_llm() -> tuple[str, str | None, str, str] | None:
    # Summaries generated while parsing count as "simple tasks" and follow the saving plan: with
    # easy_task_llm set they use the cheaper model (reusing the main LLM's key/url), otherwise the main LLM.
    api_key, base_url, model, api_format = await config.resolve_easy_task_llm_provider_config()
    if not api_key or not model:
        return None
    return api_key, base_url, model, api_format


async def generate_segment_summary(
    content: str,
    api_key: str,
    base_url: str | None,
    model: str,
    api_format: str = "openai",
    output_language: str | None = None,
    user_id: str | None = None,
) -> str:
    if not content or len(content) < 20:
        return content[:200] if content else ""

    prompt = SEGMENT_SUMMARY_PROMPT.format(
        content=content[:2000],
        output_language=normalize_output_language(output_language),
    )
    summary = await _llm_complete(
        prompt,
        api_key,
        base_url,
        model,
        api_format=api_format,
        user_id=user_id,
    )

    if len(summary) > 500:
        summary = summary[:500] + "..."
    return summary


async def generate_segment_summaries(
    segments: list[dict],
    api_key: str,
    base_url: str | None,
    model: str,
    api_format: str = "openai",
    concurrency: int = SEGMENT_SUMMARY_CONCURRENCY,
    output_language: str | None = None,
    user_id: str | None = None,
    progress_callback: Callable[[int], Awaitable[None]] | None = None,
) -> SegmentSummaryBatch:
    if not segments:
        return SegmentSummaryBatch(summaries={}, llm_indices=set())

    semaphore = asyncio.Semaphore(concurrency)
    results: dict[int, str] = {}

    total_segs = len(segments)
    if total_segs <= SEGMENT_SUMMARY_FULL_LIMIT:
        llm_indices = {segment["segment_index"] for segment in segments}
    else:
        target = min(
            SEGMENT_SUMMARY_SAMPLE_MAX,
            max(
                SEGMENT_SUMMARY_SAMPLE_MIN,
                math.ceil(total_segs * SEGMENT_SUMMARY_SAMPLE_RATIO),
            ),
        )
        positions = _evenly_spaced_indices(total_segs, target)
        llm_indices = {segments[position]["segment_index"] for position in positions}

    logger.info(
        "Segment summaries: total=%d llm=%d snippets=%d",
        total_segs,
        len(llm_indices),
        total_segs - len(llm_indices),
    )

    async def _do_one(seg: dict):
        idx = seg["segment_index"]
        content = seg["content"]
        if idx not in llm_indices:
            results[idx] = _extractive_snippet(content)
            if progress_callback:
                await progress_callback(1)
            return

        async with semaphore:
            try:
                for attempt in range(1, SEGMENT_SUMMARY_MAX_ATTEMPTS + 1):
                    try:
                        summary = await generate_segment_summary(
                            content,
                            api_key,
                            base_url,
                            model,
                            api_format=api_format,
                            output_language=output_language,
                            user_id=user_id,
                        )
                        if not summary:
                            raise ValueError("empty summary")
                        results[idx] = summary
                        logger.info(f"segment {idx} summary done ({len(summary)} chars)")
                        break
                    except Exception as error:
                        if (
                            attempt < SEGMENT_SUMMARY_MAX_ATTEMPTS
                            and _is_retryable_llm_error(error)
                        ):
                            await asyncio.sleep(min(8.0, 1.5 * (2 ** (attempt - 1))))
                            continue
                        raise
            except Exception as e:
                results[idx] = _extractive_snippet(content)
                logger.warning(f"segment {idx} summary failed, using snippet fallback: {e}")
            finally:
                if progress_callback:
                    await progress_callback(1)

    await asyncio.gather(*[_do_one(s) for s in segments])
    return SegmentSummaryBatch(summaries=results, llm_indices=llm_indices)


async def generate_file_summary(
    file_name: str,
    segment_summaries: list[str],
    api_key: str,
    base_url: str | None,
    model: str,
    api_format: str = "openai",
    output_language: str | None = None,
    user_id: str | None = None,
    preferred_summaries: list[str] | None = None,
) -> dict:
    if not segment_summaries:
        return {"summary": "", "keywords": []}

    sampled = _sample_summaries(
        preferred_summaries or [], limit=20
    )
    if len(sampled) < 20:
        seen = set(sampled)
        for summary in _sample_summaries(segment_summaries, limit=20):
            if summary not in seen:
                sampled.append(summary)
                seen.add(summary)
            if len(sampled) >= 20:
                break

    if not sampled:
        return {"summary": "", "keywords": []}

    numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(sampled))
    prompt = FILE_SUMMARY_PROMPT.format(
        filename=file_name,
        segment_summaries=numbered,
        output_language=normalize_output_language(output_language),
    )

    attempt_prompt = prompt
    raw = ""
    last_error: Exception | None = None
    for attempt in range(1, SUMMARY_GENERATION_MAX_ATTEMPTS + 1):
        try:
            raw = await _llm_complete(
                attempt_prompt,
                api_key,
                base_url,
                model,
                api_format=api_format,
                max_tokens=2048,
                temperature=0.3,
                user_id=user_id,
            )
            text = _strip_json_response(raw)
            if not text:
                raise ValueError("empty response")
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise TypeError("response JSON must be an object")
            summary = _truncate_summary(str(parsed.get("summary") or ""))
            if not summary:
                raise ValueError("missing non-empty summary")
            raw_keywords = parsed.get("keywords", [])
            if not isinstance(raw_keywords, list):
                raw_keywords = []
            keywords = [
                str(keyword).strip()[:80]
                for keyword in raw_keywords
                if str(keyword).strip()
            ][:10]
            if attempt > 1:
                logger.info(
                    "File summary recovered on attempt %d/%d",
                    attempt,
                    SUMMARY_GENERATION_MAX_ATTEMPTS,
                )
            return {"summary": summary, "keywords": keywords}
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            last_error = e
            logger.warning(
                "File summary attempt %d/%d failed: %s",
                attempt,
                SUMMARY_GENERATION_MAX_ATTEMPTS,
                e,
            )
        except Exception as e:
            last_error = e
            logger.warning(
                "File summary attempt %d/%d generation failed: %s",
                attempt,
                SUMMARY_GENERATION_MAX_ATTEMPTS,
                e,
            )

        if attempt < SUMMARY_GENERATION_MAX_ATTEMPTS:
            await _sleep_before_retry(attempt)
            attempt_prompt = _retry_prompt(prompt, str(last_error or "invalid response"))

    raw_text = _strip_json_response(raw) if raw else ""
    fallback = "" if raw_text.startswith(("{", "[")) else _truncate_summary(raw_text)
    fallback = fallback or _fallback_summary_from_lines(sampled)
    if fallback:
        logger.warning("File summary fell back after retries: %s", last_error)
    else:
        logger.warning("File summary empty after retries: %s", last_error)
    return {"summary": fallback, "keywords": []}


async def generate_project_summary(
    project_name: str,
    file_summaries: list[dict],
    api_key: str,
    base_url: str | None,
    model: str,
    api_format: str = "openai",
    output_language: str | None = None,
    user_id: str | None = None,
) -> str:
    if not file_summaries:
        return ""

    lines = "\n".join(
        f"- {fs['file_name']}: {fs['summary']}"
        for fs in file_summaries if fs.get("summary")
    )
    if not lines:
        return ""

    prompt = PROJECT_SUMMARY_PROMPT.format(
        project_name=project_name,
        file_summaries=lines,
        output_language=normalize_output_language(output_language),
    )

    attempt_prompt = prompt
    last_error: Exception | None = None
    for attempt in range(1, SUMMARY_GENERATION_MAX_ATTEMPTS + 1):
        try:
            summary = await _llm_complete(
                attempt_prompt,
                api_key,
                base_url,
                model,
                api_format=api_format,
                max_tokens=1024,
                temperature=0.3,
                user_id=user_id,
            )
            summary = _truncate_summary(summary)
            if not summary:
                raise ValueError("empty response")
            if attempt > 1:
                logger.info(
                    "Project summary recovered on attempt %d/%d",
                    attempt,
                    SUMMARY_GENERATION_MAX_ATTEMPTS,
                )
            return summary
        except Exception as e:
            last_error = e
            logger.warning(
                "Project summary attempt %d/%d failed: %s",
                attempt,
                SUMMARY_GENERATION_MAX_ATTEMPTS,
                e,
            )
            if attempt < SUMMARY_GENERATION_MAX_ATTEMPTS:
                await _sleep_before_retry(attempt)
                attempt_prompt = _retry_prompt(prompt, str(e))

    fallback = _fallback_summary_from_lines([fs["summary"] for fs in file_summaries if fs.get("summary")])
    if fallback:
        logger.warning("Project summary fell back after retries: %s", last_error)
    else:
        logger.warning("Project summary empty after retries: %s", last_error)
    return fallback


async def generate_project_overview(
    project_name: str,
    file_summaries: list[dict],
    api_key: str,
    base_url: str | None,
    model: str,
    api_format: str = "openai",
    project_description: str | None = None,
    output_language: str | None = None,
    user_id: str | None = None,
) -> dict:
    if not file_summaries:
        return {"summary": "", "color": None}

    lines = "\n".join(
        f"- {fs['file_name']}: {fs['summary']}"
        for fs in file_summaries if fs.get("summary")
    )
    if not lines:
        return {"summary": "", "color": None}

    prompt = PROJECT_OVERVIEW_PROMPT.format(
        project_name=project_name or "(untitled)",
        project_description=project_description or "(none)",
        file_summaries=lines,
        output_language=normalize_output_language(output_language),
    )

    attempt_prompt = prompt
    raw = ""
    last_error: Exception | None = None
    for attempt in range(1, SUMMARY_GENERATION_MAX_ATTEMPTS + 1):
        try:
            raw = await _llm_complete(
                attempt_prompt,
                api_key,
                base_url,
                model,
                api_format=api_format,
                max_tokens=768,
                temperature=0.3,
                user_id=user_id,
            )
            text = _strip_json_response(raw)
            if not text:
                raise ValueError("empty response")
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise TypeError("response JSON must be an object")
            summary = _truncate_summary(str(parsed.get("summary") or ""))
            if not summary:
                raise ValueError("missing non-empty summary")
            color = parsed.get("color")
            if color not in PROJECT_COLORS:
                color = "blue"
            if attempt > 1:
                logger.info(
                    "Project overview recovered on attempt %d/%d",
                    attempt,
                    SUMMARY_GENERATION_MAX_ATTEMPTS,
                )
            return {"summary": summary, "color": color}
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            last_error = e
            logger.warning(
                "Project overview attempt %d/%d failed: %s",
                attempt,
                SUMMARY_GENERATION_MAX_ATTEMPTS,
                e,
            )
        except Exception as e:
            last_error = e
            logger.warning(
                "Project overview attempt %d/%d generation failed: %s",
                attempt,
                SUMMARY_GENERATION_MAX_ATTEMPTS,
                e,
            )

        if attempt < SUMMARY_GENERATION_MAX_ATTEMPTS:
            await _sleep_before_retry(attempt)
            attempt_prompt = _retry_prompt(prompt, str(last_error or "invalid response"))

    raw_text = _strip_json_response(raw) if raw else ""
    fallback = "" if raw_text.startswith(("{", "[")) else _truncate_summary(raw_text)
    fallback = fallback or _fallback_summary_from_lines([fs["summary"] for fs in file_summaries if fs.get("summary")])
    if fallback:
        logger.warning("Project overview fell back after retries: %s", last_error)
    else:
        logger.warning("Project overview empty after retries: %s", last_error)
    return {"summary": fallback, "color": None}
