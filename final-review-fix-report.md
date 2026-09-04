# Final whole-branch review fix report

This pass addresses all seven findings from the final review of
`review-7595972..a795af8.diff`. It preserves the existing product and tenant
semantics while making storage cleanup crash-safe, tightening public contracts,
and aligning the bilingual UI and documentation with the real backend.

## Findings addressed

1. **Empty-database migration**
   - Migration `20260904_0002` now counts unowned analyses before looking up or
     requiring the bootstrap administrator. Existing databases with analyses
     still require the configured bootstrap owner and retain the original
     backfill behavior.
   - A clean database upgrades through the single linear head before the app
     lifespan creates the administrator.

2. **Durable filesystem deletion outside SQLite writer transactions**
   - New migration `20260905_0008` adds the `storage_deletion` outbox with a
     composite `(analysis_id, target)` key, attempt count, and last error. It has
     intentionally no analysis foreign key so a logical task deletion and its
     cleanup record can commit atomically.
   - Task DELETE, legacy DELETE, draft expiry, and terminal/tier retention now
     perform only state changes and outbox insertion under `BEGIN IMMEDIATE`.
     They commit before any recursive filesystem removal.
   - The drainer reads pending work in a short session, closes it, validates the
     fixed target and current task state, removes files with no database
     transaction open, then acknowledges the row in a separate short write.
     Failures increment `attempts`, retain `last_error`, and remain retryable.
   - Allowed targets are fixed to `analysis_root`, `enrollment`, `input`, `data`,
     and `engine_output`. Resolved analysis IDs and all target paths must stay
     inside the configured analysis root; corrupted IDs, targets, and escaping
     symlinks are refused.
   - Root cleanup is permitted only after the analysis row is gone or the draft
     is `expired`; tier cleanup is permitted only for terminal tasks. Retry is
     refused while a committed root/input deletion is pending, preventing a
     retry/retention race.
   - Startup reconciliation drains the outbox before bootstrap. The operation is
     idempotent, so every ordering remains recoverable: rollback before commit
     leaves storage untouched; commit before cleanup leaves durable work;
     partial/failed cleanup retries; cleanup before acknowledgement safely
     repeats the missing-path removal and acknowledges it.
   - Coverage includes task and legacy deletion, terminal and tier retention,
     draft expiry, cleanup failure/retry, restart reconciliation, the
     filesystem-before-ack crash point, path confinement, and a gated slow
     recursive removal during which API-key authentication completes its audit
     write before cleanup is released.

3. **Registration validation**
   - Identity before-validators normalize strings only. Numeric and object JSON
     values now reach Pydantic's normal type validation and return 422 instead
     of raising `AttributeError` as a 500.
   - Server email syntax now uses the same reasonable shape rule as the frontend
     (`non-space local@domain.suffix`). Case-folding, trimming, uniqueness, and
     cross-field collision protection are unchanged. Unicode addresses accepted
     by that rule remain valid.

4. **Binary media OpenAPI**
   - Task, preset, and legacy media routes explicitly declare a successful
     `video/mp4` response with a binary string schema and no successful JSON
     content. Runtime `FileResponse`, inline disposition, Range behavior, and
     authorization are unchanged.
   - `openapi.json` and `frontend/src/generated/schema.d.ts` were regenerated.

5. **Real-contract bilingual output**
   - A shared localization helper now formats backend retention durations for
     Settings and API surfaces, translates the canonical result disclaimer, and
     translates both finite warning templates emitted by
     `app/services/results.py` with their runtime counts.
   - Unknown warnings and diagnostic text pass through unchanged. Task and
     preset result pages both use the shared `ResultWorkspace` path.
   - Visual fixtures now contain the canonical backend warning/disclaimer text;
     inspected Chinese and English desktop captures show the correct localized
     output.

6. **Generated workspace contracts**
   - Workspace `Task`, `Input`, `List`, `Result`, `Usage`, preset, mode, status,
     slot, request-body, list-query, and upload path/response types now derive
     from generated OpenAPI `components`/`paths` rather than handwritten DTOs.
   - Backend `TaskPublic.mode`, `TaskInputPublic.slot`, and required task
     timestamps expose precise schemas. JSON request bodies, list queries, and
     the XHR upload path/response are checked against the generated operations.
   - Compile-time equality tests prevent the workspace aliases from drifting
     back to manual approximations.

7. **README and stale scaffold**
   - README upload guidance now states what the browser actually does (file
     chooser type hinting) and reserves container-signature/`ffprobe` validation
     for the server.
   - Retention documentation now includes 24-hour draft expiry, 7/30/180-day
     tier semantics, immediate logical deletion, durable asynchronous cleanup,
     restart retry, and target confinement.
   - Repository search proved `ProtectedRouteScaffold` and its two copy keys had
     no consumers, so the unused phased scaffold was removed. The tracked SDD
     workspace remains intact.

## TDD and verification evidence

Each behavioral change began with a focused failing regression: clean upgrade
raised the bootstrap-admin error; deletion ordering/restart/concurrency cases
failed against direct `rmtree`; invalid registration values produced 500 or
malformed email was accepted; media responses advertised JSON; real backend
strings remained untranslated; and compile-time generated-contract equality
failed against the handwritten workspace DTOs. The corresponding focused suites
then passed before the complete matrix below.

- Backend: `uv run pytest -q` — **167 passed**, 11 Alembic deprecation warnings.
- Frontend: `pnpm test` — **66 passed** across 4 files.
- TypeScript: `pnpm run typecheck` — passed.
- Production build: `pnpm run build` — passed; 79 modules transformed.
- Browser suite: `pnpm run test:e2e` — **75 passed, 7 intentionally skipped**
  across 82 project cases.
- Visual matrix: exactly **48 PNG captures** (6 pages × desktop/phone × zh/en ×
  light/dark).
- Alembic: `20260905_0008 (head)` is the only head. A fresh empty SQLite database
  upgraded through every migration, then completed an app lifespan with
  `auto_create_schema=False`.
- Generated contract reproducibility: rerunning both exporters preserved SHA-256
  `0da1e05a1223df91094cd3e9f884ab3d3fbad815bdfa6cb81b7dc1ed24b10862`
  for `openapi.json` and
  `0c52521b1a0d563b77eda127cbcdf94628afcb98edcd777e1846c23a14a77e77`
  for `frontend/src/generated/schema.d.ts`.
- v3 preset validation passed for quick-demo, mixed-actions, verified-outcome,
  and layup-demo, including verified outcome truth 17/17. The linked worktree
  excludes ignored local assets, so the validator was pointed at the same
  repository's existing `local-assets/sample-bundle/data` checkout.
- `git diff --check` — passed.

## Residual concerns

No open code finding remains. GPU/model acceptance is still Linux/NVIDIA-only as
documented and was not possible on this Mac verification host. The Alembic
warnings are the pre-existing `path_separator` configuration deprecation and do
not affect migration results.
