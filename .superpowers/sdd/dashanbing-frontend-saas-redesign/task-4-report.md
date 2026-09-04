# Task 4 implementer report

## Scope delivered

- Replaced the previous frontend page/component/CSS architecture with a new public SaaS foundation while keeping React, TypeScript, Vite, React Router, `openapi-fetch`, and the generated schema module.
- Added focused theme, locale, auth, API, icon, brand, and route-guard modules.
- Added public `/`, `/login`, and `/register` routes plus authenticated route foundations for `/workspace/*` and `/api/keys`. Protected navigation preserves the complete path and query in `next`; unsafe external-looking redirect values are rejected.
- Built a responsive public header with exactly Home/API plus theme, locale, GitHub, Online Use, and login/account actions. The exact repository URL is `https://github.com/Siyuan-Xue/dashanbing-backend`. No client/download, collections, ecosystem, news, or promotion controls were added.
- Built the new home page: compact queue-focused hero with the exact Chinese headline, original code-built analysis workspace preview, three capability cards, only quick-demo and mixed-actions public examples, CTA, and minimal footer.
- Built bilingual login and registration forms against the real cookie-auth endpoints. Login accepts username or email. Registration sends username/email/password, signs in after successful registration, localizes validation/conflict/credential failures, refreshes `/users/me`, and redirects back.
- Added persisted `zh`/`en` locale and light/dark theme providers. First theme selection honors `prefers-color-scheme`; both preferences are stored in local storage.
- Added a new, original iceberg-and-basketball inline SVG brand mark and matching favicon. All visuals are native SVG/CSS and no MinerU asset, illustration, screenshot, branding, or prose is included.
- Established light/dark semantic tokens for canvas, surfaces, text, borders, brand, accent, state, shadow, and radii, with 1040/760/430 responsive foundations and reduced-motion handling.
- Added Vitest/Testing Library component infrastructure and Playwright desktop/mobile browser infrastructure. Generated browser caches and test reports are ignored.

## RED evidence

1. Initial component run after writing the six behavioral tests:
   - Command: `pnpm test -- --reporter=verbose`
   - Result: `1 failed` test file, `6 failed` tests.
   - Expected failures included the missing exact hero, missing system/persisted theme and locale behavior, missing protected redirect-back, and missing registration UI. The old app also emitted relative-URL errors while trying to fetch its private dashboard data in jsdom; this path was removed by the replacement.
2. Browser regression after adding the desktop/mobile Playwright foundation:
   - Command: `pnpm test:e2e`
   - Result: `1 failed, 3 passed`.
   - Meaningful failure: mobile Chromium could not find the required GitHub header action because CSS had hidden it at the phone breakpoint.
3. Final mobile header completeness regression:
   - Command: `pnpm test:e2e --project=mobile-chromium --grep='approved navigation'`
   - Result: `1 failed`.
   - Meaningful failure: Online Use was present in the DOM but not visible at the phone breakpoint; it now collapses to a compact icon in the two-row mobile header.
4. Manual browser-width probe before the decorative overflow fix:
   - 390 px viewport reported `document.documentElement.scrollWidth === 405`.

## GREEN evidence

- Component suite after implementation: `1 passed` file, `6 passed` tests.
- Playwright after keeping GitHub as a mobile icon: `4 passed` across desktop Chromium (1440×900) and mobile Chromium (iPhone 13 emulation).
- Mobile browser-width probe after clipping public-page decoration: `innerWidth === 390`, `scrollWidth === 390`.
- TypeScript no-emit check: `pnpm run typecheck` exited 0.
- Production build: `pnpm run build` exited 0; Vite transformed 55 modules and emitted the SPA bundle into the existing FastAPI frontend output directory.
- Visual QA covered the public home and auth layouts at desktop and phone widths, in light/dark and Chinese/English. No external state was modified.

## Files

- App/routing: `frontend/src/App.tsx`, `frontend/src/components/RouteGuard.tsx`, `frontend/src/pages/ProtectedRouteScaffold.tsx`
- Providers/API/copy: `frontend/src/providers/*`, `frontend/src/api.ts`, `frontend/src/copy.ts`
- Public UI/auth/brand: `frontend/src/pages/HomePage.tsx`, `frontend/src/pages/AuthPage.tsx`, `frontend/src/components/*`, `frontend/src/styles.css`, `frontend/public/favicon.svg`, `frontend/index.html`
- Tests/tooling: `frontend/src/App.test.tsx`, `frontend/src/test/setup.ts`, `frontend/vitest.config.ts`, `frontend/tests/public-foundation.spec.ts`, `frontend/playwright.config.ts`, `frontend/package.json`, `frontend/pnpm-lock.yaml`, `.gitignore`

## Self-review

