#!/usr/bin/env python3
"""Measure explicit test-server preset reruns. No SSH, local GPU, or shell runner."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
import time

if __package__:
    from .measure_capacity import (MeasurementError, add_common_arguments, distribution,
                                   http_request, load_tokens, positive, safe_error, validate_base_url)
else:
    from measure_capacity import (MeasurementError, add_common_arguments, distribution,
                                  http_request, load_tokens, positive, safe_error, validate_base_url)

# Mirrors app.services.presets.PRESETS without importing app settings or data.
PRESETS = ("quick-demo", "mixed-actions", "verified-outcome", "layup-demo")
MODES = ("quick", "full")
TERMINAL = {"completed", "failed", "canceled", "expired", "interrupted"}
STATES = TERMINAL | {"queued", "running", "draft", "uploading", "cancel_requested"}


def elapsed_between(start, end):
    try:
        begin = datetime.fromisoformat(start.replace("Z", "+00:00"))
        finish = datetime.fromisoformat(end.replace("Z", "+00:00"))
        if begin.tzinfo is None or finish.tzinfo is None:
            return None
        seconds = (finish - begin).total_seconds()
        return seconds if seconds >= 0 else None
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def new_outcomes(modes, samples):
    return [{"preset": preset, "mode": mode, "sample": sample + 1, "status": "unavailable",
             "task_id": None, "error": None, "http_events": [], "wall_seconds": None,
             "queue_seconds": None, "runtime_seconds": None,
             "timing_source": "server_task_timestamps", "timing_status": "unavailable",
             "vram_peak_mb": None, "vram_status": "unavailable",
             "vram_reason": "current_api_does_not_expose_vram"}
            for preset in PRESETS for mode in modes for sample in range(samples)]


def measure(base_url, token, *, engine_version, modes=MODES, samples=1, timeout=10,
            task_timeout=3600, poll_interval=2, transport=None, evidence_kind="real"):
    base_url = validate_base_url(base_url)
    for value in (samples, timeout, task_timeout, poll_interval):
        positive(value)
    if type(samples) is not int or not modes or len(set(modes)) != len(modes) or not set(modes) <= set(MODES):
        raise MeasurementError("invalid_modes_or_samples")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}", engine_version):
        raise MeasurementError("explicit_engine_version_required")
    if evidence_kind not in ("real", "mock"):
        raise MeasurementError("invalid_evidence_kind")
    transport = transport or http_request
    report = {"schema_version": 1, "tool": "measure_gpu_acceptance", "status": "unavailable",
              "evidence_kind": evidence_kind, "gpu_measured": False,
              "base_url": base_url, "engine_version": engine_version,
              "version_source": "operator_provided", "modes": list(modes), "samples_per_case": samples,
              "started_at": datetime.now(timezone.utc).isoformat(),
              "gpu_model": None, "gpu_metadata_status": "unavailable",
              "gpu_metadata_reason": "current_api_does_not_expose_hardware",
              "outcomes": new_outcomes(modes, samples), "errors": 0, "preflight": [],
              "percentile_method": "nearest_rank"}
    started = time.perf_counter()

    def request(method, path, payload, events, limit=timeout):
        event = {"method": method, "phase": "preflight" if events is report["preflight"] else (
            "submit" if method == "POST" else "poll"), "http_status": None, "error": None}
        events.append(event)
        try:
            code, data = transport(method, base_url + path, token, payload, limit)
            event["http_status"] = code
        except Exception as error:
            event["error"] = safe_error(error)
            raise MeasurementError("request_failed") from None
        if not 200 <= code < 300:
            event["error"] = "http_error"
            raise MeasurementError("http_error")
        return data

    try:
        readiness = request("GET", "/api/v1/system/readiness", None, report["preflight"])
        expected_mode = "gpu" if evidence_kind == "real" else "simulation"
        if (not isinstance(readiness, dict) or readiness.get("ready") is not True
                or readiness.get("mode") != expected_mode):
            raise MeasurementError("required_engine_unavailable")
        presets = request("GET", "/api/v1/presets", None, report["preflight"])
        if (not isinstance(presets, list)
                or not set(PRESETS) <= {p.get("id") for p in presets if isinstance(p, dict) and isinstance(p.get("id"), str)}):
            raise MeasurementError("required_presets_unavailable")
    except MeasurementError as error:
        report["unavailable_reason"] = str(error)
        for outcome in report["outcomes"]:
            outcome["error"] = str(error)
    else:
        report["status"] = "measured"
        for outcome in report["outcomes"]:
            trial_started = time.perf_counter()
            deadline = trial_started + task_timeout
            task = {}
            try:
                task = request("POST", "/api/v1/tasks/from-preset",
                               {"preset_id": outcome["preset"], "mode": outcome["mode"]},
                               outcome["http_events"], min(timeout, task_timeout))
                task_id = task.get("id") if isinstance(task, dict) else None
                if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", task_id):
                    raise MeasurementError("invalid_task_response")
                outcome["task_id"] = task_id
                while True:
                    if not isinstance(task, dict) or task.get("status") not in STATES:
                        raise MeasurementError("invalid_task_response")
                    if task["status"] in TERMINAL:
                        outcome["status"] = task["status"]
                        if task["status"] != "completed":
                            outcome["error"] = "task_" + task["status"]
                        break
                    remaining = deadline - time.perf_counter()
                    if remaining <= 0:
                        outcome.update(status="timeout", error="poll_deadline_exceeded")
                        break
                    task = request("GET", "/api/v1/tasks/" + task_id, None,
                                   outcome["http_events"], min(timeout, remaining))
                    if isinstance(task, dict) and task.get("status") not in TERMINAL:
                        time.sleep(min(poll_interval, max(0, deadline - time.perf_counter())))
            except MeasurementError as error:
                outcome.update(status="error", error=str(error))
            finally:
                outcome["wall_seconds"] = time.perf_counter() - trial_started
                if isinstance(task, dict):
                    outcome["queue_seconds"] = elapsed_between(task.get("submitted_at"), task.get("started_at"))
                    outcome["runtime_seconds"] = elapsed_between(task.get("started_at"), task.get("completed_at"))
                    if outcome["queue_seconds"] is not None and outcome["runtime_seconds"] is not None:
                        outcome["timing_status"] = "available"
                if outcome["status"] != "completed":
                    report["errors"] += 1
        report["gpu_measured"] = evidence_kind == "real" and any(
            row["status"] == "completed" for row in report["outcomes"])
    report["wall_seconds"] = time.perf_counter() - started
    for metric in ("queue_seconds", "runtime_seconds"):
        report[metric] = distribution([row[metric] for row in report["outcomes"] if row[metric] is not None])
    # Keep separate distributions for each preset/mode; combined summary is only
    # descriptive and must not hide per-case failures or unavailable samples.
    report["cases"] = [{"preset": preset, "mode": mode,
                         "runtime_seconds": distribution([row["runtime_seconds"] for row in report["outcomes"]
                             if row["preset"] == preset and row["mode"] == mode and row["runtime_seconds"] is not None]),
                         "errors": sum(row["status"] != "completed" for row in report["outcomes"]
                             if row["preset"] == preset and row["mode"] == mode)}
                        for preset in PRESETS for mode in modes]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_arguments(parser)
    parser.add_argument("--engine-version", required=True, help="Operator-verified target engine version, not local inference")
    parser.add_argument("--mode", choices=(*MODES, "both"), default="both")
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--task-timeout", type=float, default=3600)
    parser.add_argument("--poll-interval", type=float, default=2)
    args = parser.parse_args(argv)
    try:
        base_url = validate_base_url(args.base_url)
        for value in (args.samples, args.timeout, args.task_timeout, args.poll_interval):
            positive(value)
        modes = MODES if args.mode == "both" else (args.mode,)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}", args.engine_version):
            raise MeasurementError("explicit_engine_version_required")
        if not args.execute:
            report = {"schema_version": 1, "status": "planned", "base_url": base_url,
                      "evidence_kind": args.evidence_kind, "gpu_measured": False,
                      "engine_version": args.engine_version, "version_source": "operator_provided",
                      "presets": PRESETS, "modes": modes, "samples_per_case": args.samples,
                      "planned_submissions": len(PRESETS) * len(modes) * args.samples, "outcomes": []}
        else:
            if not args.test_environment:
                raise MeasurementError("isolated_test_environment_acknowledgment_required")
            tokens = load_tokens(args.credentials_env, base_url, timeout=args.timeout)
            if len(tokens) != 1:
                raise MeasurementError("one_dedicated_gpu_test_credential_required")
            report = measure(base_url, tokens[0], engine_version=args.engine_version,
                             modes=modes, samples=args.samples, timeout=args.timeout,
                             task_timeout=args.task_timeout, poll_interval=args.poll_interval,
                             evidence_kind=args.evidence_kind)
    except (MeasurementError, OSError) as error:
        print(json.dumps({"status": "unavailable", "error": safe_error(error), "outcomes": [],
                          "evidence_kind": args.evidence_kind, "gpu_measured": False}))
        return 2
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    if report["status"] == "unavailable":
        return 2
    return 1 if report.get("errors", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
