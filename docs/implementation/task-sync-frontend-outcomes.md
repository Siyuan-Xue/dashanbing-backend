# Registration and video synchronization frontend — scoped outcomes

Date: 2026-09-07. Worktree: `/Users/milesxue/Documents/ChatGPT/dashanbing-backend/.worktrees/ai-analyst`, branch `codex/ai-analyst`.

Implemented against `docs/implementation/task-sync-contract.md` and `app/sync_schemas.py`. No commits, pushes, deployment, production services, secrets, or real user videos were used. Other agents' files were left intact. No full acceptance or optimization suite was run.

## Changed files

Implementation:

- `frontend/src/pages/NewTaskPage.tsx`: shared WorkspaceSelect registration method and nullable 1–6 count; sequential default; create/PATCH/restore fields; preserve title/upload ordering and draft write queue; submission requires all inputs, count and confirmed sync; backend replacement status; explicit failed/interrupted return-to-input; refresh persisted status after cancel, including stale confirmation conflicts.
- `frontend/src/workspace/api.ts`: optional typed registration arguments; extended task responses; return-to-input; display structured backend error messages.
- `frontend/src/lib/task-sync.ts`: interim optional task types, exact sync/preview/frame/confirm contract, version-bound requests, measured-frame lookup and cam_03 common-overlap calculations for local preview. Persisted offsets are calculated by the backend.
- `frontend/src/components/VideoSyncDialog.tsx`: desktop four videos; mobile cam_03 reference and selectable other camera; measured server-frame overlay; play/pause/seek/previous/next/select; initial pause; common-overlap linked playback; explicit confirmation; cancel/Escape discard local selections; focus trap/return; preparation polling/retry; stale, frame and playback failure handling.
- `frontend/src/styles/video-sync.css`: scoped registration/dialog styles, responsive 2×2 and full-window mobile layout, compact labeled Lucide controls.

Tests and fixtures:

- `frontend/src/pages/NewTaskPage.sync.test.tsx` — six page interactions.
- `frontend/src/components/VideoSyncDialog.test.tsx` — nine dialog interactions.
- `frontend/src/lib/task-sync.test.ts` — measured-frame boundaries and common-overlap arithmetic.
- `frontend/src/test/taskSyncFixture.ts` — synthetic network/media metadata fixture, with no production I/O.
- `frontend/src/test/TaskSyncHarness.tsx` — isolated browser fixture, never imported by the app.
- `frontend/scripts/check-task-sync-layout.mjs` — localhost-only browser component check; all API and video responses are synthetic; dedicated Vite cache and port.
- This outcomes document.

## Commands and observed results

Run frontend commands from `/Users/milesxue/Documents/ChatGPT/dashanbing-backend/.worktrees/ai-analyst/frontend`. This shell lacks `node` on its default PATH, so commands used:

```sh
export PATH=/Users/milesxue/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH
```

1. New scoped tests:

```sh
pnpm exec vitest run src/pages/NewTaskPage.sync.test.tsx src/lib/task-sync.test.ts src/components/VideoSyncDialog.test.tsx --reporter=dot
```

Result: **3 files passed; 17 tests passed**, exit 0. Last run duration 3.26s. Log: `/tmp/task-sync-scoped.log`.

2. Existing draft/upload queue regressions:

```sh
pnpm exec vitest run src/DraftTask.test.tsx -t 'uploads before naming|late metadata responses|queued edits retain' --reporter=dot
```

Result: **3 passed, 4 intentionally skipped by the filter**, exit 0. Duration 3.82s. Log: `/tmp/task-sync-existing-drafts.log`. This was not the entire existing draft suite.

3. Type checking, without regenerating schemas:

```sh
pnpm exec tsc -p tsconfig.app.json --noEmit --pretty false
```

Result: **exit 0, no diagnostics** after the final code change. Log: `/tmp/task-sync-types.log`. An earlier run caught two missing test `this` annotations (fixed here) and an in-progress `AdminConfirm.tsx` error (not edited here; absent in the later check).

4. Isolated browser dimensions and focus:

```sh
pnpm exec node scripts/check-task-sync-layout.mjs
```

Result: **exit 0** for 1280×900 Chinese, 320×568 Chinese and 320×568 English. Desktop showed four panels in 2×2; mobile showed cam_03 first and one other camera. Visible controls and labels fit without horizontal overflow. Escape restored the opener. No browser page errors. Screenshots: `/tmp/task-sync-1280-zh.png`, `/tmp/task-sync-320-zh.png`, `/tmp/task-sync-320-en.png`; log `/tmp/task-sync-layout.log`.

