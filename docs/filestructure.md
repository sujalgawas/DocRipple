# File Structure

```text
docsync-agent/
├── pyproject.toml
├── README.md                    # Package-level overview, quickstart, and demo commands
├── skills.md                    # Package agent ground rules
├── src/
│   ├── main.py                  # FastAPI lifespan, Stage 0 service wiring, router mounting, worker startup
│   ├── config.py                # Global BaseSettings (env vars)
│   ├── pipeline.py              # Stages 1–5 background worker + GitHub snapshot fetcher
│   ├── contracts/               # FROZEN BEFORE PARALLEL RUNS (Read-only for module agents)
│   │   ├── __init__.py          # Re-exports every shared schema and protocol
│   │   ├── schemas.py           # WebhookJob, ChangedSymbol, ChangeReport, CodeDocEdge, DriftReport,
│   │   │                        # PublishResult + Stage 0: DocStyleSkill, MemoryNode, MemoryEdge,
│   │   │                        # RepoMemoryMap, OnboardRepoResult
│   │   └── protocols.py         # ContextStoreProtocol (incl. style-skill + memory persistence),
│   │                            # OnboardingServiceProtocol, AnalyzerProtocol, DriftEngineProtocol
│   ├── onboarding/              # Stage 0 — repository onboarding & memory indexing
│   │   ├── router.py            # POST /api/v1/repos/onboard
│   │   │                        # GET  /api/v1/repos/{owner}/{repo}/skill
│   │   │                        # GET  /api/v1/repos/{owner}/{repo}/memory?symbols=...
│   │   ├── service.py           # OnboardingService.onboard_repository(): generate → persist → summarize
│   │   ├── style_analyzer.py    # DocStyleSkillGenerator: Markdown conventions -> compiled SKILL.md
│   │   ├── memory_builder.py    # RepoMemoryMapBuilder: module/file/symbol/doc_section nodes + typed edges
│   │   └── schemas.py           # OnboardRequest
│   ├── ingest/                  # Agent 1 owns src/ingest/ + tests/ingest/
│   │   ├── router.py            # POST /api/v1/webhooks/github
│   │   ├── dependencies.py      # verify_github_hmac, verify_unique_delivery, store/queue accessors
│   │   ├── schemas.py           # GitHubPushPayload, WebhookAckResponse
│   │   ├── service.py           # Enqueue verified WebhookJob
│   │   ├── config.py            # IngestConfig (GITHUB_WEBHOOK_SECRET)
│   │   └── exceptions.py        # InvalidSignatureError, DuplicateDeliveryError
│   ├── analyzer/                # Agent 2 owns src/analyzer/ + tests/analyzer/ (NO LLM)
│   │   ├── service.py           # analyze_diff(job) -> ChangeReport
│   │   ├── ast_extractor.py     # tree-sitter-language-pack symbol & signature extraction
│   │   ├── classifier.py        # Rule engine -> API_SURFACE | CLI | ENV_CONFIG | DEPS | BEHAVIOR
│   │   ├── schemas.py           # Internal AST span models
│   │   └── exceptions.py        # DiffParseError, GrammarExtractionError
│   ├── drift/                   # Agent 3 owns src/drift/ + tests/drift/ (NO LLM)
│   │   ├── service.py           # compute_drift(change_report, docs) -> DriftReport
│   │   ├── anchor_parser.py     # markdown-it-py section splitter + anchor extractor
│   │   ├── embed_fallback.py    # Local fastembed similarity for unanchored sections
│   │   └── schemas.py           # DocSectionNode
│   ├── orchestrator/            # Agent 4 owns src/orchestrator/ + tests/orchestrator/
│   │   ├── graph.py             # LangGraph StateGraph + AsyncSqliteSaver wiring
│   │   ├── service.py           # Loads DocStyleSkill + 2-hop memory subgraph, then invokes the graph
│   │   ├── state.py             # OrchestratorState (incl. doc_style_skill, memory_subgraph, max_retries=2)
│   │   ├── llm_client.py        # OpenAI-compatible async client (OpenRouter / Groq / Ollama)
│   │   ├── github_client.py     # Async httpx client for branch creation, commits, and PR creation
│   │   ├── prompts.py           # System prompts for Planner, Writer, Reviewer
│   │   └── nodes/
│   │       ├── planner.py       # Maps DriftReport -> edit plan; receives memory-subgraph summary
│   │       ├── writer.py        # Rewrites impacted sections using the DocStyleSkill
│   │       ├── verifier.py      # Deterministic checks: symbols, code fences, preserved anchors
│   │       ├── reviewer.py      # Diff + style critique; loops to writer if needed
│   │       └── publisher.py     # Opens PR with Evidence Table; refreshes symbol/doc_section memory nodes
│   └── context_store/           # Agent 5 owns src/context_store/ + tests/context_store/
│       ├── service.py           # create_context_store() factory
│       ├── sqlite_store.py      # aiosqlite queries, WAL transactions, 2-hop memory traversal
│       ├── models.py            # SQLite DDL (7 tables — see below)
│       └── exceptions.py        # DatabaseNotInitializedError, StorageError
└── tests/
    ├── conftest.py              # Shared async fixtures & in-memory SQLite ContextStore
    ├── onboarding/              # Stage 0 style-skill, memory-map, subgraph, and API tests
    ├── ingest/
    ├── analyzer/
    ├── drift/
    ├── orchestrator/
    ├── context_store/
    └── integration/             # Stage 0 → Stages 1–5 end-to-end coverage
```

