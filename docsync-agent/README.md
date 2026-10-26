# DocRipple (DocSync Agent)

> **Self-updating GitHub documentation agent powered by Stage 0 repository onboarding, deterministic AST parsing, hierarchical memory, and a LangGraph multi-agent repair loop.**

[![Tests](https://img.shields.io/badge/pytest-58%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)]()
[![Tree--sitter](https://img.shields.io/badge/Tree--sitter-AST%20Analysis-orange.svg)]()
[![LangGraph](https://img.shields.io/badge/LangGraph-Orchestrator-7c3aed.svg)]()
[![Stage 0](https://img.shields.io/badge/Stage%200-Memory%20%2B%20Style%20Skill-0ea5e9.svg)]()

---

## The Problem: Hallucinated & Expensive Documentation PRs

Most AI documentation tools feed entire git diffs and full documentation files directly to an LLM on every commit. This causes three critical failure modes:

1. **Hallucinated Edits**: LLMs rewrite unrelated documentation sections, alter working sample code, or delete markdown headers.
2. **Prohibitive LLM Token Costs**: Running multi-thousand token prompts on every push (including internal refactors, comments, and private helpers) rapidly exhausts API budgets.
3. **Flaky CI/CD**: Unverified documentation PRs break hyperlinks, code snippet fences, or introduce invalid syntax.

### The DocRipple Solution: Deterministic Pre-Filtering (0 LLM Tokens Spent)

DocRipple enforces a strict **deterministic gate** before any LLM is ever invoked:

- **Stage 0 (Repository Onboarding - Zero LLM by default)**: Learns the repository before the first webhook arrives — a repository-specific writing-style skill plus a hierarchical memory map of modules, files, symbols, and documentation sections.
- **Stage 2 (Change Analyzer - Zero LLM)**: Uses `tree-sitter` AST parsing and unified diff hunk analysis to extract precise modified symbols (functions, classes, routes, CLI flags, env vars) and classify their semantic `ChangeClass` (`API_SURFACE`, `CLI`, `ENV_CONFIG`, `DEPS`, `BEHAVIOR`).
- **Stage 3 (Drift Engine - Zero LLM)**: Uses `markdown-it-py` to parse documentation anchors (`<!-- doc-anchor: ... -->`) and code block references, performing set intersection between changed AST symbols and documented references.
- **Early-Exit Gate**: If internal code changes do not impact any documented symbol, DocRipple exits immediately with **0 LLM calls and zero token cost**.
- **Stage 4 (Orchestrator - LangGraph)**: When drift is verified, a multi-agent StateGraph (`Planner` → `Writer` → `Verifier` → `Reviewer` → `Publisher`) runs with the repository's own style skill and a 2-hop memory subgraph, producing a PR with a verifiable Markdown Evidence Table.

---

## Two Things That Make DocRipple Different

### 1. Adaptive Repo Writing-Style Skill (`DocStyleSkill`)

DocRipple reads `README.md` and `docs/**/*.md` **once per registered repository** and compiles a `SKILL.md` instruction block describing how that repository actually writes:

- heading hierarchy and dominant `## → ###` transitions
- tone and voice (tutorial-first imperative vs. reference-style declarative)
- code-fence language tags (`bash`, `python`, `json`, ...) and `curl` conventions
- pipe tables, `> [!NOTE]` callouts, inline backticks, and `<!-- doc-anchor: ... -->` patterns

That skill is injected into the Writer and Reviewer prompts, so generated updates sound like the repository — not like a generic documentation bot.

### 2. Hierarchical Node Memory Map (`RepoMemoryMap`)

Stage 0 builds a node-and-edge graph in SQLite:

- **`module`** nodes with hierarchical `CONTAINS` edges
- **`file`** nodes for every indexed source file
- **`symbol`** nodes from `ast_extractor` (functions, classes, routes) plus CLI flags, env vars, and config constants
- **`doc_section`** nodes from `anchor_parser`
- **`IMPORTS`**, **`DEFINES`**, and **`DOCUMENTED_IN`** edges

Before each run, the Orchestrator loads a **2-hop subgraph** around the changed symbols. The Planner sees parent packages, sibling symbols, and the exact documentation sections that already reference the change — without loading the whole repository.

---

## Architecture Diagram

```
Repository Registration
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ 0. Onboarding (src/onboarding/) — [ZERO LLM BY DEFAULT]│
│    ┌────────────────────────┐  ┌────────────────────┐  │
│    │ 0A DocStyleSkill       │  │ 0B RepoMemoryMap   │  │
│    │    Generator           │  │    Builder         │  │
│    │ • Heading hierarchy    │  │ • Module/file nodes│  │
│    │ • Tone & voice         │  │ • AST symbol nodes │  │
│    │ • Fences, tables,      │  │ • Doc-section nodes│  │
│    │   callouts, anchors    │  │ • CONTAINS/IMPORTS │  │
│    └───────────┬────────────┘  └─────────┬──────────┘  │
│                │                        │              │
│                ▼                        ▼              │
│         repo_style_skills        repo_memory_nodes     │
│         (SKILL.md prompt)        repo_memory_edges     │
│                                         │              │
│                                         ▼              │
│                               initial code_doc_edges   │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
GitHub Webhook (Push / PR)
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ 1. Ingest (FastAPI)                                    │
│    • Verify X-Hub-Signature-256 (HMAC-SHA256)          │
│    • Deduplicate X-GitHub-Delivery (SQLite ContextStore)│
│    • Enqueue WebhookJob (asyncio.Queue)                │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ 2. Change Analyzer (Tree-sitter) — [ZERO LLM TOKENS]   │
│    • Parse unified diff & AST symbols                  │
│    • Classify ChangeClass (API, CLI, ENV, DEPS, etc.)  │
│    • Early Exit if no public symbols changed           │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ 3. Drift Engine (markdown-it-py) — [ZERO LLM TOKENS]   │
│    • Extract Markdown anchors & code block symbols     │
│    • Intersect changed symbols ∩ doc references        │
│    • Query Stage 0 graph edges & embedding fallback    │
│    • Early Exit if 0 doc sections impacted             │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ 4. LangGraph Orchestrator                              │
│    • Loads DocStyleSkill + 2-hop memory subgraph       │
│    ┌─────────┐     ┌────────┐     ┌──────────┐         │
│    │ Planner │ ──► │ Writer │ ──► │ Verifier │ (AST/md)│
│    └─────────┘     └────▲───┘     └────┬─────┘         │
│                         │              │               │
│                  Fixes  │              ▼               │
│                  Needed └─────── ┌──────────┐          │
│                                  │ Reviewer │ (Diff +  │
│                                  └─────┬────┘  style)  │
│                                        │ Approved      │
│                                        ▼               │
│                                  ┌───────────┐         │
│                                  │ Publisher │         │
│                                  └───────────┘         │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ 5. SQLite ContextStore & GitHub PR                     │
│    • Persist style skill, memory nodes/edges           │
│    • Persist (symbol ↔ doc) CodeDocEdges in WAL mode   │
│    • Update touched symbol/doc_section nodes           │
│    • Open GitHub PR with Markdown Evidence Table       │
└────────────────────────────────────────────────────────┘
```

---

## Package Layout

```text
docsync-agent/
├── src/
│   ├── onboarding/      # Stage 0: style skill + memory map (APIs under /api/v1/repos)
│   ├── ingest/          # Stage 1: verified GitHub webhooks
│   ├── analyzer/        # Stage 2: tree-sitter diff analysis (no LLM)
│   ├── drift/           # Stage 3: anchor matching + embedding fallback (no LLM)
│   ├── orchestrator/    # Stage 4: LangGraph Planner → Writer → Verifier → Reviewer → Publisher
│   ├── context_store/   # Stage 5: SQLite WAL store (7 tables)
│   ├── contracts/       # Frozen Pydantic + Protocol contracts
│   ├── pipeline.py      # Background worker chaining Stages 1–5
│   └── main.py          # FastAPI lifespan, routers, and app state
└── tests/
    ├── onboarding/      # Stage 0 unit + API coverage
    ├── integration/     # Stage 0 → Stages 1–5 end-to-end coverage
    └── ...              # One test package per module
```

See [`../docs/filestructure.md`](../docs/filestructure.md) for the complete tree and
[`../docs/architecture.md`](../docs/architecture.md) for the full architecture reference.

---

## Quickstart

### Prerequisites
- Python 3.12+
- `uv` (recommended) or `pip`

### 1. Installation

```bash
# From the package directory
cd docsync-agent
uv sync

# Or using pip:
# pip install -e .
```

### 2. Configure Environment

Copy the example environment configuration:

```bash
cp .env.example .env
```

Edit `.env` to configure your settings (works out-of-the-box in local dev mode):

```env
# GitHub auth (PAT fallback; OAuth is optional)
GITHUB_TOKEN=ghp_your_token_here
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# Full public HTTPS URL of /api/v1/webhooks/github (ngrok, cloudflared, etc.).
# Leave blank for local-only use and trigger runs from the dashboard.
PUBLIC_WEBHOOK_URL=
GITHUB_WEBHOOK_SECRET=docripple-secret
FRONTEND_URL=http://localhost:5173

# LLM provider
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=your_key_here
LLM_MODEL=gpt-4o-mini

# Storage
SQLITE_DB_PATH=docsync_context.db
CHECKPOINT_DB_PATH=:memory:
LOG_LEVEL=INFO
```

`GITHUB_TOKEN` needs `contents:read`, `pull_requests:write`, and
`webhooks:write` (or `repo` scope for classic tokens). Both webhook
installation and HMAC verification use `GITHUB_WEBHOOK_SECRET`.

### 3. Run the Application

```bash
# Start FastAPI application with live reload
uv run uvicorn src.main:app --reload --port 8000
```

The server is available at `http://localhost:8000`:
- Swagger API Docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

To use the React dashboard (repository onboarding, activity, and settings):

```bash
cd ../frontend
npm install
npm run dev
```

Vite serves the dashboard at `http://localhost:5173` and calls
`http://localhost:8000/api/v1/...` by default. Override the backend URL with
`VITE_API_BASE_URL` if needed.

### 4. Run the Test Suite

```bash
# Run all unit and integration tests (58 tests)
uv run pytest tests/ -q

# Run with verbose output
uv run pytest tests/ -v

# Run linter
uv run ruff check src/ tests/
```

---

## API Endpoints

| Method | Endpoint | Stage | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/auth/me` | — | GitHub identity used by the React dashboard. |
| `GET` | `/api/v1/auth/github/login` | — | OAuth redirect; falls back to the dashboard with a PAT. |
| `GET` | `/api/v1/github/repos` | — | Repositories available to the authenticated token. |
| `POST` | `/api/v1/repos/connect` | 0 | Snapshot, onboard, install webhook, and monitor a repository. |
| `POST` | `/api/v1/repos/onboard` | 0 | Generate and persist the repo `DocStyleSkill`, memory map, and initial code-doc edges. |
| `GET` | `/api/v1/repos/{owner}/{repo}/skill` | 0 | Return the stored `DocStyleSkill`, including `skill_markdown`. |
| `GET` | `/api/v1/repos/{owner}/{repo}/memory` | 0 | Return the full memory map; add `?symbols=foo,bar` for a 2-hop subgraph. |
| `GET` | `/api/v1/dashboard` | — | Dashboard stats, monitored repositories, and latest runs. |
| `GET` | `/api/v1/activity` | — | Activity runs, newest first (`?repo_full_name=` to filter). |
| `POST` | `/api/v1/repos/{owner}/{repo}/trigger` | 1–5 | Enqueue the latest (or specified) commit for the full pipeline. |
| `GET` / `PATCH` | `/api/v1/settings` | — | Read or update user preferences. |
| `POST` | `/api/v1/settings/disconnect` | — | Remove installed webhooks and clear monitored repositories. |
| `POST` | `/api/v1/webhooks/github` | 1 | Verified GitHub push/PR webhook. |
| `POST` | `/api/v1/demo/run` | 2–5 | Run analyzer → drift → orchestrator synchronously. |
| `GET` | `/api/v1/runs/{delivery_id}` | 5 | Fetch the persisted publish result for a delivery. |
| `GET` | `/health` | — | Service health and queue depth. |

---

## Stage 0: Onboard a Repository

Run onboarding once per repository (or whenever docs/code are re-indexed). You can
post the snapshot inline:

```bash
curl -X POST "http://localhost:8000/api/v1/repos/onboard" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_full_name": "acme/billing-service",
    "code_files": {
      "src/billing.py": "def calc_total(items: list[int], tax_rate: float = 0.05) -> int:\n    \"\"\"Calculate the invoice total with tax.\"\"\"\n    return int(sum(items) * (1 + tax_rate))\n"
    },
    "docs": {
      "README.md": "# Billing Service\n\n## Overview\n\nUse the billing API. Run the example below.\n\n| Option | Meaning |\n| --- | --- |\n| `--tax` | Tax rate |\n\n```bash\ncurl -X POST http://localhost:8000/billing\n```\n\n<!-- doc-anchor: calc_total -->\n\n## Billing\n\nCall `calc_total` to compute a total.\n"
    }
  }'
```

Or let Stage 0 fetch the branch from GitHub:

```bash
curl -X POST "http://localhost:8000/api/v1/repos/onboard" \
  -H "Content-Type: application/json" \
  -d '{"repo_full_name": "acme/billing-service", "branch": "main"}'
```

Inspect what was learned:

```bash
# The compiled repo-specific SKILL.md block
curl "http://localhost:8000/api/v1/repos/acme/billing-service/skill"

# Full hierarchical memory map
curl "http://localhost:8000/api/v1/repos/acme/billing-service/memory"

# 2-hop subgraph around changed symbols
curl "http://localhost:8000/api/v1/repos/acme/billing-service/memory?symbols=calc_total"
```

---

## Live Hackathon Testing & Demo Commands

### 1. Instant Demo Pipeline (`POST /api/v1/demo/run`)
Demonstrate the complete Stage 2 (Analyzer) → Stage 3 (Drift) → Stage 4 (Orchestrator) → Stage 5 (Persistence) pipeline synchronously with a single `curl` command:

```bash
curl -X POST "http://localhost:8000/api/v1/demo/run" \
  -H "Content-Type: application/json" \
  -d '{
    "delivery_id": "demo-run-001",
    "repo_full_name": "acme/billing-service",
    "raw_diff": "--- a/src/billing.py\n+++ b/src/billing.py\n@@ -1,2 +1,3 @@\n-def calc_total(items: list[int]) -> int:\n-    return sum(items)\n+def calc_total(items: list[int], tax_rate: float = 0.05) -> int:\n+    return int(sum(items) * (1 + tax_rate))\n",
    "docs": {
      "README.md": "## Billing\n\n<!-- doc-anchor: billing -->\n\nCalculates invoice total:\n\n```python\nfrom src.billing import calc_total\ntotal = calc_total([10, 20])\n```\n"
    }
  }'
```

> Run `POST /api/v1/repos/onboard` first to see the differentiators in action: the demo then uses the repository's style skill and a 2-hop memory subgraph.

### 2. Live GitHub Webhook (`POST /api/v1/webhooks/github`)

Simulate an incoming GitHub webhook push event with HMAC-SHA256 signature:

```bash
# Set secret and test payload
SECRET="docripple-secret"
PAYLOAD='{"ref":"refs/heads/main","before":"1111111111111111111111111111111111111111","after":"2222222222222222222222222222222222222222","repository":{"full_name":"sujalgawas/DocRipple"}}'

# Compute signature
SIG="sha256=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')"

# Send webhook
curl -X POST "http://localhost:8000/api/v1/webhooks/github" \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Delivery: delivery-test-101" \
  -H "X-GitHub-Event: push" \
  -H "X-Hub-Signature-256: $SIG" \
  -d "$PAYLOAD"
```

### 3. Check Delivery Status & Health

```bash
# Check service health & queue size
curl -X GET "http://localhost:8000/health"

# Query the run result and evidence table for a delivery
curl -X GET "http://localhost:8000/api/v1/runs/delivery-test-101"
```

---

## Evidence Table in Every PR

Every Pull Request opened by DocRipple includes a deterministic audit trail:

| doc_file | section | changed_symbol | change_class | match_method | verification |
|---|---|---|---|---|---|
| `README.md` | Billing | `calc_total` | `api_surface` | `exact_anchor` | `passed` |

Reviewers can verify why each change was made, which AST symbols triggered it, and confirm that both deterministic AST syntax checks and reviewer LLM critique passed.

---

## License

MIT License. Designed and built for the Alan AI Hackathon.
