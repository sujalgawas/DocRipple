# Frontend

The frontend is a React 19 single-page application built with Vite, TypeScript, Tailwind CSS, and React Router.

## User-facing routes

| Route | Screen |
| --- | --- |
| `/` | Landing page and product explanation |
| `/login` | GitHub connection and token entry |
| `/repositories` | Connected repository dashboard |
| `/repositories/new` | Repository picker and onboarding flow |
| `/repositories/:owner/:repo` | Repository details and history |
| `/activity` | Pipeline activity and run status |
| `/settings` | User and repository settings |

`App.tsx` owns route composition. Page components own screen behavior, while shared layout and visual primitives live under `src/components`.

## API client

There are two typed client surfaces:

- `frontend/src/lib/api.ts` contains the typed low-level request helpers and Stage 0/demo calls.
- `frontend/src/services/api.ts` contains dashboard-facing operations such as auth, repositories, activity, settings, and manual triggers.

Both use `VITE_API_BASE_URL`, falling back to `http://localhost:8000`. Keep API response types close to the client functions that consume them; this makes backend contract changes visible during the TypeScript build.

## Local frontend configuration

```powershell
cd frontend
npm install
$env:VITE_API_BASE_URL="http://localhost:8000"
npm run dev
```

For Vercel, set `VITE_API_BASE_URL` to the public Render API URL at build time. The backend must include the same frontend origin in `FRONTEND_URL` or `ALLOWED_ORIGINS`.

## Build and lint

```powershell
npm run build
npm run lint
```

The production build runs `tsc -b` before Vite. Treat TypeScript errors as API contract failures, not just frontend formatting issues.
