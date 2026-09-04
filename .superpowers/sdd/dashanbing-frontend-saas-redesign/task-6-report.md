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

### Review round 1

The review fixes used additional RED/GREEN coverage without weakening existing assertions:

1. `tests/test_app.py` first failed for `/api/` (JSON 404) and root `theme-bootstrap.js` / `favicon.svg` (SPA HTML). The explicit, allow-listed `FileResponse` routes now pass with the declared bodies, media types, and `public, max-age=3600` cache policy while unknown API routes remain JSON 404s.
2. `ApiCenter.test.tsx` first failed for an absent `python3` polling loop, raw Chinese retention units, no keyboard-selectable one-time secret, and modal-scoped create failure. The guide now waits for a terminal task state before fetching the result; known retention values are localized; the secret is a labelled read-only input that selects on clipboard rejection; and create/revoke failures remain in their dialogs.
3. The busy-revoke test first failed because the dialog had no live status. It now asserts `aria-busy`, a localized `role=status`, disabled controls, and that Tab stays on the focusable dialog root while the request is pending.
4. `Workspace.test.tsx` first failed because worker `Complete` was rendered unchanged in Chinese. Stable messages are now mapped per locale, while unknown server strings pass through unchanged.
5. The first deterministic visual-matrix run found an ambiguous list readiness selector. It was replaced with route-specific list heading/table readiness, then the exact 48-case matrix passed. The runner has a fixed UTC timezone and each route waits for its controlled fixture before capture.

## Verification

- Focused backend SPA fallback tests: `38 passed`.
- Full backend suite: `145 passed`; it emitted only the nine existing Alembic `path_separator` deprecation warnings.
- Full Vitest suite: `3 files, 62 passed`.
- TypeScript: `pnpm exec tsc --noEmit` exited 0.
- Production build: `pnpm build` exited 0; regenerated schema and emitted FastAPI's ignored SPA bundle (`78` modules transformed).
- OpenAPI consistency: `uv run python scripts/export_openapi.py` and `pnpm run generate:api` completed; `git diff --exit-code -- openapi.json frontend/src/generated/schema.d.ts` exited 0.
- API-center Playwright: `4 passed` on the mobile project, including mobile table header/label coverage.
- Full Playwright: `71 passed, 5 intentional project-specific skips`.
- Visual matrix: exactly `48 passed` captures: 6 pages (home/new/list/detail/docs/keys) × desktop 1440×900 and phone × zh/en × light/dark. Artifacts are intentionally ignored at `frontend/test-results/**/visual-matrix/`; the last matrix produced 48 PNGs there, all with controlled route fixtures and no user data or copied assets.
- Visual/a11y scan covered centered desktop layout, sticky TOC, phone collapse, create/revoke modal semantics, contrast checks, keyboard drawer containment, and no horizontal overflow.
- `git diff --check` exited 0.

## Review round 1 follow-up

All nine review findings are addressed: root Vite assets are allow-listed and cached correctly; the Curl walkthrough polls terminal status safely; README presents registration and `/tasks`; `/api/` deep-links to the SPA; API-key dialogs keep errors/live busy state/focus inside; clipboard fallback is keyboard usable; phone key cards retain semantic column headers and visible labels; the visual matrix has fixed timezone plus route-fixture readiness; Chinese retention durations and known worker progress messages are localized. The final browser run also retained no-overflow, sticky/collapsed navigation, modal, contrast, and keyboard assertions.

## Review round 2 follow-up

The API-key modal now restores focus only to a connected, enabled invoking control. When a successful fifth key creation disables that control it moves focus to the stable API-key heading; when a revocation removes its row action it moves focus to the enabled create control after refreshed data renders. Controlled Chromium tests cover both flows. Visual readiness now waits for the authenticated `coach` identity in either public or workspace header, with a delayed-auth regression, before all 48 captures. Worker stage localization covers every currently emitted worker, task, supervisor, cancellation, restart, expiry, and dynamic `Validating {slot}` value; both TaskDetailPage and ResultWorkspace use the same safe-fallback helper. The API guide now states the copyable `python3 -m pip install requests` prerequisite in both languages, and README invokes the project exporter with `uv run python`.

Final review-round verification: 145 backend tests passed (nine existing Alembic warnings), 63 Vitest tests passed, TypeScript and production build passed, OpenAPI/schema generation had no drift, and the full Playwright suite passed 74 tests with 6 intentional project-specific skips. The visual-matrix test produced exactly 48 unique PNG captures at `frontend/test-results/**/visual-matrix/` plus two non-capture delayed-auth regressions.

## Review round 3 follow-up

The create flow now tracks its post-create key/usage refresh separately from the one-time secret. If acknowledgement occurs before that refresh settles, the secret is still immediately discarded, while focus restoration is armed until the refreshed DOM renders; it then selects the live create control or stable key-list heading. A controlled Chromium regression delays that refresh for 900 ms, dismisses the fifth-key secret immediately, and proves focus ends on the 5/5 heading rather than `BODY`. Focused Chromium, API-center Vitest (63 tests), TypeScript, and diff checks passed.

`uv run python scripts/validate_v3_presets.py` remains unable to run in this checkout because the supplied local sample bundle is incomplete: `local-assets/sample-bundle/data/outputs/v3/group_04/report.json` is absent. This is independent of Task 6; the complete Python test suite above passed.

## Files

- API routes/UI: `frontend/src/App.tsx`, `frontend/src/components/ApiShell.tsx`, `frontend/src/pages/ApiDocsPage.tsx`, `frontend/src/pages/ApiKeysPage.tsx`, `frontend/src/apiCenter/api.ts`, `frontend/src/apiCenter/copy.ts`, `frontend/src/styles.css`, `frontend/src/workspace/labels.ts`, `frontend/src/pages/TaskDetailPage.tsx`
- Contracts/integration: `openapi.json`, `frontend/src/generated/schema.d.ts`, `frontend/src/api.ts`, `frontend/vite.config.ts`, `app/main.py`
- Tests/QA: `frontend/src/ApiCenter.test.tsx`, `frontend/src/Workspace.test.tsx`, `frontend/tests/api-center.spec.ts`, `frontend/tests/visual-matrix.spec.ts`, `frontend/playwright.config.ts`, `tests/test_app.py`
- Documentation/tooling: `README.md`, `frontend/package.json`

## Self-review

- Contract/security: API docs use only actual `/api/v1/tasks` routes and backend media kinds; key rows have only prefix/last-four metadata. The new secret stays in component state only until its explicit acknowledgement and no fake historical-secret copy action exists.
- Routing: documentation is public, management is protected, production deep links return the built SPA, and API typos remain API errors rather than HTML.
- Scope/copyright: the shell contains only Docs/Management; it adds no excluded header or product areas. All visual work is CSS/SVG/native application UI; no MinerU material or user artifacts is committed.
- Accessibility/responsiveness: semantic landmarks/headings/labels/status feedback, modal focus loops/Escape, drawer focus containment/Escape/trigger restoration, sticky desktop TOC, and phone overflow checks are covered by deterministic browser tests.
