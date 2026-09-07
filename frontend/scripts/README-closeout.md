# Local closeout UI capture

`capture-closeout.mjs` reads the isolated fixture at `http://127.0.0.1:8013`. Start/build that fixture separately. This script does not build the app, seed a database, mock responses, submit tasks, or run administrative actions. It uses `runtime/release-closeout/fixture-credentials.json` (`accounts[0]` and `admin`) for real UI login. Do not point it at production.

Run from the repository root. Set Node on PATH if the bundled pnpm launcher cannot find it:

```sh
export PATH=/Users/milesxue/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH
node frontend/scripts/capture-closeout.mjs --help
node --test frontend/scripts/capture-closeout.test.mjs
```

A new evidence directory under the repository's ignored `runtime/` is required. Relative output and credential paths resolve from the repository root. Existing output directories are rejected to preserve prior evidence. Default `--mode dry-run` reads no credentials, opens no browser, and writes no evidence; it prints the plan:

```sh
node frontend/scripts/capture-closeout.mjs \
  --mode dry-run \
  --output-dir runtime/release-closeout/ui-capture-pending
```

The development smoke captures four pages (home, login, ordinary new task, administrator overview) and ordinary/admin role checks at one geometry. It is explicitly labeled `development_smoke_not_acceptance`:

```sh
node frontend/scripts/capture-closeout.mjs \
  --mode smoke \
  --output-dir runtime/release-closeout/ui-smoke-001 \
  --executable-path '/Users/milesxue/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
```

In the managed environment, the browser/local HTTP command may require sandbox escalation. Never treat a sandbox connection error as evidence that the application is unavailable.

Full measurement is an explicit separate invocation using `--mode capture`. The default plan contains 300 page cases: 15 pages × five geometries × two locales × two themes. It also checks both roles for each of the 20 geometry/locale/theme variants. No full measurement is performed by a dry run or smoke. The full measurement command has not been run during script preparation.

Options include:

- `--sizes 320x900,390x900,768x900,1440x900,1920x900`: explicit CSS viewport and screen geometry, device scale factor 1.
- `--locales zh,en` and `--themes light,dark`.
- `--pages home,login,register,new,tasks,profiles,settings,api/docs,api/keys,admin-overview,admin-users,admin-scheduling,admin-quotas,admin-operations,admin-audit` to narrow page cases. Role checks remain included; smoke never exceeds four page cases.
- `--browser auto|chrome|chromium`. Auto attempts branded Chrome, then labels a fallback as Chromium. An explicit `--executable-path` is verified with that executable's `--version`; an unverified binary is not called Google Chrome. An invalid explicit executable fails setup rather than silently replacing it.
- `--timeout-ms 20000`, `--settle-ms 350`: bounded page/locator waits and a quiet window for current main-document API reads. Chrome/Chromium CDP request IDs track reads across navigation, cancellation, redirects, and request completion. A response header does not finish a read. `Page.frameNavigated` confirms main-document replacement: reads from its prior loader move to `superseded_document_reads` as unresolved evidence, never fabricated completions. Current or unknown-loader reads never expire by age; timeouts retain request/loader IDs, sanitized URLs, status, and age as findings, without retrying the case.
- `--full-page`: an additional separately named full-page image. The default viewport PNG always remains separate and keeps exact requested dimensions.

Evidence files:

- `plan.json`, `summary.json`: scope, browser identity, exact geometry plan, method limitations, raw case outcomes and counts.
- `cases.jsonl`, `boundaries.jsonl`: append-only per-case records, retained if later cases fail.
- `cases/*.viewport.png`, optional `*.full-page.png`: direct browser screenshots; credential inputs/fixture account identities are masked.
- `cases/*.geometry.json`: viewport, screen, outer window, visual viewport, document extents, horizontal overflow, table row/header bounds, contained scrollers, screenshot PNG dimensions, and exact-geometry comparisons.
- `cases/*.timings.json`: raw Navigation/Resource/Paint Timing, supported performance observers, available long-task/LCP observations. No pass/fail timing threshold or speed claim is imposed.
- `cases/*.events.json`: redacted console/page errors (including console source locations), request status/timing metadata, sanitized CDP API-read lifecycle events, main-document transitions, and current/superseded outstanding reads at close. No request/response headers or bodies.
- `boundaries/*.account.viewport.png`, `*.account.geometry.json`, `*.events.json`: header role-scope evidence and boundary event records.

Each page has a fresh browser context. Authenticated pages are measured after UI login; sign-in also loads app assets. Request routing disables HTTP cache. Only same-origin fixture requests are allowed; mutations are restricted to login/logout. There are no response mocks, repairs, traces, HAR files, saved cookies/storage state, or credential output. Screenshots preserve layout; masking only hides credential fields and fixture identities.

Role checks cover login destinations despite an opposite-role `next`, ordinary forbidden admin pages, admins redirected out of workspace/API keys, absence of role-forbidden UI data requests, server 403s for opposite-role metadata endpoints, public account link scope, and real cookie logout followed by `/users/me` returning 401.

On mobile, account checks open the actual `.public-menu-toggle` before the account dropdown. Existing open menus are preserved. An anonymous bootstrap `GET /api/v1/users/me` returning 401 is retained and labeled `expected_account_bootstrap_401`; its native browser console error is expected only when the source URL and status text correlate with that response within two seconds. Console entries remain in raw evidence. Authenticated 401s, other endpoints/statuses, and application console errors remain findings.

The script makes one attempt per page/role group. Failures are recorded and later independent cases continue. It never repairs the UI, changes configuration, retries a failed case, or declares full acceptance. Exit 0 means evidence recorded with no detected findings within the selected scope; exit 2 means findings or capture/setup failures. Always read the scope and raw records.
