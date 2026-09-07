# Administrator frontend implementation record

Worktree: `/Users/milesxue/Documents/ChatGPT/dashanbing-backend/.worktrees/ai-analyst`
Branch: `codex/ai-analyst`

## Implemented scope

- `/admin` redirects to `/admin/overview`; six sections: overview, users, scheduling, quotas, operations, audit.
- Role-aware login/register completion, private route guards, and public account destinations. Admins cannot mount the user workspace or API key page; ordinary users see a forbidden state for admin URLs.
- Separate admin shell reuses the 260px sidebar, hover expansion, keyboard collapse, mobile drawer focus handling, locale and theme controls. Cookie logout is wired in both admin and public account controls.
- Users: username/email search, active-state filter, pagination, metadata drawer, enable/disable, revoke all sessions/API keys, and per-user quota overrides (blank removes an override).
- Scheduling: admission/pause settings, job kind/status filters, pagination, allowed-actions-based hold/release/priority/retry/backfill. Selection is one kind, at most the server bound capped at 10. Mutations use immutable confirmation targets.
- Quotas: default quotas and AI concurrency use server-provided bounds and send only changed fields. Repair budget is displayed with its UTC date.
- Overview and operations show actual returned resource/queue/usage metadata; unavailable telemetry is shown as unknown. Operations has no mutation controls.
- Audit lists actor, action, targets, reason, and time. Drawers render an explicit metadata allowlist, including safe setting changes, rather than arbitrary JSON.
- Every mutation requires a 3–500 character reason and an explicit acknowledgement. Error bodies are not shown; status codes select localized messages. Success notices require a successful API response; mutation errors keep the confirmation open.
- Admin-only CSS provides flat surfaces, 44px table headers, 14px text, 68px base rows, blue/brown-red Icon controls, and responsive table scrolling. Chinese/English and existing theme tokens are used.

## Contract

Uses `docs/implementation/admin-contract.md` and backend `app/admin_schemas.py` / `app/api/routes/admin.py` as implemented on 2026-09-07. Base `/api/v1/admin`; cookie credentials included. Mutations send JSON `reason`; force logout sends `{reason}` and handles 204. Browser supplies same-origin Origin for JSON mutations. No frontend-generated schema changes.

## Changed files in this scope

Existing files:

