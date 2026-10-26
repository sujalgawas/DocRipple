# Architecture

![DocRipple Architecture](architecture.svg)

<details open>
<summary><b>Interactive Flowchart (Mermaid)</b></summary>

```mermaid
flowchart TD
    GH(["GitHub Webhook"]):::trigger -->|"POST push event"| Ingest["<b>1. Ingest (FastAPI)</b><br/>• Verify HMAC SHA-256<br/>• Dedupe delivery-id<br/>• Enqueue verified job"]:::module

    Ingest -->|"WebhookJob"| Analyzer["<b>2. Change Analyzer (Tree-sitter)</b><br/><i>(Deterministic • No LLM)</i><br/>• Parse unified diff<br/>• Extract AST symbols & signatures<br/>• Classify: API | CLI | ENV | DEPS | BEHAVIOR"]:::module

    Analyzer -->|"ChangeReport"| Drift["<b>3. Drift Engine (markdown-it-py)</b><br/><i>(Deterministic • No LLM)</i><br/>• Extract doc anchors & code refs<br/>• Intersect: changed symbols ∩ doc anchors<br/>• Fastembed cosine fallback for unanchored docs"]:::module

    Drift -->|"DriftReport"| Orchestrator

    subgraph Orchestrator ["<b>4. Orchestrator (LangGraph State Machine)</b>"]
        direction LR
        Planner["Planner<br/><i>(Draft edit plan)</i>"] --> Writer["Writer<br/><i>(Rewrite markdown)</i>"]
        Writer --> Verifier["Verifier<br/><i>(Deterministic checks)</i>"]
        Verifier --> Reviewer{"Reviewer<br/><i>(LLM critique)</i>"}
        Reviewer -->|"Needs Revision"| Writer
        Reviewer -->|"Approved"| Publisher["Publisher<br/><i>(Evidence Table)</i>"]
    end

    Orchestrator <-->|"Reads / Writes<br/>• symbol ↔ doc graph<br/>• embeddings & traces"| Store[("<b>5. ContextStore (SQLite WAL)</b><br/>• code_doc_edges<br/>• webhook_deliveries<br/>• doc_embeddings<br/>• run_traces")]:::storage

    Ingest -.->|"Dedupe check"| Store

    Publisher -->|"Opens PR"| PR["<b>GitHub Docs PR</b><br/>• Updated documentation<br/>• Evidence Table in PR body"]:::target

    classDef trigger fill:#0284c7,stroke:#38bdf8,stroke-width:2px,color:#ffffff;
    classDef module fill:#1e293b,stroke:#475569,stroke-width:1.5px,color:#f8fafc;
    classDef storage fill:#065f46,stroke:#34d399,stroke-width:1.5px,color:#ffffff;
    classDef target fill:#7c3aed,stroke:#c084fc,stroke-width:1.5px,color:#ffffff;
```

</details>

---

## Component Breakdown

### 1. Ingest (`src/ingest/`)
- **FastAPI Webhook**: Listens for push events (`POST /api/v1/webhooks/github`).
- **HMAC Verification**: Validates GitHub signature using `GITHUB_WEBHOOK_SECRET`.
- **Deduplication**: Enforces idempotency using `X-GitHub-Delivery` recorded in `ContextStore`.
- **Enqueueing**: Hands off verified jobs for asynchronous background processing.

### 2. Change Analyzer (`src/analyzer/`) — *Deterministic (No LLM)*
- **Diff Parsing**: Analyzes incoming unified diffs without calling LLMs.
- **Tree-sitter AST Extraction**: Extracts symbol definitions and signatures (functions, classes, methods, routes, CLI flags, env vars).
- **Classification Engine**: Categorizes changes into semantic change classes:
  - `API_SURFACE`
  - `CLI`
  - `ENV_CONFIG`
  - `DEPS`
  - `BEHAVIOR`

### 3. Drift Engine (`src/drift/`) — *Deterministic (No LLM)*
- **Anchor Parsing**: Uses `markdown-it-py` to split documentation into sections and extract doc anchors.
- **Intersection Matching**: Computes `changed_symbols ∩ doc_anchors` to pinpoint impacted documentation sections.
- **Embedding Fallback**: Applies local fast embedding cosine similarity (`fastembed`) for documentation sections lacking explicit anchors.

### 4. Orchestrator (`src/orchestrator/`) — *LangGraph State Machine*
- **StateGraph Execution**: Orchestrates document updates across a multi-step workflow:
  - **Planner**: Maps `DriftReport` to a targeted edit plan.
  - **Writer**: Rewrites affected markdown sections and walkthroughs.
  - **Verifier**: Performs deterministic checks on links, symbols, and code fences.
  - **Reviewer**: Evaluates edits against the diff and loops back to Writer if criteria are not met.
  - **Publisher**: Opens a GitHub PR with an Evidence Table in the PR description.
- **Persistence**: Checkpointed via `AsyncSqliteSaver`.

### 5. ContextStore (`src/context_store/`) — *SQLite WAL*
- **Storage Layer**: Built on `aiosqlite` running in WAL mode.
- **Data Models**:
  - `code_doc_edges`: Symbol-to-doc relationship graph.
  - `webhook_deliveries`: Delivery ID idempotency registry.
  - `doc_embeddings`: Vector representations for doc sections.
  - `run_traces`: Execution history and agent runs.
