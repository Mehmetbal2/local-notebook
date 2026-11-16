import os
from typing import Optional
from pydantic import BaseModel


SETTING_KEYS = {
    "llm_api_key",
    "llm_base_url",
    "llm_model",
    "llm_api_format",
    "easy_task_llm",
    "easy_task_llm_verified",
    "vlm_api_key",
    "vlm_base_url",
    "vlm_model",
    "embedding_source",
    "embedding_model",
    "embedding_api_key",
    "embedding_base_url",
    "embedding_local_url",
    "ocr_base_url",
    "ocr_api_key",
    "ocr_model",
    "pdf_engine",
    "funasr_base_url",
    "funasr_api_key",
    "funasr_model",
    "funasr_verified",
    "tts_base_url",
    "tts_api_key",
    "tts_model",
    "tts_voice",
    "tts_verified",
    "searxng_base_url",
    "llm_verified",
    "vlm_verified",
    "embedding_verified",
    "ocr_verified",
    "web_search_verified",
}


SETTING_DEFAULTS = {
    "llm_api_format": "openai",
    "embedding_source": "local",
    "embedding_local_url": f"http://127.0.0.1:{os.getenv('EMBEDDING_PORT', '8001')}",
    "tts_voice": "deniz",
    # auto: local PyMuPDF when the PDF has a text layer, the OCR service otherwise
    "pdf_engine": "auto",
    "searxng_base_url": "http://127.0.0.1:8888",
}


class SettingsUpdate(BaseModel):
    settings: dict[str, Optional[str]]
    force: bool = False


class SettingsResponse(BaseModel):
    settings: dict[str, Optional[str]]
