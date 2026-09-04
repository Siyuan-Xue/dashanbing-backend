# Task 2 Implementer Report — Unified staged task API, quotas, and lifecycle

## Implementation

- Added the durable `TaskInput` model and Alembic revision `20260904_0004`. Each row is keyed by `(task_id, slot)` and records the original filename, byte size, validation state, private storage path, and timestamps for one of the five supported upload slots.
- Added the authenticated staged task API:
  - `POST /api/v1/tasks`
  - `PUT /api/v1/tasks/{task_id}/inputs/{slot}`
  - `POST /api/v1/tasks/{task_id}/submit`
  - `POST /api/v1/tasks/from-preset`
  - paginated/filterable `GET /api/v1/tasks`
  - task detail, result, media, cancel, retry, and delete routes
- Reused `Analysis` as the queue/worker record so the existing single-GPU supervisor, quick/full modes, worker manifest, product result, range-capable media responses, and retention tiers remain intact.
- Added public task status normalization: worker substages and `cancel_requested` are `running`; `interrupted` is `failed`; the API exposes only `draft|uploading|queued|running|completed|failed|canceled|expired`.
- Staged uploads now publish `uploading` during server validation, stream through existing header, ffprobe, disk-reserve, and aggregate-size guards, and install with temporary/backup files. A validation or database failure restores the prior valid slot and removes temporary files.
- Submission requires all five valid files, copies the configured deployment sync file only at submission, writes the existing worker manifest, sets `submitted_at`, and queues the task.
- Enforced owner-scoped limits under SQLite `BEGIN IMMEDIATE` write reservations: three drafts, five unfinished tasks, and twenty submitted tasks per UTC day. Retry and both legacy submission paths use the same limits, preventing compatibility routes from bypassing quotas.
- Drafts expire after 24 hours both lazily on task access and during the existing hourly retention pass. Expiration removes draft storage while preserving an `expired` task record; supervisor restart returns an interrupted upload to a recoverable draft.
- Legacy `/api/v1/analyses/*` remains response-compatible, now includes `Deprecation: true` and an HTTP-date `Sunset` header, records task-input metadata for new legacy submissions, shares quota/deletion handling, and remains able to retry pre-migration manifests without `TaskInput` rows.

## Files changed

- `app/models.py`
- `app/api/router.py`
- `app/api/routes/tasks.py`
- `app/api/routes/analyses.py`
- `app/main.py`
- `app/services/tasks.py`
- `app/services/storage.py`
- `app/services/analysis_state.py`
- `app/services/supervisor.py`
- `app/services/retention.py`
- `migrations/versions/20260904_0004_task_inputs.py`
- `tests/test_tasks_api.py`
- `tests/test_migrations.py`
- `tests/test_retention.py`
- `tests/test_supervisor.py`

## TDD evidence

### Initial focused RED

Command:

```sh
UV_CACHE_DIR=/tmp/task2-uv-cache uv run --offline pytest tests/test_tasks_api.py tests/test_migrations.py::test_task_input_migration_records_staged_upload_metadata -q
```

Result: `10 failed, 2 warnings in 1.45s`. `/api/v1/tasks` returned 405, legacy responses had no deprecation headers, and Alembic had no `task_input` table.

### Initial focused GREEN

The same command passed: `10 passed, 2 warnings in 1.50s`.

### Compatibility and lifecycle RED/GREEN cycles

- Legacy preset metadata/quota tests first failed `2 failed in 0.62s` because no `TaskInput` rows were written and the 21st daily submission returned 201; after delegation helpers they passed `2 passed in 0.60s`.
- The existing legacy upload lifecycle test first failed because task-input foreign keys made deletion return 500. A retention regression with task inputs also failed with `FOREIGN KEY constraint failed`; explicit child deletion made both pass: `2 passed in 0.52s`.
- Observable upload state first failed because a concurrent detail request saw `draft`; after committing the transient state and reconciling cancellation/failure atomically, upload-state and replacement tests passed: `2 passed in 0.55s`.
- Legacy retry quota first returned 200 instead of 429; shared unfinished/daily enforcement made it pass.
- Background draft expiration first left the database row in `draft`; the retention pass now marks it `expired` and removes storage.
- Supervisor restart first left an interrupted task in `uploading`; it now returns it to `draft` with a recovery message.
- New retry of a retained pre-migration legacy manifest first returned 409; manifest fallback made it pass with status `queued`.

### Relevant integration suite

