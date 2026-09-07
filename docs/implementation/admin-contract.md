# Administrator backend contract

Base `/api/v1/admin`. Admin session JWT only; business user and all API keys rejected. All mutations require exact same-origin `Origin` and JSON `reason` (trimmed, 3–500 characters). Auth `/api/v1/users/me` returns `role: user|admin`; admin uses existing login/logout. Administrator cannot access business content APIs.

Six UI routes may map to: overview→overview+deployment; users→users; scheduling→settings+jobs; quotas→settings+users; operations→jobs+deployment; audit→audit.

- `GET /overview`: `{resources:{cpu:{logical_count,load_average},memory:{total_bytes,available_bytes}|null,disk:{total_bytes,used_bytes,free_bytes}|null,gpu:[{utilization_percent,memory_used_bytes,memory_total_bytes}]|null},queues:{video:{queued,running,failed,completed},ai:{queued,running,failed,completed},preset:{queued,running,failed,completed}},usage:{ai_attempts,ai_tokens,video_submissions},users:{total,active},repair_budget:{utc_date,video_used,video_limit,ai_used,ai_limit}}`.
- `GET /users?page=1&page_size=20&q=&is_active=`: `{items:[{id,username,email,role,is_active,created_at,quotas:{drafts,unfinished,daily_video,daily_ai},quota_overrides:{...},usage:{drafts,unfinished,daily_video,daily_ai}}],total,page,page_size}`. Search username/email only; ordinary users only.
- `PATCH /users/{id}`: `{reason:string,is_active?:boolean,quotas?:{drafts?:int|null,unfinished?:int|null,daily_video?:int|null,daily_ai?:int|null}}`; null removes per-user override. Returns user DTO.
- `POST /users/{id}/force-logout`: `{reason:string}`; 204; revokes all JWT sessions and API keys.
- `GET /settings`: `{current:{video_enabled,video_paused,ai_enabled,ai_paused,ai_concurrency,default_quotas:{drafts,unfinished,daily_video,daily_ai}},bounds:{ai_concurrency:{min,max},priority:{min,max},quotas:{drafts:{min,max},unfinished:{min,max},daily_video:{min,max},daily_ai:{min,max}},batch_size,admin_retries},repair_budget:{utc_date,video_used,video_limit,ai_used,ai_limit}}`.
- `PATCH /settings`: partial `current` shape, partial `default_quotas`, plus required `reason:string`; returns same as GET. Limits affect new admission, pause/disable affects new claims only.
- `GET /jobs?kind=video|ai|preset&status=&page=1&page_size=20`: `{items:[{id,kind,owner_id|null,task_id|null,status,created_at,updated_at,attempts,held,priority,admin_retries,allowed_actions:[hold|release|priority|retry|backfill]}],total,page,page_size}`. Kind/status optional. No titles, filenames, paths, raw errors, report/chat/profile bodies.
- `POST /jobs/actions`: `{reason:string,kind:"video"|"ai"|"preset",ids:[1..10 unique IDs],action:"hold"|"release"|"priority"|"retry"|"backfill",priority?:int}`; `{items:[{id,status}]}`. Atomic batch; 409 for ineligible/stale state, 429 for repair budget, 422 invalid payload. Retry failed inputs only; backfill only stored expected versions (including completed preparation jobs with missing original locale/subject/style variants); never overwrite success. At most 3 extra retries per failed job; UTC day 20 videos/100 actual AI requests.
- `GET /audit?page=1&page_size=20`: `{items:[{id,actor_id,action,reason,target_kind,target_ids:[...],created_at,changes:{before:{...},after:{...},outcome:{status:"applied"|"rejected",http_status:int}}}],total,page,page_size}`. IDs are UUID strings. Settings snapshots contain only whitelisted settings; account snapshots contain `is_active`, `session_version`, effective `quotas`, `quota_overrides`; job snapshots map job IDs to `{status,held,priority,admin_retries}`. Successful mutations and audit share one transaction. Authorized, valid payloads rejected by service HTTP errors roll back all changes, then persist a rejected audit with identical before/after and the reason; no exception details. Malformed/unauthorized requests need not be audited.
- `GET /deployment`: `{application:{version,database_revision},workers:{video_enabled,ai_enabled},backup:{status:"unknown"},read_only:true}`. Unknown backup means no authenticated status source available. No command, deployment, restore, delete, role, or password endpoints.

