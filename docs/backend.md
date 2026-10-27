# Backend workflow

The backend is a FastAPI application in `docsync-agent/src`. `src/main.py` creates the application, initializes shared resources during the lifespan, and mounts the onboarding, ingest, and web API routers.

## Startup wiring

On startup the application:

1. Opens and initializes the SQLite context store.
2. Seeds the demo repository only when the store is empty.
3. Creates one `asyncio.Queue[WebhookJob]`.
4. Creates the analyzer, drift engine, GitHub service, orchestrator, and pipeline.
5. Stores shared services on `app.state`.
6. Starts the queue worker unless the deployment is running in inline serverless mode.

The queue is intentionally exposed as both `app.state.queue` and `app.state.webhook_queue`. The ingest dependency and the web API use the same object, so a webhook is never placed on a queue that the worker cannot see.

## Stage 0: onboarding

Repository registration is the expensive indexing boundary. `OnboardingService` receives either an inline snapshot or a GitHub repository reference and coordinates two activities:

- `DocStyleSkillGenerator` reads existing Markdown and compiles heading, tone, code-fence, table, callout, and anchor conventions into a reusable prompt.
- `RepoMemoryMapBuilder` creates module, file, symbol, and documentation-section nodes with typed `CONTAINS`, `IMPORTS`, `DEFINES`, and `DOCUMENTED_IN` edges.

The resulting skill, graph, and initial code-to-documentation edges are saved before webhook processing begins.

## Stages 1-3: deterministic gate

### Stage 1: ingest

`src/ingest/` accepts GitHub events at `/api/v1/webhooks/github` and compatibility paths `/webhook` and `/api/v1/webhook`. The handler:

1. Reads the raw request body.
2. Validates the HMAC SHA-256 signature.
3. Uses `X-GitHub-Delivery` to reject duplicate deliveries.
4. Normalizes supported push and pull request events into a frozen `WebhookJob`.
5. Places the job on the shared queue.

### Stage 2: analyzer

`ChangeAnalyzerService` parses the unified diff and uses Tree-sitter grammars to identify changed functions, classes, methods, routes, flags, environment variables, and configuration symbols. The classifier assigns a semantic change class such as `api_surface`, `behavior`, `env_config`, `deps`, or `cli`.

This stage does not call an LLM. That makes its output repeatable and keeps internal refactors from becoming model prompts.

### Stage 3: drift engine

`DriftEngineService` parses Markdown into sections and searches for:

1. Explicit `doc-anchor` references.
2. Known code-documentation edges from the memory graph.
3. Inline code symbols and heading references.
4. Similar unanchored sections using the local embedding fallback.

The default fallback is NumPy TF-IDF and character n-gram similarity. `fastembed` is imported only when `EMBEDDING_MODE=fastembed`.

If there are no public changes or no impacted documentation sections, the pipeline records a no-drift result and stops before the LLM stage.

## Stage 4: LangGraph orchestration

When drift is found, `OrchestratorService` loads the repository style skill and a two-hop memory subgraph around the changed symbols. The LangGraph state machine runs:

```text
Planner -> Writer -> Verifier -> Reviewer -> Publisher
                    ^              |
                    |-- revision --|
```

- **Planner:** Converts the drift report into a bounded edit plan.
- **Writer:** Rewrites only the impacted sections using the repository style skill.
- **Verifier:** Checks symbols, anchors, links, fences, and required structure.
- **Reviewer:** Critiques the patch for correctness and style; sends failed work back to the writer.
- **Publisher:** Creates a branch, commits the documentation update, opens a pull request, and records the evidence table.

The orchestrator uses an OpenAI-compatible client, so OpenRouter, another hosted provider, or a local compatible endpoint can be configured through environment variables.

## Stage 5: persistence and activity

`SqliteContextStore` uses `aiosqlite` and WAL mode. It stores repository configuration, onboarding artifacts, delivery idempotency, activity runs, memory edges, and generated results. LangGraph checkpoints use the configured checkpoint database path.

The dashboard reads activity from the same store. This is why a webhook run, a manual trigger, and a generated pull request can be shown consistently in the frontend.

## Error boundaries

- Invalid signatures and malformed webhook payloads return explicit HTTP errors.
- Duplicate deliveries are acknowledged without running the pipeline twice.
- GitHub failures are translated into gateway errors by the web API.
- Pipeline failures are recorded against the delivery and logged with the delivery ID.
- Missing GitHub or LLM credentials fail at the operation that requires them instead of silently pretending that a pull request was created.