```sh
UV_CACHE_DIR=/tmp/task2-uv-cache uv run --offline pytest tests/test_tasks_api.py tests/test_analysis_api.py tests/test_retention.py tests/test_supervisor.py tests/test_worker.py tests/test_migrations.py -q
```

Result before the final edge-case cycles: `47 passed, 7 warnings in 4.88s`.

### Final verification

```sh
UV_CACHE_DIR=/tmp/task2-uv-cache uv run --offline python -m compileall -q app migrations
UV_CACHE_DIR=/tmp/task2-uv-cache uv run --offline pytest -q
git diff --check
```

Result: compile and whitespace checks exited 0; full suite `102 passed, 7 warnings in 6.93s`. All warnings are the existing Alembic `path_separator` deprecation.

## Self-review

- Ownership is applied before every task read, media/result response, upload, and lifecycle mutation; cross-tenant IDs return 404.
- Quota checks are per owner and serialized for all creation/retry entry points, including legacy routes. Draft creation does not consume the daily submission limit until submit.
- File validation completes against a temporary file before replacement. Prior slot metadata remains unchanged while validation runs; a failed validation removes the temporary file and returns the task to `draft`.
- Sync injection is absent from new upload drafts and occurs only in the submit operation. Presets retain their existing read-only sample manifest and never copy/delete sample inputs.
- Worker-facing `Analysis.status` substages and manifest shape were preserved; mapping occurs only in the new public task response.
- Result and media payloads reuse the existing builders/allowlists, with only generated URLs changed to `/api/v1/tasks/...`.
- Retention explicitly removes child metadata before deleting task rows in auto-created SQLite schemas, while the migration also declares `ON DELETE CASCADE` for deployed databases.
- No API-key or frontend work was included.

## Fix Round 1 — durable quota events, crash-safe replacement, and legacy lifecycle

### Findings fixed

- Added an immutable `submission_event` ledger. Initial submissions and every retry append an event in the same short SQLite write transaction as the task state change. Daily quota counting uses these retained events, so hard deletion cannot refund usage and repeated retries cannot overwrite their history. A compatibility fallback counts any unledgered `Analysis.submitted_at` rows, and migration `20260904_0005` backfills existing submissions.
- Extended staged replacement into a recoverable filesystem transaction. Each validated install now carries a pending marker and optional backup; every exception from post-install writer acquisition through task reload, input lookup, and commit rolls the file back before restoring task state. Startup scans pending/temp/backup artifacts, restores uncommitted replacements, finalizes committed replacements, removes partial first uploads, and runs even when the worker is disabled.
- Shortened legacy upload database admission. It performs fast preliminary quota checks, releases the read transaction during five-file streaming/ffprobe work, then takes `BEGIN IMMEDIATE`, rechecks both quotas authoritatively, records metadata plus the submission event, and commits. A late quota loss removes the uploaded task root.
- Unified deletion eligibility through `task_can_be_deleted`. Both APIs allow deletion only for drafts or terminal tasks; legacy calls can no longer delete `uploading` or `queued` staged tasks.
- Closed `TaskPublic.status` to the exact public `Literal` and replaced pass-through mapping with an exhaustive `AnalysisStatus` map. Unknown internal values now fail instead of leaking through the public API/OpenAPI contract.

### Covering tests

- `test_deleting_submitted_tasks_does_not_refund_the_daily_quota`
- `test_retry_consumes_a_new_daily_submission_at_the_limit`
- `test_post_install_database_failure_restores_the_prior_slot`
- `test_supervisor_recovers_an_interrupted_replacement_and_cleans_artifacts`
- `test_app_restart_recovers_upload_artifacts_when_worker_is_disabled`
- `test_legacy_upload_does_not_hold_the_database_writer_during_media_io`
- `test_legacy_delete_obeys_staged_task_lifecycle_rules`
- `test_task_status_schema_is_closed_and_unknown_internal_states_fail`
- Extended `test_identity_migration_backfills_existing_analyses_before_making_owner_required` for ledger backfill.
- Updated the existing legacy upload lifecycle test to require cancel-before-delete after retry queues the task.

### RED evidence

