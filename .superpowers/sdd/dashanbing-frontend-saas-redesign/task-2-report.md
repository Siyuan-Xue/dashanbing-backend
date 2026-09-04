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