- `frontend/src/App.tsx`
- `frontend/src/components/PublicHeader.tsx`
- `frontend/src/components/RouteGuard.tsx`
- `frontend/src/pages/AuthPage.tsx` (the repository's combined login/register page)
- `frontend/src/providers/AuthProvider.tsx`

Added components:

- `frontend/src/components/AdminAccountMenu.tsx`
- `frontend/src/components/AdminConfirm.tsx`
- `frontend/src/components/AdminDialog.tsx`
- `frontend/src/components/AdminMetadataDrawer.tsx`
- `frontend/src/components/AdminQuotaEditor.tsx`
- `frontend/src/components/AdminRepairBudget.tsx`
- `frontend/src/components/AdminResources.tsx`
- `frontend/src/components/AdminSettingsForm.tsx`
- `frontend/src/components/AdminShared.tsx`
- `frontend/src/components/AdminShell.tsx`

Added pages:

- `frontend/src/pages/AdminPage.tsx`
- `frontend/src/pages/AdminOverviewPage.tsx`
- `frontend/src/pages/AdminUsersPage.tsx`
- `frontend/src/pages/AdminSchedulingPage.tsx`
- `frontend/src/pages/AdminQuotasPage.tsx`
- `frontend/src/pages/AdminOperationsPage.tsx`
- `frontend/src/pages/AdminAuditPage.tsx`

Added support and tests:

- `frontend/src/lib/adminApi.ts`
- `frontend/src/lib/adminCopy.ts`
- `frontend/src/lib/adminLoadable.ts`
- `frontend/src/lib/adminRole.ts`
- `frontend/src/styles/admin.css`
- `frontend/src/components/AdminControls.test.tsx`
- `frontend/src/components/AdminRouting.test.tsx`
- `frontend/src/pages/AdminPage.test.tsx`
- `docs/implementation/admin-frontend.md`

## Scoped verification outcomes

Commands ran in the worktree's `frontend` directory with bundled Node available:

```sh
export PATH=/Users/milesxue/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH
pnpm exec vitest run src/pages/AdminPage.test.tsx src/components/AdminControls.test.tsx src/components/AdminRouting.test.tsx --reporter=dot
pnpm exec vitest run src/components/AdminRouting.test.tsx --reporter=dot
pnpm exec vitest run src/App.test.tsx -t 'authentication and protected routes|account dropdown|failed logout' --reporter=dot
pnpm exec tsc -b --pretty false
```

- Tests first: routing baseline 4 expected failures / 1 ordinary-route pass; page baseline 6 expected failures against the empty shell.
- During implementation, initial test startup hit missing Node on PATH and then another agent's not-yet-created VideoSyncDialog import. The bundled runtime and subsequently landed component resolved these environment/concurrent-write blockers.
- Admin combined run at 12:13 UTC: **14 passed**. This included 6 page tests, 3 confirmation/metadata tests, and 5 routing tests.
- Added the mobile keyboard/logout routing check and an active-index navigation assertion. The assertion first reproduced the missing active nav item; `/admin` now redirects to `/admin/overview`. Its asynchronous test was adjusted to wait for that destination, rather than the intermediate `/admin` location.
- Latest page/confirmation results at 12:15 UTC: **9 passed**. Latest routing-only run at 12:15 UTC after the index assertion timing correction: **6 passed**. These cover the 15 scoped admin tests; no claim is made of a full acceptance run.
- TypeScript at 12:15 UTC: **exit 0**, no diagnostics. Earlier implementation diagnostics found and fixed the error guard's `unknown` ReactNode type and quota input accessible names that included the bounds hint.
- Existing ordinary-auth/public-account subset at 12:15 UTC: **16 passed, 1 failed, 11 skipped; 1 unhandled error**. The failing account-dropdown test visits `/api/docs`; the concurrent `CurrentLimits` component reads `.limit` from missing fixture data (`ApiDocsPage.tsx:128`). Reported to parent; that owned component and existing test fixture were not changed here. This is not recorded as a pass.

No full acceptance suite, visual matrix, live-backend/real-user-data testing, production actions, commit, push, build, schema generation, or deployment was performed. Responsive styling is implemented but no browser visual acceptance is claimed. Other agents' changes remain untouched.

## Follow-up additions (2026-09-07)

- Changed `AdminAudit.id` to `string` to match the backend UUID contract.
- Added optional overview `timings` and `errors` types plus `AdminPerformanceSummary.tsx`. Timing rows show server count/P50/P95 in seconds; missing or null percentiles display unavailable while numeric zero is preserved. Labels state successful completions today (UTC) and current failed backlog across all dates. Error categories use localized names for the backend allowlist with the coarse code alongside them.
- Added `AdminOverviewPage.test.tsx`: initial missing-summary run failed three tests; latest scoped run passed all three. TypeScript passed after the optional DTO/component addition. No source owned by another agent was changed.
- Added `frontend/scripts/capture-closeout.mjs`, its Node tests, and `frontend/scripts/README-closeout.md`. Dry-run verified the 300-page default plan and 20 role-boundary variants without reading credentials or measuring pages. Nine focused script tests passed for matrix construction, bounded smoke, argument/output safeguards, redaction, geometry, continuation after failure, actual browser identity, and API-read readiness.
- Real HTTP smoke is reserved for the parent's static-build-ready signal and requires sandbox escalation for local browser/network access. No full measurement has been run.

## Final concentrated test facts — read-only review, 2026-09-07

The entries above describe their historical implementation-stage scope. The parent subsequently ran the concentrated tests. This review only read those existing artifacts and related source; it did not rerun acceptance, modify code/tests/assertions, or convert failures into passes.

- `runtime/release-closeout/evidence/backend-tests.xml` and `backend-tests.log`: 842 tests, 817 passed, 25 failed, zero errors/skips. The 75 recorded `tests.test_admin*` cases passed. The 25 failures remain failures: 13 differences follow explicit contract changes; 12 are blocked before their intended behavior by incompatible fixtures/injection points. No new-contract product defect is established by those failures alone, but eight scoped in-flight revocation cases, three product-pipeline artifact cases, and one complete preset-generation CLI case remain unverified.
- `runtime/release-closeout/evidence/frontend-unit.json`: 263 tests, 262 passed, one failed. The failing assertion excludes the now-documented single-upload analyses endpoint. AdminControls (3), AdminRouting (6), AdminOverviewPage (3), and AdminPage (6) all recorded passed, 18 cases total. Top-level metadata reports two failed suites, while the detailed results contain one failing file/assertion; this is not counted as a second failed test.
- `runtime/release-closeout/evidence/frontend-e2e.json` and `frontend-e2e.log`: 177 expected, four unexpected, 61 skipped, zero flaky. Two API-documentation failures use the old endpoint exclusion. Two logout-retry failures stop at a global alert locator that matches both the logout error and the quota error from missing API fixtures. The subsequent retry, focus, cookie/route-clearance and refresh assertions did not execute; this review does not claim them passed or infer native Safari results.

Every failed node, source location, raw record and remaining risk is documented in [failure-triage.md](../acceptance/2026-09-07/failure-triage.md). Other formal acceptance documents remain parent-owned.