```sh
UV_CACHE_DIR=/tmp/task2-uv-cache uv run --offline pytest \
  tests/test_tasks_api.py::test_deleting_submitted_tasks_does_not_refund_the_daily_quota \
  tests/test_tasks_api.py::test_retry_consumes_a_new_daily_submission_at_the_limit \
  tests/test_tasks_api.py::test_post_install_database_failure_restores_the_prior_slot \
  tests/test_tasks_api.py::test_supervisor_recovers_an_interrupted_replacement_and_cleans_artifacts \
  tests/test_tasks_api.py::test_legacy_upload_does_not_hold_the_database_writer_during_media_io \
  tests/test_tasks_api.py::test_legacy_delete_obeys_staged_task_lifecycle_rules \
  tests/test_tasks_api.py::test_task_status_schema_is_closed_and_unknown_internal_states_fail \
  tests/test_migrations.py::test_identity_migration_backfills_existing_analyses_before_making_owner_required -q
```

Result: `8 failed, 2 warnings in 2.20s`. Failures showed HTTP 201 after twenty deleted submissions, HTTP 200 for a retry at the limit, the new replacement left installed after a database error, restart left the replacement/backup/temp intact, a concurrent writer missed the 500ms bound, legacy delete returned 204 for `uploading`, the OpenAPI status had no enum, and `submission_event` did not exist.

The worker-disabled app-restart regression was then isolated and failed `1 failed in 0.53s`: reopening the application left the task in `uploading`.

### GREEN evidence

The same eight-test focused command passed: `8 passed, 2 warnings in 1.48s`.

The restart-specific command passed: `1 passed in 0.48s`.

Covering integration command:

```sh
UV_CACHE_DIR=/tmp/task2-uv-cache uv run --offline pytest \
  tests/test_tasks_api.py tests/test_analysis_api.py tests/test_supervisor.py \
  tests/test_retention.py tests/test_migrations.py -q
```

Result: `49 passed, 7 warnings in 5.50s`.

Final verification:

```sh
UV_CACHE_DIR=/tmp/task2-uv-cache uv run --offline python -m compileall -q app migrations
UV_CACHE_DIR=/tmp/task2-uv-cache uv run --offline pytest -q
git diff --check
```

Result: compile and whitespace checks exited 0; full suite `110 passed, 7 warnings in 8.13s`. All warnings remain the pre-existing Alembic `path_separator` deprecation.

### Fix-round self-review

- Submission events deliberately have no task foreign key, so task/retention deletion preserves quota history; they retain an owner foreign key for tenant accounting.
- Every quota-producing endpoint performs quota check plus event insert under `BEGIN IMMEDIATE`. Only legacy media I/O runs outside that transaction, with a mandatory second check before commit.
- Recovery distinguishes uncommitted `uploading`/concurrently `canceled` operations from committed draft/queued states. It restores the newest backup, removes partial untracked destinations, and deletes pending/temp artifacts without changing `TaskInput` metadata.
- Database exceptions after file installation cannot skip file rollback; status restoration is attempted in a `finally` path, and restart recovery handles database unavailability that persists beyond the request.
- Legacy and new deletion routes call the same eligibility predicate. Existing legacy result/media/ownership/deprecation behavior is unchanged.

## Fix Round 2 — committed replacement phase and serialized legacy deletion

### Findings fixed

- Added an explicit durable filesystem commit phase for staged slot replacement. After the database transaction commits the new `TaskInput`, the route atomically renames its `.pending` marker to `.committed` before cleanup. Startup recovery inspects the newest operation marker per slot and treats `.committed` as authoritative regardless of a later task status such as `canceled`; it keeps the installed file and removes the obsolete backup and markers. Uncommitted `uploading` recovery continues to restore the prior slot.
- Added the shared `BEGIN IMMEDIATE` writer reservation to legacy delete before its owner-scoped lookup and deletion predicate. A competing upload transition can no longer commit `uploading` between the legacy route's status check and storage/database deletion.

### Covering tests

- `test_restart_keeps_committed_replacement_after_finalize_interruption_and_cancel`
- `test_legacy_delete_serializes_lifecycle_check_against_upload_transition`
- Existing recovery coverage: `test_supervisor_recovers_an_interrupted_replacement_and_cleans_artifacts`
- Existing steady-state legacy coverage: `test_legacy_delete_obeys_staged_task_lifecycle_rules`

### RED evidence

```sh
.venv/bin/pytest -q \
  tests/test_tasks_api.py::test_restart_keeps_committed_replacement_after_finalize_interruption_and_cancel \
  tests/test_tasks_api.py::test_legacy_delete_serializes_lifecycle_check_against_upload_transition
```

Result: `2 failed in 0.70s`. Restart restored the old bytes over the database-committed replacement after cancellation, and the competing upload reached media validation while legacy delete was paused after its lifecycle read.

