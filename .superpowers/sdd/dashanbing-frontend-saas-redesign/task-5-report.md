# Task 5 implementer report

## Scope delivered

- Replaced the authenticated workspace placeholder with real nested routes for `/workspace/new`, `/workspace/tasks`, `/workspace/tasks/:taskId`, `/workspace/examples/:presetId`, and `/workspace/settings`, while preserving the Task 4 providers, route guard, auth race protections, theme/locale behavior, tokens, brand, and API-key placeholder boundary.
- Added an original DaShanBing workspace shell with a fixed 256 px desktop rail, 82 px tablet rail, phone drawer and bottom actions, recent tasks, account identity, and the exact GitHub/API/settings actions. The shell contains no Collections, client/download, promotional, billing, team, webhook, or storage controls.
- Added staged task creation against the real `/api/v1/tasks` contract: lazy draft creation, title and quick/full mode, exact `enrollment_video` and `cam_01`–`cam_04` slots, multipart XHR PUT uploads with byte progress, independent success/error/retry/replace UI, atomic-server-state submit gating, explicit submit, and all four real presets. Slot writes are serialized because the backend deliberately puts the draft into `uploading` during each replacement; the card states remain independent.
- Added the task library with `q`, `status`, `mode`, `page`, and `page_size` URL/query behavior, dense desktop table, phone cards, state chips, pagination, detail navigation, and allowed cancel/retry/delete actions behind named modal confirmations.
- Added a stable task result workspace with phase/camera tabs and video player on the left, summary/timeline/JSON views on the right, in-place queued/running progress, generation-safe polling that stops at terminal state or navigation, result error/retry handling, and a JSON download only after a completed result is available.
- Reused the result workspace for preset detail and wired real `/api/v1/tasks/from-preset` execution. Settings reads only `/api/v1/account/usage` and renders quota/retention plus the existing local locale/theme preferences.
- Added responsive and keyboard behavior: drawer initial focus, Escape and navigation focus restoration, explicit drawer control relationship, visible focus for selects/radios/file targets, reduced-motion inheritance, mobile cards, and horizontal-overflow assertions.
- All production requests use cookie credentials; uploads use `XMLHttpRequest.withCredentials`. No production mock business behavior, copied imagery, or third-party assets were introduced. The supplied MinerU screenshots informed spacing and density only.

## RED evidence

1. Initial Task 5 component run, after adding focused route/workflow tests but before replacing the protected scaffold:
   - Result: `1 failed` test file with `5 failed` Task 5 tests; all `22` existing Task 4 tests remained green.
   - Failures named the missing creation route, staged upload recovery/gating, list filters/actions, task result polling/media, preset execution, and settings behavior.
2. Backend state-machine regression:
   - Command: `pnpm vitest run src/Workspace.test.tsx -t "serializes slot writes"`
   - Result: `1 failed`; two XHR slot PUTs were active together when the backend permits one draft replacement at a time.
3. Poll lifecycle regression:
   - Command: `pnpm vitest run src/Workspace.test.tsx -t "does not schedule another poll"`
   - Result: `1 failed`; a deferred queued response armed a second poll after the detail route had unmounted (`2` calls instead of `1`).
4. Phone drawer keyboard regressions:
   - Focused Playwright initially showed that opening the drawer did not focus its first route.
   - The later navigation-close regression failed because focus stayed on the translated-offscreen task link instead of returning to the menu trigger.

## GREEN evidence

- Focused upload serialization: `1 passed`, `7 skipped`.
- Focused post-unmount polling stop: `1 passed`, `6 skipped` at that point in the suite.
- Focused stale-auth regression after introducing the two legitimate task-list requests: `1 passed`, `21 skipped`; the pre-existing test now asserts the exact five requests and their endpoint counts rather than weakening its previous total-call assertion.
- Focused phone drawer keyboard/geometry run: `1 passed` on mobile Chromium.
- Task 5 Playwright suite: `6 passed`, `2 intentional project skips` across desktop Chromium and iPhone 13 Chromium.
- Focused review-fix component suite: `1 passed` file, `28 passed` Task 5 tests.
- Full component suite before final report: `2 passed` files, `50 passed` tests.
- Full browser suite before final report: `17 passed`, `3 intentional project skips` across both configured projects.
- TypeScript: `pnpm run typecheck` exited 0.
- Production build: `pnpm run build` exited 0, regenerated the existing schema with no diff, transformed `74` modules, and emitted the Vite bundle to the existing ignored FastAPI frontend output directory.
- Diff hygiene: `git diff --check` exited 0.