- Requirement scan: all Task 4 public/auth/provider/guard items are represented; no Task 5 workspace workflow or Task 6 API-center page was implemented. The protected scaffold is deliberately content-light and exists only to prove guard and redirect-back behavior.
- Contract scan: auth calls match current backend routes and payload formats (`application/x-www-form-urlencoded` login, JSON registration, HttpOnly cookie via `credentials: include`, `/users/me` refresh). The generated schema remains preserved and is intentionally not regenerated from the current backend until Task 6, per plan.
- Security/error scan: redirect targets are constrained to same-origin absolute paths, passwords are never persisted, auth errors do not expose tokens, and non-JSON proxy errors fall back to localized UI copy.
- Accessibility/responsive scan: semantic headings/nav/forms, persistent visible focus, stable label/error associations, accessible control names, reduced-motion support, and no 390 px horizontal overflow. Mobile visibly retains Home/API, theme, language, GitHub, Online Use (as a compact icon), and account/login in a clean two-row header.
- Copyright scan: only original SVG geometry and CSS-built courts/workspace previews are present. MinerU references informed spacing/hierarchy only.

## Known handoff note

The repository's `openapi.json` predates Tasks 1–3. `frontend/src/api.ts` therefore keeps the generated client for existing/generated contracts and uses a narrow manually typed auth boundary for current endpoints. Task 6 remains responsible for final OpenAPI export and generated type refresh.

## Review fix round 1

### Fixes

- Reworked auth bootstrap into a generation-guarded state transition. Only a real 401 becomes anonymous; network, 5xx, invalid JSON, and malformed user payloads become an operational auth error. Protected routes now show localized error/retry UI, and pending bootstrap exposes localized status text to assistive technology.
- Invalidated pending bootstrap work when login, registration, logout, or a newer refresh starts. A deferred-response regression proves a late anonymous bootstrap cannot overwrite a completed login or keep the redirect destination loading.
- Added light/dark `--on-brand` tokens and verified both primary and hover pairs at WCAG AA contrast. Dark mode retains the existing lavender brand colors with dark ink rather than failing white text.
- Added a self-hosted, CSP-compatible head bootstrap (`/theme-bootstrap.js`) so stored/system theme is applied before the app and imported CSS render. The typed runtime theme helper keeps provider transitions and computed action tokens coherent.
- Mirrored backend registration constraints exactly: required username/email/password, maxima 50/255/128, existing minima, localized required/max errors, and localized FastAPI 422 field mapping.
- Localized the navigation landmark, brand/home accessible names and visible hierarchy, preview label, document title, and meta description. Metadata updates on locale changes and restores from persisted locale.
- Replaced the nonfunctional preview play button with an `aria-hidden` decorative status glyph.
- Expanded Playwright from static assertions to actual theme/locale clicks and reloads, client routing, deterministic mocked login plus redirect-back, and mobile action/overflow checks. The browser run also caught and fixed hidden mobile login/account accessible names.

### RED evidence

1. Component regressions before fixes: `pnpm test -- --reporter=verbose` produced `10 failed, 4 passed`. Failures directly covered first-render theme, missing contrast token, untranslated names/metadata, dead preview control, inaccessible loading status, auth operational errors, stale bootstrap login race, missing registration constraints, and generic 422 handling. A malformed `/users/me` case was added to the same operational-error matrix before implementation.
2. First interactive browser run: `pnpm test:e2e` produced `5 failed, 4 passed, 1 skipped`. Besides two deliberately strict locator issues, mobile Chromium proved that CSS-hidden login/account text removed its accessible name; protected login therefore also lacked a visible named account action.

### GREEN evidence

- Focused component suite: `pnpm test` → `1 passed` file, `17 passed` tests.
- Interactive browser suite: `PLAYWRIGHT_BROWSERS_PATH=/private/tmp/dashanbing-playwright-browsers-task4 pnpm test:e2e` → `9 passed, 1 intentionally skipped` across desktop Chromium and iPhone 13 Chromium. The skip is the desktop instance of a mobile-only geometry assertion; all shared behavior runs in both projects.
- TypeScript: `pnpm run typecheck` → exit 0.
- Production: `pnpm run build` → exit 0, Vite `56 modules transformed`, output emitted to `app/frontend`.
- Diff hygiene: `git diff --check` → exit 0; generated schema remained unchanged.

### Review self-check

- Auth error classification is based on `ApiError.status === 401`; response-shape validation prevents a malformed 200 from masquerading as an authenticated user.
- Every async auth state write is conditional on the current generation, including `finally`, so stale requests cannot clear a newer loading/session state.
- Registration changes stop at the current auth contract; no workspace or API-center UI from Tasks 5/6 was added.
- The external head theme bootstrap uses only same-origin JavaScript and no inline script, nonce, remote asset, or third-party dependency. Playwright used the already provisioned local Chromium cache at the path shown above; no unrelated browser was downloaded.
