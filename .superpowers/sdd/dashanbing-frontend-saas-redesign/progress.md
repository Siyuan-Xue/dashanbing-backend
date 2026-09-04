# SDD ledger — plan: /private/tmp/dashanbing-frontend-saas-redesign.md

Spec source: the user-approved plan is represented by the plan file above; there is no separate repository spec.

## Preflight conflict and interface scan

| Tasks | Producer / consumer overlap | Finding and ruling |
|---|---|---|
| Task 1 self | User/Analysis schema, auth, legacy route ownership, migration | Internally consistent. Tests exercise registration, login and tenant isolation before implementation. |
| Task 2 self | TaskInput schema, `/tasks`, upload/storage, quotas, legacy lifecycle | Internally consistent. Existing worker statuses remain internal; new API maps `interrupted` to `failed`. |
| Task 3 self | ApiKey schema, shared auth dependency, usage endpoint | Internally consistent. Full secret is a create-only response and never appears in list responses. |
| Task 4 self | New frontend foundation, public/auth routes and tests | Ruling: introduce Playwright test infrastructure in Task 4 because it is the first frontend behavior task; Task 6 expands it into the full visual matrix. Cost if wrong: Task 4 carries a small dev-dependency/setup diff earlier than the final QA task. |
| Task 5 self | Workspace shell and task workflows | Internally consistent. It consumes only new `/tasks` APIs and reuses result payloads. |
| Task 6 self | API center, contracts, visual QA, docs and integration | Internally consistent. Final OpenAPI regeneration captures all backend work. |
| Tasks 1 → 2 | Analysis ownership and user identity consumed by unified task service | Clean dependency; Task 2 must query through owner-scoped helpers introduced in Task 1. |
| Tasks 1 → 3 | User identity and common authentication consumed by API keys | Clean dependency; API key auth returns the same User object as JWT auth. |
| Tasks 1 ↔ 2 | Both touch legacy analyses routes | Ruling: Task 1 adds ownership only; Task 2 adds deprecation headers and delegates lifecycle behavior. Cost if wrong: duplicated route edits may require conflict cleanup, but sequencing keeps the interface stable. |
| Tasks 2 → 5 | `/tasks` request/response shapes consumed by workspace | Clean dependency; generated OpenAPI may be refreshed after backend tasks for development, then regenerated finally in Task 6. |
| Tasks 3 → 5/6 | Usage and API key contracts consumed by settings/API management | Clean dependency; no frontend placeholder APIs are permitted. |
| Tasks 4 → 5/6 | Providers, route guards, design tokens and public header consumed by both application shells | Clean dependency; workspace and API shells live in separate modules to avoid style coupling. |
| Tasks 5 ↔ 6 | Shared authenticated layout primitives and API navigation | Ruling: Task 5 owns generic workspace components; Task 6 may reuse tokens/icons but creates a separate API shell. Cost if wrong: some small UI primitives may be duplicated or need extraction. |

Merge base: 7595972

