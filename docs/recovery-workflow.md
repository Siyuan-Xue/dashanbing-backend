# Recovery and measurement tools

Scope: operator-run tools and an offline workflow. A later explicitly requested
synthetic recovery drill is recorded below; no production backup, restore, schedule,
capacity measurement or GPU acceptance was performed by this helper task. Parent
coordination owns final acceptance and the main documentation index.

## Implementation plan and contracts

1. Write focused synthetic tests for offline snapshot/verify/restore/rollback,
   unsafe inputs, corruption, concurrent writers and file changes. Implement in
   `scripts/release_recovery.py`; keep failures observable and destinations intact.
2. Write injected-transport tests for 1/5/10/20-user raw HTTP measurements, explicit
   environment credentials, percentiles and error redaction. Implement in
   `scripts/measure_capacity.py` without importing application settings.
3. Write injected-transport tests for the four presets in quick/full mode, missing
   GPU prerequisites, failure/timeout preservation and unavailable telemetry.
   Implement in `scripts/measure_gpu_acceptance.py`; no remote execution here.
4. Run only the scoped tests and CLI help/dry-run checks; record exact outcomes
   below. No final acceptance or performance optimization loops, commits or deploys.

Recovery public functions: `plan(source, target, database=..., includes=...)`,
`snapshot(..., offline=True)`, `verify(source)`, `restore(source, target,
offline=True)` and `rollback(source, target, offline=True)`. Source/target are
explicit absolute paths. Selection paths are strict relative paths. Rollback
materializes a previous snapshot into a different empty directory; switching the
application release and data location remains an operator action.

Measurement tools default to a network-free plan. Execution requires `--execute`,
`--test-environment`, an explicit base URL, and a credentials environment variable.
Capacity emits `runs[]` for 1/5/10/20 users, each with raw `outcomes[]`, `errors`,
`wall_seconds` and nearest-rank `latency_ms` p50/p95/p99. GPU emits per-preset,
per-mode, per-sample outcomes; missing data is null/unavailable, never zero or pass.

## Offline snapshot and recovery procedure

The CLI does not drain queues, stop processes, acquire an application-wide writer
lease, change a release, or restart a service. Before `--offline` is valid, the
operator must complete these steps outside the CLI:

1. Block new submissions and uploads. Drain inference, analyst/report/chat, retry,
   and storage-deletion queues, recording outstanding/failed jobs. If a queue
   cannot drain, stop and resolve that state; do not call the snapshot consistent.
2. Stop API processes, workers, schedulers, retention/cleanup jobs and all other
   database/file writers. Keep them stopped throughout selection, snapshot,
   verification and any restore/switch. Merely having no active HTTP requests is
   insufficient. An offline flag is an operator attestation, not process detection.
3. With writers stopped, use the deployment's established SQLite procedure to
   checkpoint WAL and close all handles. Convert WAL mode to rollback journal
   mode before this tool runs. The tool refuses WAL mode and any `-wal`, `-shm`
   or `-journal` sidecar; it never deletes sidecars or repairs the source database.
4. Explicitly list the one SQLite database and every required data directory/file
   from the same offline root. Include completed outputs, required inputs,
   persisted reports, media and other retained artifacts needed by that database.
   Record application/engine release and selection scope separately without
   dumping settings, connection strings or credentials. The CLI cannot infer
   database-to-file references or decide what a complete application backup is.
5. Plan, snapshot, verify, then restore to an isolated empty target and run the
   parent's authorized acceptance process. Only the operator decides whether to
   switch the release/data location and resume writers.

The following are **command templates**, not executed drills. Every absolute path
is a placeholder for an operator-selected, isolated offline dataset. There are no
default production paths. On macOS use physical paths, such as `/private/tmp`,
because symlinks in any path component are refused.