## Files

- Routing/shell: `frontend/src/App.tsx`, `frontend/src/components/WorkspaceShell.tsx`, `frontend/src/components/Icon.tsx`
- Workspace API/types/copy/hooks: `frontend/src/session.ts`, `frontend/src/workspace/api.ts`, `frontend/src/workspace/types.ts`, `frontend/src/workspace/copy.ts`, `frontend/src/workspace/labels.ts`, `frontend/src/workspace/useLoadable.ts`, `frontend/src/workspace/useWorkspaceCopy.ts`
- Shared workspace UI: `frontend/src/components/ConfirmDialog.tsx`, `frontend/src/components/PresetCards.tsx`, `frontend/src/components/ResultWorkspace.tsx`, `frontend/src/components/StatusChip.tsx`, `frontend/src/components/WorkspaceState.tsx`
- Pages: `frontend/src/pages/NewTaskPage.tsx`, `frontend/src/pages/TaskListPage.tsx`, `frontend/src/pages/TaskDetailPage.tsx`, `frontend/src/pages/ExampleDetailPage.tsx`, `frontend/src/pages/SettingsPage.tsx`
- Styling/tests: `frontend/src/styles.css`, `frontend/src/Workspace.test.tsx`, `frontend/src/App.test.tsx`, `frontend/src/test/setup.ts`, `frontend/tests/public-foundation.spec.ts`, `frontend/tests/workspace.spec.ts`

## Self-review

- Requirement scan: every Task 5 route and workflow is represented. The only API surface outside Task 5 is the preserved Task 4 `/api/keys` scaffold and an ordinary document navigation link to `/api/docs`; Task 6 still owns both shells and their content.
- Contract scan: task and account fields were checked directly against current backend route/model/test definitions. List aliases, slot names, permitted lifecycle actions, task states, result/media URLs, usage fields, and preset requests match those definitions. The narrow types intentionally live outside the generated schema until Task 6.
- Async scan: simultaneous initial selections share one draft creation promise; input PUTs execute in backend-safe sequence; a failed slot cannot block later queued writes; task inputs returned by the server remain authoritative; polling never overlaps and cannot re-arm or update state after unmount/task-generation change.
- Auth regression scan: all task/account fetches include `credentials: "include"`; uploads set `withCredentials`; the existing stale-bootstrap test remains exact by accounting for the shell recent request and task-page request separately.
- Accessibility/responsive scan: semantic navigation, headings, labels, progress bars, tab roles and selection, named modal confirmations, keyboard drawer behavior, persisted-locale first render, desktop 256 px geometry, phone bottom navigation/cards, and no phone horizontal overflow are covered. Task 4 auth and public behavior remains in the full browser/component suites.
- Copyright/scope scan: preset/court art is original CSS geometry and existing DaShanBing SVG/icon language. No screenshot pixels, MinerU prose/brand/assets, client/collection/promotion UI, or fake production results were added.

## Review fix round 1

All eleven review findings were handled with focused regression coverage:

