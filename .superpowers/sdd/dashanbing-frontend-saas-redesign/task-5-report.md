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
- Full component suite before final report: `2 passed` files, `31 passed` tests.
- Full browser suite before final report: `17 passed`, `3 intentional project skips` across both configured projects.
- TypeScript: `pnpm run typecheck` exited 0.
- Production build: `pnpm run build` exited 0, regenerated the existing schema with no diff, transformed `72` modules, and emitted the Vite bundle to the existing ignored FastAPI frontend output directory.
- Diff hygiene: `git diff --check` exited 0.

## Files

- Routing/shell: `frontend/src/App.tsx`, `frontend/src/components/WorkspaceShell.tsx`, `frontend/src/components/Icon.tsx`
- Workspace API/types/copy/hooks: `frontend/src/workspace/api.ts`, `frontend/src/workspace/types.ts`, `frontend/src/workspace/copy.ts`, `frontend/src/workspace/useLoadable.ts`, `frontend/src/workspace/useWorkspaceCopy.ts`
- Shared workspace UI: `frontend/src/components/ConfirmDialog.tsx`, `frontend/src/components/PresetCards.tsx`, `frontend/src/components/ResultWorkspace.tsx`, `frontend/src/components/StatusChip.tsx`, `frontend/src/components/WorkspaceState.tsx`
- Pages: `frontend/src/pages/NewTaskPage.tsx`, `frontend/src/pages/TaskListPage.tsx`, `frontend/src/pages/TaskDetailPage.tsx`, `frontend/src/pages/ExampleDetailPage.tsx`, `frontend/src/pages/SettingsPage.tsx`
- Styling/tests: `frontend/src/styles.css`, `frontend/src/Workspace.test.tsx`, `frontend/src/App.test.tsx`, `frontend/src/test/setup.ts`, `frontend/tests/workspace.spec.ts`

## Self-review

- Requirement scan: every Task 5 route and workflow is represented. The only API surface outside Task 5 is the preserved Task 4 `/api/keys` scaffold and an ordinary document navigation link to `/api/docs`; Task 6 still owns both shells and their content.
- Contract scan: task and account fields were checked directly against current backend route/model/test definitions. List aliases, slot names, permitted lifecycle actions, task states, result/media URLs, usage fields, and preset requests match those definitions. The narrow types intentionally live outside the generated schema until Task 6.
- Async scan: simultaneous initial selections share one draft creation promise; input PUTs execute in backend-safe sequence; a failed slot cannot block later queued writes; task inputs returned by the server remain authoritative; polling never overlaps and cannot re-arm or update state after unmount/task-generation change.
- Auth regression scan: all task/account fetches include `credentials: "include"`; uploads set `withCredentials`; the existing stale-bootstrap test remains exact by accounting for the shell recent request and task-page request separately.
- Accessibility/responsive scan: semantic navigation, headings, labels, progress bars, tab roles and selection, named modal confirmations, keyboard drawer behavior, persisted-locale first render, desktop 256 px geometry, phone bottom navigation/cards, and no phone horizontal overflow are covered. Task 4 auth and public behavior remains in the full browser/component suites.
- Copyright/scope scan: preset/court art is original CSS geometry and existing DaShanBing SVG/icon language. No screenshot pixels, MinerU prose/brand/assets, client/collection/promotion UI, or fake production results were added.

## Known handoff note

`openapi.json` and `frontend/src/generated/schema.d.ts` remain unchanged, as required: Task 6 owns final OpenAPI export and generated-client refresh. The production build runs the existing generator, but the checked-in result had no diff. API documentation and API-key management are intentionally not implemented here.
