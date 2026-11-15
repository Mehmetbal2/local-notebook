from typing import Literal

from kosong.chat_provider import ChatProvider
from kosong.contrib.chat_provider.anthropic import Anthropic
from kosong.contrib.chat_provider.openai_legacy import OpenAILegacy


LLM_API_FORMAT_OPENAI: Literal["openai"] = "openai"
LLM_API_FORMAT_ANTHROPIC: Literal["anthropic"] = "anthropic"
LLMApiFormat = Literal["openai", "anthropic"]


def normalize_llm_api_format(value: str | None) -> LLMApiFormat:
    normalized = (value or "").strip().lower().replace("-", "_")
    if normalized in {"anthropic", "anthropic_messages", "claude", "claude_messages"}:
        return LLM_API_FORMAT_ANTHROPIC
    return LLM_API_FORMAT_OPENAI


def normalize_openai_base_url(base_url: str | None) -> str | None:
    if not base_url:
        return None
    normalized = base_url.strip().rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].rstrip("/")
            break
    return normalized or None


def normalize_anthropic_base_url(base_url: str | None) -> str | None:
    if not base_url:
        return None
    normalized = base_url.strip().rstrip("/")
    for suffix in ("/v1/messages", "/messages", "/v1"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].rstrip("/")
            break
    return normalized or None


def create_llm_chat_provider(
    *,
    api_key: str,
    base_url: str | None,
    model: str,
    api_format: str | None = None,
    max_tokens: int = 4000,
    temperature: float | None = None,
    stream: bool = True,
) -> ChatProvider:
    generation_kwargs: dict = {"max_tokens": max_tokens}
    if temperature is not None:
        generation_kwargs["temperature"] = temperature

    if normalize_llm_api_format(api_format) == LLM_API_FORMAT_ANTHROPIC:
        provider = Anthropic(
            model=model,
            api_key=api_key,
            base_url=normalize_anthropic_base_url(base_url),
            stream=stream,
            default_max_tokens=max_tokens,
            prompt_cache=False,
        )
        return provider.with_generation_kwargs(
            beta_features=[],
            **generation_kwargs,
        )

    provider = OpenAILegacy(
        model=model,
        api_key=api_key,
        base_url=normalize_openai_base_url(base_url),
        stream=stream,
        reasoning_key="reasoning_content",
    )
    return provider.with_generation_kwargs(**generation_kwargs)


async def complete_text(
    prompt: str,
    *,
    system_prompt: str,
    user_id: str | None = None,
    max_tokens: int = 2000,
    timeout: float = 60.0,
    easy_task: bool = True,
    thinking: bool = False,
    stream: bool = False,
) -> str:
    """One quick, non-streaming model call that returns plain text ("" on failure).

    Reasoning models (the configured DeepSeek one among them) otherwise spend the
    whole token budget thinking and return no answer, so thinking is switched off.
    A server that refuses that switch is retried once without it."""
    import asyncio
    import logging

    import config
    import kosong
    from kosong.message import Message as KosongMessage
    from kosong.tooling.simple import SimpleToolset

    log = logging.getLogger("llm_provider")
    if easy_task:
        api_key, base_url, model, api_format = await config.resolve_easy_task_llm_provider_config()
    else:
        api_key, base_url, model, api_format = await config.resolve_llm_provider_config()
    if not api_key or not model:
        return ""

    def provider(no_thinking: bool):
        chat_provider = create_llm_chat_provider(
            model=model,
            api_key=api_key,
            base_url=base_url,
            api_format=api_format,
            max_tokens=max_tokens,
            temperature=0,
            # Long answers stream: the SDK gives up on a non-streaming request after 10 minutes.
            stream=stream,
        )
        if no_thinking:
            if isinstance(chat_provider, Anthropic):
                chat_provider = chat_provider.with_thinking("off")
            else:
                chat_provider = chat_provider.with_generation_kwargs(
                    extra_body={"thinking": {"type": "disabled"}, "enable_thinking": False}
                )
        return chat_provider

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last_error: Exception | None = None
    # thinking=True leaves the model's reasoning on (slower, needs a larger max_tokens).
    for no_thinking in ((False,) if thinking else (True, False)):
        remaining = deadline - loop.time()
        if remaining <= 1:
            break
        # Leave time for the second try in case the server rejects the thinking switch.
        attempt_timeout = min(remaining, timeout * 0.6) if no_thinking else remaining
        label = "off" if no_thinking else "default"
        try:
            result = await asyncio.wait_for(
                kosong.step(
                    chat_provider=provider(no_thinking),
                    system_prompt=system_prompt,
                    toolset=SimpleToolset([]),
                    history=[KosongMessage(role="user", content=prompt)],
                ),
                timeout=attempt_timeout,
            )
        except asyncio.TimeoutError:
            last_error = TimeoutError(f"no answer within {attempt_timeout:.0f}s")
            log.warning(f"model call timed out after {attempt_timeout:.0f}s (thinking {label})")
            continue
        except Exception as exc:
            last_error = exc
            log.warning(f"model call failed (thinking {label}): {type(exc).__name__}: {str(exc)[:300]}")
            continue
        if user_id:
            try:
                from services.usage_service import record_model_usage

                await record_model_usage(user_id=user_id, model=model, usage=result.usage)
            except Exception:
                pass
        return result.message.extract_text() or ""
    log.warning(f"model call failed: {last_error}")
    return ""