```sh
python scripts/release_recovery.py plan \
  --source /absolute/offline-dataset --target /absolute/snapshots/release-before \
  --database data.sqlite --include files --include reports

python scripts/release_recovery.py snapshot --dry-run \
  --source /absolute/offline-dataset --target /absolute/snapshots/release-before \
  --database data.sqlite --include files --include reports

python scripts/release_recovery.py snapshot --offline \
  --source /absolute/offline-dataset --target /absolute/snapshots/release-before \
  --database data.sqlite --include files --include reports

python scripts/release_recovery.py verify \
  --source /absolute/snapshots/release-before

python scripts/release_recovery.py restore --dry-run \
  --source /absolute/snapshots/release-before --target /absolute/isolated-restore

python scripts/release_recovery.py restore --offline \
  --source /absolute/snapshots/release-before --target /absolute/isolated-restore

python scripts/release_recovery.py rollback --offline \
  --source /absolute/snapshots/release-before --target /absolute/isolated-rollback
```

Snapshot targets must not exist; restore/rollback targets must be absent or empty,
and their parent must already exist. Source and target cannot overlap. No command
overwrites an existing data tree. Rollback restores a prior snapshot into a new
directory and leaves the failed release/data tree intact for investigation. It
does not reverse migrations in place or merge post-snapshot writes. Coordinate
the matching application version and any data-loss window outside this tool.

Absolute file references stored in SQLite are not rewritten. Before opening a
restored application, isolate it from the original filesystem and services and
arrange the correct path mapping. Restore verification proves bytes and SQLite
integrity, not application semantics or completeness of operator selections.

Snapshot layout:

```text
snapshot/
  manifest.json       # format_version, timestamp, database, dirs, file sizes/SHA-256
  manifest.sha256     # SHA-256 of exact manifest bytes
  payload/            # selected relative data paths, including the SQLite file
```

The snapshot holds an exclusive SQLite lock while hashing and copying files,
rechecks the selected tree, and validates the copied database using SQLite
`integrity_check` and `foreign_key_check`. A held writer lock, failed checks,
changed source bytes, unexpected payload entries or digest mismatches refuse
publication. Restore validates the whole snapshot before copying, validates the
restored database, rechecks the snapshot, then publishes the staged directory.
Files and directories are synced before rename. This is a local-filesystem
workflow; shared/network filesystems and hostile processes replacing path
components are outside its supported offline operating model.

The manifest covers empty directories and every selected file. Verification rejects
traversal, absolute paths, ambiguous case-folded names, symlinks (including parent
components), hardlinks, FIFOs/devices and malformed manifests. It supports exactly
one SQLite database; an additional SQLite header in the selected files is refused.
This tool uses directories, not archive extraction. SHA-256 detects corruption;
it is not authentication against an attacker who can rewrite both manifest and
payload. Keep an independently trusted copy/digest under operator control.

Selections containing dotfiles, credential/secret names, configuration directories,
common configuration formats (`.env`, `.ini`, `.toml`, `.yaml`, `.yml`) or key
material (`.pem`, `.key`, `.p12`, `.pfx`) are refused. They are not silently omitted.
There is no general content-based secret detector: the operator must explicitly
select data only and exclude any configuration hidden under ordinary data names.
Provision configuration and credentials separately through the established secure
process. Neither configuration nor database row values are printed. Snapshot data
can itself be sensitive; newly created files use mode 0600 and directories 0700.
No secret store, environment file, real runtime tree or real video is accessed by
the tests. No backup or retention schedule is installed.

Recovery exit codes are 0 for the reported operation and 2 for refusal. Diagnostics
use fixed codes rather than raw exception messages, paths or SQL values. JSON
`status: verified` applies only to snapshot checks. Recovery does not report
performance timings except when `snapshot --fixture` explicitly labels the input
as synthetic and adds `evidence_kind: synthetic_fixture` and `wall_seconds`.
Never use that fixture flag to label real data.

## Capacity measurements

`measure_capacity.py` calls one explicit authenticated GET endpoint using 1, 5,
10 and 20 concurrent clients, in that order. Each client issues its configured
number of requests serially; a barrier starts each concurrency level together.
This is a closed-loop workload, without warm-up, retries or automatic tuning.
It measures that endpoint and sample size, not maximum production capacity.