Business `GET /api/v1/account/usage` retains existing response fields and returns effective per-user limits. Additional `GET /api/v1/account/limits`: `{quotas:{drafts,unfinished,daily_video,daily_ai},application:{max_upload_size_gb,draft_ttl_hours,enrollment_retention_days,raw_retention_days,result_retention_days,analyst_daily_limit}}`, authenticated ordinary users only.

Mutation DTOs `UserPatch`, `SettingsPatch`, `JobAction`, and force logout all require `reason`; it is persisted and exposed as `audit.items[].reason`.

Additive overview DTO (2026-09-07):

```ts
type TimingSummary = { count: number; p50: number | null; p95: number | null };
// Additional fields on GET /overview:
type OverviewObservability = {
  timings: {
    video_queue_seconds: TimingSummary;
    video_execution_seconds: TimingSummary;
    ai_total_seconds: TimingSummary;
  };
  errors: Array<{
    kind: 'video' | 'ai' | 'preset';
    code: 'engine_failed' | 'interrupted' | 'unknown' |
      'registration_count_mismatch' | 'registration_quality_failed' |
      'registration_config_required' | 'preparation_failed' | 'generation_failed';
    count: number;
  }>;
};
```

Timings sample successful jobs completed in the current UTC calendar day. Video queue time is `submitted_at→started_at`; execution is `started_at→completed_at`. AI total is report/chat/preset `created_at→completed updated_at`, including queue, retries, provider backoff and execution; preparation is excluded. These are not provider-only timings. Missing/negative spans are excluded, empty samples return `{count:0,p50:null,p95:null}`; percentiles use linear interpolation and round to three decimal seconds. Errors count the current failed/interrupted backlog across all dates, with allowlisted coarse codes only; no raw errors, log paths, or bodies.

Restart recovery requeues the same ordinary report/chat/preset identity within its existing three-attempt limit. Every resumed provider call increments both the job attempt counter and the actual-attempt ledger; incomplete chat is cleared. Leases with held kernel locks are never reclaimed; persisted provider backoff survives recovery. Exhausted and interrupted admin-repair jobs stay failed until an eligible explicit repair action. Repair calls always consume the UTC repair budget. The application AI concurrency maximum is eight; server configuration may lower the cap to any integer from one to eight. Ordinary daily AI admission still counts operations, not provider retries.

Single-host shared-runtime liveness: each claim persists its identity in SQLite and holds a corresponding POSIX file lock in `runtime/tmp/lease-locks`. Recovery is serialized with claims by the SQLite writer lock. An unlocked recorded lock proves that its owner stopped even after a container hostname change or PID reuse; a held lock protects legitimate slow or suspended work without heartbeat deadlines or termination signals. Video children inherit both the GPU mutex and this lease lock. A process cannot release another process's recorded claim, and rolled-back claims close their descriptors. All concurrent workers must use this protocol and share the same local runtime/SQLite with working POSIX locks; distributed storage is outside this guarantee. Preserve lock files/inodes while workers are active. Legacy foreign claims without a recorded lock cannot be proved dead and remain untouched; drain/stop legacy workers during upgrade rather than guessing their liveness. No schema change is required for this lock protocol.

Video repair rechecks the durable pending-storage-deletion guard under the mutation writer lock, including after an earlier jobs listing advertised retry eligibility. Pending cleanup returns 409 with no task/control/accounting changes. An accepted repair sets a new `submitted_at` and clears `started_at`/`completed_at`; it preserves the original SubmissionEvent and does not add an ordinary quota admission, including legacy inputs without a submission ledger. Video audit before/after snapshots additionally include those three timestamps as ISO strings or null.

Worker public errors are bounded: only the three registration codes above expose fixed registration messages and validated counts (stage `注册失败`). Unknown engine exceptions expose fixed `ENGINE_FAILED`/`分析失败` text, with details only in server-side logs. The diagnostic is removed before each new subprocess; stale, malformed, oversized, or symlinked diagnostics are ignored.

## Backend handoff and scoped verification — 2026-09-07

