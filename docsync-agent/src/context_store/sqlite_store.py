"""SqliteContextStore — aiosqlite-backed persistence implementing ContextStoreProtocol.

Single class with all persistence methods: delivery deduplication, code-doc edge
graph CRUD, embedding cache, run traces, and orchestrator publish-result storage.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import aiosqlite

from src.context_store.exceptions import DatabaseNotInitializedError
from src.context_store.models import SCHEMA_SQL

if TYPE_CHECKING:
    from src.contracts.schemas import CodeDocEdge
    from src.orchestrator.schemas import EvidenceRow, PublishResult

logger = logging.getLogger(__name__)


class SqliteContextStore:
    """Persistent, async SQLite store fulfilling ContextStoreProtocol + extensions."""

    def __init__(self, db_path: str = "docsync_context.db") -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Open the database, enable WAL/foreign keys, and run schema migrations."""
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA_SQL)
        await self._conn.commit()
        logger.info("SqliteContextStore initialised at %s (WAL mode)", self._db_path)

    async def close(self) -> None:
        """Close the database connection cleanly."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def _db(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise DatabaseNotInitializedError(
                "SqliteContextStore not initialised — call initialize() first"
            )
        return self._conn

    # ── ContextStoreProtocol: delivery deduplication ─────────────────────

    async def check_and_record_delivery(
        self, delivery_id: str, repo_full_name: str
    ) -> bool:
        """Atomically insert a delivery. Returns True only for the first insert."""
        received_at = datetime.now(UTC).isoformat()
        cursor = await self._db.execute(
            "INSERT OR IGNORE INTO webhook_deliveries (delivery_id, repo_full_name, received_at) "
            "VALUES (?, ?, ?)",
            (delivery_id, repo_full_name, received_at),
        )
        await self._db.commit()
        return cursor.rowcount == 1

    # ── ContextStoreProtocol: code-doc edge graph ────────────────────────

    async def get_edges_for_symbols(
        self, repo_full_name: str, symbol_names: list[str]
    ) -> list[CodeDocEdge]:
        """Return all code-doc edges matching repo and symbol names."""
        from src.contracts.schemas import CodeDocEdge

        if not symbol_names:
            return []

        placeholders = ",".join("?" for _ in symbol_names)
        params = [repo_full_name, *symbol_names]
        query = (
            "SELECT repo_full_name, symbol_name, file_path, doc_path, section_heading, anchor_type "
            f"FROM code_doc_edges WHERE repo_full_name = ? AND symbol_name IN ({placeholders})"
        )

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [
            CodeDocEdge(
                repo_full_name=row["repo_full_name"],
                symbol_name=row["symbol_name"],
                file_path=row["file_path"],
                doc_path=row["doc_path"],
                section_heading=row["section_heading"],
                anchor_type=row["anchor_type"],
            )
            for row in rows
        ]

    async def upsert_edges(self, edges: list[CodeDocEdge]) -> None:
        """Batch-insert or update code-doc edges.

        On conflict over the composite PK, updates ``file_path``, ``anchor_type``,
        and ``updated_at`` without creating duplicate rows.
        """
        if not edges:
            return

        updated = datetime.now(UTC).isoformat()
        rows = [
            (
                e.repo_full_name,
                e.symbol_name,
                e.file_path,
                e.doc_path,
                e.section_heading,
                e.anchor_type,
                updated,
            )
            for e in edges
        ]

        await self._db.executemany(
            """INSERT INTO code_doc_edges
               (repo_full_name, symbol_name, file_path, doc_path, section_heading, anchor_type, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (repo_full_name, symbol_name, doc_path, section_heading)
               DO UPDATE SET file_path = excluded.file_path,
                             anchor_type = excluded.anchor_type,
                             updated_at = excluded.updated_at""",
            rows,
        )
        await self._db.commit()

    # ── Run traces: PublishResult persistence ────────────────────────────

    async def save_run_result(
        self,
        delivery_id: str,
        repo_full_name: str,
        result: PublishResult,
        evidence: list[EvidenceRow],
    ) -> None:
        """Persist a completed orchestrator run (PublishResult + evidence)."""
        completed_at = datetime.now(UTC).isoformat()

        # Store both the serialized evidence and the full result so
        # ``get_run_result`` can round-trip every field faithfully.
        payload = {
            "evidence": [e.model_dump() for e in evidence],
            "result": result.model_dump(),
        }
        evidence_json = json.dumps(payload)

        await self._db.execute(
            """INSERT OR REPLACE INTO run_traces
               (delivery_id, repo_full_name, pr_url, pr_number, branch_name,
                evidence_table_md, evidence_json, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                delivery_id,
                repo_full_name,
                result.pr_url or "",
                result.pr_number or 0,
                f"docsync/{delivery_id[:8]}",
                result.evidence_table_md,
                evidence_json,
                completed_at,
            ),
        )
        await self._db.commit()

    async def get_run_result(self, delivery_id: str) -> PublishResult | None:
        """Retrieve a previously saved PublishResult by delivery_id."""
        from src.orchestrator.schemas import PublishResult

        cursor = await self._db.execute(
            "SELECT * FROM run_traces WHERE delivery_id = ?",
            (delivery_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        # Reconstruct the full result from the serialized payload if present.
        try:
            payload = json.loads(row["evidence_json"])
            result_data = payload.get("result")
            if isinstance(result_data, dict):
                return PublishResult.model_validate(result_data)
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

        # Fallback: reconstruct from columns alone.
        return PublishResult(
            delivery_id=row["delivery_id"],
            pr_url=row["pr_url"] or None,
            pr_number=row["pr_number"],
            evidence_table_md=row["evidence_table_md"],
            verification_status="passed",
            error=None,
        )

    # ── Orchestrator-friendly shims ──────────────────────────────────────

    async def save_edges(self, edges: list[CodeDocEdge]) -> None:
        """Alias for upsert_edges — the name expected by OrchestratorContextStoreProtocol."""
        await self.upsert_edges(edges)

    async def save_publish_result(self, result: PublishResult) -> None:
        """Persist a PublishResult directly (no explicit evidence list)."""
        await self.save_run_result(
            delivery_id=result.delivery_id,
            repo_full_name="",  # caller should populate if needed
            result=result,
            evidence=[],
        )

    # ── Embedding cache (bonus) ──────────────────────────────────────────

    async def get_cached_embedding(
        self,
        repo_full_name: str,
        doc_path: str,
        section_heading: str,
        content_hash: str,
    ) -> list[float] | None:
        """Return a cached embedding vector if the content_hash matches.

        Returns ``None`` when no cache entry exists or the hash has changed.
        """
        cursor = await self._db.execute(
            "SELECT content_hash, embedding_json FROM doc_embeddings "
            "WHERE repo_full_name = ? AND doc_path = ? AND section_heading = ?",
            (repo_full_name, doc_path, section_heading),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        if row["content_hash"] != content_hash:
            return None
        return json.loads(row["embedding_json"])

    async def set_cached_embedding(
        self,
        repo_full_name: str,
        doc_path: str,
        section_heading: str,
        content_hash: str,
        embedding: list[float],
    ) -> None:
        """Store or refresh a section embedding cache entry."""
        embedding_json = json.dumps(embedding)
        await self._db.execute(
            """INSERT OR REPLACE INTO doc_embeddings
               (repo_full_name, doc_path, section_heading, content_hash, embedding_json)
               VALUES (?, ?, ?, ?, ?)""",
            (repo_full_name, doc_path, section_heading, content_hash, embedding_json),
        )
        await self._db.commit()