"""Local semantic-similarity fallback for documentation sections.

The matcher uses lightweight NumPy TF-IDF vectors by default, which keeps the
Render free tier below its 512 MB memory limit. Set ``EMBEDDING_MODE=fastembed``
to opt in to local ``fastembed`` vectors; the package is imported lazily so the
default path never imports or downloads ONNX weights. No network or LLM calls
are made by this module.
"""

from __future__ import annotations

import itertools
import logging
import re
import threading
from collections import Counter
from collections.abc import Callable
from math import log

import numpy as np

from src.config import settings
from src.drift.schemas import DocSectionNode

logger = logging.getLogger(__name__)

Embedder = Callable[[list[str]], np.ndarray]

DEFAULT_MODEL_NAME = "BAAI/bge-small-en-v1.5"
DEFAULT_SIMILARITY_THRESHOLD = 0.45

_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "with",
    }
)
_SUFFIXES = (
    "ingly",
    "edly",
    "ations",
    "ation",
    "ings",
    "ing",
    "ies",
    "ied",
    "ment",
    "ness",
    "ers",
    "er",
    "ed",
    "es",
    "s",
)

# Small, deterministic concept facets compensate for the fact that a lexical
# fallback cannot learn that "rate limiting" and "throttling/quota" are the same
# documentation topic.  Words are stemmed with the same stemmer used for the
# TF-IDF features, so plural and -ing forms collapse to the same facet.
_CONCEPT_GROUPS: dict[str, tuple[str, ...]] = {
    "rate_limiting": (
        "rate",
        "rates",
        "limit",
        "limits",
        "limiting",
        "throttle",
        "throttles",
        "throttling",
        "quota",
        "quotas",
        "rps",
        "qps",
        "burst",
        "backoff",
        "429",
    ),
    "middleware": (
        "middleware",
        "middlewares",
        "handler",
        "handlers",
        "filter",
        "filters",
        "interceptor",
        "interceptors",
        "decorator",
        "decorators",
    ),
    "authentication": (
        "auth",
        "authentication",
        "authenticate",
        "authorization",
        "token",
        "tokens",
        "oauth",
        "jwt",
        "credential",
        "credentials",
        "signature",
        "signatures",
        "secret",
        "secrets",
        "permission",
        "permissions",
        "scope",
        "scopes",
        "login",
        "logout",
    ),
    "webhook": (
        "webhook",
        "webhooks",
        "callback",
        "callbacks",
        "event",
        "events",
        "payload",
        "payloads",
        "delivery",
        "deliveries",
        "hook",
        "hooks",
    ),
    "configuration": (
        "env",
        "environment",
        "environments",
        "variable",
        "variables",
        "config",
        "configuration",
        "configure",
        "configured",
        "setting",
        "settings",
        "option",
        "options",
        "flag",
        "flags",
    ),
    "database": (
        "database",
        "databases",
        "db",
        "sql",
        "query",
        "queries",
        "storage",
        "store",
        "stores",
        "migration",
        "migrations",
        "table",
        "tables",
        "index",
        "indexes",
        "postgres",
        "postgresql",
        "mysql",
        "sqlite",
    ),
    "users": (
        "user",
        "users",
        "account",
        "accounts",
        "member",
        "members",
        "profile",
        "profiles",
        "customer",
        "customers",
    ),
    "http_api": (
        "api",
        "apis",
        "endpoint",
        "endpoints",
        "route",
        "routes",
        "request",
        "requests",
        "response",
        "responses",
        "http",
        "rest",
        "client",
        "clients",
        "server",
        "servers",
    ),
    "errors": (
        "error",
        "errors",
        "exception",
        "exceptions",
        "failure",
        "failures",
        "fail",
        "failed",
        "retry",
        "retries",
        "status",
        "statuses",
    ),
    "deployment": (
        "deploy",
        "deploys",
        "deployment",
        "deployments",
        "release",
        "releases",
        "publish",
        "publishes",
        "build",
        "builds",
        "ci",
    ),
    "installation": (
        "install",
        "installs",
        "installation",
        "installations",
        "setup",
        "upgrade",
        "upgrades",
    ),
    "cli": (
        "cli",
        "command",
        "commands",
        "terminal",
        "argument",
        "arguments",
        "flag",
        "flags",
        "option",
        "options",
    ),
    "async_tasks": (
        "async",
        "task",
        "tasks",
        "queue",
        "queues",
        "worker",
        "workers",
        "background",
        "job",
        "jobs",
    ),
    "testing": (
        "test",
        "tests",
        "testing",
        "fixture",
        "fixtures",
        "mock",
        "mocks",
        "assert",
        "assertion",
        "assertions",
    ),
    "caching": (
        "cache",
        "caches",
        "caching",
        "cached",
        "redis",
        "ttl",
    ),
}

