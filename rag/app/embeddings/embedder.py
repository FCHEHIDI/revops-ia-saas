import asyncio
import logging
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Wraps sentence-transformers to generate embeddings.

    The model is loaded once at startup and reused across requests.
    Inference runs in a thread-pool executor to avoid blocking the event loop.
    """

    def __init__(self, model_name: str, batch_size: int = 32) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._model: Any = None

    def _load_model(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import]

            logger.info("Loading embedding model '%s' …", self.model_name)
            self._model = SentenceTransformer(self.model_name)
            logger.info("Embedding model loaded (dim=%d)", self.dimensions)
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed. "
                "Add it to requirements.txt and rebuild."
            ) from exc

    @property
    def dimensions(self) -> int:
        if self._model is None:
            self._load_model()
        return int(self._model.get_sentence_embedding_dimension())

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous embedding — runs in thread pool."""
        self._load_model()
        vectors = self._model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return [v.tolist() for v in vectors]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Async embedding — runs synchronous inference in thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._embed_sync, texts)

    async def embed_one(self, text: str) -> list[float]:
        results = await self.embed([text])
        return results[0]

    def load(self) -> None:
        """Eagerly load the model (call at app startup)."""
        self._load_model()


@lru_cache(maxsize=1)
def get_embedder(model_name: str, batch_size: int) -> EmbeddingService:
    """Singleton factory — one model instance per process."""
    svc = EmbeddingService(model_name, batch_size)
    svc.load()
    return svc
