# Task 6 implementer report

## Handoff and scope

Task 6 was resumed from an uncommitted partial implementation after its original implementer stopped for model capacity. I audited every changed production, generated, documentation, and test file before continuing; the existing API center, OpenAPI refresh, SPA fallback, and visual-matrix work was retained because it matched the actual Task 1–5 backend contracts. I added mobile-drawer keyboard containment, trailing-slash deep-link fallback, English API-guide corrections, and dialog focus restoration with regressions.

- `/api/docs` is public and uses a dedicated API shell with only API Docs/API Management, centered documentation, a sticky desktop table of contents, and a collapsed phone drawer.
- `/api/keys` is guarded and uses the real `/api/v1/api-keys` and `/api/v1/account/usage` endpoints. It only renders server-provided masked metadata, never gives existing keys a copy action, and only exposes the one-time create response in an accessible warning modal with copy feedback and a named revoke confirmation.
- The guide covers quick/full, `dsb_live_` bearer auth, draft creation, all five exact uploads, submit/poll/result/media lifecycle, quota/retention limits, state table, errors, and executable Curl/Python examples using `/api/v1/tasks`.
- `openapi.json` was freshly exported; `frontend/src/generated/schema.d.ts` was freshly generated. Frontend auth and API-center types now consume generated components where the contract supplies them.
- FastAPI serves the SPA for UI deep links including `/api/docs` and `/api/keys`, while unknown `/api/*` paths remain JSON 404s. The Vite proxy is correctly restricted to `/api/v1`, so the document route stays client-rendered in development.
- README now documents the user-facing guide, staged API, API-key semantics, and the visual suite.

## TDD evidence

The inherited API-center behavior tests were present before this handoff. The new behavior discovered during visual/a11y review followed a strict red/green cycle:

1. Added the mobile Playwright regression `the mobile API navigation keeps keyboard focus inside the open drawer`.
2. RED: `pnpm exec playwright test tests/api-center.spec.ts --project=mobile-chromium --grep 'keeps keyboard focus'` failed because `Shift+Tab` from the close button escaped the drawer rather than focusing API Management.
3. GREEN: the API shell now traps both Tab directions within the drawer and restores the trigger on close. The same focused command passed (`1 passed`), followed by TypeScript verification.

## Verification

- Focused backend SPA fallback tests: `33 passed`.
- Full backend suite: `142 passed`; it emitted only the nine existing Alembic `path_separator` deprecation warnings.
- Full Vitest suite: `3 files, 57 passed`.
- TypeScript: `pnpm run typecheck` exited 0.
- Production build: `pnpm run build` exited 0; regenerated schema and emitted FastAPI's ignored SPA bundle (`78` modules transformed).
- OpenAPI consistency: the checked-in JSON parsed identically to `create_app().openapi()`; generation of `schema.d.ts` completed successfully.
- API-center Playwright: `4 passed` across desktop and phone.
- Full Playwright: `70 passed, 4 intentional project-specific skips`.
- Visual matrix: exactly `48 passed` captures: 6 pages (home/new/list/detail/docs/keys) × desktop 1440×900 and phone × zh/en × light/dark. Artifacts are intentionally ignored at `frontend/test-results/**/visual-matrix/`; the last matrix produced 48 PNGs there, all with controlled route fixtures and no user data or copied assets.
- Visual/a11y scan covered centered desktop layout, sticky TOC, phone collapse, create/revoke modal semantics, contrast checks, keyboard drawer containment, and no horizontal overflow.
- `git diff --check` exited 0.

## Independent review follow-up

An independent final review found and verified four improvements before commit: API UI deep links now accept a trailing slash; API lifecycle docs correctly include `uploading` cancellation; the English upload step says `multipart field`; and all API-key dialog close paths restore their invoking control. The final Playwright fixture also waits for the authenticated API-management heading before its contrast probe, removing a phone-only async race without weakening any product assertion.

`uv run python scripts/validate_v3_presets.py` remains unable to run in this checkout because the supplied local sample bundle is incomplete: `local-assets/sample-bundle/data/outputs/v3/group_04/report.json` is absent. This is independent of Task 6; the complete Python test suite above passed.

## Files

- API routes/UI: `frontend/src/App.tsx`, `frontend/src/components/ApiShell.tsx`, `frontend/src/pages/ApiDocsPage.tsx`, `frontend/src/pages/ApiKeysPage.tsx`, `frontend/src/apiCenter/api.ts`, `frontend/src/apiCenter/copy.ts`, `frontend/src/styles.css`
- Contracts/integration: `openapi.json`, `frontend/src/generated/schema.d.ts`, `frontend/src/api.ts`, `frontend/vite.config.ts`, `app/main.py`
- Tests/QA: `frontend/src/ApiCenter.test.tsx`, `frontend/tests/api-center.spec.ts`, `frontend/tests/visual-matrix.spec.ts`, `tests/test_app.py`
- Documentation/tooling: `README.md`, `frontend/package.json`

## Self-review

- Contract/security: API docs use only actual `/api/v1/tasks` routes and backend media kinds; key rows have only prefix/last-four metadata. The new secret stays in component state only until its explicit acknowledgement and no fake historical-secret copy action exists.
- Routing: documentation is public, management is protected, production deep links return the built SPA, and API typos remain API errors rather than HTML.
- Scope/copyright: the shell contains only Docs/Management; it adds no excluded header or product areas. All visual work is CSS/SVG/native application UI; no MinerU material or user artifacts is committed.
- Accessibility/responsiveness: semantic landmarks/headings/labels/status feedback, modal focus loops/Escape, drawer focus containment/Escape/trigger restoration, sticky desktop TOC, and phone overflow checks are covered by deterministic browser tests.
