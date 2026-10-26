"""SQLite DDL — schema definitions for webhook_deliveries, code_doc_edges, doc_embeddings, run_traces."""

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS webhook_deliveries (
        delivery_id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        repo_full_name TEXT NOT NULL,
        received_at TEXT NOT NULL DEFAULT (datetime('now')),
        status TEXT NOT NULL DEFAULT 'pending'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS code_doc_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol_name TEXT NOT NULL,
        doc_path TEXT NOT NULL,
        doc_section TEXT NOT NULL,
        anchor TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(symbol_name, doc_path, doc_section)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS doc_embeddings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_path TEXT NOT NULL,
        section TEXT NOT NULL,
        embedding BLOB,
        model_name TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_traces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT NOT NULL,
        step TEXT NOT NULL,
        payload TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_edges_symbol ON code_doc_edges(symbol_name)",
    "CREATE INDEX IF NOT EXISTS idx_traces_job ON run_traces(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_embeddings_doc ON doc_embeddings(doc_path, section)",
]