Provision 20 distinct test-account credentials outside the script. Set the named
environment variable to a JSON array using **one** of these forms per account:

```json
[{"token": "FAKE-EXAMPLE-ONLY"}]
```

```json
[{"username": "synthetic-account", "password": "FAKE-EXAMPLE-ONLY"}]
```

Those one-entry examples describe the shape only; capacity execution requires at
least 20 distinct entries/tokens. Different bearer tokens cannot prove different
account identities; the operator must ensure they belong to distinct test users.
Username/password entries authenticate using `/api/v1/login/access-token` before
measurement timing starts. The script does not register users, read `.env`, use
browser cookies or print credentials. Credentials stay in process memory.

```sh
# Network-free; the environment variable need not exist for a plan.
python scripts/measure_capacity.py --dry-run \
  --base-url https://capacity-fixture.invalid --path /api/v1/presets \
  --credentials-env CAPACITY_TEST_CREDENTIALS --samples-per-user 3

# Operator-run template for a separately provisioned test server and accounts.
python scripts/measure_capacity.py --execute --test-environment \
  --base-url https://capacity-fixture.invalid --path /api/v1/presets \
  --credentials-env CAPACITY_TEST_CREDENTIALS --samples-per-user 3 \
  > capacity-run-unique.json
```

Use a new output filename for every run; retain failures and their original JSON.
The script emits JSON to stdout and does not manage or overwrite report files.
The output includes the explicit target origin/path, sample ordinal, user ordinal,
HTTP status, error category, each observed latency, errors per concurrency level,
wall time, and p50/p95/p99 for all attempts and for successful attempts separately.
No response body, account name, token, raw transport exception or server error
message enters the report. Percentiles use the nearest-rank method; no samples
means null. Low sample counts do not provide stable tail estimates.

Only explicit HTTP(S) origins without URL credentials/query strings are accepted.
Redirects and environment proxy settings are disabled; HTTPS certificate checking
is retained. Use HTTPS for any test service beyond local loopback. A declared test
environment is required for execution; the tool cannot discover whether a supplied
host is actually production. Choose a GET route whose side effects are acceptable
in the isolated test service. A GET name alone does not guarantee no application
side effects.

`--evidence-kind real` records actual test-server observations; injected transports
and simulation exercises belong to `mock` and must stay in separate reports.
For capacity, real HTTP timing does not imply real GPU execution. Exit 0 means
the plan ran or all measured requests succeeded; exit 1 preserves HTTP/transport
failures, and exit 2 means unavailable/refused setup. There are no latency gates,
performance grades, fabricated measurements or pass claims for missing services.

## GPU measurement operator procedure

The GPU tool defaults to a network-free plan covering these exact existing presets:
`quick-demo`, `mixed-actions`, `verified-outcome`, `layup-demo`. Each is measured in
`quick` and `full` modes, with `--samples` repetitions per preset/mode. `--mode`
can select either mode explicitly. Each configured sample is a distinct submitted
test job, not a retry intended to replace a failure.

Supply **one** dedicated test account via the same JSON credential format and
explicitly record the target engine version. The version is operator-provided
metadata (`version_source: operator_provided`); the tool does not infer a remote
version from this checkout's `research_engine/VERSION`.

```sh
python scripts/measure_gpu_acceptance.py --dry-run \
  --base-url https://gpu-fixture.invalid --credentials-env GPU_TEST_CREDENTIALS \
  --engine-version fixture-1 --mode both --samples 1

# Template only. This task does not execute a remote GPU or this command.
python scripts/measure_gpu_acceptance.py --execute --test-environment \
  --base-url https://gpu-fixture.invalid --credentials-env GPU_TEST_CREDENTIALS \
  --engine-version fixture-1 --mode both --samples 1 \
  --task-timeout 3600 --poll-interval 2 --timeout 10 \
  > gpu-run-unique.json
```