### GREEN evidence

The same focused command passed: `2 passed in 1.22s`.

Covering task API command:

```sh
.venv/bin/pytest -q tests/test_tasks_api.py
```

Result: `22 passed in 3.78s`.

Full verification:

```sh
.venv/bin/pytest -q
git diff --check
```

Result: full suite `112 passed, 7 warnings in 8.75s`; whitespace validation exited 0. All warnings remain the pre-existing Alembic `path_separator` deprecation.

### Fix-round self-review

- The marker phase transition is an atomic rename within the task input directory. Cleanup removes the backup before the committed marker; if cleanup is interrupted at either point, recovery preserves the new destination and finishes removing artifacts.
- Recovery chooses the newest marker per slot, so a stale committed marker cannot make a newer pending replacement look committed. It preserves the previous rule for old pending-only artifacts according to task state.
- Legacy delete now uses the same lock ordering, owner-scoped reload, and predicate serialization as new delete. The race test verifies ordering rather than only checking static status values.
- No quota, public status, worker/result/media, API-key, or frontend behavior changed in this round.

## Fix Round 3 — database-correlated upload commit evidence

### Finding fixed

- Added nullable private `TaskInput.upload_operation_id` metadata and Alembic revision `20260904_0006`. Every staged install already has a UUID in its filesystem marker name; the upload route now persists that same UUID with the filename, size, path, validation state, and draft transition in the single metadata transaction.
- Startup recovery now loads each task input's committed operation UUID. If publishing `.pending` to `.committed` failed after the database commit, recovery recognizes a newest pending marker whose UUID matches the database row as committed, preserves the new destination, and removes the old backup and artifacts even if the task was later canceled.
- A pending marker whose UUID does not match the database row remains uncommitted. Existing interrupted-upload recovery therefore still restores the prior file and metadata rather than accepting an install whose database transaction did not commit.
- Legacy/new deletion behavior is unchanged in this round.

### Covering tests

- `test_restart_uses_committed_metadata_when_marker_publication_fails`
- Extended `test_task_input_migration_records_staged_upload_metadata` to require the deployed `upload_operation_id` column.
- Preserved recovery coverage: `test_restart_keeps_committed_replacement_after_finalize_interruption_and_cancel`, `test_supervisor_recovers_an_interrupted_replacement_and_cleans_artifacts`, and `test_app_restart_recovers_upload_artifacts_when_worker_is_disabled`. The last test now includes a pending marker whose UUID differs from the previously committed row, proving restart still rolls the uncommitted file back.

### RED evidence

```sh
.venv/bin/pytest -q \
  tests/test_tasks_api.py::test_restart_uses_committed_metadata_when_marker_publication_fails \
  tests/test_migrations.py::test_task_input_migration_records_staged_upload_metadata
```

Result: `2 failed, 2 warnings in 0.77s`. The behavioral regression restored `old` over the committed `new` file after cancellation/restart, and the migration assertion showed `upload_operation_id` was absent.

### GREEN evidence

The same focused command passed: `2 passed, 2 warnings in 0.70s`.

Recovery branch verification:

```sh
.venv/bin/pytest -q \
  tests/test_tasks_api.py::test_restart_uses_committed_metadata_when_marker_publication_fails \
  tests/test_tasks_api.py::test_restart_keeps_committed_replacement_after_finalize_interruption_and_cancel \
  tests/test_tasks_api.py::test_supervisor_recovers_an_interrupted_replacement_and_cleans_artifacts \
  tests/test_supervisor.py::test_app_restart_recovers_upload_artifacts_when_worker_is_disabled
```

Result: `4 passed in 0.69s`.

Covering integration command:

```sh
.venv/bin/pytest -q tests/test_tasks_api.py tests/test_migrations.py tests/test_supervisor.py
```

Result: `31 passed, 7 warnings in 4.06s`.

Full verification:

```sh
.venv/bin/pytest -q
.venv/bin/python -m compileall -q app migrations
.venv/bin/alembic heads
git diff --check
```

Result: full suite `113 passed, 7 warnings in 8.58s`; compile and whitespace checks exited 0, and Alembic reports the single head `20260904_0006`. All warnings remain the pre-existing Alembic `path_separator` deprecation.

### Fix-round self-review

