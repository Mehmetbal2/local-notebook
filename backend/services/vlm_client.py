import asyncio
import base64
import logging
import os
from typing import Optional

import httpx

import config
from utils.errors import UserFacingError
from utils.i18n import msg as ui_msg

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


# Largest image sent to the vision model. The file is read whole and sent base64 inside a
# JSON body (about 2.7 copies in memory), so the general upload limit is far too high here.
VLM_MAX_IMAGE_MB = _env_int("VLM_MAX_IMAGE_MB", 20)


async def resolve_vlm_config() -> tuple[str, str, str]:
    api_key = await config.get_setting("vlm_api_key", "")
    base_url = await config.get_setting("vlm_base_url", "")
    model = await config.get_setting("vlm_model", "")
    return api_key or "", base_url or "", model or ""


def encode_image_to_base64(image_path: str) -> str:
    size = os.path.getsize(image_path)
    if size > VLM_MAX_IMAGE_MB * 1024 * 1024:
        raise UserFacingError(
            ui_msg("image_too_large", size=max(1, size // (1024 * 1024)), limit=VLM_MAX_IMAGE_MB)
        )
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read(VLM_MAX_IMAGE_MB * 1024 * 1024 + 1)).decode("utf-8")


def get_image_mime_type(image_path: str) -> str:
    ext = image_path.lower().split(".")[-1] if "." in image_path else ""
    mime_types = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
        "bmp": "image/bmp",
    }
    return mime_types.get(ext, "image/jpeg")


async def describe_image(
    image_path: str,
    prompt: Optional[str] = None,
    timeout: float = 60.0,
) -> tuple[str, str]:
    api_key, base_url, model = await resolve_vlm_config()

    if not api_key:
        raise RuntimeError("VLM API key is not configured. Configure VLM in Settings.")
    if not base_url:
        raise RuntimeError("VLM base URL is not configured.")
    if not model:
        raise RuntimeError("VLM model is not configured.")

    if prompt is None:
        prompt = (
            "Describe this image in English. Include:\n"
            "1. The main subject and overall content.\n"
            "2. Key visual elements such as objects, people, scenes, text, or charts.\n"
            "3. The overall style and atmosphere.\n"
            "Be detailed but concise."
        )

    base64_image = await asyncio.to_thread(encode_image_to_base64, image_path)
    mime_type = get_image_mime_type(image_path)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}"
                        },
                    },
                ],
            }
        ],
        "max_tokens": 1000,
    }

    target_url = base_url.strip().rstrip("/")
    if not target_url.endswith("/chat/completions"):
        target_url = f"{target_url}/chat/completions"

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(target_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            if "choices" in data and len(data["choices"]) > 0:
                description = data["choices"][0]["message"]["content"]
                return description.strip(), model
            else:
                raise RuntimeError(f"Unexpected VLM response format: {data}")

        except httpx.HTTPStatusError as e:
            error_msg = f"VLM API error: {e.response.status_code}"
            try:
                error_data = e.response.json()
                if "error" in error_data:
                    error_msg += f" - {error_data['error'].get('message', '')}"
            except Exception:
                pass
            raise RuntimeError(error_msg)
        except Exception as e:
            raise RuntimeError(f"VLM call failed: {e}")