Worktree: `/Users/milesxue/Documents/ChatGPT/dashanbing-backend/.worktrees/ai-analyst`, branch `codex/ai-analyst`. No commit, push, deployment, production migration, real user data operation, or live provider/GPU execution was performed.

Integration handoff: `AdminAudit.id` is a UUID string. The video supervisor sets `app.state.video_worker_lock_fds`; the now-delegated `worker._run_subprocess` passes those descriptors to `asyncio.create_subprocess_exec`. This preserves the GPU mutex if the supervisor dies while its child still runs. The inherited-FD behavior was verified with an isolated synthetic subprocess. Sync router is mounted and migration 0013 follows 0012.

Earlier scoped command, before worker/observability/recovery additions (exit 0):

```sh
.venv/bin/python -m pytest tests/test_admin_auth.py tests/test_admin_scheduling.py tests/test_admin_presets.py tests/test_admin_migration.py tests/test_migrations.py tests/test_glm.py tests/test_analysis_state.py -q --tb=short
```

Actual result: **166 passed, 17 warnings in 6.00s**. All warnings are the existing Alembic `path_separator` configuration deprecation (2 from admin migration tests, 15 from existing migration tests). No broad final acceptance run or post-acceptance optimization loop was performed. Earlier implementation red tests and debugging were limited to this scope; their failures were not represented as passes.

Additional commands (all exit 0): `git diff --check`; `python -m compileall -q` over the owned backend, CLI, and migration files listed below; `.venv/bin/python scripts/migrate_admin_account.py --help`; `.venv/bin/python scripts/generate_analyst_presets.py --help`. CLI migration was exercised only on isolated pytest SQLite databases, including dry-run rollback, drained-queue checks, collisions, owner transfer, body/timestamp continuity, report-cache and message-request dedup rekeying, and credential revocation.

Files changed by the administrator backend scope (paths relative to the worktree above):

- `app/admin_models.py`
- `app/admin_schemas.py`
- `app/api/deps.py`
- `app/api/router.py` (admin and task_sync router registration)
- `app/api/routes/admin.py`
- `app/api/routes/account.py`
- `app/api/routes/auth.py`
- `app/config.py`
- `app/database.py`
- `app/main.py`
- `app/security.py`
- `app/services/admin.py`
- `app/services/admin_audit.py`
- `app/services/admin_jobs.py`
- `app/services/admin_leases.py`
- `app/services/admin_metrics.py`
- `app/services/admin_scheduling.py`
- `app/services/admin_presets.py`
- `app/services/analyst.py`
- `app/services/supervisor.py`
- `app/services/worker.py` (subsequently delegated)
- `app/services/tasks.py` (quota enforcement and ordinary-submission repair accounting only; parent owns task_public)
- `scripts/migrate_admin_account.py`
- `scripts/generate_analyst_presets.py`
- `migrations/versions/20260907_0012_admin.py`
- `tests/test_admin_auth.py`
- `tests/test_admin_scheduling.py`
- `tests/test_admin_presets.py`
- `tests/test_admin_migration.py`
- `tests/test_admin_observability.py`
- `tests/test_admin_recovery.py`
- `tests/test_admin_lease_liveness.py`
- `tests/test_admin_video_repair.py`
- `tests/test_worker.py` (subsequently delegated)
- `docs/implementation/admin-contract.md`

`app/models.py`, research/storage/task/sync route implementations, frontend, and other agents' tests were not edited by this scope. Parent-coordinated fixture updates now use ordinary business users. Legacy expectations for pre-provider attempts (now zero), role fields, and global sync are intentional contract changes; those assertions were not changed here. Existing-account readiness no longer treats `.env` administrator password as credential authority: the database password governs login, and bootstrap never changes an existing account.

## Added-scope implementation verification — 2026-09-07

Worker lock inheritance, bounded registration diagnostics, generic-error privacy, overview timings/coarse errors, transactional audit snapshots/outcomes, and bounded ordinary AI/preset restart recovery are implemented. This is scoped implementation verification; final acceptance has not started.