## SQLite Schema (`src/context_store/models.py`)

| Table | Primary Key | Purpose |
| :--- | :--- | :--- |
| `repo_style_skills` | `repo_full_name` | One frozen `DocStyleSkill` per repository, including compiled `skill_markdown`. |
| `repo_memory_nodes` | `(repo_full_name, node_id)` | Module, file, symbol, and doc-section nodes with deterministic summaries. |
| `repo_memory_edges` | `(repo_full_name, source_id, target_id, relation)` | `CONTAINS`, `IMPORTS`, `DEFINES`, and `DOCUMENTED_IN` relationships. |
| `code_doc_edges` | `(repo_full_name, symbol_name, doc_path, section_heading)` | Symbol ↔ documentation links, pre-populated in Stage 0 and refreshed by the Publisher. |
| `webhook_deliveries` | `delivery_id` | Idempotency registry for `X-GitHub-Delivery`. |
| `doc_embeddings` | `(repo_full_name, doc_path, section_heading)` | Embedding cache keyed by section content hash. |
| `run_traces` | `delivery_id` | Published PR metadata, evidence JSON, and completion time. |

Indexes cover `code_doc_edges` by symbol and doc path, `doc_embeddings` by section, and
`repo_memory_nodes`/`repo_memory_edges` by name, path, source, and target for fast traversal.

## Module Responsibilities

| Stage | Module Path | Test Path | LLM Allowed? | Primary Responsibility |
| :--- | :--- | :--- | :--- | :--- |
| **0. Onboarding** | `src/onboarding/` | `tests/onboarding/` | Optional refinement only | Generate a repository-specific `DocStyleSkill`, build the `RepoMemoryMap`, persist both, and pre-populate `code_doc_edges` before any webhook is processed. |
| **0. Contracts** | `src/contracts/` | — | No | Frozen Pydantic v2 schemas and `typing.Protocol` interfaces shared by every module. |
| **1. Ingest** | `src/ingest/` | `tests/ingest/` | No | HMAC verification, delivery dedupe, and queue handoff. |
| **2. Analyzer** | `src/analyzer/` | `tests/analyzer/` | **Strictly No** | Diff parsing and AST symbol extraction/classification. |
| **3. Drift Engine** | `src/drift/` | `tests/drift/` | **Strictly No** | Anchor matching, graph-edge lookup, and embedding fallback. |
| **4. Orchestrator** | `src/orchestrator/` | `tests/orchestrator/` | **Yes** | LangGraph `Planner → Writer → Verifier → Reviewer → Publisher` loop consuming the Stage 0 skill and memory subgraph. |
| **5. ContextStore** | `src/context_store/` | `tests/context_store/` | No | SQLite WAL persistence for skills, memory nodes/edges, code-doc edges, deliveries, embeddings, and run traces. |
| **Pipeline** | `src/pipeline.py` | `tests/integration/` | No | Background worker chaining Stages 1–5 and fetching GitHub diffs/docs. |
| **App** | `src/main.py` | `tests/integration/` | No | Lifespan wiring for the store, Stage 0 service, worker, and routers. |
