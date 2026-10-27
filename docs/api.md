# API reference

The backend base URL is `http://localhost:8000` locally. All application routes except `/health` use the `/api/v1` prefix.

## System and demo routes

| Method | Route | Use |
| --- | --- | --- |
| `GET`, `HEAD` | `/health` | Liveness probe. Both methods return `200`. |
| `POST` | `/api/v1/demo/run` | Run a supplied diff through analysis, drift detection, orchestration, and persistence. |
| `GET` | `/api/v1/runs/{delivery_id}` | Retrieve a stored result for a delivery. |

## Onboarding routes

| Method | Route | Use |
| --- | --- | --- |
| `POST` | `/api/v1/repos/onboard` | Build and persist a repository style skill and memory map. |
| `GET` | `/api/v1/repos/{owner}/{repo}/skill` | Read the compiled writing skill. |
| `GET` | `/api/v1/repos/{owner}/{repo}/memory` | Read the full graph or filter it with `?symbols=foo,bar`. |

## GitHub webhook routes

The canonical route is `/api/v1/webhooks/github`. The other two paths are compatibility aliases for existing GitHub installations:

| Method | Route | Required headers |
| --- | --- | --- |
| `POST` | `/api/v1/webhooks/github` | `X-GitHub-Delivery`, `X-GitHub-Event`, `X-Hub-Signature-256` |
| `POST` | `/webhook` | Same as above |
| `POST` | `/api/v1/webhook` | Same as above |

The request body must be the original GitHub JSON payload. Do not parse and re-serialize it before signature verification.

## Dashboard and authentication routes

| Method | Route | Use |
| --- | --- | --- |
| `GET` | `/api/v1/auth/me` | Return the current GitHub identity. |
| `GET` | `/api/v1/auth/config` | Report OAuth availability and callback URL. |
| `POST` | `/api/v1/auth/token` | Validate and store a GitHub personal access token. |
| `GET` | `/api/v1/auth/github/login` | Start GitHub OAuth. |
| `GET` | `/api/v1/auth/github/callback` | Exchange the OAuth code and update all runtime GitHub clients. |
| `GET` | `/api/v1/github/repos` | List repositories visible to the authenticated user. |
| `POST` | `/api/v1/repos/connect` | Onboard a repository and install its webhook. |
| `GET` | `/api/v1/dashboard` | Return dashboard summary data. |
| `GET` | `/api/v1/activity` | Return recent activity runs. |
| `GET` | `/api/v1/repos/{owner}/{repo}/history` | Return repository activity history. |
| `POST` | `/api/v1/repos/{owner}/{repo}/trigger` | Trigger a manual synchronization. |
| `GET` | `/api/v1/settings` | Read user and monitored-repository settings. |
| `PATCH` | `/api/v1/settings` | Update settings. |
| `POST` | `/api/v1/settings/disconnect` | Remove the current connection and installed webhooks. |

## Authentication token lifecycle

After a token is accepted, the backend updates:

1. `request.app.state.github_service`, used by the dashboard and publisher.
2. `request.app.state.pipeline.fetcher`, used to fetch diffs and documentation.
3. `request.app.state.github_oauth_token` and the runtime settings value.

This matters because the pipeline is long-lived. Updating only the request-local service would leave the worker using an old token.