1. Task detail is keyed by `taskId` and also clears task/result/media/error/loading state at the start of each generation. A same-route completed A → deferred queued B regression proves A's result, media, and JSON disappear immediately.
2. Lazy creation snapshots the trimmed title/mode and disables both controls as soon as draft creation begins. A deferred POST regression verifies the displayed values cannot diverge from the submitted draft.
3. Cancel/retry/delete no longer patch the current row locally. Success and `409` conflicts refresh the authoritative filtered query; deleting the only row on a later page moves down one page before loading. Regressions cover failed-filter retry, cancel-filter refresh, conflict refresh, and a page-two last-row deletion.
4. A small shared session-expiry signal connects workspace fetch and upload XHR `401` responses to `AuthProvider`, which invalidates auth without issuing a refresh loop. Both ordinary request and upload-cookie expiry redirect through the existing guarded login flow. Task 4 mocks that intentionally exercise successful authenticated navigation now return valid task-list responses rather than an accidental catch-all `401`; their original assertions remain.
5. `AbortSignal` is threaded through task and result reads. Each route generation/retry owns one controller, polling is sequential and single-flight, and cleanup aborts task/result work and timers. Deferred route-change, retry, and unmount regressions assert the exact signals and absence of stale content.
6. Task-list draft filter controls resynchronize from the current URL query whenever browser history changes. A two-entry back-navigation regression checks `q`, `status`, and `mode` together.
7. `ConfirmDialog` now has named/described modal semantics, initial cancel focus, Escape close, forward/backward focus containment, busy-state protection, and trigger focus restoration. Keyboard regressions cover initial focus, containment (including externally displaced focus), Escape, and restoration.
8. The closed phone drawer is inert and accessibility-hidden. The open drawer is a modal with focus containment, Escape, and menu-trigger restoration; the page and bottom actions are inert while open. Playwright verifies closed-state exclusion and both tab-wrap directions.
9. Result workspace has distinct localized empty-state copy for draft, uploading, queued, running, completed-without-result, failed, canceled, and expired.
10. Task title is required and limited to 120 Unicode code points using code-point counting rather than native UTF-16 `maxLength`. Structured FastAPI `422` issues are preserved and mapped to localized title feedback before upload begins. The regression exercises 121 and 120 basketball emoji plus a first-upload server `422`.
11. Status, mode, source, result action/outcome, and all four preset titles/descriptions/tags are rendered through locale mappings while API identifiers and request values remain unchanged. Completion history and confirmation copy also avoid leaking raw identifiers. The backend list route has no source query parameter, so no unsupported source filter was invented; source identifiers are localized wherever the backend exposes them for display.

### Review RED/GREEN evidence

- Initial focused review suite before implementation: `27` Task 5 tests ran, `16 failed` and `11 passed`. The failures spanned pending-create locking, code-point/server validation, fetch/XHR expiry, authoritative lifecycle refresh/paging, history synchronization, modal/drawer semantics, detail generation/abort behavior, explicit task states, and bilingual identifiers.
- Modal regressions: one focused run failed because the dialog message was not connected by `aria-describedby`; a later focus-displacement run failed because keyboard focus could resume outside the modal. Both passed after wiring the stable description id and window-scoped modal key containment.
- Final localization edge regression: focused run failed on the raw timeline value `completed`; it passed after using the stable status label mapping.
- Full Task 4/5 component run exposed two auth fixtures whose unexpected task-list calls returned catch-all `401`s; after giving those authenticated flows valid empty task responses, the unmodified login/race assertions and new expiry behavior all pass.
- Full browser run exposed the Task 4 mobile auth assertion trying to reach the deliberately inert closed drawer. The test now opens the drawer on phone before making the same account-link assertion; focused desktop/mobile rerun passed `2/2`.
- Final focused Task 5 component result: `28 passed`.
- Final full component result: `50 passed` across `2` files.
- Final focused Task 5 browser result: `6 passed`, `2 intentional project skips`.
- Final full browser result: `17 passed`, `3 intentional project skips` across desktop Chromium and iPhone 13 Chromium.
- Final TypeScript and production build both exited `0`; build transformed `74` modules and generated no checked-in schema diff.
- Final `git diff --check` exited `0`.

### Review self-check

- Async/auth: every new controller is disposed on task generation change, retry, or unmount; result fetches cannot outlive their owning task; polling cannot overlap; every workspace fetch/XHR `401` takes the same auth invalidation path without a second `/users/me` request.
- State/URL: task-specific UI is generation-scoped, draft metadata is frozen during creation, list state is server-authoritative, page correction preserves filters/page size, and form controls follow history rather than retaining stale local values.
- Accessibility/responsive: confirmation and drawer focus loops were keyboard-tested; closed mobile navigation is absent from the accessibility tree and tab order; desktop navigation remains directly available.
- Contract/localization: title limits match the backend's 120-code-point validator, FastAPI issue structure is retained narrowly, raw API values remain untouched, and only displayed stable identifiers are localized. No OpenAPI/API-key/docs implementation was added.

## Known handoff note

`openapi.json` and `frontend/src/generated/schema.d.ts` remain unchanged, as required: Task 6 owns final OpenAPI export and generated-client refresh. The production build runs the existing generator, but the checked-in result had no diff. API documentation and API-key management are intentionally not implemented here.
