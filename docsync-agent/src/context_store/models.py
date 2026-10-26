"""SQLite DDL — 4-table schema for webhook_deliveries, code_doc_edges, doc_embeddings, run_traces.

``SCHEMA_SQL`` is applied on ``initialize()`` via ``executescript`` with
``PRAGMA journal_mode=WAL`` and ``PRAGMA foreign_keys=ON``.
``DDL_STATEMENTS`` is kept as a list of individual statements for backward
compatibility (e.g. the shared ``tests/conftest.py`` fixture).
"""

_DDL_WEBHOOK_DELIVERIES = """
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    delivery_id        TEXT PRIMARY KEY,
    repo_full_name     TEXT NOT NULL,
    received_at        TEXT NOT NULL
);
"""

_DDL_CODE_DOC_EDGES = """
CREATE TABLE IF NOT EXISTS code_doc_edges (
    repo_full_name      TEXT NOT NULL,
    symbol_name         TEXT NOT NULL,
    file_path           TEXT NOT NULL,
    doc_path            TEXT NOT NULL,
    section_heading     TEXT NOT NULL,
    anchor_type         TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    PRIMARY KEY (repo_full_name, symbol_name, doc_path, section_heading)
);
"""

_DDL_DOC_EMBEDDINGS = """
CREATE TABLE IF NOT EXISTS doc_embeddings (
    repo_full_name      TEXT NOT NULL,
    doc_path            TEXT NOT NULL,
    section_heading     TEXT NOT NULL,
    content_hash        TEXT NOT NULL,
    embedding_json      TEXT NOT NULL,
    PRIMARY KEY (repo_full_name, doc_path, section_heading)
);
"""

_DDL_RUN_TRACES = """
CREATE TABLE IF NOT EXISTS run_traces (
    delivery_id         TEXT PRIMARY KEY,
    repo_full_name      TEXT NOT NULL,
    pr_url              TEXT NOT NULL,
    pr_number           INTEGER NOT NULL,
    branch_name         TEXT NOT NULL,
    evidence_table_md   TEXT NOT NULL,
    evidence_json       TEXT NOT NULL,
    completed_at        TEXT NOT NULL
);
"""

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_edges_symbol
    ON code_doc_edges (repo_full_name, symbol_name);

CREATE INDEX IF NOT EXISTS idx_edges_doc
    ON code_doc_edges (repo_full_name, doc_path);

CREATE INDEX IF NOT EXISTS idx_embeddings_lookup
    ON doc_embeddings (repo_full_name, doc_path, section_heading);
"""

# Individual CREATE TABLE statements (for statement-by-statement execution).
DDL_STATEMENTS: list[str] = [
    _DDL_WEBHOOK_DELIVERIES,
    _DDL_CODE_DOC_EDGES,
    _DDL_DOC_EMBEDDINGS,
    _DDL_RUN_TRACES,
]

# Full script (pragmas + tables + indexes) applied via executescript.
SCHEMA_SQL = "\n\n".join(
    [
        "PRAGMA journal_mode = WAL;",
        "PRAGMA foreign_keys = ON;",
        *[stmt.strip() for stmt in DDL_STATEMENTS],
        _INDEXES.strip(),
    ]
)