"""Opt-in GLM invocation measurements for the isolated closeout fixture only.

Importing this module has no application side effects. No provider requests,
retries, scheduling changes, or report validation are performed here.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import threading
import time
from uuid import uuid4


ERROR_CODES = frozenset({
    "rate_limited", "upstream_error", "timeout", "transport_error",
    "invalid_response", "incomplete_response",
})
STATUSES = frozenset({"draft", "uploading", "queued", "running", "completed", "failed",
                      "canceled", "expired"})


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if isinstance(value, str) else None


def _allowed(value, choices):
    return value if isinstance(value, str) and value in choices else "unknown"


def sanitize_usage(value):
    """Copy only nonnegative integer token counters; never stringify metadata."""
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens", "reasoning_tokens"):
        count = value.get(key)
        if type(count) is int and 0 <= count <= 2**63 - 1:
            result[key] = count
    for key, counter in (("prompt_tokens_details", "cached_tokens"),
                         ("completion_tokens_details", "reasoning_tokens")):
        details = value.get(key)
        if isinstance(details, dict):
            count = details.get(counter)
            if type(count) is int and 0 <= count <= 2**63 - 1:
                result[key] = {counter: count}
    return result


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError):
        return None


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _epoch(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def _first(values):
    return min((value for value in values if value), key=_epoch, default=None)


def _elapsed(start, end):
    if not start or not end:
        return None
    seconds = _epoch(end) - _epoch(start)
    return seconds if seconds >= 0 else None


class Recorder:
    """One process's actual delegated call lifetimes, with append-only events.

    The lock serializes bookkeeping only. It never limits provider concurrency.
    Runtime write failures are counted locally and never replace client outcomes.
    """

    def __init__(self, output):
        directory = Path(output).resolve()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "glm-calls.jsonl"
        # Fail before startup if the explicitly chosen destination is unwritable.
        with self.path.open("a", encoding="utf-8"):
            pass
        self.path.chmod(0o600)
        self._lock = threading.RLock()
        self.active_calls = 0
        self.peak_active_calls = 0
        self.write_failures = 0

    def _write(self, row):
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n")
        except OSError:
            self.write_failures += 1

    def _event(self, call, event):
        self._write({**{k: v for k, v in call.items() if not k.startswith("_")},
                     "event": event, "active_calls": self.active_calls,
                     "peak_active_calls": self.peak_active_calls})

    def begin(self, method, request_id):
        with self._lock:
            self.active_calls += 1
            self.peak_active_calls = max(self.peak_active_calls, self.active_calls)
            call = {"invocation_id": _hash(str(uuid4())), "request_id_sha256": _hash(request_id),
                    "method": method, "started_at": _now(), "finished_at": None,
                    "elapsed_seconds": None, "supplier_network_seconds": 0.0, "first_formal_text_at": None,
                    "first_formal_text_seconds": None, "usage": {}, "error_code": None,
                    "outcome": "in_progress", "_start": time.perf_counter()}
            self._event(call, "invocation_started")
            return call

    def first_text(self, call):
        with self._lock:
            if call["first_formal_text_at"] is None:
                call["first_formal_text_at"] = _now()
                call["first_formal_text_seconds"] = time.perf_counter() - call["_start"]
                self._event(call, "first_formal_text")

    def finish(self, call, error):
        with self._lock:
            call["finished_at"] = _now()
            call["elapsed_seconds"] = time.perf_counter() - call["_start"]
            if error is None:
                call["outcome"] = "provider_success"
            else:
                call["outcome"] = "provider_error"
                if isinstance(error, asyncio.CancelledError):
                    call["error_code"] = "cancelled"
                    call["outcome"] = "cancelled"
                elif isinstance(error, GeneratorExit):
                    call["error_code"] = "closed"
                    call["outcome"] = "closed"
                else:
                    code = getattr(error, "code", None)
                    call["error_code"] = code if isinstance(code, str) and code in ERROR_CODES else "unknown_error"
            self.active_calls -= 1
            self._event(call, "invocation_finished")


def instrument_client(client_class, recorder):
    """Subclass the supplied real client; injection allows completely offline tests."""
    class MeasuredGlmClient(client_class):
        _closeout_recorder = recorder

        async def complete_json(self, messages, request_id):
            call = recorder.begin("complete_json", request_id)
            error = None
            try:
                before = time.perf_counter()
                try:
                    result = await super().complete_json(messages, request_id=request_id)
                finally:
                    call["supplier_network_seconds"] += time.perf_counter() - before
                call["usage"] = sanitize_usage(result.usage)
                return result
            except BaseException as exc:
                error = exc
                raise
            finally:
                recorder.finish(call, error)

        async def stream(self, messages, request_id):
            call = recorder.begin("stream", request_id)
            error = None
            iterator = None
            try:
                iterator = super().stream(messages, request_id=request_id)
                while True:
                    before = time.perf_counter()
                    try:
                        item = await anext(iterator)
                    except StopAsyncIteration:
                        break
                    finally:
                        call["supplier_network_seconds"] += time.perf_counter() - before
                    if item.type == "text" and item.text:
                        recorder.first_text(call)
                    elif item.type == "usage":
                        call["usage"] = sanitize_usage(item.usage)
                    yield item
            except BaseException as exc:
                error = exc
                raise
            finally:
                try:
                    if iterator is not None:
                        before = time.perf_counter()
                        try:
                            await iterator.aclose()
                        finally:
                            call["supplier_network_seconds"] += time.perf_counter() - before
                except BaseException as exc:
                    if error is None:
                        error = exc
                        raise
                finally:
                    recorder.finish(call, error)

    return MeasuredGlmClient


def install(output):
    """Explicit fixture startup hook: install(root / 'output') before workers start.

    Patch only this process, including already imported aliases in the two known
    consumers. A repeated call for the same destination cannot double-wrap.
    """
    from app.services import glm

    original = glm.GlmClient
    previous = getattr(original, "_closeout_recorder", None)
    if previous is not None:
        if previous.path.parent != Path(output).resolve():
            raise ValueError("GLM measurements already installed for another fixture output")
        return previous
    recorder = Recorder(output)
    measured = instrument_client(original, recorder)
    glm.GlmClient = measured
    for name in ("app.services.analyst", "app.services.admin_presets"):
        module = sys.modules.get(name)
        if module is not None:
            for alias, value in tuple(vars(module).items()):
                if value is original:
                    setattr(module, alias, measured)
    return recorder


def _json(value):
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return None


def _call_starts(path):
    starts = {}
    if path is None:
        return starts
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            row = _json(line)
            if not isinstance(row, dict) or row.get("event") != "invocation_started":
                continue
            key, at = row.get("request_id_sha256"), _timestamp(row.get("started_at"))
            if isinstance(key, str) and len(key) == 64 and all(c in "0123456789abcdef" for c in key) and at:
                starts[key] = _first((starts.get(key), at))
    return starts


def snapshot(fixture_db, output=None, *, calls_path=None):
    """Read an explicitly selected, marked fixture.db; return only safe metadata.

    Optional output is a JSON filename. No database discovery or app settings are
    consulted. Missing timing evidence is null, never a fabricated zero.
    """
    path = Path(fixture_db)
    marker = path.parent / "fixture-manifest.json"
    if path.name != "fixture.db" or path.is_symlink() or not path.is_file() or not marker.is_file():
        raise ValueError("An explicit isolated fixture.db and fixture manifest are required")
    manifest = _json(marker.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("fixture") is not True:
        raise ValueError("An isolated fixture manifest is required")
    starts = _call_starts(calls_path)
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        tasks = list(connection.execute("SELECT id,status,analyst_locale,created_at,updated_at,completed_at FROM analysis"))
        reports = list(connection.execute("SELECT id,task_id,status,kind,locale,style,subject_id,created_at,updated_at FROM analyst_report"))
        # JSON projection avoids loading prompts, facts, questions, or report bodies.
        jobs = list(connection.execute("""SELECT id,task_id,report_id,message_id,request_id,status,kind,attempts,
            created_at,updated_at,available_at,usage_json,
            json_extract(CASE WHEN json_valid(payload_json) THEN payload_json ELSE '{}' END, '$.locale') AS locale,
            json_extract(CASE WHEN json_valid(payload_json) THEN payload_json ELSE '{}' END, '$.style') AS style,
            json_extract(CASE WHEN json_valid(payload_json) THEN payload_json ELSE '{}' END, '$.subject_id') IS NOT NULL AS has_subject,
            CASE WHEN kind='prepare' AND json_valid(payload_json) THEN json_extract(payload_json,'$.subjects') END AS subjects,
            CASE WHEN kind='prepare' AND json_valid(payload_json) THEN json_extract(payload_json,'$.collection_version') END AS collection_version
            FROM analyst_job"""))
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        attempts = {}
        if "admin_attempt" in tables:
            for row in connection.execute("SELECT job_id,created_at FROM admin_attempt WHERE kind='ai'"):
                attempts[row["job_id"]] = _first((attempts.get(row["job_id"]), _timestamp(row["created_at"])))
    finally:
        connection.close()

    safe_jobs = []
    for row in jobs:
        invoked = starts.get(_hash(row["request_id"]))
        created = _timestamp(row["created_at"])
        safe_jobs.append({"job_id_sha256": _hash(row["id"]), "task_id_sha256": _hash(row["task_id"]),
                          "report_id_sha256": _hash(row["report_id"]), "message_id_sha256": _hash(row["message_id"]),
                          "request_id_sha256": _hash(row["request_id"]),
                          "status": _allowed(row["status"], STATUSES),
                          "kind": _allowed(row["kind"], {"prepare", "report", "message"}),
                          "locale": _allowed(row["locale"], {"zh", "en"}),
                          "style": _allowed(row["style"], {"coach", "roast"}), "has_subject": bool(row["has_subject"]),
                          "attempts": row["attempts"] if type(row["attempts"]) is int and row["attempts"] >= 0 else None,
                          "created_at": created, "updated_at": _timestamp(row["updated_at"]),
                          "available_at": _timestamp(row["available_at"]),
                          "first_attempt_at": attempts.get(row["id"]), "first_invocation_at": invoked,
                          "queue_to_first_invocation_seconds": _elapsed(created, invoked),
                          "usage": sanitize_usage(_json(row["usage_json"]))})
    safe_reports = []
    for row in reports:
        linked = [job for job in safe_jobs if job["report_id_sha256"] == _hash(row["id"])]
        safe_reports.append({"report_id_sha256": _hash(row["id"]), "task_id_sha256": _hash(row["task_id"]),
                             "status": _allowed(row["status"], STATUSES),
                             "kind": _allowed(row["kind"], {"session", "comparison"}),
                             "locale": _allowed(row["locale"], {"zh", "en"}),
                             "style": _allowed(row["style"], {"coach", "roast"}),
                             "has_subject": row["subject_id"] is not None,
                             "created_at": _timestamp(row["created_at"]), "updated_at": _timestamp(row["updated_at"]),
                             "first_attempt_at": _first(job["first_attempt_at"] for job in linked)})
    safe_tasks = []
    for task in tasks:
        task_jobs = [row for row in jobs if row["task_id"] == task["id"]]
        task_reports = [row for row in reports if row["task_id"] == task["id"]
                        and row["kind"] == "session" and row["locale"] == task["analyst_locale"]]
        completed = _timestamp(task["completed_at"]) if task["status"] == "completed" else None
        ready = [_timestamp(row["updated_at"]) for row in task_reports if row["status"] == "completed"]
        first_ready = _first(at for at in ready if _elapsed(completed, at) is not None)
        preparations = [row for row in task_jobs if row["kind"] == "prepare" and _timestamp(row["created_at"])]
        prepared = max(preparations, key=lambda row: _epoch(_timestamp(row["created_at"])), default=None)
        full_ready = None
        expected_count = None
        if (prepared is not None and prepared["status"] == "completed" and prepared["collection_version"] == 1
                and prepared["locale"] == task["analyst_locale"]):
            subjects = _json(prepared["subjects"])
            if isinstance(subjects, list) and all(isinstance(value, str) for value in subjects):
                expected = {(subject, style) for subject in [None, *subjects] for style in ("coach", "roast")}
                expected_count = len(expected)
                variants = {}
                for row in task_reports:
                    key = (row["subject_id"], row["style"])
                    existing = variants.get(key)
                    if existing is None or (_timestamp(row["created_at"]) and
                            _epoch(_timestamp(row["created_at"])) > _epoch(_timestamp(existing["created_at"]) or "1970-01-01T00:00:00Z")):
                        variants[key] = row
                if all(key in variants and variants[key]["status"] == "completed"
                       and _elapsed(completed, _timestamp(variants[key]["updated_at"])) is not None for key in expected):
                    full_ready = max((_timestamp(variants[key]["updated_at"]) for key in expected), key=_epoch)
        queued = _first(_timestamp(row["created_at"]) for row in task_jobs)
        invoked = _first(starts.get(_hash(row["request_id"])) for row in task_jobs)
        safe_tasks.append({"task_id_sha256": _hash(task["id"]), "status": _allowed(task["status"], STATUSES),
                           "locale": _allowed(task["analyst_locale"], {"zh", "en"}),
                           "created_at": _timestamp(task["created_at"]), "updated_at": _timestamp(task["updated_at"]),
                           "video_completed_at": completed, "queued_at": queued,
                           "first_attempt_at": _first(attempts.get(row["id"]) for row in task_jobs),
                           "first_invocation_at": invoked, "queue_to_first_invocation_seconds": _elapsed(queued, invoked),
                           "first_ready_at": first_ready, "first_ready_seconds": _elapsed(completed, first_ready),
                           "full_ready_at": full_ready, "full_ready_seconds": _elapsed(completed, full_ready),
                           "expected_report_count": expected_count})
    result = {"snapshot_at": _now(), "readiness_basis": "persisted_report_status",
              "tasks": safe_tasks, "jobs": safe_jobs, "reports": safe_reports}
    if output is not None:
        destination = Path(output)
        # A snapshot must never overwrite its input or SQLite sidecars.
        if destination.resolve() in {path.resolve(), marker.resolve(),
                                     Path(str(path.resolve()) + "-wal"), Path(str(path.resolve()) + "-shm")}:
            raise ValueError("Snapshot output must be separate from fixture inputs")
        if calls_path is not None and destination.resolve() == Path(calls_path).resolve():
            raise ValueError("Snapshot output must preserve invocation history")
        with destination.open("w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, allow_nan=False)
            handle.write("\n")
        destination.chmod(0o600)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-db", required=True, type=Path)
    parser.add_argument("--calls", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        snapshot(args.fixture_db, args.output, calls_path=args.calls)
    except (ValueError, OSError, sqlite3.Error):
        parser.exit(1, "Isolated GLM snapshot failed; verify fixture inputs and output destination.\n")


if __name__ == "__main__":
    main()