The initial localhost launch hit sandbox `EPERM`; the same synthetic-only operation was approved for local execution. The first browser run reproduced mobile footer clipping caused by the existing backdrop rule overriding mobile padding. The scoped selector fixed that issue. This checks component layout using generated synthetic WebM/JPEG; it does **not** validate backend conversion, actual uploaded videos, or real camera synchronization.

5. Tracked-file whitespace check (run from worktree root):

```sh
git diff --check -- frontend/src/pages/NewTaskPage.tsx frontend/src/workspace/api.ts
```

Result: **exit 0**.

## Test-first and implementation debugging record

- Before implementation, the five initial page tests failed for missing registration selectors, submission gating, replacement status and correction entry behavior.
- The new dialog/helper tests were written before their modules; the first run could not resolve those not-yet-created modules. This was an import failure, not a passing behavior check.
- During implementation, the mobile accessible name test exposed concatenated selection text; explicit accessible labels fixed it.
- A new playback rejection test failed because a rejected linked play still left confirmation enabled. The implementation now stops the group and requires reloading after that failure.
- A new stale/cancel page test failed because the parent page retained its previous confirmed status. Cancel now reloads the backend task and disables submission during refresh.
- Final scoped results are recorded above. No passes are inferred for omitted suites.

## Parent integration and limits

- `TaskDetailPage.tsx` currently redirects only draft/uploading tasks to the input page. The parent should add a failed/interrupted task action linking to `/workspace/new?draft={id}`. This owned page already presents an explicit “修改注册输入” action and calls `POST /tasks/{id}/return-to-input`; it does not silently reopen a failed task.
- The four skipped existing `DraftTask.test.tsx` submission cases use fixtures that omit registration count and sync confirmation. Update those fixtures to the new submission contract before running that suite in full; do not weaken the new submission gate to satisfy them.
- Parent-owned OpenAPI/schema regeneration and ApiDocs edits were not touched. Optional manual extensions are compatible with the interim schema.
- Backend route/conversion/version-snapshot tests belong to the backend agent. This frontend scope did not run backend integration or production/media acceptance.

## 2026-09-07 follow-up — legacy fixtures and regenerated schema

The user authorized a bounded legacy-test update, then explicitly authorized two production-source adjustments after schema regeneration. This entry supersedes the earlier pending legacy-fixture item; the earlier commands/results remain historical evidence.

### Changes and reasons

- `frontend/src/DraftTask.test.tsx`: incomplete drafts now explicitly carry sequential registration, null count and unconfirmed sync. Only the four existing submit-ready fixtures receive `expected_persons: 2` and `sync_status: confirmed`, representing already-uploaded and previously-confirmed drafts. The simulated submit endpoint rejects missing registration, missing files and missing/currently stale sync. Original title, save-failure, reload, upload queue and navigation assertions are unchanged.
- `frontend/src/Workspace.test.tsx`: the common task fixture includes generated required fields and returns `Task`; input slots use generated `TaskSlot` types. The staged upload server persists registration PATCHes, retains uploaded inputs, invalidates camera versions and confirms only through the sync PUT contract. Its existing workflow now selects a count and explicitly selects/confirms all four camera frames before the original submit assertions. The preset-create response includes registration/count/confirmed-sync metadata representing its prepared manifest. Existing preset request assertions remain unchanged.
- `frontend/tests/draft-upload.spec.ts`: task creation/restoration/upload/PATCH/submit responses carry registration and sync state. Existing upload-resume tests explicitly perform sync through the UI before submitting. The two already-complete restored-draft layout fixtures include their saved count and confirmation state. Original upload, replacement, language/theme, reload, overflow and navigation assertions remain.
- `frontend/tests/workspace.spec.ts`: the staged upload fixture now persists its count and task state, serves the exact sync contract, and requires explicit synchronization before the original submit assertions. Other workspace E2E scenarios are unchanged.
- `frontend/src/test/legacyTaskSyncFixture.ts`: shared test-only contract responses for GET sync, POST/GET preview, versioned video/frame requests and PUT confirmation. Confirmation requires current versions and four measured timestamps; upload responses never automatically claim confirmation. Submission fixture validation rejects invalid count/method, missing inputs and unconfirmed/stale sync.
- `frontend/src/test/legacySyncMediaFixture.ts`: embedded generated 320×180, 25 fps, 0.4-second solid-color H.264 clip and its JPEG first frame. It contains no user data. This supplies decodable media for browser fixtures without adding Node filesystem dependencies to frontend test compilation.
- `frontend/tests/task-sync.fixture.ts`: test-only response adapter and desktop/mobile UI prerequisite helper, using the actual count combobox, cam_03 reference, mobile camera tabs, frame selection and explicit confirm button.
- `frontend/src/workspace/api.create.test.ts`: request-boundary checks for omitted registration defaulting to sequential and preservation of explicit lineup/count selection.
- Authorized source adjustment: `frontend/src/workspace/api.ts` now explicitly includes `enrollment_mode: sequential` before optional registration overrides, satisfying regenerated `TaskCreate` typing and the backend default.
- Authorized copy adjustment: removed the four Chinese full stops from the new explanatory strings in `frontend/src/pages/NewTaskPage.tsx`; behavior and English strings are unchanged.
- Inspected `frontend/src/App.test.tsx` and `frontend/tests/public-foundation.spec.ts`: these have auth/account-registration flows and empty task-list responses, with no valid task-create/submit fixture requiring enrollment fields. They were left unchanged. TaskDetail return-to-input and ApiDocs/CurrentLimits remain parent-owned.

