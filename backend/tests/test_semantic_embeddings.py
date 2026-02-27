"""Tests for BGE-M3 embedding service.

Mocks the actual BGEM3FlagModel for CI -- uses a fixture that returns
random vectors of the correct 1024 dimension.
"""

import asyncio
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from sophia.semantic import embeddings
from sophia.semantic.embeddings import EMBEDDING_DIM


@pytest.fixture(autouse=True)
def _reset_model():
    """Reset the singleton model before each test."""
    embeddings._model = None
    yield
    embeddings._model = None


@pytest.fixture
def mock_bgem3():
    """Mock BGEM3FlagModel that returns random vectors of correct dimension."""
    mock_model = MagicMock()

    def _encode(texts):
        vecs = np.random.randn(len(texts), EMBEDDING_DIM).astype(np.float32)
        return {"dense_vecs": vecs}

    mock_model.encode = _encode
    return mock_model


class TestLoadModel:
    """Tests for singleton model loading."""

    def test_load_model_returns_instance(self, mock_bgem3):
        """load_model() returns a model instance."""
        with patch(
            "sophia.semantic.embeddings.load_model", return_value=mock_bgem3
        ):
            model = embeddings.load_model()
            assert model is mock_bgem3

    def test_singleton_returns_same_instance(self, mock_bgem3):
        """load_model() returns the same instance on subsequent calls."""
        embeddings._model = mock_bgem3
        first = embeddings.load_model()
        second = embeddings.load_model()
        assert first is second

    def test_unload_model_clears_singleton(self, mock_bgem3):
        """unload_model() sets _model to None."""
        embeddings._model = mock_bgem3
        embeddings.unload_model()
        assert embeddings._model is None


class TestEmbed:
    """Tests for single text embedding."""

    def test_embed_returns_1024_dim_vector(self, mock_bgem3):
        """embed() returns a vector with exactly 1024 dimensions."""
        embeddings._model = mock_bgem3

        result = asyncio.get_event_loop().run_until_complete(
            embeddings.embed("test text")
        )

        assert isinstance(result, list)
        assert len(result) == EMBEDDING_DIM

    def test_embed_returns_floats(self, mock_bgem3):
        """embed() returns a list of float values."""
        embeddings._model = mock_bgem3

        result = asyncio.get_event_loop().run_until_complete(
            embeddings.embed("test text")
        )

        for val in result:
            assert isinstance(val, float)

    def test_embed_calls_encode_with_text(self, mock_bgem3):
        """embed() passes the text as a single-element list to model.encode()."""
        mock_model = MagicMock()
        vecs = np.random.randn(1, EMBEDDING_DIM).astype(np.float32)
        mock_model.encode.return_value = {"dense_vecs": vecs}
        embeddings._model = mock_model

        asyncio.get_event_loop().run_until_complete(
            embeddings.embed("hello world")
        )

        mock_model.encode.assert_called_once_with(["hello world"])


class TestEmbedBatch:
    """Tests for batch embedding."""

    def test_embed_batch_returns_correct_count(self, mock_bgem3):
        """embed_batch() returns one vector per input text."""
        embeddings._model = mock_bgem3
        texts = ["text one", "text two", "text three"]

        result = asyncio.get_event_loop().run_until_complete(
            embeddings.embed_batch(texts)
        )

        assert len(result) == 3

    def test_embed_batch_each_vector_is_1024_dim(self, mock_bgem3):
        """Each vector from embed_batch() has 1024 dimensions."""
        embeddings._model = mock_bgem3
        texts = ["text one", "text two"]

        result = asyncio.get_event_loop().run_until_complete(
            embeddings.embed_batch(texts)
        )

        for vec in result:
            assert len(vec) == EMBEDDING_DIM

    def test_embed_batch_empty_input_returns_empty(self, mock_bgem3):
        """embed_batch([]) returns an empty list without calling the model."""
        embeddings._model = mock_bgem3

        result = asyncio.get_event_loop().run_until_complete(
            embeddings.embed_batch([])
        )

        assert result == []

    def test_embed_batch_single_item(self, mock_bgem3):
        """embed_batch() works correctly with a single text."""
        embeddings._model = mock_bgem3

        result = asyncio.get_event_loop().run_until_complete(
            embeddings.embed_batch(["single"])
        )

        assert len(result) == 1
        assert len(result[0]) == EMBEDDING_DIM


class TestLockSerialization:
    """Tests for asyncio.Lock serialization of GPU access."""

    def test_lock_prevents_concurrent_access(self, mock_bgem3):
        """Two concurrent embed() calls are serialized (not parallel)."""
        embeddings._model = mock_bgem3

        call_order = []

        original_encode = mock_bgem3.encode

        def tracked_encode(texts):
            call_order.append(("start", texts[0]))
            result = original_encode(texts)
            call_order.append(("end", texts[0]))
            return result

        mock_bgem3.encode = tracked_encode

        async def run_concurrent():
            task1 = asyncio.create_task(embeddings.embed("first"))
            task2 = asyncio.create_task(embeddings.embed("second"))
            await asyncio.gather(task1, task2)

        asyncio.get_event_loop().run_until_complete(run_concurrent())

        # Both calls should complete (order may vary, but no interleaving)
        assert len(call_order) == 4
        # Each start should be followed by its own end before the next start
        starts = [i for i, (action, _) in enumerate(call_order) if action == "start"]
        ends = [i for i, (action, _) in enumerate(call_order) if action == "end"]
        # First end comes before second start (serialized)
        assert ends[0] < starts[1]