Tests preceded new behavior. The worker diagnostic/lock additions first produced 12 failures; after implementation the then-current worker suite passed 27 tests. Observability/audit first produced 8 failures and 1 pass, then 9 passes. Recovery plus the explicit generic-error privacy test and the two unchanged legacy restart tests first produced **11 failed, 10 passed, 67 deselected**; after the recovery implementation, those 21 selected tests passed. The generic unknown-error public text was already fixed when its dedicated test was added, and that test passed without further worker changes. Failures were implementation evidence, never recorded as acceptance passes.

Combined scoped command (exit 0):

```sh
.venv/bin/python -m pytest tests/test_admin_auth.py tests/test_admin_scheduling.py tests/test_admin_presets.py tests/test_admin_migration.py tests/test_admin_observability.py tests/test_admin_recovery.py tests/test_worker.py tests/test_migrations.py tests/test_glm.py tests/test_analysis_state.py 'tests/test_analyst_jobs.py::test_cancellation_and_restart_recover_running_job_without_duplicate_rows' -q --tb=short
```

Actual result: **223 passed, 17 warnings in 9.12s**. The 17 warnings are the existing Alembic `path_separator` deprecation. Fixtures use temporary SQLite/runtime directories, fake providers, and lightweight local subprocesses; no live provider, research GPU, production data, or production migration was used. The two existing restart tests were run unchanged; unrelated intentional legacy assertion mismatches were not edited or included in this pass claim.

`git diff --check` and scoped `.venv/bin/python -m compileall -q` over owned backend/CLI/migration files also exited 0. No commit, push, deployment, fixture-server restart, broad final acceptance, or acceptance optimization loop was performed.

## Final integration additions — 2026-09-07

The kernel-lock liveness, pending-cleanup guard, repair timing reset, eight-slot application cap, and detached-message accounting migration fixes were requested before final acceptance. New registration messages now use Chinese commas without `。`; unrelated existing copy is unchanged.

The offline migration recognizes only terminal message jobs with null task/report/message links, null error, and exactly `{"automatic": boolean}` as privacy-redacted accounting records. It transfers their owner and preserves their original request hash, attempts, usage and timestamps without reconstructing or rekeying a deleted conversation. The original hash stays globally reserved, including collision checks for surviving messages being rekeyed. Unrecognized missing-message provenance still aborts and rolls back. The fixture exercises the real ordinary task DELETE endpoint before dry-run and applied migration, on a temporary database only.

Initial implementation regressions: liveness/cleanup/timing tests produced **9 failed, 1 passed**. Migration/cap/legacy-video-quota tests produced **3 failed, 8 passed**, then **11 passed** after fixes. Test setup corrections included removing a nonexistent simulation setting and using a lightweight synthetic research child for deliberately non-video input fixtures; these were not application defects or acceptance passes. The intermediate worker/recovery/audit/liveness/repair scope passed **66 tests** before the final migration/cap additions.

The combined scope initially produced **1 failed, 241 passed** because this agent's earlier inherited-lock test expected one descriptor. The child now needs both the GPU mutex and claim lock; that test was updated to require both. Other agents' legacy assertions were not edited.

Final combined scoped command (exit 0):

```sh
.venv/bin/python -m pytest tests/test_admin_auth.py tests/test_admin_scheduling.py tests/test_admin_presets.py tests/test_admin_migration.py tests/test_admin_observability.py tests/test_admin_recovery.py tests/test_admin_lease_liveness.py tests/test_admin_video_repair.py tests/test_worker.py tests/test_migrations.py tests/test_glm.py tests/test_analysis_state.py 'tests/test_analyst_jobs.py::test_cancellation_and_restart_recover_running_job_without_duplicate_rows' -q --tb=short
```

Actual result: **242 passed, 17 warnings in 16.96s**. Warnings remain the existing Alembic `path_separator` deprecation. Scoped `compileall` and `git diff --check` exited 0. These were implementation checks using isolated temporary fixtures and synthetic subprocesses/providers, not final acceptance or real GPU/GLM measurements.

Source stable after these requested fixes: 25 owned source/CLI/migration files, combined SHA-256 `3218c72ab49b8027f6a9070a6ef9231efa9248c38e3d4438e1abe457de950be1`. No source changes are planned without further explicit direction. No schema migration, production execution, commit, push, or deployment was performed in this integration round.
