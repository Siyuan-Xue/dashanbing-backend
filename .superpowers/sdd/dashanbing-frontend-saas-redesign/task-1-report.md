# Task 1 Implementer Report — User registration, tenancy, and schema foundation

## Implementation

- Added `User.email` (nullable and unique), `is_active`, and `created_at`.
- Added `POST /api/v1/register`, which normalizes username/email with trim + casefold, hashes passwords, returns a public user, and returns HTTP 409 for either normalized duplicate identity.
- Extended login so the existing OAuth2 `username` form field accepts a normalized username or email while preserving the HttpOnly cookie. Inactive accounts are rejected both at login and when an existing token is used.
- Added required `Analysis.owner_id`, `submitted_at`, `created_via`, and `retry_count`. Legacy upload/preset creation records the authenticated owner and provenance; retry increments `retry_count`.
- Scoped every legacy analysis create/list/detail/result/media/cancel/retry/delete operation by the authenticated owner, returning the existing 404 shape for another tenant's analysis. Static preset catalog endpoints remain authenticated as before; preset reruns now create owner-scoped analyses.
- Added Alembic revision `20260904_0002`, which adds identity/tenant columns, locates the configured bootstrap admin, backfills legacy analysis ownership and submission time, then makes `owner_id` non-null with a foreign key and index.

## Files changed

- `app/models.py`, `app/security.py`, `app/api/deps.py`
- `app/api/routes/auth.py`, `app/api/routes/analyses.py`
- `migrations/versions/20260904_0002_identity_tenancy.py`
- `tests/test_app.py`, `tests/test_analysis_api.py`, `tests/test_migrations.py`
- `tests/test_retention.py`, `tests/test_supervisor.py`, `tests/test_worker.py`

## TDD evidence

### Initial focused RED

Command:

```sh
uv run pytest tests/test_app.py::test_registration_normalizes_identity_and_returns_a_public_user tests/test_app.py::test_registration_rejects_duplicate_normalized_username_or_email tests/test_app.py::test_login_accepts_normalized_email tests/test_app.py::test_login_rejects_an_inactive_user tests/test_analysis_api.py::test_legacy_analysis_routes_are_isolated_between_users tests/test_migrations.py::test_identity_migration_backfills_existing_analyses_before_making_owner_required -q
```

Result: `6 failed` — registration returned HTTP 405 and the upgrade left `analysis.owner_id` absent, exactly matching the unimplemented behavior.

### Initial focused GREEN

The same command passed: `6 passed, 2 warnings in 1.13s`. The warnings are Alembic's existing `path_separator` configuration deprecation.

### Required-owner RED/GREEN

Added `test_analysis_owner_is_required` after review to prevent a default bootstrap owner from silently assigning an unowned analysis. It first failed with `Failed: DID NOT RAISE IntegrityError`; after removing the model default and explicitly updating valid test fixtures it passed: `1 passed in 0.35s`.

### Full suite

```sh
uv run pytest
```

Final result: `82 passed, 2 warnings in 4.39s`. The two warnings are the same Alembic configuration deprecation above.

## Self-review

- Confirmed identity normalization is applied before validation/querying and duplicate detection checks both unique fields.
- Confirmed inactive accounts cannot obtain or continue to use credentials.
- Confirmed tenant filtering occurs before status/result/media processing, preventing resource existence leakage across users.
- Confirmed migration order is add nullable owner → backfill configured bootstrap admin → enforce non-null FK, with a real old-schema upgrade test.
- Confirmed analysis creation in application code always supplies `owner_id`; direct test fixtures now do likewise except the deliberate required-owner failure test.
- No Task 2 deprecation headers or delegation behavior were added, per the preflight ruling.

## Fix Round 1 — identity collision, bootstrap normalization, and insert-race handling

### Findings fixed

- Registration now tests both proposed normalized identities against both stored identity fields. An email can no longer equal another account's username (and the symmetric username/email collision is also rejected).
- Login uses the same trimmed/lowercase SQL lookup for username and email, allowing existing mixed-case bootstrap rows to authenticate with normalized form input. Newly bootstrapped admin usernames are stored normalized, while existing bootstrap rows are validated with normalized comparison for compatibility.
- `register` now catches commit-time `IntegrityError`, rolls the session back, and returns the same HTTP 409 duplicate response as the precheck.

### Covering tests added

- `test_registration_rejects_an_email_matching_an_existing_username`
- `test_registration_returns_conflict_when_a_duplicate_wins_the_insert_race`
- `test_mixed_case_bootstrap_username_can_log_in`

### RED/GREEN evidence

Initial RED command:

```sh
uv run pytest tests/test_app.py::test_registration_rejects_an_email_matching_an_existing_username tests/test_app.py::test_registration_returns_conflict_when_a_duplicate_wins_the_insert_race tests/test_app.py::test_mixed_case_bootstrap_username_can_log_in -q
```

Result: `3 failed in 0.71s` — the cross-field registration returned 201, the forced real uniqueness race returned 500, and mixed-case bootstrap login returned 401.

The same focused command then passed: `3 passed in 0.66s`.

Covering verification:

```sh
uv run pytest tests/test_app.py
```

Result: `23 passed in 1.93s`.

Full verification:

```sh
uv run pytest
```

Result: `85 passed, 2 warnings in 4.69s`. The two warnings are Alembic's existing `path_separator` configuration deprecation.

### Files changed in this round

- `app/api/routes/auth.py`
- `app/main.py`
- `tests/test_app.py`
- `.superpowers/sdd/dashanbing-frontend-saas-redesign/task-1-report.md`
