# Task: Remove Clerk authentication completely (hackathon mode)

Repo: `e:\qwen\company-brain`

## Goal
Strip **all Clerk auth** so the UI is open with no sign-in. Keep **X-Brain-Api-Key** for agent/integrations. Unauthenticated browser calls use org `default`.

Do **not** commit. Do **not** push. Prefer small, working edits over drive-by refactors.

## Frontend (must)

1. `frontend/src/main.tsx` — remove `ClerkProvider` and `VITE_CLERK_PUBLISHABLE_KEY` requirement. Render `RouterProvider` / app directly.
2. `frontend/src/router.tsx` — remove SignIn/SignUp routes. Remove `ProtectedRoute` wrapper; `/app` uses `AppShell` + `Outlet` only. Optional: redirect `/sign-in` and `/sign-up` → `/app/dashboard`.
3. `frontend/src/components/auth/ProtectedRoute.tsx` — either delete or make a no-op that just renders children (no Clerk). Prefer delete + update imports.
4. `frontend/src/lib/api.ts` — remove Clerk token getter / Bearer interceptor. API calls need no auth header for UI (backend will allow open org).
5. Strip all `@clerk/clerk-react` imports/usages from:
   - `Landing.tsx` — CTA should go to `/app/dashboard` (and/or `/app/onboard`). Remove Sign In / Sign Up Clerk flows. Drop marketing line that sells Clerk auth.
   - `Sidebar.tsx` — remove `UserButton` / `useAuth`; keep a simple static label like “Demo” or org name.
   - `Brain.tsx` and any other page using `useAuth` / `useUser` / `getToken`.
6. Delete or gut `SignIn.tsx` / `SignUp.tsx` if unused.
7. `frontend/package.json` — remove `@clerk/clerk-react` dependency; run `npm install` in `frontend/` so lockfile updates.
8. `frontend/.env` / `.env.example` if present — remove `VITE_CLERK_*` (do not invent secrets).

## Backend (must)

1. `backend/middleware/clerk_auth.py` — rename purpose to dual/open auth:
   - Keep public paths + `X-Brain-Api-Key` → org from Mongo.
   - **Remove Clerk JWKS / JWT verification entirely.**
   - If neither API key nor JWT: set `request.state.org_id = "default"`, `auth_type = "open"`, and **allow** the request (no 401). Hackathon open mode.
2. `backend/main.py` — remove Clerk webhook route (`/clerk/webhook`) and `_verify_clerk_jwt` usages for query-param JWT. SSE/stream org resolution: default to `"default"` when no API key.
3. `backend/config.py` — Clerk settings can stay as unused optional strings OR be removed if nothing references them. Prefer remove unused Clerk settings if safe.
4. Keep API-key auth for integrations (`X-Brain-Api-Key`).

## Docs (light touch)

- `README.md`: say auth is open for demo/hackathon; agents still use API keys. Remove “sign up with Clerk” onboarding steps.
- Skip huge PROJECT_MASTER rewrites unless a line would be blatantly wrong.

## Verify

1. `cd frontend && npm run build` must succeed.
2. Hit `http://127.0.0.1:8000/health` (start/restart uvicorn if needed after backend changes).
3. With API running, `GET http://127.0.0.1:8000/brain/skills` **without** Authorization must return **200** (open mode).
4. If frontend vite is on 5173/5174, confirm `/app/dashboard` loads without redirect to `/sign-in`.
5. Write a short report to `e:\qwen\company-brain\CLERK_REMOVAL_REPORT.md` with files changed + verify results.

## Out of scope
- Do not deploy ECS.
- Do not reintroduce Outcome Feedback Loop.
- Do not require E2E_EMAIL/PASSWORD.
