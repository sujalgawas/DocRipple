# Deployment and operations

DocRipple uses a split production topology:

```text
Browser -> Vercel frontend -> Render FastAPI backend -> GitHub API
                                      |
                                      +-> OpenRouter-compatible LLM
                                      +-> SQLite on writable local storage
```

## Render backend

[`render.yaml`](../render.yaml) creates the `docripple-api` web service from `docsync-agent/`:

- Python runtime
- `pip install .` build
- `uvicorn src.main:app --host 0.0.0.0 --port $PORT` start command
- `/health` health check
- `EMBEDDING_MODE=tfidf`
- OpenRouter model defaults

Set these values as Render secrets or environment variables:

- `GITHUB_TOKEN`
- `GITHUB_WEBHOOK_SECRET`
- `LLM_API_KEY`
- `FRONTEND_URL`

Use the public Render URL as `PUBLIC_WEBHOOK_URL`, normally ending in `/api/v1/webhooks/github`.

## Vercel frontend

The `frontend/` project is a Vite static build. Configure:

```text
VITE_API_BASE_URL=https://<your-render-service>.onrender.com
```

The Vercel project should use `frontend/` as its root directory and run the standard Vite build. Preview deployments are supported by the backend CORS regular expression for `*.vercel.app`.

## CORS and health checks

The API allows:

- `FRONTEND_URL`
- every origin listed in `ALLOWED_ORIGINS`
- Vercel deployments
- Cloudflare Pages deployments
- localhost origins with any port

`GET /health` and `HEAD /health` both return a successful liveness response. This supports Render and external keep-alive services such as cron-job.org.

## Storage limitations

The free Render plan and Vercel functions should be treated as ephemeral:

- SQLite files under `/tmp` can be removed on restart or redeploy.
- Vercel functions should use inline execution because background tasks do not remain alive after a response.
- Render uses the lightweight TF-IDF embedding fallback by default to avoid loading ONNX model weights.

For durable activity history, move the context store to persistent storage or add a backup/export process before relying on it operationally.

## Webhook setup checklist

1. Deploy the backend and verify `/health`.
2. Set `PUBLIC_WEBHOOK_URL` to the canonical webhook route.
3. Set the same `GITHUB_WEBHOOK_SECRET` in Render and GitHub.
4. Connect a repository through the dashboard.
5. Confirm GitHub sends a delivery with `X-Hub-Signature-256`.
6. Check `/api/v1/activity` and the generated pull request.

## Operational troubleshooting

| Symptom | Check |
| --- | --- |
| Browser CORS error | Confirm `VITE_API_BASE_URL`, `FRONTEND_URL`, and `ALLOWED_ORIGINS`. |
| Webhook returns `401` | Compare the GitHub webhook secret and ensure the raw body is signed. |
| Webhook returns `404` | Use `/api/v1/webhooks/github`, `/webhook`, or `/api/v1/webhook`; all are registered. |
| No pull request is created | Check `GITHUB_TOKEN`, repository permissions, and the activity run error. |
| Memory usage is high | Confirm `EMBEDDING_MODE=tfidf` and do not install or enable `fastembed` unnecessarily. |
| Token changes do not affect a run | Confirm the runtime token was updated on both the shared GitHub service and pipeline fetcher. |
