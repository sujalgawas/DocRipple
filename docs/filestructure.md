# File Structure

```text
docsync-agent/
├── pyproject.toml
├── skills.md                    # Root agent ground rules (symlinked as AGENTS.md / CLAUDE.md)
├── src/
│   ├── main.py                  # FastAPI lifespan, router mounting, background worker startup
│   ├── config.py                # Global BaseSettings (env vars)
│   ├── contracts/               # FROZEN BEFORE PARALLEL RUNS (Read-only for module agents)
│   │   ├── __init__.py
│   │   ├── schemas.py           # WebhookJob, ChangedSymbol, ChangeReport, CodeDocEdge, DriftReport, EvidenceRow, PublishResult
│   │   └── protocols.py         # ContextStoreProtocol, AnalyzerProtocol, DriftEngineProtocol
│   ├── ingest/                  # Agent 1 owns src/ingest/ + tests/ingest/
│   │   ├── router.py            # POST /api/v1/webhooks/github & GET /api/v1/ingest/status/{delivery_id}
│   │   ├── dependencies.py      # verify_github_hmac, verify_unique_delivery
│   │   ├── schemas.py           # GitHubPushPayload, WebhookAckResponse
│   │   ├── service.py           # Enqueue verified WebhookJob
│   │   ├── config.py            # IngestConfig (GITHUB_WEBHOOK_SECRET)
│   │   └── exceptions.py        # InvalidSignatureError, DuplicateDeliveryError
│   ├── analyzer/                # Agent 2 owns src/analyzer/ + tests/analyzer/ (NO LLM)
│   │   ├── service.py           # analyze_diff(job) -> ChangeReport
│   │   ├── ast_extractor.py     # tree-sitter-language-pack symbol & signature extraction
│   │   ├── classifier.py        # Rule engine -> API_SURFACE | CLI | ENV_CONFIG | DEPS | BEHAVIOR
│   │   ├── schemas.py           # Internal AST span models
│   │   └── exceptions.py        # DiffParseError, GrammarLoadError
│   ├── drift/                   # Agent 3 owns src/drift/ + tests/drift/ (NO LLM)
│   │   ├── service.py           # compute_drift(change_report, docs) -> DriftReport
│   │   ├── anchor_parser.py     # markdown-it-py section splitter + anchor extractor
│   │   ├── embed_fallback.py    # Local fastembed similarity for unanchored sections
│   │   └── schemas.py           # DocSectionNode
│   ├── orchestrator/            # Agent 4 owns src/orchestrator/ + tests/orchestrator/
│   │   ├── graph.py             # LangGraph StateGraph + AsyncSqliteSaver wiring
│   │   ├── state.py             # OrchestratorState definition (with max_retries=2)
│   │   ├── llm_client.py        # OpenAI-compatible async client (OpenRouter / Groq / Ollama)
│   │   ├── github_client.py     # Async httpx client for branch creation, commits, and PR creation
│   │   ├── prompts.py           # System prompts for Planner, Writer, Reviewer
│   │   └── nodes/
│   │       ├── planner.py       # Maps DriftReport -> targeted edit plan
│   │       ├── writer.py        # Rewrites impacted Markdown sections + walkthroughs
│   │       ├── verifier.py      # Deterministic check: valid links, symbols, fenced blocks
│   │       ├── reviewer.py      # LLM critique against diff; loops to writer if needed
│   │       └── publisher.py     # Opens GitHub PR with Markdown Evidence Table
│   └── context_store/           # Agent 5 owns src/context_store/ + tests/context_store/
│       ├── service.py           # SqliteContextStore implementing ContextStoreProtocol
│       ├── sqlite_store.py      # Low-level aiosqlite queries & WAL transactions
│       ├── models.py            # SQLite DDL (webhook_deliveries, code_doc_edges, doc_embeddings, run_traces)
│       └── exceptions.py        # StorageError, EdgeNotFoundError
└── tests/
    ├── conftest.py              # Shared async fixtures & in-memory SQLite ContextStore
    ├── ingest/
    ├── analyzer/
    ├── drift/
    ├── orchestrator/
    └── context_store/
```