Execution first reads `/api/v1/system/readiness` and `/api/v1/presets`. Real runs
require `ready: true` and `mode: gpu`; mock runs require `mode: simulation`.
Missing/unready engine or presets yields unavailable outcomes without submitting
any jobs. The server's readiness check may itself perform its configured GPU
probe; that happens only on an explicitly executed test-server run.

Samples use `POST /api/v1/tasks/from-preset` and poll `GET /api/v1/tasks/{id}`.
The tool records preset, mode, sample, task ID, HTTP outcomes, terminal task state,
client wall time, queue wait (`started_at - submitted_at`) and runtime
(`completed_at - started_at`) from server timestamps. Missing, malformed, naive
or reversed timestamps stay unavailable. Runtime aggregates retain available
failed-task durations too; per-case outcomes remain authoritative. HTTP timings
and server task runtimes measure different things.

The current API exposes no GPU model or VRAM telemetry, so hardware and
`vram_peak_mb` remain null with `unavailable` metadata. No cached preset runtime,
advertised expected duration, guessed memory value or local host GPU is substituted.
`gpu_measured` only describes completed tasks on a server reporting GPU mode; it
does not claim quality acceptance or independently verify hardware identity.
Mock runs always report `gpu_measured: false`.

The CLI never uses SSH, invokes a remote shell, reads local model/video files,
installs models or executes a local GPU process. Rerunning presets on an explicitly
selected test server can create server-side test files and jobs; it must only be
used with the operator's authorized isolated fixtures and quotas.

Timeouts retain task IDs and error outcomes; the tool does not cancel, retry,
delete or clean up server jobs. A timed-out/failed submission may still be active
server-side, and a submission transport failure may not yield an ID. Inspect the
dedicated account's jobs separately before further operator runs. Subsequent
configured samples still run, so an earlier timed-out task can affect their queue
wait. `--task-timeout` bounds polling checks, while `--timeout` is a socket timeout;
they are not server-side cancellation or an exact process-wide wall-clock limit.
Raw outcomes are emitted when the process finishes; an externally killed process
cannot supply a complete report. Retain server-side evidence for interrupted runs.

Exit 0 describes a completed plan or samples without errors; exit 1 retains sample
failures/timeouts, and exit 2 identifies unavailable prerequisites/setup. The
filename “acceptance” does not imply a verdict: quality review, performance
requirements and final acceptance remain the parent's responsibility. Do not
combine mock and real results or replace failed samples with later successful runs.

## Scoped implementation verification record — 2026-09-07

All execution used temporary synthetic SQLite databases/files or injected HTTP
transports. The tools were not pointed at a running service, deployment runtime,
real video, real account or GPU. This record is implementation verification only.

| Command / stage | Actual outcome |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/test_release_recovery.py tests/test_measurement_capacity.py tests/test_measurement_gpu.py --tb=short` before implementation | Exit 1: 36 setup errors (`ModuleNotFoundError` for the three scripts) |
| Focused initial recovery run | Exit 1: 23 passed, 1 failed; active SQLite writer was incorrectly accepted by a read-only connection |
| Synthetic SQLite lock reproduction | `mode=ro` accepted `BEGIN EXCLUSIVE` despite active writer; `mode=rw` refused with “database is locked” |
| Recovery + capacity after lock correction | Exit 0: 30 passed in 0.15s |
| Initial GPU injected-transport tests | Exit 0: 6 passed in 0.06s |
| Expanded scoped tests | Exit 1: 51 passed, 1 failed; missing database raised `FileNotFoundError` instead of the helper's fixed refusal type |
| Same expanded command after normalizing missing regular-file refusal | Exit 0: **52 passed in 0.28s** |
| `.venv/bin/python scripts/release_recovery.py --help`, `.venv/bin/python scripts/measure_capacity.py --help`, `.venv/bin/python scripts/measure_gpu_acceptance.py --help` | All printed CLI usage successfully; no data/network operations |
| `.venv/bin/python scripts/measure_capacity.py --dry-run --base-url https://capacity-fixture.invalid --path /api/v1/presets --credentials-env MISSING_FIXTURE_ENV --samples-per-user 3` | Exit 0: `status: planned`, users 1/5/10/20, 20 required credentials, empty measured runs |
| `.venv/bin/python scripts/measure_gpu_acceptance.py --dry-run --base-url https://gpu-fixture.invalid --credentials-env MISSING_FIXTURE_ENV --engine-version fixture-1 --mode both --samples 1` | Exit 0: `status: planned`, 8 planned submissions, `gpu_measured: false`, empty measured outcomes |