_FEATURE_WEIGHTS = {
    "word": 3.0,
    "bigram": 1.0,
    "char": 0.5,
    "concept": 20.0,
}


def _stem(word: str) -> str:
    """Apply a tiny, deterministic suffix-stripping stemmer."""
    if len(word) <= 3:
        return word

    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            if suffix in {"ies", "ied"}:
                return f"{word[: -len(suffix)]}y"
            return word[: -len(suffix)]

    # Normalise rate/rating and throttle/throttling style pairs.
    if len(word) > 4 and word.endswith("e"):
        return word[:-1]
    return word


def _build_concept_terms() -> dict[str, tuple[str, ...]]:
    """Map stemmed vocabulary words to deterministic concept labels."""
    mapping: dict[str, set[str]] = {}
    for label, words in _CONCEPT_GROUPS.items():
        for word in words:
            mapping.setdefault(_stem(word), set()).add(f"g:{label}")
    return {stem: tuple(sorted(labels)) for stem, labels in mapping.items()}


_CONCEPT_TERMS = _build_concept_terms()


def _feature_kind(term: str) -> str:
    """Classify a prefixed feature for weighting."""
    if term.startswith("g:"):
        return "concept"
    if term.startswith("c"):
        return "char"
    if term.startswith("b:"):
        return "bigram"
    return "word"


def _tokenize(text: str) -> list[str]:
    """Tokenise text into stemmed words, bigrams, n-grams, and concept facets."""
    normalized = _CAMEL_BOUNDARY_RE.sub(" ", text).lower()
    words = [word for word in _WORD_RE.findall(normalized) if word not in _STOPWORDS]
    stems = [_stem(word) for word in words]

    terms: list[str] = [f"w:{word}" for word in stems]
    terms.extend(f"b:{left}_{right}" for left, right in itertools.pairwise(stems))
    for word in stems:
        if len(word) < 3:
            continue
        padded = f"<{word}>"
        for size in (3, 4, 5):
            if len(padded) <= size:
                continue
            terms.extend(
                f"c{size}:{padded[index : index + size]}"
                for index in range(len(padded) - size + 1)
            )

    for word in stems:
        terms.extend(_CONCEPT_TERMS.get(word, ()))
    return terms


def fallback_embed(texts: list[str]) -> np.ndarray:
    """Embed texts with deterministic TF-IDF and character n-gram features.

    Word, bigram, character n-gram, and concept-facet features are weighted and
    L2-normalised, which makes the dot product of two rows their cosine
    similarity.  Vocabulary ordering is sorted so identical inputs always
    produce identical vectors.
    """
    if not texts:
        return np.zeros((0, 0), dtype=np.float64)

    tokenized = [_tokenize(text) for text in texts]
    document_frequency: Counter[str] = Counter()
    for terms in tokenized:
        document_frequency.update(set(terms))

    vocabulary = sorted(document_frequency)
    if not vocabulary:
        return np.zeros((len(texts), 0), dtype=np.float64)

    column = {term: index for index, term in enumerate(vocabulary)}
    matrix = np.zeros((len(texts), len(vocabulary)), dtype=np.float64)
    total_documents = len(texts)

    for row, terms in enumerate(tokenized):
        counts = Counter(terms)
        for term, count in counts.items():
            kind = _feature_kind(term)
            # Concept facets are already rare by construction; applying IDF
            # would penalise exactly the shared topic we want to reward.
            inverse_document_frequency = (
                1.0
                if kind == "concept"
                else log((1.0 + total_documents) / (1.0 + document_frequency[term]))
                + 1.0
            )
            matrix[row, column[term]] = (
                (1.0 + log(count))
                * inverse_document_frequency
                * _FEATURE_WEIGHTS[kind]
            )

    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    np.divide(matrix, norms, out=matrix, where=norms > 0.0)
    return matrix


