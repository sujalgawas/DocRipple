"""Shared async fixtures and in-memory SQLite ContextStore for tests."""

import aiosqlite
import pytest

from src.context_store.models import DDL_STATEMENTS


@pytest.fixture
async def db() -> aiosqlite.Connection:
    """In-memory SQLite database with full schema."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    for ddl in DDL_STATEMENTS:
        await conn.execute(ddl)
    await conn.commit()
    yield conn
    await conn.close()