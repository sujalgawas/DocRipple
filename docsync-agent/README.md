# DocRipple (DocSync Agent)

> **Self-updating GitHub documentation agent powered by deterministic AST parsing, drift filtering, and a LangGraph multi-agent repair loop.**

[![Tests](https://img.shields.io/badge/pytest-32%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)]()
[![Tree--sitter](https://img.shields.io/badge/Tree--sitter-AST%20Analysis-orange.svg)]()
[![LangGraph](https://img.shields.io/badge/LangGraph-Orchestrator-7c3aed.svg)]()

---

## The Problem: Hallucinated & Expensive Documentation PRs

Most AI documentation tools feed entire git diffs and full documentation files directly to an LLM on every commit. This causes three critical failure modes:

1. **Hallucinated Edits**: LLMs rewrite unrelated documentation sections, alter working sample code, or delete markdown headers.
2. **Prohibitive LLM Token Costs**: Running multi-thousand token prompts on every push (including internal refactors, comments, and private helpers) rapidly exhausts API budgets.
3. **Flaky CI/CD**: Unverified documentation PRs break hyperlinks, code snippet fences, or introduce invalid syntax.

### The DocRipple Solution: Deterministic Pre-Filtering (0 LLM Tokens Spent)

DocRipple enforces a strict **deterministic gate** before any LLM is ever invoked:

- **Stage 2 (Change Analyzer - Zero LLM)**: Uses `tree-sitter` AST parsing and unified diff hunk analysis to extract precise modified symbols (functions, classes, routes, CLI flags, env vars) and classify their semantic `ChangeClass` (`API_SURFACE`, `CLI`, `ENV_CONFIG`, `DEPS`, `BEHAVIOR`).
- **Stage 3 (Drift Engine - Zero LLM)**: Uses `markdown-it-py` to parse documentation anchors (`<!-- doc-anchor: ... -->`) and code block references, performing set intersection between changed AST symbols and documented references.
- **Early-Exit Gate**: If internal code changes do not impact any documented symbol, DocRipple exits immediately with **0 LLM calls and zero token cost**.
- **Stage 4 (Orchestrator - LangGraph)**: When drift is verified, a multi-agent StateGraph (`Planner` → `Writer` → `Verifier` → `Reviewer` → `Publisher`) runs with a deterministic verification repair loop and outputs a PR with a verifiable Markdown Evidence Table.

---

## Architecture Diagram

```
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
│    • Classify ChangeClass (API, CLI, ENV, DEPS, etc.)   │
│    • Early Exit if no public symbols changed           │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ 3. Drift Engine (markdown-it-py) — [ZERO LLM TOKENS]   │
│    • Extract Markdown anchors & code block symbols     │
│    • Intersect changed symbols ∩ doc references        │
│    • Query ContextStore edge graph & embedding fallback│
│    • Early Exit if 0 doc sections impacted             │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ 4. LangGraph Orchestrator                              │
│    ┌─────────┐     ┌────────┐     ┌──────────┐         │
│    │ Planner │ ──► │ Writer │ ──► │ Verifier │ (AST/md)│
│    └─────────┘     └────▲───┘     └────┬─────┘         │
│                         │              │               │
│                  Fixes  │              ▼               │
│                  Needed └─────── ┌──────────┐          │
│                                  │ Reviewer │ (Critique│
│                                  └─────┬────┘          │
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
│    • Persist (symbol ↔ doc) CodeDocEdges in SQLite WAL │
│    • Store Run Result & Verification Status            │
│    • Open GitHub PR with Markdown Evidence Table       │
└────────────────────────────────────────────────────────┘
```

---

## Quickstart

### Prerequisites
- Python 3.12+
- `uv` (recommended) or `pip`

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/sujalgawas/DocRipple.git
cd DocRipple/docsync-agent

# Install dependencies using uv
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
GITHUB_WEBHOOK_SECRET=dev-secret
GITHUB_TOKEN=ghp_your_token_here
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=your_key_here
LLM_MODEL=gpt-4o-mini
SQLITE_DB_PATH=docsync_context.db
CHECKPOINT_DB_PATH=:memory:
LOG_LEVEL=INFO
```

### 3. Run the Application

```bash
# Start FastAPI application with live reload
uv run uvicorn src.main:app --reload --port 8000
```

The server is available at `http://localhost:8000`:
- Swagger API Docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

### 4. Run the Test Suite

```bash
# Run all unit and integration tests (32 tests)
uv run pytest tests/ -q

# Run with verbose output
uv run pytest tests/integration/test_full_system.py -v

# Run linter
uv run ruff check src/ tests/
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

### 2. Live GitHub Webhook (`POST /api/v1/webhooks/github`)

Simulate an incoming GitHub webhook push event with HMAC-SHA256 signature:

```bash
# Set secret and test payload
SECRET="dev-secret"
PAYLOAD='\''{"ref":"refs/heads/main","before":"1111111111111111111111111111111111111111","after":"2222222222222222222222222222222222222222","repository":{"full_name":"sujalgawas/DocRipple"}}'\''

# Compute signature
SIG="sha256=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | sed '\''s/^.* //\'')"

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