- The operation UUID is backend-only and is intentionally omitted from `TaskInputPublic`; no API response contract changed.
- UUID comparison uses the newest marker for a slot, preventing an older stranded committed/pending operation from classifying a newer uncommitted install.
- Existing migrated and preset inputs have a null operation UUID and retain status-based legacy recovery behavior. New staged uploads use 32-character UUID hex values matching the new column bound.
- The operation UUID is written before the database commit and is never updated during marker publication, so recovery evidence does not depend on the fallible post-commit rename.

## Fix Round 4 — authoritative pending-marker correlation

### Finding fixed

- Replaced the recovery boolean's fall-through ordering with an explicit decision tree. A durable `.committed` marker remains authoritative; a `.pending` marker with a non-null database operation ID now commits only on an exact ID match and rolls back on mismatch, independent of task status.
- A pending first upload without any `TaskInput` row is treated as uncommitted and its installed destination is removed. The existing `valid_slots` input distinguishes that case from migrated/legacy `TaskInput` rows whose operation ID is null; only those rows retain the prior status-based recovery heuristic.
- No model, migration, API, lifecycle, quota, or public response contract changed.

### Covering tests

- `test_restart_rolls_back_unmatched_pending_replacement_for_draft`
- `test_restart_rolls_back_unmatched_pending_first_upload_for_draft`
- `test_restart_keeps_pending_replacement_for_legacy_null_operation_id`
- Preserved matching-correlation and durable-marker coverage through `test_restart_uses_committed_metadata_when_marker_publication_fails` and `test_restart_keeps_committed_replacement_after_finalize_interruption_and_cancel`.

### RED evidence

```sh
.venv/bin/pytest -q \
  tests/test_tasks_api.py::test_restart_rolls_back_unmatched_pending_replacement_for_draft \
  tests/test_tasks_api.py::test_restart_rolls_back_unmatched_pending_first_upload_for_draft \
  tests/test_tasks_api.py::test_restart_keeps_pending_replacement_for_legacy_null_operation_id
```

Result: `2 failed, 1 passed in 0.83s`. The replacement test found `new` bytes instead of the backed-up `old` bytes, and the first-upload test found the uncommitted destination still present. The legacy null-ID characterization passed.

### GREEN evidence

The same focused command passed: `3 passed in 0.83s`.

Recovery matrix:

```sh
.venv/bin/pytest -q \
  tests/test_tasks_api.py::test_restart_rolls_back_unmatched_pending_replacement_for_draft \
  tests/test_tasks_api.py::test_restart_rolls_back_unmatched_pending_first_upload_for_draft \
  tests/test_tasks_api.py::test_restart_keeps_pending_replacement_for_legacy_null_operation_id \
  tests/test_tasks_api.py::test_restart_uses_committed_metadata_when_marker_publication_fails \
  tests/test_tasks_api.py::test_restart_keeps_committed_replacement_after_finalize_interruption_and_cancel \
  tests/test_tasks_api.py::test_supervisor_recovers_an_interrupted_replacement_and_cleans_artifacts \
  tests/test_supervisor.py::test_app_restart_recovers_upload_artifacts_when_worker_is_disabled
```

Result: `7 passed in 1.10s`.

Covering task/supervisor suite:

```sh
.venv/bin/pytest -q tests/test_tasks_api.py tests/test_supervisor.py
```

Result: `31 passed in 4.54s`.

Full verification:

```sh
.venv/bin/pytest -q
.venv/bin/python -m compileall -q app migrations
.venv/bin/alembic heads
git diff --check
```

Result: full suite `116 passed, 7 warnings in 9.46s`; compile and whitespace checks exited 0, and Alembic reports the single head `20260904_0006`. All warnings remain the pre-existing Alembic `path_separator` deprecation.

### Files changed

- `app/services/storage.py`
- `tests/test_tasks_api.py`
- `.superpowers/sdd/dashanbing-frontend-saas-redesign/task-2-report.md`

### Fix-round self-review

- The decision order prevents task status from overriding explicit non-null correlation evidence: matching pending IDs commit, mismatches roll back, and `.committed` markers still win.
- A slot in `valid_slots` but absent from `committed_operations` is precisely a persisted null-ID row, so legacy status recovery remains available without conflating it with an unpersisted first upload.
- Replacement rollback restores the newest backup and removes all operation artifacts; first-upload rollback removes untracked installed bytes and its pending marker.
- The recovery matrix exercises realistic mutations of every decision branch: wrong correlation comparison, missing first-upload cleanup, removed null-ID fallback, and lost committed evidence would each fail a covering test.