Task 1: fix round 1/5 (1 addressed, 2 open — insert race fixed; cross-field concurrent identity and Unicode bootstrap normalization open; commits 32585b8..b154eeb)
Task 1: fix round 2/5 (3 addressed, 0 open — global identity registry and canonical casefold; commits b154eeb..e687910)
Task 1: complete (commits 7595972..e687910, review clean; independent verification: 88 passed, 5 pre-existing Alembic warnings)
Task 2: fix round 1/5 (3 addressed, 2 open — durable quota, writer lock and status schema fixed; committed replacement recovery and legacy delete race open; commits 0953a7c..bfa0a39)
Task 2: fix round 2/5 (1 addressed, 1 open — legacy delete serialized; marker publication failure window open; commits bfa0a39..bd174f3)
Task 2: fix round 3/5 (finding partially addressed — DB-correlated operation ID added; unmatched pending draft fallback open; commits bd174f3..74ec7ff)
Task 2: fix round 4/5 (finding addressed, 1 new open — authoritative correlation fixed; stale older generation could supersede a later replacement; commits 74ec7ff..1cbe8a9)
Task 2: fix round 5/5 (1 addressed, 0 open — pre-replacement generation reconciliation; commits 1cbe8a9..e46a4a1)
Task 2: minor (deferred): legacy deletion holds the SQLite writer reservation during recursive storage deletion; final review should assess production impact.
Task 2: complete (commits e687910..e46a4a1, review clean; independent verification: 117 passed, 7 pre-existing Alembic warnings)
Task 3: fix round 1/5 (2 open — expiry time captured before lock acquisition; malformed/unsupported Authorization can downgrade to cookie authentication; implementer commit 284f7e6)
Task 3: fix round 1/5 (2 addressed, 0 open — lock-time expiry/monotonic audit timestamp and authoritative Bearer-only API key classification; commits 284f7e6..be4e480)
Task 3: complete (commits e46a4a1..be4e480, review clean; independent verification: 132 passed, 9 known Alembic warnings)
Task 4: fix round 1/5 (9 open — auth outage/race, dark primary contrast, accessible guard status, pre-paint system theme, registration limits, fully localized metadata/a11y copy, nonfunctional preview control, and browser interaction coverage; implementer commit f8672b3)
Task 4: fix round 1/5 (8 addressed, 1 open — structured 422 type is discarded, so Unicode string_too_short is mislabeled as too long; commits f8672b3..62547ee)
Task 4: fix round 2/5 (structured 422 semantics addressed, 1 open — native HTML maxLength counts UTF-16 units and rejects valid astral-character values before code-point validator; commits 62547ee..4aab248)
Task 4: fix round 3/5 (1 addressed, 0 open — removed native UTF-16 caps and verified exact Pydantic-compatible code-point limits in Chromium; commits 4aab248..da4f0e5)
Task 4: complete (commits be4e480..da4f0e5, review clean; independent verification: 22 Vitest tests, TypeScript, Vite production build, and 11 Playwright tests passed with 1 intentional desktop skip)
Task 5: fix round 1/5 (11 open — task-param stale result, draft metadata race, authoritative list refresh/page correction, workspace 401 session invalidation, abort/single-flight detail loads, URL-to-filter sync, confirmation modal focus, drawer inert/focus trap, exact state messaging, 120-code-point title/422 validation, and enum/preset/result localization; implementer commit 79beb38)
Task 5: fix round 1/5 (10 addressed, 1 open — mobile drawer focus loop excludes brand/Home, lacks an announced internal dismiss control, and Settings does not close on navigation; commits 79beb38..7d11c25)
Task 5: fix round 2/5 (1 addressed, 0 open — complete mobile drawer focus order, internal localized dismiss control, and same-origin navigation closure; commits 7d11c25..c82e042)
Task 5: complete (commits da4f0e5..c82e042, review clean; independent verification: 51 Vitest tests, TypeScript, Vite production build, and 17 Playwright tests passed with 3 intentional project-specific skips)
Task 6: implementation delivered (resumed from partial handoff; API center, regenerated contracts, SPA fallback, README, 48-capture visual matrix, and mobile drawer focus containment completed; review pending)
Task 6: fix round 1/5 (9 open — root Vite assets swallowed by SPA fallback, non-polling Curl flow, stale README registration/legacy contract, `/api/` deep link, modal error/busy focus, clipboard fallback, mobile key-table labels, deterministic visual readiness/timezone, and localized retention units; integration note: also localize stable worker stage messages exposed by Task 6 visual QA; implementer commit cecb76c)
Task 6: fix round 1/5 (9 addressed, 0 open — explicit root asset serving, terminal-state API polling docs, registration/tasks README, `/api/` fallback, dialog a11y/error/focus and keyboard secret fallback, mobile table labels/headers, deterministic UTC route-fixture visual matrix, duration/stage-message localization; verification: 145 backend, 62 Vitest, TypeScript, production build, 71 Playwright passed with 5 intentional project skips, and 48 visual captures)
Task 5: complete (implementation commit; self-review clean; verification: 31 Vitest tests, TypeScript, Vite production build, and 17 Playwright tests passed with 3 intentional project skips)
Task 5: fix round 1/5 (11 addressed, 0 open — task generations reset and abort, draft metadata locked, lifecycle queries authoritative with page correction, fetch/XHR 401 auth invalidation, URL filter sync, modal/drawer focus semantics, exact states, Unicode title/422 validation, and stable identifier localization; verification: 50 Vitest tests, TypeScript, Vite production build, and 17 Playwright tests passed with 3 intentional project skips)
Task 5: fix round 2/5 (1 addressed, 0 open — drawer focus loop includes Home and close, localized in-drawer close action, and all same-origin navigation closes; verification: 51 Vitest tests, TypeScript, Vite production build, and 17 Playwright tests passed with 3 intentional project skips)
