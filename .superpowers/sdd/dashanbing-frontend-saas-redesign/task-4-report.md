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
