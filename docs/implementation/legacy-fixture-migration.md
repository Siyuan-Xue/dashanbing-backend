# Bounded legacy fixture migration — implementation debugging

Worktree: `/Users/milesxue/Documents/ChatGPT/dashanbing-backend/.worktrees/ai-analyst`, branch `codex/ai-analyst`.

This is fixture migration during implementation, not final acceptance. Writes are limited to the seven assigned legacy test files, `tests/business_fixture.py`, and this record. No application, frontend, schema, migration, admin/sync test, commit, push, or production changes belong to this scope.

## Initial evidence

Before edits, a selected nine-case run across all seven assigned files returned **8 failed, 1 passed in 1.69s** (exit 1). Business requests failed with 403 / `Business user access required`, or missing `id` after that rejection. The bootstrap-admin hashing test passed.

A second selected run of `test_current_user_accepts_bearer_for_api_tooling` and `test_registration_normalizes_identity_and_returns_a_public_user` returned **2 failed in 0.68s** (exit 1): a manually minted token lacks the admin role, and the exact public-user response assertion omits the newly required `role` field.

## Parent handoff: deliberate contract conflicts

Preserve these old assertions and report their actual failures; fixture migration cannot decide to rewrite behavior tests:

- `test_submit_requires_all_slots_and_injects_sync_only_at_submit` expects a copy of global `{"offset":17}` and a manifest containing only file paths. The approved contract requires a task-local confirmed versioned snapshot and registration metadata instead.
- `test_update_task_metadata_rejects_invalid_payload` includes `{}`, title-only, and mode-only patches as invalid. This was flagged during inspection because the sync contract describes partial patches, but **all these cases passed in the actual scoped run**; no assertion was changed.
- `test_registration_normalizes_identity_and_returns_a_public_user` asserts an exact response without `role`; the admin contract now requires that field.

## First post-migration file runs: parent notification

All commands use `.venv/bin/python -m pytest` from the worktree with `-q --tb=short`. No tests were skipped or marked xfail.

- Selected ten-case fixture check: **10 passed in 2.38s**, exit 0.
- `tests/test_tasks_api.py tests/test_analysis_api.py`: **1 failed, 85 passed in 21.23s**, exit 1. Only the old global-sync equality fails; the old manifest equality later in the same test is also incompatible but was not reached.
- `tests/test_analyst_api.py tests/test_analyst_jobs.py`: **13 failed, 61 passed in 19.79s**, exit 1. Seven quota failures return 202 instead of 429 after mutating runtime `analyst_daily_limit`; two cancellation/restart cases see `failed` instead of `running` and log a provider `RuntimeError`; four claim/load invalidation cases expect `attempts == 1` but see zero.
- `tests/test_api_keys.py tests/test_app.py tests/test_deletions.py`: **2 failed, 73 passed in 14.73s**, exit 1. The exact public-user response omits `role`; `test_readiness_rejects_admin_password_that_does_not_match_database` returns 200 instead of 503.

## Fixture migration and latest results

`tests/business_fixture.py` is opt-in. It registers an ordinary account through the real registration route, logs in through the real login route, and returns the actual owner ID. Seeded analyses and submission ledgers now belong to that business account. Explicit bootstrap-admin, malformed-token, and admin-cookie/header precedence tests retain admin identities.

Task and multipart fixtures provide four expected persons. New submissions confirm synchronization through GET/PUT using actual current upload versions. Preset fixtures contain valid cam_03-anchored offsets. The local media-decoding mock exposes 50 frames at 25 fps, a 4000 ms source origin, and a two-second duration; chosen timestamps are actual frames. Files, headers, version hashes, sync validation, snapshot generation, and quota admission still execute. No global conftest or authorization/validation override was added. Existing readiness stubs remain limited to the original API fixtures; readiness-specific tests use the real service.

The seven analyst quota failures were fixture defects: runtime `AppSettings.analyst_daily_limit` is only a startup default once administrator settings are persisted. `set_daily_ai_limit` now persists the test owner's effective quota and checks it via `/account/limits`. Existing 429, idempotency, and non-refund assertions are unchanged.

After that correction:

```sh
.venv/bin/python -m pytest tests/test_analyst_jobs.py -q --tb=short
```

Result: **6 failed, 63 passed in 14.36s**, exit 1, no skips. All seven previously failing quota cases now pass; the six remaining cases are implementation/behavior conflicts below, with no changes to their assertions.