The 52 focused cases include corruption and rehashed-invalid-manifest refusal,
restore/rollback, empty/nonempty targets, unsafe paths/link types, SQLite integrity
and FK failures, existing and newly competing writers, source-byte preservation,
change detection, credential redaction, redirect/proxy refusal, percentile handling,
all concurrency levels, quick/full preset samples, unready/mocked engines, submission
failures and polling timeouts. Test elapsed times above describe synthetic test
execution only. They are not backup/restore RTOs, capacity figures or GPU runtimes.
No final acceptance failure/optimization loop was run.

The scoped static check also completed successfully: all seven assigned files had
clean whitespace and all six Python files compiled in memory. Git reported branch
`codex/ai-analyst`; concurrent changes outside the seven assigned files were left
untouched. No files were staged or committed.

## Subsequently authorized isolated recovery drill — 2026-09-07

At the parent's explicit request, one drill ran against its prepared offline source
`/private/tmp/dsb-closeout-recovery/source`, containing only `data.sqlite` (12,288
bytes) and `files/synthetic.bin` (110,592 bytes). No application or worker was
attached to those files. No fallback source was needed, and the original source
remained byte-for-byte unchanged.

The single executed orchestration command, from the designated worktree, was:

```sh
.venv/bin/python runtime/release-closeout/evidence/recovery/run_once.py
```

It exited 0. The results below are saved outcomes from that run; handing them to
the parent does not rerun the drill.

The drill ran from **04:50:24.037829 to 04:50:24.267654 UTC**. Exactly eight recovery
CLI invocations ran once and all exited 0: plan old state, snapshot old, verify old,
restore old into an isolated candidate, snapshot the subsequently modified synthetic
new state, verify new, restore new into another empty target, and rollback old into
a separate empty target. The sole simulated upgrade changed only the restored
candidate's database and binary using recorded synthetic SQL and a recorded suffix.
It did not switch an application release or deploy anything.

All **12 independent checks** passed in one evaluation: source unchanged; old
snapshot and initial restore matched the source; both selected files changed in
the simulated new state; new snapshot and restore matched that state; rollback
matched the old state exactly and left the new state intact; SQLite integrity and
foreign-key checks succeeded for all six examined databases; manifest digests
matched; and the recovery tool's source hash was unchanged during the drill.

Whole-drill wall time was **0.229828583 seconds**, including subprocess startup.
Per-command timings and snapshot-internal timings are retained separately. These
are observations on a tiny synthetic fixture, not production RTOs or performance
gates. No failed step was retried and no optimization or acceptance loop ran.

Local, Git-ignored evidence is retained at
`runtime/release-closeout/evidence/recovery/`:

- `drill.json`: full results, timings, observed tool hash, all file sizes/checksums,
  exact synthetic mutation and independent checks.
- `commands.txt`, `commands.jsonl`, and numbered JSON files: exact commands and
  sanitized results recorded as each command finished.
- `snapshot-old/`, `snapshot-new/`, `release-new/`, `restored-new/`, `rollback-old/`:
  retained synthetic snapshots and restore/rollback outputs.
- `checksums.sha256`: integrity hashes for 28 evidence artifacts, excluding itself.
- `README.md` and `run_once.py`: summary and exact one-run orchestration source.

Parent will attach final source-freeze metadata separately; the observed tool hash
does not imply a frozen repository-wide revision. The completed drill was saved
before subsequent native Safari preflight and is independent of concurrent app edits.
