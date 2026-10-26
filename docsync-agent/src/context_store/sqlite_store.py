"""Low-level aiosqlite queries with WAL mode transactions."""

import logging
from typing import Optional

import aiosqlite

from src.context_store.models import DDL_STATEMENTS
from src.context_store.exceptions import StorageError
from src.contracts.schemas import CodeDocEdge

logger = logging.getLogger(__name__)


class SqliteStore:
    """aiosqlite wrapper with WAL mode and schema management."""

    def __init__(self, db_path: str = "docsync.db"):
        self._db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Open connection in WAL mode and run migrations."""
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        for ddl in DDL_STATEMENTS:
            await self._conn.execute(ddl)
        await self._conn.commit()
        logger.info("SqliteStore connected to %s (WAL mode)", self._db_path)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise StorageError("SqliteStore not connected")
        return self._conn

    async def insert_delivery(self, delivery_id: str, job_id: str, repo_full_name: str) -> bool:
        """Insert a webhook delivery. Returns False if delivery_id already exists."""
        try:
            await self.conn.execute(
                "INSERT INTO webhook_deliveries (delivery_id, job_id, repo_full_name) VALUES (?, ?, ?)",
                (delivery_id, job_id, repo_full_name),
            )
            await self.conn.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def upsert_edge(self, edge: CodeDocEdge) -> None:
        """Insert or update a code-document edge."""
        await self.conn.execute(
            """INSERT OR REPLACE INTO code_doc_edges (symbol_name, doc_path, doc_section, anchor)
               VALUES (?, ?, ?, ?)""",
            (edge.symbol_name, edge.doc_path, edge.doc_section, edge.anchor),
        )
        await self.conn.commit()

    async def get_edges_by_symbol(self, symbol_name: str) -> list[CodeDocEdge]:
        """Retrieve all doc edges for a given symbol."""
        cursor = await self.conn.execute(
            "SELECT symbol_name, doc_path, doc_section, anchor FROM code_doc_edges WHERE symbol_name = ?",
            (symbol_name,),
        )
        rows = await cursor.fetchall()
        return [
            CodeDocEdge(
                symbol_name=row["symbol_name"],
                doc_path=row["doc_path"],
                doc_section=row["doc_section"],
                anchor=row["anchor"],
            )
            for row in rows
        ]

    async def insert_trace(self, job_id: str, step: str, payload: str) -> None:
        """Record a run trace entry."""
        await self.conn.execute(
            "INSERT INTO run_traces (job_id, step, payload) VALUES (?, ?, ?)",
            (job_id, step, payload),
        )
        await self.conn.commit()