Admin JWT fixtures explicitly include the matching role and session-version claims. The forged, expired, and no-expiration fixtures each retain their intended single defect rather than also failing due to missing/mismatched role or version.

After the final JWT fixture correction:

```sh
.venv/bin/python -m pytest tests/test_app.py::test_current_user_accepts_bearer_for_api_tooling tests/test_app.py::test_current_user_rejects_invalid_tokens -q --tb=short
```

Result: **6 passed in 0.99s**, exit 0, no skips. The other file groups were not rerun because this correction only changes those token fixtures.

`git diff --check --` with all nine owned paths completed with exit 0. A read-only AST comparison against `git show HEAD:<file>` verified that all **142 existing test functions** and their complete behavior assertions are preserved across the seven files. The only assertion identifier adjustment is `admin_key` → `owner_key`, reflecting the same owner-isolation scenario under ordinary-account authentication. The new helper also parses successfully.

## Remaining failures for parent decision

There are **9 remaining failing cases** across the assigned files in the latest file runs (226 passing cases in aggregate; this is not one aggregate acceptance run).

| File and test | Cases | Actual result and boundary |
| --- | ---: | --- |
| `test_tasks_api.py::test_submit_requires_all_slots_and_injects_sync_only_at_submit` | 1 | Submission succeeds; snapshot contains schema/version, cam_03 offsets and current input versions instead of global `{"offset":17}`. The later file-only manifest assertion was not reached and also contradicts the approved contract. |
| `test_app.py::test_registration_normalizes_identity_and_returns_a_public_user` | 1 | Exact response differs only by the required `role: user` field. |
| `test_app.py::test_readiness_rejects_admin_password_that_does_not_match_database` | 1 | `/readyz` returns 200, expected 503. `app/main.py::_bootstrap_admin` returns true whenever an identity already exists and treats persisted identities as authoritative; the old mismatch check is not performed. Parent must decide the intended readiness behavior. |
| `test_analyst_jobs.py::test_cancellation_and_restart_recover_running_job_without_duplicate_rows[report/message]` | 2 | After cancellation, job is `failed`, expected `running`. `AnalystSupervisor.run_once` explicitly catches `CancelledError`, calls `_fail(RuntimeError("Worker stopped"))`, then re-raises. This is not a pausing-provider/event-loop fixture failure; subsequent restart assertions are not reached. |
| `test_analyst_jobs.py::test_invalidation_between_claim_and_load_cannot_delete_ledger_or_restart_message[before_load/after_load-report/message]` | 4 | `attempts == 0`, expected 1. `claim_ai` increments preparation attempts only; `record_ai_attempt` increments report/message attempts immediately before provider invocation. These tests intentionally invalidate before any provider call. Parent must reconcile the old claim-based expectation with actual-request accounting. |

No failing case is skipped, xfailed, removed, or made to pass by altering the application or weakening assertions. The initial partial-PATCH concern did **not** reproduce: TaskUpdate still requires title and mode, and all original invalid-payload cases passed.

## Modified files and covered tests

- `tests/test_tasks_api.py`: ordinary-user fixture and owner-scoped seeded rows; valid preset sync, expected-person count, explicit sync confirmation in the two submission tests, and required multipart fields for the media-I/O concurrency test.
- `tests/test_analysis_api.py`: ordinary-user fixture and owner-scoped historical rows; valid preset sync and upload configuration; ordinary-user setup in the standalone readiness/disabled-worker cases. Bootstrap-cookie security test is retained.
- `tests/test_analyst_api.py`: completed-task owner is a registered ordinary user; all five tests passed in the scoped analyst API/jobs run.
- `tests/test_analyst_jobs.py`: registered ordinary owner; five daily-limit setup sites now use persisted effective quotas; 69 cases exercised in the latest file run.
- `tests/test_api_keys.py`: ordinary key owner and returned owner IDs for usage rows; admin browser-cookie/header-security cases are retained. All API-key cases passed in the grouped run.
- `tests/test_app.py`: valid admin bearer claims, and defect-specific invalid JWT fixtures; bootstrap, login, registration and readiness assertions otherwise unchanged.
- `tests/test_deletions.py`: ordinary-user fixture; all deletion cases passed in the grouped run.
- `tests/business_fixture.py`: new shared, opt-in account/media/sync fixture helpers.
- `docs/implementation/legacy-fixture-migration.md`: this evidence and parent handoff.

Only those files were written by this worker. Concurrent changes elsewhere belong to other workers. No full suite, admin/sync test files, final acceptance, optimization loop, commit, push, production migration, or deployment was run.
