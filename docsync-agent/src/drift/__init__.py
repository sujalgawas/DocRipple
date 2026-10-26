"""Drift module — deterministic documentation-drift detection (no LLM)."""

from src.drift.anchor_parser import (
    extract_explicit_anchors,
    extract_inline_code_tokens,
    parse_markdown,
    parse_markdown_sections,
)
from src.drift.embed_fallback import EmbeddingMatcher, fallback_embed
from src.drift.schemas import DocSectionNode
from src.drift.service import DriftEngineService

__all__ = [
    "DocSectionNode",
    "DriftEngineService",
    "EmbeddingMatcher",
    "extract_explicit_anchors",
    "extract_inline_code_tokens",
    "fallback_embed",
    "parse_markdown",
    "parse_markdown_sections",
]
