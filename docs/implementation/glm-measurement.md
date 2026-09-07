# Isolated GLM measurement sidecar

Preparation for one measurement pass; no requests or optimization runs are made
by this module. Only the isolated fixture launcher should opt in, after fixture
creation and before workers start:

```python
from scripts.closeout_glm_metrics import install, snapshot

recorder = install(root / "output")
# Start the existing application normally. After the measurement:
snapshot(root / "runtime" / "fixture.db", root / "output" / "glm-snapshot.json",
         calls_path=recorder.path)
```

`install(output_directory)` subclasses the real `app.services.glm.GlmClient` in
the current process and replaces loaded aliases in `analyst` and `admin_presets`.
It preserves constructor settings, arguments, returned objects, exceptions,
cancellation and explicit stream closure. It adds no retries, concurrency limits
or production startup hooks. An already injected application client is untouched.
Repeated installation for the same output is idempotent; use one server process.

`glm-calls.jsonl` appends start, first nonempty formal-text, and finish events.
Each invocation has its own opaque ID; SHA256 of the original request ID joins
retries to a job. Retries are never deduplicated. UTC timestamps and monotonic
durations record actual delegated calls, including failures. First formal text
means text surfaced by the real transport, not reasoning, persisted text or a
validated report. Unconsumed stream iterators generate no invocation.

`supplier_network_seconds` sums time executing/awaiting the real client, including
provider processing, network transport, client parsing and cleanup. These parts
cannot be separated from this boundary. It excludes time the stream consumer
holds a yielded event. `elapsed_seconds` measures the complete invocation lifetime
and includes consumer pauses and small instrumentation overhead. Neither field
measures internal GPU waiting. Active/peak counts measure overlapping delegated
call lifetimes in this process, including suspended streams; they are not GPU
utilization, socket counts or configured concurrency. A provider-success event
does **not** assert that application report validation or persistence succeeded.

The snapshot requires an explicit, nonsymlink `fixture.db` beside the existing
`fixture-manifest.json` with `fixture: true`. It opens SQLite with `mode=ro` and
`query_only`, reads one transaction, and never loads report bodies. It emits only
hashed IDs, allowlisted statuses/kinds/locales/styles, subject-presence booleans,
timestamps, attempt counts, numeric token usage and derived readiness metadata.
Durable `admin_attempt` timestamps and actual invocation timestamps remain distinct.

For each task's initial locale, first readiness is the first persisted completed
session-report timestamp after video completion. Full readiness requires both
styles for the session and every subject listed by the latest completed version-1
preparation job. Missing expected-set metadata, variants, timestamps or failed
variants leave full readiness `null`. These are persisted metadata observations,
not a fresh validation of report bodies or cache freshness. Later regeneration or
row deletion can change the snapshot; this is not a historical transition log.
Queue delay is job creation to first actual invocation; at task level it starts
with the earliest analyst job, including preparation. Missing evidence stays
`null`; no internal provider/GPU wait is inferred. Usage is retained per job and
per invocation, so retry usage must not be summed twice across those sources.

No prompts, outputs, keys, URLs, paths, subject labels or raw errors enter the
artifacts. Error codes and numeric usage keys use fixed allowlists; unknown codes
become `unknown_error`. IDs are hashed for correlation, not guaranteed anonymity
against guessed IDs. Runtime log-write failures increment `recorder.write_failures`
without altering client outcomes; nonzero failures or unmatched start events mean
incomplete measurements. No missing finish is synthesized after a process crash.

Offline checks: `.venv/bin/python -m pytest tests/test_closeout_glm_metrics.py -q`.
