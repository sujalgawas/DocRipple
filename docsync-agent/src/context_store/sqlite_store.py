"""SqliteContextStore — aiosqlite-backed persistence implementing ContextStoreProtocol.

Single class with all persistence methods: delivery deduplication, code-doc edge
graph CRUD, embedding cache, run traces, and orchestrator publish-result storage.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite

from src.context_store.exceptions import DatabaseNotInitializedError
from src.context_store.models import SCHEMA_SQL

if TYPE_CHECKING:
    from src.contracts.schemas import (
        CodeDocEdge,
        DocStyleSkill,
        MemoryNode,
        RepoMemoryMap,
    )
    from src.orchestrator.schemas import EvidenceRow, PublishResult

logger = logging.getLogger(__name__)


def _resolve_writable_db_path(db_path: str) -> str:
    if not db_path or db_path == ":memory:" or db_path.startswith("file:"):
        return ":memory:"
    p = Path(db_path)
    parent = p.parent if p.is_absolute() else Path.cwd() / p.parent
    # If running on Vercel (/var/task) or parent directory is not writable, force into /tmp
    if os.getenv("VERCEL") or not p.is_absolute() or not os.access(str(parent), os.W_OK):
        p = Path("/tmp") / p.name
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return ":memory:"
    return str(p)


class SqliteContextStore:
    """Persistent, async SQLite store fulfilling ContextStoreProtocol + extensions."""

    def __init__(self, db_path: str = "docsync_context.db") -> None:
        self._db_path = _resolve_writable_db_path(db_path)
        self._conn: aiosqlite.Connection | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Open the database, enable WAL/foreign keys, and run schema migrations."""
        try:
            self._conn = await aiosqlite.connect(self._db_path)
        except sqlite3.OperationalError:
            self._db_path = ":memory:"
            self._conn = await aiosqlite.connect(":memory:")

        self._conn.row_factory = aiosqlite.Row

        try:
            await self._conn.execute("PRAGMA journal_mode=WAL;")
        except sqlite3.OperationalError:
            try:
                await self._conn.execute("PRAGMA journal_mode=MEMORY;")
            except sqlite3.OperationalError:
                pass

        try:
            await self._conn.executescript(SCHEMA_SQL)
        except sqlite3.OperationalError:
            fallback_sql = SCHEMA_SQL.replace(
                "PRAGMA journal_mode = WAL;", "PRAGMA journal_mode = MEMORY;"
            )
            await self._conn.executescript(fallback_sql)

        await self._conn.commit()
        logger.info("SqliteContextStore initialised at %s", self._db_path)

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

    # ── Stage 0: DocStyleSkill persistence ───────────────────────────────

    async def save_style_skill(self, skill: DocStyleSkill) -> None:
        """Persist (or replace) the repository-specific documentation style skill."""
        await self._db.execute(
            """INSERT INTO repo_style_skills
               (repo_full_name, tone_and_voice, heading_conventions_json,
                code_block_rules_json, formatting_patterns_json, skill_markdown,
                generated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (repo_full_name) DO UPDATE SET
                   tone_and_voice = excluded.tone_and_voice,
                   heading_conventions_json = excluded.heading_conventions_json,
                   code_block_rules_json = excluded.code_block_rules_json,
                   formatting_patterns_json = excluded.formatting_patterns_json,
                   skill_markdown = excluded.skill_markdown,
                   generated_at = excluded.generated_at""",
            (
                skill.repo_full_name,
                skill.tone_and_voice,
                json.dumps(skill.heading_conventions),
                json.dumps(skill.code_block_rules),
                json.dumps(skill.formatting_patterns),
                skill.skill_markdown,
                skill.generated_at.isoformat(),
            ),
        )
        await self._db.commit()

    async def get_style_skill(self, repo_full_name: str) -> DocStyleSkill | None:
        """Load a repository's DocStyleSkill, or ``None`` before onboarding."""
        from src.contracts.schemas import DocStyleSkill

        cursor = await self._db.execute(
            "SELECT * FROM repo_style_skills WHERE repo_full_name = ?",
            (repo_full_name,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        try:
            return DocStyleSkill(
                repo_full_name=row["repo_full_name"],
                tone_and_voice=row["tone_and_voice"],
                heading_conventions=json.loads(row["heading_conventions_json"]),
                code_block_rules=json.loads(row["code_block_rules_json"]),
                formatting_patterns=json.loads(row["formatting_patterns_json"]),
                skill_markdown=row["skill_markdown"],
                generated_at=datetime.fromisoformat(row["generated_at"]),
            )
        except (ValueError, TypeError, json.JSONDecodeError):
            logger.warning("Ignoring malformed style skill for %s", repo_full_name)
            return None

    # ── Stage 0: repository memory graph ─────────────────────────────────

    async def save_memory_map(self, memory_map: RepoMemoryMap) -> None:
        """Replace a repository's memory nodes and edges atomically."""
        from src.contracts.schemas import RepoMemoryMap

        memory_map = RepoMemoryMap.model_validate(memory_map)
        repo = memory_map.repo_full_name

        node_rows = [
            (
                repo,
                node.node_id,
                node.node_type,
                node.name,
                node.path,
                node.summary,
                node.metadata_json,
            )
            for node in memory_map.nodes
        ]
        edge_rows = [
            (repo, edge.source_id, edge.target_id, edge.relation)
            for edge in memory_map.edges
        ]

        try:
            await self._db.execute(
                "DELETE FROM repo_memory_edges WHERE repo_full_name = ?", (repo,)
            )
            await self._db.execute(
                "DELETE FROM repo_memory_nodes WHERE repo_full_name = ?", (repo,)
            )

            await self._db.executemany(
                """INSERT OR REPLACE INTO repo_memory_nodes
                   (repo_full_name, node_id, node_type, name, path, summary, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                node_rows,
            )
            await self._db.executemany(
                """INSERT OR REPLACE INTO repo_memory_edges
                   (repo_full_name, source_id, target_id, relation)
                   VALUES (?, ?, ?, ?)""",
                edge_rows,
            )
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise

    async def get_memory_subgraph(
        self,
        repo_full_name: str,
        seed_symbols: list[str],
        max_hops: int = 2,
    ) -> RepoMemoryMap:
        """Traverse both edge directions around matching seed nodes.

        Nodes match a seed when their name, path, node id, symbol suffix, or
        doc-section anchor suffix equals the seed. An empty seed list returns
        the complete memory map for the repository.
        """
        from src.contracts.schemas import MemoryEdge, MemoryNode, RepoMemoryMap

        node_cursor = await self._db.execute(
            "SELECT * FROM repo_memory_nodes WHERE repo_full_name = ? ORDER BY node_id",
            (repo_full_name,),
        )
        node_rows = await node_cursor.fetchall()
        nodes = [
            MemoryNode(
                node_id=row["node_id"],
                repo_full_name=row["repo_full_name"],
                node_type=row["node_type"],
                name=row["name"],
                path=row["path"],
                summary=row["summary"],
                metadata_json=row["metadata_json"],
            )
            for row in node_rows
        ]

        edge_cursor = await self._db.execute(
            """SELECT repo_full_name, source_id, target_id, relation
               FROM repo_memory_edges WHERE repo_full_name = ?
               ORDER BY source_id, target_id, relation""",
            (repo_full_name,),
        )
        edge_rows = await edge_cursor.fetchall()
        edges = [
            MemoryEdge(
                repo_full_name=row["repo_full_name"],
                source_id=row["source_id"],
                target_id=row["target_id"],
                relation=row["relation"],
            )
            for row in edge_rows
        ]

        if not seed_symbols:
            return RepoMemoryMap(
                repo_full_name=repo_full_name,
                nodes=nodes,
                edges=edges,
                updated_at=datetime.now(UTC),
            )

        seeds = {seed.strip() for seed in seed_symbols if seed.strip()}
        seed_ids = {
            node.node_id for node in nodes if _node_matches_seed(node, seeds)
        }

        visited = set(seed_ids)
        frontier = set(seed_ids)
        for _ in range(max(0, max_hops)):
            next_frontier: set[str] = set()
            for edge in edges:
                if edge.source_id in frontier and edge.target_id not in visited:
                    next_frontier.add(edge.target_id)
                if edge.target_id in frontier and edge.source_id not in visited:
                    next_frontier.add(edge.source_id)
            if not next_frontier:
                break
            visited.update(next_frontier)
            frontier = next_frontier

        selected_nodes = [node for node in nodes if node.node_id in visited]
        selected_edges = [
            edge
            for edge in edges
            if edge.source_id in visited and edge.target_id in visited
        ]

        return RepoMemoryMap(
            repo_full_name=repo_full_name,
            nodes=sorted(selected_nodes, key=lambda node: node.node_id),
            edges=sorted(
                selected_edges,
                key=lambda edge: (edge.source_id, edge.target_id, edge.relation),
            ),
            updated_at=datetime.now(UTC),
        )

    async def get_memory_map(self, repo_full_name: str) -> RepoMemoryMap:
        """Return the complete repository memory map."""
        return await self.get_memory_subgraph(repo_full_name, [])

    async def upsert_memory_nodes(self, nodes: list[MemoryNode]) -> None:
        """Insert or update memory nodes without replacing the whole graph."""
        if not nodes:
            return

        rows = [
            (
                node.repo_full_name,
                node.node_id,
                node.node_type,
                node.name,
                node.path,
                node.summary,
                node.metadata_json,
            )
            for node in nodes
        ]
        await self._db.executemany(
            """INSERT INTO repo_memory_nodes
               (repo_full_name, node_id, node_type, name, path, summary, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (repo_full_name, node_id) DO UPDATE SET
                   node_type = excluded.node_type,
                   name = excluded.name,
                   path = excluded.path,
                   summary = excluded.summary,
                   metadata_json = excluded.metadata_json""",
            rows,
        )
        await self._db.commit()

    async def update_memory_nodes(self, nodes: list[MemoryNode]) -> None:
        """Alias for :meth:`upsert_memory_nodes`."""
        await self.upsert_memory_nodes(nodes)

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

    # ── Web API: monitored repositories ─────────────────────────────────

    async def upsert_monitored_repo(
        self,
        repo_full_name: str,
        owner: str,
        name: str,
        *,
        watch_branch: str = "main",
        doc_paths: list[str] | None = None,
        drift_action: str = "open_pr",
        status: str = "listening",
        language: str | None = None,
        webhook_id: int | None = None,
        last_pushed_at: str | None = None,
    ) -> None:
        """Insert or update a repository watched by the web dashboard."""
        doc_paths = doc_paths or ["README.md", "docs/**/*.md"]
        created_at = datetime.now(UTC).isoformat()

        await self._db.execute(
            """INSERT INTO monitored_repos
               (repo_full_name, owner, name, watch_branch, doc_paths_json,
                drift_action, status, language, webhook_id, last_pushed_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (repo_full_name) DO UPDATE SET
                   owner = excluded.owner,
                   name = excluded.name,
                   watch_branch = excluded.watch_branch,
                   doc_paths_json = excluded.doc_paths_json,
                   drift_action = excluded.drift_action,
                   status = excluded.status,
                   language = excluded.language,
                   webhook_id = COALESCE(excluded.webhook_id, monitored_repos.webhook_id),
                   last_pushed_at = COALESCE(
                       excluded.last_pushed_at, monitored_repos.last_pushed_at
                   )""",
            (
                repo_full_name,
                owner,
                name,
                watch_branch,
                json.dumps(doc_paths),
                drift_action,
                status,
                language,
                webhook_id,
                last_pushed_at,
                created_at,
            ),
        )
        await self._db.commit()

    async def get_monitored_repo(self, repo_full_name: str) -> dict | None:
        """Return one monitored repository row with parsed doc paths."""
        cursor = await self._db.execute(
            "SELECT * FROM monitored_repos WHERE repo_full_name = ?",
            (repo_full_name,),
        )
        row = await cursor.fetchone()
        return _monitored_repo_row(row) if row is not None else None

    async def list_monitored_repos(self) -> list[dict]:
        """Return every monitored repository, newest first."""
        cursor = await self._db.execute(
            "SELECT * FROM monitored_repos ORDER BY created_at DESC, repo_full_name"
        )
        rows = await cursor.fetchall()
        return [_monitored_repo_row(row) for row in rows]

    async def delete_monitored_repo(self, repo_full_name: str) -> None:
        """Remove a repository from the dashboard watch list."""
        await self._db.execute(
            "DELETE FROM monitored_repos WHERE repo_full_name = ?",
            (repo_full_name,),
        )
        await self._db.commit()

    async def clear_monitored_repos(self) -> int:
        """Delete every monitored repository and return the removed count."""
        cursor = await self._db.execute("DELETE FROM monitored_repos")
        await self._db.commit()
        return cursor.rowcount

    # ── Web API: activity runs ──────────────────────────────────────────

    async def create_activity_run(
        self,
        delivery_id: str,
        repo_full_name: str,
        *,
        commit_sha: str = "",
        commit_message: str = "",
        author: str = "",
        status: str = "running",
        llm_calls: int = 0,
        diff_preview: dict | str | None = None,
    ) -> None:
        """Insert a new run row when a webhook or manual trigger starts."""
        diff_payload = (
            json.dumps(diff_preview)
            if isinstance(diff_preview, dict)
            else diff_preview
        )
        await self._db.execute(
            """INSERT OR IGNORE INTO activity_runs
               (delivery_id, repo_full_name, commit_sha, commit_message, author,
                status, llm_calls, diff_preview, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                delivery_id,
                repo_full_name,
                commit_sha,
                commit_message,
                author,
                status,
                llm_calls,
                diff_payload,
                datetime.now(UTC).isoformat(),
            ),
        )
        await self._db.commit()

    async def update_activity_run(
        self,
        delivery_id: str,
        *,
        commit_sha: str | None = None,
        commit_message: str | None = None,
        author: str | None = None,
        status: str | None = None,
        llm_calls: int | None = None,
        pr_url: str | None = None,
        pr_number: int | None = None,
        evidence_table_md: str | None = None,
        diff_preview: dict | str | None = None,
    ) -> None:
        """Patch fields on an activity run as it moves through the pipeline."""
        updates: list[str] = []
        params: list[object] = []
        values = {
            "commit_sha": commit_sha,
            "commit_message": commit_message,
            "author": author,
            "status": status,
            "llm_calls": llm_calls,
            "pr_url": pr_url,
            "pr_number": pr_number,
            "evidence_table_md": evidence_table_md,
        }
        for column, value in values.items():
            if value is not None:
                updates.append(f"{column} = ?")
                params.append(value)

        if diff_preview is not None:
            updates.append("diff_preview = ?")
            params.append(
                json.dumps(diff_preview)
                if isinstance(diff_preview, dict)
                else diff_preview
            )

        if not updates:
            return

        params.append(delivery_id)
        await self._db.execute(
            f"UPDATE activity_runs SET {', '.join(updates)} WHERE delivery_id = ?",
            params,
        )
        await self._db.commit()

    async def get_activity_run(self, delivery_id: str) -> dict | None:
        """Return one activity row with its diff preview decoded."""
        cursor = await self._db.execute(
            "SELECT * FROM activity_runs WHERE delivery_id = ?",
            (delivery_id,),
        )
        row = await cursor.fetchone()
        return _activity_run_row(row) if row is not None else None

    async def list_activity_runs(
        self,
        *,
        repo_full_name: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Return activity runs newest first, optionally scoped to a repo."""
        query = "SELECT * FROM activity_runs"
        params: list[object] = []
        if repo_full_name:
            query += " WHERE repo_full_name = ?"
            params.append(repo_full_name)
        query += " ORDER BY created_at DESC, delivery_id DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [_activity_run_row(row) for row in rows]

    async def get_activity_stats(self) -> dict[str, int]:
        """Aggregate dashboard counters from activity runs."""
        week_start = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM activity_runs WHERE created_at >= ?",
            (week_start,),
        )
        runs_this_week = (await cursor.fetchone())[0]

        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM activity_runs "
            "WHERE status = 'no_drift' AND llm_calls = 0"
        )
        skipped_zero_tokens = (await cursor.fetchone())[0]

        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM activity_runs WHERE status = 'merged'"
        )
        prs_merged = (await cursor.fetchone())[0]

        return {
            "runs_this_week": int(runs_this_week),
            "skipped_zero_tokens": int(skipped_zero_tokens),
            "prs_merged": int(prs_merged),
        }

    async def get_run_counts_by_repo(self) -> dict[str, int]:
        """Return activity counts keyed by repository full name."""
        cursor = await self._db.execute(
            "SELECT repo_full_name, COUNT(*) FROM activity_runs GROUP BY repo_full_name"
        )
        rows = await cursor.fetchall()
        return {row[0]: int(row[1]) for row in rows}

    # ── Web API: user settings ──────────────────────────────────────────

    async def get_user_settings(self) -> dict:
        """Return the singleton settings row, creating defaults on first read."""
        await self._db.execute(
            "INSERT OR IGNORE INTO user_settings (id) VALUES (1)"
        )
        await self._db.commit()
        cursor = await self._db.execute("SELECT * FROM user_settings WHERE id = 1")
        row = await cursor.fetchone()
        return dict(row) if row is not None else {}

    async def update_user_settings(
        self,
        *,
        github_username: str | None = None,
        require_reviewer_approval: int | None = None,
        skip_internal_changes: int | None = None,
        email_on_failed_runs: int | None = None,
    ) -> dict:
        """Update the singleton settings row and return the fresh values."""
        await self.get_user_settings()
        updates: list[str] = []
        params: list[object] = []
        values = {
            "github_username": github_username,
            "require_reviewer_approval": require_reviewer_approval,
            "skip_internal_changes": skip_internal_changes,
            "email_on_failed_runs": email_on_failed_runs,
        }
        for column, value in values.items():
            if value is not None:
                updates.append(f"{column} = ?")
                params.append(value)

        if updates:
            await self._db.execute(
                f"UPDATE user_settings SET {', '.join(updates)} WHERE id = 1",
                params,
            )
            await self._db.commit()

        return await self.get_user_settings()

    async def clear_github_username(self) -> None:
        """Clear the stored GitHub username (used by the disconnect action)."""
        await self.get_user_settings()
        await self._db.execute(
            "UPDATE user_settings SET github_username = NULL WHERE id = 1"
        )
        await self._db.commit()

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


def _monitored_repo_row(row: aiosqlite.Row) -> dict:
    """Serialize a monitored_repos row, decoding its JSON doc path list."""
    data = dict(row)
    try:
        doc_paths = json.loads(data.get("doc_paths_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        doc_paths = []
    data["doc_paths"] = doc_paths if isinstance(doc_paths, list) else []
    return data


def _activity_run_row(row: aiosqlite.Row) -> dict:
    """Serialize an activity_runs row, decoding its JSON diff preview."""
    data = dict(row)
    raw_preview = data.get("diff_preview")
    if isinstance(raw_preview, str) and raw_preview:
        try:
            data["diff_preview"] = json.loads(raw_preview)
        except json.JSONDecodeError:
            data["diff_preview"] = None
    else:
        data["diff_preview"] = None
    return data


def _node_matches_seed(node: MemoryNode, seeds: set[str]) -> bool:
    """Return True when a memory node corresponds to any requested seed."""
    if node.name in seeds or node.path in seeds or node.node_id in seeds:
        return True

    suffix_positions = (node.node_id.rfind("::"), node.node_id.rfind("#"))
    return any(
        position >= 0 and node.node_id[position + 2 :] in seeds
        for position in suffix_positions
    )
