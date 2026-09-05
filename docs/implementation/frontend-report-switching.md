# Frontend and pre-generated report update

Approved user plan, 2026-09-05, base 2b6a7f3

## Shared contract

Reports are full reports for a scope, not filtered player paragraphs
GET /api/v1/{tasks|presets}/{id}/analyst/reports?locale=zh returns {items: ReportVariant[], facts: AnalystFacts, subjects: Subject[], provenance?: existing preset provenance}
ReportVariant is ReportState plus subject_id: string|null, locale: zh|en, style: coach|roast
POST /api/v1/tasks/{id}/analyst/reports with {locale} ensures the complete locale set and returns the same collection
POST /api/v1/tasks/{id}/analyst/report accepts the existing fields plus optional subject_id and refreshes only that variant
Old report GET/POST with no subject_id continues to mean the whole session
Successful old report bodies remain available while their replacement is queued/running
Initial generation produces both styles for whole session and all facts subjects in task analyst_locale, default zh for old clients/tasks
Collections are cached in the frontend per account/source/locale, switching scope/style never triggers generation
Comparison POST continues its existing contract, also queues the other style on an explicit comparison operation
No automatic comparisons or profile-binding-induced original changes

## Task 1: Backend and integration (controller)

Add task analyst_locale and report subject_id using additive migration, preserve old bodies/cache lookup
Scope facts and validate evidence for personal reports, no invented statistics for sparse players
Collection API, quota once per active collection request, single-refresh quota unchanged
Durable automatic completion/backfill enqueues missing variants, independent retries/restart recovery
Concurrency 8 shared by report and chat jobs, prevent duplicate calls
Carry current UI language through draft create/update and preset creation
Extend verified preset generation and reading for scope variants, reuse existing true reports
Update OpenAPI, frontend generated types, docs, integration and release verification

## Task 2: Analyst UI

Full vertical content at every breakpoint, one top toolbar with title/config/bind/compare/refresh
Config contains exactly two equal width Filter-style selects: whole session/player and coach/roast
No apply button, no selector in report content, full scope report switching
Read/cache collections, retain old body while refreshing current variant, show independent generation state
Move comparison controls to top, preserve atomic binding and chat scope/evidence interactions
Phone toolbar icon-only with accessible labels and one row
Only semantic border between raw results and analyst, no unnecessary analyst-internal dividers

## Task 3: Profiles and task table

Profiles become full table matching task header, 44px/14px table head, 68px rows
Columns name/type/goals/updated/actions, name search/type filter/client pagination using existing list API
Profile detail route /workspace/profiles/:profileId, create/edit dialogs
Friendly centered empty profiles/history/tasks/filter results with contextual action
Tasks action column about128px, progress >=180px, flex inline progress/percent, local table scroll

## Task 4: Icons and homepage

Replace hand-drawn UI SVG and icon text with official lucide-react through shared Icon mapping
RefreshCw universally, consistent size/stroke/spin and accessible buttons
Own logo unchanged, GitHub official brand asset exception approved
Restore original pre-AI Hero at7b222c1 without rolling back unrelated fixes, title/copy/buttons preserved
Restore basketball ProductPreview using real frames and verified metrics
Add independent one-screen AI section after Hero, before existing capabilities
Capture new real UI after implementation, no generated/fake promotional output, static homepage assets only

## Task 5: Verification and release

Backend/frontend regression tests, types/build, key E2E
320/390/768/1440/1920 zh/en light/dark layouts, single row toolbar, empty states
Real preset verification, refresh original-preservation, parallel report tests, per-user isolation
Independent code review then SCP deploy with code/env/database backup, additive migration, read-only data and static checks
