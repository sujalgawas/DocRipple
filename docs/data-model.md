# Data model

DocRipple stores operational state in SQLite. The database is a local context store rather than the source of truth for GitHub: GitHub remains authoritative for repositories, commits, branches, and pull requests.

## Repository memory

The memory graph is split into nodes and edges:

| Table | Key | Purpose |
| --- | --- | --- |
| `repo_memory_nodes` | repository and node ID | Modules, files, symbols, and Markdown sections. |
| `repo_memory_edges` | repository, source, target, relation | `CONTAINS`, `IMPORTS`, `DEFINES`, and `DOCUMENTED_IN` relationships. |
| `code_doc_edges` | repository, symbol, document, section | Fast symbol-to-document lookup used by drift detection. |
| `repo_style_skills` | repository name | The compiled writing conventions for one repository. |

The orchestrator asks for a bounded two-hop subgraph instead of loading the entire repository. This keeps prompts focused and gives the model local context around the changed symbols.

## Delivery and activity state

| Table | Purpose |
| --- | --- |
| `webhook_deliveries` | Idempotency registry keyed by `X-GitHub-Delivery`. |
| `activity_runs` | Dashboard-friendly status, commit metadata, diff preview, and pull request metadata. |
| `run_traces` | Detailed publish result, evidence table, and completion data. |
| `doc_embeddings` | Cached similarity vectors for documentation sections. |
| `monitored_repos` | Connected repository, branch, documentation paths, drift action, and webhook ID. |
| `user_settings` | Single-user dashboard settings and GitHub identity. |

## Core in-memory contracts

The backend passes frozen Pydantic models between stages:

```text
WebhookJob
    -> ChangeReport
    -> DriftReport
    -> PublishResult
```

- `WebhookJob` describes the event and commit range.
- `ChangeReport` describes changed symbols and their classifications.
- `DriftReport` identifies impacted documentation sections and match methods.
- `PublishResult` describes verification, publication, and evidence.

`DocStyleSkill`, `RepoMemoryMap`, `MemoryNode`, and `MemoryEdge` are the Stage 0 contracts used to make later runs repository-aware.

## Consistency rules

- A delivery ID must be recorded before its job is queued.
- A duplicate delivery must never create a second activity run.
- Memory edges must reference nodes from the same repository.
- A published result must retain its evidence table so reviewers can understand why a section was changed.
- SQLite paths must be writable in the target environment. Vercel and ephemeral Render storage use `/tmp`.
