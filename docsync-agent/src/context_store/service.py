"""ContextStore service — implements ContextStoreProtocol on top of SqliteStore."""

import logging

from src.contracts.schemas import CodeDocEdge
from src.context_store.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)

# Singleton store instance
_store = SqliteStore()

# Exported alias for use by other modules
context_store = _store


async def init_context_store(db_path: str = "docsync.db") -> SqliteStore:
    """Initialize and connect the global context store."""
    global _store
    _store = SqliteStore(db_path)
    await _store.connect()
    return _store


async def shutdown_context_store() -> None:
    """Close the global context store connection."""
    await _store.close()