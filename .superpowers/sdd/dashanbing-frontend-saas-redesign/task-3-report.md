# Task 3 Implementer Report — API key authentication and account usage APIs

## Implementation

- Added the owner-scoped `ApiKey` model and Alembic revision `20260904_0007`. The table stores a unique SHA-256 HMAC digest, display-only prefix and last four characters, name, created/expiry/last-used/revoked timestamps, and an owner foreign key. It has no plaintext secret/token column.
- Added authenticated API-key management routes:
  - `GET /api/v1/api-keys`
  - `POST /api/v1/api-keys`
  - `DELETE /api/v1/api-keys/{id}`
- Creation returns a cryptographically random `dsb_live_...` bearer secret exactly once. The response model marks that field `repr=False`; list responses contain only display metadata and computed `active|expired|revoked` status.
- New keys expire after 90 days unless the caller supplies a bounded `expires_in_days` value. Creation takes the existing SQLite `BEGIN IMMEDIATE` writer reservation before counting and inserting, so concurrent requests cannot exceed five active, non-revoked, non-expired keys per owner.
- Extended the shared authentication dependency with deterministic credential selection: an explicit Bearer header takes precedence over a browser cookie; `dsb_live_` values use API-key authentication; all other Bearer/cookie tokens retain the existing JWT path. API-key authentication verifies the HMAC and active lifecycle state under a writer reservation, checks that the owner is active, then records `last_used_at` before returning the same `User` object used by JWT auth.
- Added authenticated `GET /api/v1/account/usage`. It returns owner-scoped usage/limit pairs for submissions today (`20`), unfinished tasks (`5`), drafts (`3`), and active API keys (`5`), plus server-configured draft/enrollment/raw/result retention descriptions.
- Reused the immutable `SubmissionEvent` ledger plus the existing unledgered-task compatibility fallback for today's submitted count, and reused the staged task status sets and lazy draft expiration for the other task counts.

## Files changed

- `app/models.py`
- `app/security.py`
- `app/api/deps.py`
- `app/api/router.py`
- `app/api/routes/api_keys.py`
- `app/api/routes/account.py`
- `app/services/api_keys.py`
- `app/services/tasks.py`
- `migrations/versions/20260904_0007_api_keys.py`
- `tests/test_api_keys.py`
- `tests/test_migrations.py`
- `.superpowers/sdd/dashanbing-frontend-saas-redesign/task-3-report.md`

No frontend files were modified.

## TDD evidence

### Initial focused RED

Command:

```sh
.venv/bin/pytest -q \
  tests/test_api_keys.py \
  tests/test_migrations.py::test_api_key_migration_creates_owner_scoped_non_plaintext_credentials
```

Result: `9 failed, 2 warnings in 1.22s`.

The failures were specific to the missing feature: API-key POST returned 405, management and usage GETs returned 404, a `dsb_live_` header was ignored in favor of the browser cookie, explicit JWT Bearer did not override a stale cookie, and Alembic had no `api_key` table.

### Initial focused GREEN

The same focused command passed after the minimal implementation: `9 passed, 4 warnings in 1.57s`. The two additional warnings came from test-only SQLite datetime adapters and were removed by using literal expired timestamps; the final focused result is `11 passed, 2 warnings in 1.48s` after adding input-boundary coverage.

### Input-validation RED/GREEN

Command:

```sh
.venv/bin/pytest -q tests/test_api_keys.py::test_api_key_name_validation_returns_a_client_error
```

The numeric-name case first returned HTTP 500: `1 failed, 1 passed in 0.56s`. Restricting trimming to string inputs restored Pydantic's normal validation path; the same command then passed: `2 passed in 0.43s`.

### Final verification

Command:

```sh
.venv/bin/python -m compileall -q app migrations
.venv/bin/pytest -q
git diff --check
```

Result: compile and whitespace checks exited 0; the complete Python suite passed `128 passed, 9 warnings in 9.20s`. All warnings are the existing Alembic `path_separator` deprecation; the new migration test exercises that same known warning twice.

## Test coverage

- One-time secret disclosure, exact prefix, 90-day default, HMAC persistence, absent plaintext columns, absent list/repr secret leakage.
- Invalid, expired, and revoked bearer rejection; successful use records `last_used_at`.
- Owner-scoped listing/revocation and cross-tenant 404 behavior.
- Five-active-key limit, with revoked and expired keys excluded from the active count.
- JWT Bearer precedence over a stale browser cookie and invalid API-key precedence without cookie fallback.
- API-key task creation returning a task owned by the key's user.
- Usage cards backed by immutable daily submission events, staged task states, active key state, tenant filters, configured retention periods, and authentication.
- Migration columns, non-null verifier/owner, owner foreign key, and unique digest index.
- Invalid API-key names return 422 rather than creating empty records or surfacing server errors.

## Self-review

- The full secret exists only in the create function's local variable and create-only response model. Database rows, list responses, and normal model representations cannot expose it.
- HMAC lookup uses the server-side configured secret, so a database leak alone cannot authenticate an attacker. Key IDs and displayed prefix/tail are not accepted as credentials.
- Explicit Authorization always wins over ambient cookie state. Invalid, expired, revoked, missing-owner, and inactive-owner API keys fail closed with the common 401 response.
- Authentication and revocation both reserve the SQLite writer before checking key state. A revoke cannot race a last-used update into authenticating a key after revocation, and key use never changes task ownership logic.
- Key creation reserves the writer before the active count and holds it through insert/commit. Revoked and expired rows remain available for audit/display but do not consume the five-key active quota.
- Usage values are calculated on the server and filtered by the authenticated owner. Deleted submitted tasks remain counted through immutable ledger rows, matching quota enforcement.
- The daily-quota enforcement function now delegates to the same counting helper used by account usage, preventing the UI and admission logic from drifting.
- No task, worker, result/media, upload, retention-deletion, legacy response, or frontend behavior was otherwise changed.
