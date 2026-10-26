"""Local fastembed cosine similarity fallback for unanchored doc sections."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Lazily imported to avoid blocking startup
_embed_model: Any = None


def _get_model() -> Any:
    global _embed_model
    if _embed_model is None:
        try:
            from fastembed import TextEmbedding

            _embed_model = TextEmbedding()  # default: BAAI/bge-small-en-v1.5
        except Exception:
            logger.warning("fastembed not available; embedding fallback disabled")
            return None
    return _embed_model


async def cosine_similarity(text_a: str, text_b: str) -> float:
    """Compute cosine similarity between two text snippets using fastembed."""
    model = _get_model()
    if model is None:
        return 0.0

    embeddings = list(model.embed([text_a, text_b]))
    if len(embeddings) != 2:
        return 0.0

    vec_a = embeddings[0]
    vec_b = embeddings[1]

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def find_best_match(query: str, candidates: list[str], threshold: float = 0.5) -> tuple[str | None, float]:
    """Return the best matching candidate and its similarity score."""
    best_score = 0.0
    best_candidate: str | None = None
    for candidate in candidates:
        score = await cosine_similarity(query, candidate)
        if score > best_score:
            best_score = score
            best_candidate = candidate
    if best_score < threshold:
        return None, best_score
    return best_candidate, best_score