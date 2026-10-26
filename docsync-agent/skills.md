# DocSync Agent — Ground Rules

- Keep each agent module self-contained: one module owns its `src/<module>/` and `tests/<module>/` exclusively.
- Contracts (`src/contracts/`) are **frozen** before parallel runs — read-only for all module agents.
- The Analyzer and Drift engines are **deterministic** — no LLM calls allowed in `src/analyzer/` or `src/drift/`.
- The Orchestrator is the only module that calls an LLM or interacts with GitHub.
- All async I/O uses `aiosqlite` (WAL mode) through the `ContextStoreProtocol`.
- Maximum retries in the orchestrator state machine: 2.
- Environment variables managed via `pydantic-settings` `BaseSettings` in each module's `config.py`.

## Running

```bash
uv sync
uv run uvicorn src.main:app --reload
```

## Testing

```bash
uv run pytest -v
```