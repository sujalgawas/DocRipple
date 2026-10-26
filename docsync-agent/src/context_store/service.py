"""Thin factory / convenience module for ContextStore instantiation."""

import logging

from src.context_store.config import ContextStoreConfig
from src.context_store.sqlite_store import SqliteContextStore

logger = logging.getLogger(__name__)


async def create_context_store(db_path: str | None = None) -> SqliteContextStore:
    """Factory: create and initialise a SqliteContextStore.

    Uses ``ContextStoreConfig`` when ``db_path`` is not provided.
    """
    path = db_path or ContextStoreConfig().sqlite_db_path
    store = SqliteContextStore(path)
    await store.initialize()
    return store