def _cosine_similarities(query: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    """Cosine similarity between one query vector and candidate rows."""
    if candidates.size == 0 or query.size == 0:
        return np.zeros(candidates.shape[0], dtype=np.float64)

    query_norm = float(np.linalg.norm(query))
    candidate_norms = np.linalg.norm(candidates, axis=1)
    denominators = candidate_norms * query_norm
    similarities = np.zeros(candidates.shape[0], dtype=np.float64)
    np.divide(candidates @ query, denominators, out=similarities, where=denominators > 0.0)
    return np.clip(similarities, 0.0, 1.0)


def _build_default_embedder() -> Embedder:
    """Return fastembed only when enabled; use TF-IDF on the default path."""
    mode = (settings.EMBEDDING_MODE or "tfidf").strip().lower()
    if mode != "fastembed":
        return fallback_embed

    try:
        from fastembed import TextEmbedding
    except ImportError:
        logger.info(
            "EMBEDDING_MODE=fastembed but fastembed is not installed; "
            "using deterministic TF-IDF fallback"
        )
        return fallback_embed

    try:
        model = TextEmbedding(
            DEFAULT_MODEL_NAME,
            local_files_only=True,
        )
    except Exception as exc:  # noqa: BLE001 - fastembed raises several vendor errors
        logger.warning(
            "fastembed model %s unavailable (%s); using deterministic TF-IDF fallback",
            DEFAULT_MODEL_NAME,
            exc,
        )
        return fallback_embed

    def _embed(texts: list[str]) -> np.ndarray:
        try:
            vectors = list(model.embed(texts))
            matrix = np.asarray(vectors, dtype=np.float64)
            if matrix.ndim != 2 or matrix.shape[0] != len(texts):
                raise ValueError("fastembed returned an unexpected vector shape")
            return matrix
        except Exception:
            logger.warning(
                "fastembed inference failed; using deterministic TF-IDF fallback",
                exc_info=True,
            )
            return fallback_embed(texts)

    return _embed


class EmbeddingMatcher:
    """Cosine-similarity matcher with a pluggable, sync embedder function."""

    def __init__(
        self,
        embedder: Embedder | None = None,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> None:
        if not 0.0 <= similarity_threshold <= 1.0:
            raise ValueError("similarity_threshold must be between 0.0 and 1.0")

        self._embedder = embedder
        self._default_embedder: Embedder | None = None
        self._embedder_lock = threading.Lock()
        self.similarity_threshold = similarity_threshold

    def _resolve_embedder(self) -> Embedder:
        if self._embedder is not None:
            return self._embedder

        with self._embedder_lock:
            if self._default_embedder is None:
                self._default_embedder = _build_default_embedder()
            return self._default_embedder

    def compute_similarities(self, query: str, candidates: list[str]) -> np.ndarray:
        """Return cosine similarities for ``query`` against every candidate."""
        if not candidates:
            return np.zeros(0, dtype=np.float64)

        texts = [query, *candidates]
        embedder = self._resolve_embedder()
        try:
            with self._embedder_lock:
                matrix = np.asarray(embedder(texts), dtype=np.float64)
            if matrix.ndim != 2 or matrix.shape[0] != len(texts):
                raise ValueError("embedder returned an unexpected vector shape")
        except Exception:
            logger.warning(
                "embedder failed; using deterministic TF-IDF fallback",
                exc_info=True,
            )
            matrix = fallback_embed(texts)

        return _cosine_similarities(matrix[0], matrix[1:])

    def match_sections(
        self,
        query: str,
        sections: list[DocSectionNode],
        threshold: float | None = None,
    ) -> list[tuple[DocSectionNode, float]]:
        """Return sections whose similarity is at or above ``threshold``.

        Results are ordered by descending similarity, then by document order so
        the output is deterministic.
        """
        if not sections:
            return []

        effective_threshold = self.similarity_threshold if threshold is None else threshold
        if not 0.0 <= effective_threshold <= 1.0:
            raise ValueError("threshold must be between 0.0 and 1.0")

        scores = self.compute_similarities(
            query,
            [section.raw_markdown for section in sections],
        )
        matches = [
            (section, float(score))
            for section, score in zip(sections, scores)
            if float(score) >= effective_threshold
        ]
        matches.sort(
            key=lambda item: (
                -item[1],
                item[0].doc_path,
                item[0].start_line,
                item[0].heading,
            )
        )
        return matches
