# File structure

```text
DocRipple/
├── README.md
├── render.yaml
├── run.ps1 / run.bat / run.sh
├── docs/
│   ├── README.md
│   ├── architecture.md
│   ├── backend.md
│   ├── frontend.md
│   ├── api.md
│   ├── data-model.md
│   ├── deployment.md
│   └── filestructure.md
├── docsync-agent/
│   ├── pyproject.toml
│   ├── .env.example
│   ├── src/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── pipeline.py
│   │   ├── contracts/
│   │   ├── onboarding/
│   │   ├── ingest/
│   │   ├── analyzer/
│   │   ├── drift/
│   │   ├── orchestrator/
│   │   ├── context_store/
│   │   └── web_api/
│   └── tests/
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── public/
    └── src/
        ├── App.tsx
        ├── components/
        ├── pages/
        ├── services/
        ├── lib/
        └── assets/
```

## Where to make a change

| Change | Start here |
| --- | --- |
| Add or change an HTTP route | `docsync-agent/src/web_api/router.py`, `src/onboarding/router.py`, `src/ingest/router.py`, or `src/main.py` |
| Change a shared request/response contract | `docsync-agent/src/contracts/schemas.py` and the matching frontend client type |
| Change diff understanding | `docsync-agent/src/analyzer/` |
| Change documentation matching | `docsync-agent/src/drift/` |
| Change generated writing behavior | `docsync-agent/src/orchestrator/prompts.py` and `src/orchestrator/nodes/` |
| Change repository memory | `docsync-agent/src/onboarding/memory_builder.py` and `src/context_store/` |
| Change persistence | `docsync-agent/src/context_store/models.py` and `sqlite_store.py` |
| Change dashboard screens | `frontend/src/pages/` |
| Change shared dashboard layout | `frontend/src/components/` |
| Change frontend/backend URL configuration | `frontend/src/lib/api.ts`, `frontend/src/services/api.ts`, and deployment environment variables |
| Change deployment behavior | `render.yaml`, `frontend/vercel.json`, `docsync-agent/vercel.json`, and `docs/deployment.md` |

`src/contracts/` is the boundary between pipeline stages. Update it deliberately and run the full backend suite when changing a shared model.
