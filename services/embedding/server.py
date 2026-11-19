"""
Local Notebook Embedding Service
=================================
OpenAI-compatible embedding server backed by sentence-transformers.

Startup:
    python server.py                        # auto-detect device
    MODEL=../../local-notebook-data/models/bge-m3 python server.py
    uvicorn server:app --port 8001

Device priority: CUDA > MPS (Apple Silicon) > CPU
"""
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Union

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = Path(os.getenv("LOCAL_NOTEBOOK_DATA_DIR", _PROJECT_ROOT / "local-notebook-data")).resolve()
_MODELS_DIR = _DATA_DIR / "models"
os.environ.setdefault("HF_HOME", str(_MODELS_DIR / "huggingface"))
os.environ.setdefault("TORCH_HOME", str(_MODELS_DIR / "torch"))

import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger("embedding-server")

# ── Config ────────────────────────────────────────────────────────────────────

_DEFAULT_MODEL_DIR = _MODELS_DIR / "bge-m3"
MODEL_NAME = os.getenv("MODEL", str(_DEFAULT_MODEL_DIR))
PORT = int(os.getenv("PORT", "8001"))
MAX_BATCH = int(os.getenv("MAX_BATCH", "64"))


def _detect_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


# ── App state ─────────────────────────────────────────────────────────────────

model: SentenceTransformer | None = None
device: str = "cpu"


def _embedding_dim(m: SentenceTransformer) -> int | None:
    fn = getattr(m, "get_embedding_dimension", None) or getattr(m, "get_sentence_embedding_dimension", None)
    return fn() if callable(fn) else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model, device
    model_path = Path(MODEL_NAME)
    if (MODEL_NAME == str(_DEFAULT_MODEL_DIR) or MODEL_NAME.startswith(("/", "./", "../"))) and not model_path.exists():
        raise RuntimeError(f"Local embedding model directory not found: {model_path.resolve()}")
    device = _detect_device()
    logger.info(f"Loading model '{MODEL_NAME}' on device '{device}' ...")
    t0 = time.time()
    model = SentenceTransformer(MODEL_NAME, device=device)
    logger.info(f"Model loaded in {time.time() - t0:.1f}s  |  dim={_embedding_dim(model)}")
    yield
    model = None


app = FastAPI(
    title="Local Notebook Embedding Service",
    description="OpenAI-compatible /embeddings endpoint backed by sentence-transformers",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Schemas (OpenAI compatible) ───────────────────────────────────────────────

class EmbeddingRequest(BaseModel):
    input: Union[str, list[str]]
    model: str | None = None     # accepted but ignored — server uses MODEL_NAME


class EmbeddingObject(BaseModel):
    object: str = "embedding"
    index: int
    embedding: list[float]


class UsageInfo(BaseModel):
    prompt_tokens: int
    total_tokens: int


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: list[EmbeddingObject]
    model: str
    usage: UsageInfo


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "device": device,
        "dim": _embedding_dim(model) if model else None,
    }


@app.post("/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(req: EmbeddingRequest) -> EmbeddingResponse:
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    # Normalise to list
    texts: list[str] = [req.input] if isinstance(req.input, str) else req.input

    if not texts:
        raise HTTPException(status_code=422, detail="input must not be empty")

    # Batch encode — run in sync (sentence-transformers releases the GIL)
    import asyncio
    loop = asyncio.get_event_loop()
    vectors = await loop.run_in_executor(
        None,
        lambda: model.encode(
            texts,
            batch_size=MAX_BATCH,
            show_progress_bar=False,
            normalize_embeddings=True,
        ).tolist(),
    )

    token_count = sum(len(t.split()) for t in texts)   # rough estimate

    return EmbeddingResponse(
        model=MODEL_NAME,
        data=[EmbeddingObject(index=i, embedding=v) for i, v in enumerate(vectors)],
        usage=UsageInfo(prompt_tokens=token_count, total_tokens=token_count),
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=False)
