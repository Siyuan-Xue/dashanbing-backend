# AI analyst implementation ledger

Approved plan: independent wide video -> AI analyst -> original result tabs, GLM-5.3 automatic report and chat, confirmed player/team memory, repair existing research pose linkage, actual screenshot-based homepage

## Constraints
Reuse models and existing inputs, no retraining or extra data capture
No GLM key yet: implement and mock-test now, real reports and promotional screenshots await key
Existing headline/buttons, blue/redbrown palette, video width and autoplay preserved
No automatic identity continuity across tasks, no synthetic 3D/wrist angles, no mock report marketed as real

## Work and interfaces
- Research task: research_engine and pose tests -> analyst_pose.json with verified provenance, common clock and camera offsets
- Facts/memory task: models, migration, facts, profiles/context APIs -> typed facts, owner-isolated persistent memory
- Provider task: glm.py -> strict report JSON and formal-content SSE streaming, safe provider errors
- UI task: independent analyst, profiles and hero/capture scripts -> documented REST/SSE contract
- Integration task: durable analyst queue, report/chat routes, lifecycle/retention, config, generated types and docs
- Verification task: backend/frontend/build/E2E and independent review

## Preflight
| Producer/consumer | Check |
|---|---|
| Research -> facts | Stable clip+student IDs privately, public opaque IDs only, explicit verified pose provenance |
| Facts -> AI queue | Compact data with evidence references, backend-derived metrics, no raw media or paths |
| Queue -> UI | Report statuses independent of video status, persisted chat snapshots via SSE |
| Memory -> queue | Owner scope, manually confirmed identity, dedupe same inputs, invalidate changed history |
| UI -> hero | Actual verified GLM report required before publishing screenshot assets |

Baseline: 210 backend tests passed before changes
Working branch: codex/ai-analyst in .worktrees/ai-analyst

## Implemented
- Task-scoped verified pose export, anonymous AnalystFacts and migration 0009 with seven tables
- Official GLM-5.3 provider, independent durable prepare/report/message queue, deduplication, restart recovery, quotas and SSE snapshots
- Confirmed profile/player/team memory, source deduplication, compatible history defaults and scoped invalidation
- Wide video -> independent analyst -> original stable-height data tabs, evidence seeks, follow-up questions, two tones and training profiles UI
- Homepage capability copy, real-frame fallback, verified screenshot manifest and capture/generation scripts
- OpenAPI export, TypeScript definitions, API docs and server configuration

## Verification on 2026-09-05
- Backend full suite: 509 passed, including migration round-trip, queue races, evidence validation and memory isolation
- Frontend full unit suite: 123 passed
- TypeScript build and Vite production build passed
- Desktop/mobile Playwright: 121 passed, 49 project-specific cases intentionally skipped
- Analyst matrix: 320/390/768/1440/1920 px, zh/en, light/dark; video position, 2:1 columns, overflow and data-tab height checked
- Screenshot metadata/crop guards: 5 passed, plus native-browser 16-variant crop/header test passed; live no-Key capture refused publication as expected
- Independent review fixes: video hashing outside SQLite writer locks, task lifecycle rechecks, invalidated request replay, dependency-scoped memory cleanup and preservation of valid comparison selections

## Pending external acceptance
- No GLM API Key was provided and no real GLM request was made
- Real preset reports and final public screenshot assets await the Key; mocked E2E images are not promotional assets
- Real GPU inference was not run locally; geometric/research pipeline tests exercise production code with GPU/media boundaries replaced by test doubles
- The current sample calibration fails the conservative analyst pose quality gate, so its analyst facts intentionally omit 3D angles
