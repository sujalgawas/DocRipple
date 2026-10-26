"""ContextStore module — SQLite WAL persistence layer.

Exports the core ``SqliteContextStore`` class and factory helpers.
"""

from src.context_store.service import create_context_store
from src.context_store.sqlite_store import SqliteContextStore

__all__ = ["SqliteContextStore", "create_context_store"]