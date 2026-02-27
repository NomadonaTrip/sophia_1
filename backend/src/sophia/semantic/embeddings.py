"""BGE-M3 singleton embedding service with asyncio.Lock GPU serialization.

Loads the BAAI/bge-m3 model once via singleton pattern and produces
1024-dimensional dense vectors. GPU access is serialized via asyncio.Lock
to stay within the RTX 3080 VRAM budget (NFR24).

For CI/testing, the model is mocked -- see tests/conftest.py.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Module-level singleton -- loaded once, kept resident
_model = None
_lock = asyncio.Lock()

# BGE-M3 dense embedding dimension
EMBEDDING_DIM = 1024


def load_model():
    """Lazy-load BGE-M3 model onto GPU with fp16. ~1.1GB VRAM.

    Returns the same instance on subsequent calls (singleton pattern).
    Called once at startup, kept resident for the lifetime of the process.
    """
    global _model
    if _model is None:
        logger.info("Loading BGE-M3 model (BAAI/bge-m3, fp16)...")
        from FlagEmbedding import BGEM3FlagModel

        _model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
        logger.info("BGE-M3 model loaded successfully.")
    return _model


def unload_model() -> None:
    """Unload model to free VRAM for STT/TTS models (future use).

    Not called in Phase 2 but defines the interface for VRAM management.
    """
    global _model
    if _model is not None:
        logger.info("Unloading BGE-M3 model to free VRAM.")
        _model = None


async def embed(text: str) -> list[float]:
    """Generate 1024-dim dense embedding for a single text.

    Acquires asyncio.Lock before GPU access to serialize concurrent calls.
    Runs model.encode() in an executor thread to avoid blocking the event loop.
    ~50ms on RTX 3080.

    Args:
        text: The text to embed.

    Returns:
        1024-dimensional float vector.
    """
    async with _lock:
        model = load_model()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: model.encode([text])["dense_vecs"][0].tolist(),
        )
        return result


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Batch embed multiple texts for bulk operations (re-index, initial load).

    Same asyncio.Lock serialization as embed(). Processes all texts in a
    single model.encode() call for efficiency.

    Args:
        texts: List of texts to embed.

    Returns:
        List of 1024-dimensional float vectors, one per input text.
    """
    if not texts:
        return []
    async with _lock:
        model = load_model()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: [v.tolist() for v in model.encode(texts)["dense_vecs"]],
        )
        return result