### Scoped verification

Commands ran from the frontend directory with the bundled Node PATH described above. No full build, full acceptance suite, visual baseline update, optimization pass, commit, push or deployment was run.

Initial targeted legacy run: **5 failed**, because the original submit fixtures omitted count/sync prerequisites. The new default-create request test initially produced **1 failed / 1 passed**, showing the omitted `enrollment_mode` field before its source fix.

Final targeted unit command:

```sh
pnpm exec vitest run src/DraftTask.test.tsx src/Workspace.test.tsx src/workspace/api.create.test.ts -t 'uploads before naming|opens a draft from task history|does not submit a draft with unsaved metadata|enforces the title length at submission|late metadata responses|late submission cannot navigate|queued edits retain|serializes slot writes|recovers a failed slot|reuses the result workspace for presets|create sends|create preserves' --reporter=dot
```

Observed: **12 passed, 35 skipped by the explicit filter, 3 files passed**, exit 0, 7.83s. All seven DraftTask tests were included. Log: `/tmp/legacy-sync-fixtures-scoped.log`.

Desktop fixture command:

```sh
PLAYWRIGHT_BASE_URL=http://127.0.0.1:53176 pnpm exec playwright test tests/draft-upload.spec.ts tests/workspace.spec.ts --project=desktop-chromium --grep 'draft uploads resume|restored draft layout|staged browser upload' --workers=1 --retries=0 --max-failures=1 --output=/tmp/legacy-sync-playwright-desktop
```

Observed: **7 passed**, exit 0, 9.0s. Covers the four existing language/theme upload cases, two existing restored-draft layouts and the staged upload retry/submit case. Log: `/tmp/legacy-sync-e2e-desktop.log`.

Mobile fixture command:

```sh
PLAYWRIGHT_BASE_URL=http://127.0.0.1:53176 pnpm exec playwright test tests/draft-upload.spec.ts --project=mobile-chromium --grep 'draft uploads resume' --workers=1 --retries=0 --max-failures=1 --output=/tmp/legacy-sync-playwright-mobile
```

Observed: **4 passed**, exit 0, 10.0s. Log: `/tmp/legacy-sync-e2e-mobile.log`.

An initial desktop fixture run was interrupted after reproducing a helper locator mismatch: the wrapped native select was present as the “注册人数” combobox, but an exact `getByLabel` match timed out. The helper now uses that actual combobox role/name. This was test-fixture debugging; no application selector or validation was weakened. Playwright emitted only the environment warning that `NO_COLOR` is ignored when `FORCE_COLOR` is set.

Schema/type command:

```sh
pnpm exec tsc -p tsconfig.app.json --noEmit --pretty false
```

Observed after the final fixture type corrections: **exit 0, no diagnostics**. Log: `/tmp/legacy-sync-fixtures-types.log`. During implementation TSC identified the required create default, literal fixture-state narrowing, a string-vs-TaskSlot fixture mismatch and an unnecessary Node filesystem import in a frontend test helper; these were corrected within the authorized files.

All browser API/media responses were mocked with contract-shaped data and generated synthetic media. These outcomes do not claim backend conversion, real-input synchronization, or full application acceptance.
