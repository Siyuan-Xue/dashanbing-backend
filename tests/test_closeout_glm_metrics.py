import asyncio
from datetime import datetime
import hashlib
import json
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from app.services.glm import GlmError, GlmJsonResult, GlmTextDelta, GlmUsage
from scripts import closeout_glm_metrics as metrics


SECRET = "private-key-prompt-output-https://private.example/private/path"
MESSAGES = [{"role": "user", "content": SECRET}]


def hashed(value):
    return hashlib.sha256(value.encode()).hexdigest()


def events(recorder):
    return [json.loads(line) for line in recorder.path.read_text().splitlines()]


def assert_private(recorder):
    text = recorder.path.read_text()
    for forbidden in (SECRET, "https://", "/private/path", "raw_error", "validation_passed"):
        assert forbidden not in text


class FakeClient:
    def __init__(self, api_key, **kwargs):
        self.api_key = api_key
        self.kwargs = kwargs

    async def complete_json(self, messages, request_id):
        assert messages is MESSAGES
        assert request_id == SECRET
        return GlmJsonResult({"summary": SECRET}, {
            "prompt_tokens": 4, "completion_tokens": True, "total_tokens": -1,
            "secret": SECRET, "prompt_tokens_details": {"cached_tokens": 2, "secret": SECRET},
            "completion_tokens_details": {"reasoning_tokens": 3},
        })

    async def stream(self, messages, request_id):
        yield GlmTextDelta("")
        yield GlmTextDelta(SECRET)
        yield GlmUsage({"total_tokens": 7, "secret": SECRET})


def test_delegates_unchanged_records_safe_usage_and_timestamps(tmp_path):
    recorder = metrics.Recorder(tmp_path)
    cls = metrics.instrument_client(FakeClient, recorder)
    assert issubclass(cls, FakeClient)
    client = cls(SECRET, base_url=SECRET, timeout=13)
    result = asyncio.run(client.complete_json(MESSAGES, request_id=SECRET))
    assert result.data == {"summary": SECRET}
    assert result.usage["secret"] == SECRET  # Only the log is sanitized.
    assert client.api_key == SECRET and client.kwargs == {"base_url": SECRET, "timeout": 13}
    start, end = events(recorder)
    assert start["event"] == "invocation_started"
    assert end["event"] == "invocation_finished"
    assert start["request_id_sha256"] == end["request_id_sha256"] == hashed(SECRET)
    assert end["outcome"] == "provider_success"
    assert end["usage"] == {"prompt_tokens": 4, "prompt_tokens_details": {"cached_tokens": 2},
                            "completion_tokens_details": {"reasoning_tokens": 3}}
    assert datetime.fromisoformat(end["finished_at"]) >= datetime.fromisoformat(start["started_at"])
    assert end["elapsed_seconds"] >= 0
    assert 0 <= end["supplier_network_seconds"] <= end["elapsed_seconds"]
    assert end["first_formal_text_at"] is None
    assert start["active_calls"] == end["peak_active_calls"] == 1
    assert end["active_calls"] == 0
    assert_private(recorder)


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("error,code", [
    (GlmError("rate_limited", retryable=True), "rate_limited"),
    (GlmError(SECRET, retryable=False), "unknown_error"),
    (RuntimeError(SECRET), "unknown_error"),
    (asyncio.CancelledError(SECRET), "cancelled"),
])
def test_preserves_errors_cancellation_and_redacts(tmp_path, stream, error, code):
    class Failing(FakeClient):
        async def complete_json(self, *args, **kwargs):
            raise error

        async def stream(self, *args, **kwargs):
            yield GlmTextDelta(SECRET)
            raise error

    recorder = metrics.Recorder(tmp_path)
    client = metrics.instrument_client(Failing, recorder)(SECRET)

    async def run():
        with pytest.raises(type(error)) as caught:
            if stream:
                async for _ in client.stream(MESSAGES, request_id=SECRET):
                    pass
            else:
                await client.complete_json(MESSAGES, request_id=SECRET)
        assert caught.value is error

    asyncio.run(run())
    end = events(recorder)[-1]
    assert end["error_code"] == code and end["outcome"] != "provider_success"
    assert end["active_calls"] == 0 and end["finished_at"]
    assert bool(end["first_formal_text_at"]) == stream
    assert_private(recorder)


def test_stream_first_text_and_explicit_close_propagate(tmp_path):
    recorder = metrics.Recorder(tmp_path)
    client = metrics.instrument_client(FakeClient, recorder)(SECRET)

    async def run():
        received = [item async for item in client.stream(MESSAGES, SECRET)]
        assert [item.text for item in received if item.type == "text"] == ["", SECRET]
        assert received[-1].usage["secret"] == SECRET

    asyncio.run(run())
    end = events(recorder)[-1]
    assert end["usage"] == {"total_tokens": 7}
    assert 0 <= end["first_formal_text_seconds"] <= end["elapsed_seconds"]
    assert end["started_at"] <= end["first_formal_text_at"] <= end["finished_at"]
    closed = []

    class CloseClient(FakeClient):
        async def stream(self, *args, **kwargs):
            try:
                yield GlmTextDelta(SECRET)
            finally:
                closed.append(True)

    async def close():
        iterator = metrics.instrument_client(CloseClient, recorder)(SECRET).stream(MESSAGES, SECRET)
        await anext(iterator)
        await iterator.aclose()

    asyncio.run(close())
    assert closed == [True]
    assert events(recorder)[-1]["error_code"] == "closed"
    assert events(recorder)[-1]["active_calls"] == 0
    assert_private(recorder)


def test_overlapping_calls_and_retries_are_not_throttled_or_deduplicated(tmp_path):
    recorder = metrics.Recorder(tmp_path)

    async def run():
        entered = 0
        ready = asyncio.Event()

        class Overlap(FakeClient):
            async def complete_json(self, *args, **kwargs):
                nonlocal entered
                entered += 1
                if entered == 3:
                    ready.set()
                await asyncio.wait_for(ready.wait(), 1)
                return GlmJsonResult({}, {})

        client = metrics.instrument_client(Overlap, recorder)(SECRET)
        await asyncio.gather(*(client.complete_json(MESSAGES, SECRET) for _ in range(3)))

    asyncio.run(run())
    rows = events(recorder)
    starts = [row for row in rows if row["event"] == "invocation_started"]
    assert len(starts) == 3
    assert len({row["invocation_id"] for row in starts}) == 3
    assert max(row["active_calls"] for row in rows) == 3
    assert rows[-1]["peak_active_calls"] == 3 and rows[-1]["active_calls"] == 0


def test_install_patches_real_module_and_loaded_aliases_once(tmp_path, monkeypatch):
    from app.services import glm
    monkeypatch.setattr(glm, "GlmClient", FakeClient)
    analyst = SimpleNamespace(GlmClient=FakeClient)
    admin = SimpleNamespace(Provider=FakeClient)
    monkeypatch.setitem(sys.modules, "app.services.analyst", analyst)
    monkeypatch.setitem(sys.modules, "app.services.admin_presets", admin)
    recorder = metrics.install(tmp_path)
    assert analyst.GlmClient is glm.GlmClient is admin.Provider
    assert issubclass(glm.GlmClient, FakeClient)
    assert metrics.install(tmp_path) is recorder
    asyncio.run(glm.GlmClient(SECRET).complete_json(MESSAGES, SECRET))
    assert len(events(recorder)) == 2


def fixture_db(tmp_path):
    path = tmp_path / "fixture.db"
    (tmp_path / "fixture-manifest.json").write_text('{"fixture":true}')
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE analysis (id TEXT, status TEXT, analyst_locale TEXT, created_at TEXT,
                updated_at TEXT, completed_at TEXT);
            CREATE TABLE analyst_report (id TEXT, task_id TEXT, status TEXT, kind TEXT, locale TEXT,
                style TEXT, subject_id TEXT, created_at TEXT, updated_at TEXT);
            CREATE TABLE analyst_job (id TEXT, task_id TEXT, report_id TEXT, message_id TEXT,
                request_id TEXT, status TEXT, kind TEXT, attempts INTEGER, created_at TEXT,
                updated_at TEXT, available_at TEXT, usage_json TEXT, payload_json TEXT);
            CREATE TABLE admin_attempt (kind TEXT, job_id TEXT, created_at TEXT);
        """)
        db.execute("INSERT INTO analysis VALUES (?, 'completed', 'en', ?, ?, ?)",
                   (SECRET, "2026-09-07T00:00:00Z", "2026-09-07T00:00:10Z", "2026-09-07T00:00:10Z"))
        for index, style in enumerate(("coach", "roast")):
            rid = f"report-{index}"
            db.execute("INSERT INTO analyst_report VALUES (?, ?, 'completed', 'session', 'en', ?, NULL, ?, ?)",
                       (rid, SECRET, style, "2026-09-07T00:00:11Z", f"2026-09-07T00:00:{20 + index * 10}Z"))
            db.execute("INSERT INTO analyst_job VALUES (?, ?, ?, NULL, ?, 'completed', 'report', 2, ?, ?, ?, ?, ?)",
                       (rid, SECRET, rid, SECRET if index == 0 else "request-2", "2026-09-07T00:00:11Z",
                        "2026-09-07T00:00:30Z", "2026-09-07T00:00:12Z",
                        json.dumps({"total_tokens": 9, "secret": SECRET}),
                        json.dumps({"locale": "en", "style": style, "question": SECRET})))
        db.execute("INSERT INTO analyst_job VALUES ('prepare', ?, NULL, NULL, 'prepare-request', 'completed', 'prepare', 1, ?, ?, ?, '{}', ?)",
                   (SECRET, "2026-09-07T00:00:10Z", "2026-09-07T00:00:11Z", "2026-09-07T00:00:10Z",
                    '{"collection_version":1,"locale":"en","subjects":[]}'))
        db.execute("INSERT INTO admin_attempt VALUES ('ai', 'report-0', '2026-09-07T00:00:12Z')")
    return path


def test_snapshot_read_only_redacted_and_readiness_uses_persisted_reports(tmp_path):
    path = fixture_db(tmp_path)
    before = path.read_bytes()
    calls = tmp_path / "calls.jsonl"
    calls.write_text(json.dumps({"event": "invocation_started", "request_id_sha256": hashed(SECRET),
                                 "started_at": "2026-09-07T00:00:14Z", "secret": SECRET}) + "\n")
    result = metrics.snapshot(path, calls_path=calls)
    assert path.read_bytes() == before
    assert SECRET not in json.dumps(result)
    task = result["tasks"][0]
    assert task["task_id_sha256"] == hashed(SECRET)
    assert task["first_ready_seconds"] == 10
    assert task["full_ready_seconds"] == 20
    assert task["queue_to_first_invocation_seconds"] == 4
    job = next(row for row in result["jobs"] if row["job_id_sha256"] == hashed("report-0"))
    assert job["queue_to_first_invocation_seconds"] == 3
    assert job["first_attempt_at"] == "2026-09-07T00:00:12Z"
    assert job["usage"] == {"total_tokens": 9}
    with sqlite3.connect(path) as db:
        db.execute("UPDATE analyst_report SET status='failed' WHERE style='roast'")
    result = metrics.snapshot(path, calls_path=calls)
    assert result["tasks"][0]["full_ready_seconds"] is None
    assert result["tasks"][0]["first_ready_seconds"] == 10


def test_snapshot_does_not_claim_full_readiness_without_expected_set(tmp_path):
    path = fixture_db(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM analyst_job WHERE kind='prepare'")
    assert metrics.snapshot(path)["tasks"][0]["full_ready_seconds"] is None


def test_snapshot_refuses_non_fixture_or_unmarked_database(tmp_path):
    path = fixture_db(tmp_path)
    with pytest.raises(ValueError):
        metrics.snapshot(tmp_path / "production.db")
    (tmp_path / "fixture-manifest.json").unlink()
    with pytest.raises(ValueError):
        metrics.snapshot(path)


def test_runtime_log_write_failure_preserves_result(tmp_path):
    recorder = metrics.Recorder(tmp_path)
    recorder.path.unlink()
    recorder.path.mkdir()
    client = metrics.instrument_client(FakeClient, recorder)(SECRET)
    result = asyncio.run(client.complete_json(MESSAGES, SECRET))
    assert result.data == {"summary": SECRET}
    assert recorder.write_failures == 2 and recorder.active_calls == 0


def test_snapshot_missing_subject_variant_and_untrusted_metadata(tmp_path):
    path = fixture_db(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE analyst_job SET payload_json=? WHERE kind='prepare'",
                   (json.dumps({"collection_version": 1, "locale": "en", "subjects": [SECRET]}),))
        db.execute("UPDATE analyst_report SET style=?,created_at=? WHERE style='roast'", (SECRET, SECRET))
        db.execute("UPDATE analyst_job SET status=?,usage_json=? WHERE kind='report'",
                   (SECRET, json.dumps({"total_tokens": 1.5, "prompt_tokens": True, "secret": SECRET})))
    result = metrics.snapshot(path)
    assert result["tasks"][0]["expected_report_count"] == 4
    assert result["tasks"][0]["full_ready_seconds"] is None
    assert SECRET not in json.dumps(result)
    assert result["reports"][1]["style"] == "unknown"
    assert result["reports"][1]["created_at"] is None
    assert result["jobs"][0]["status"] == "unknown" and result["jobs"][0]["usage"] == {}


def test_snapshot_uses_read_only_connection_and_preserves_call_history(tmp_path, monkeypatch):
    path = fixture_db(tmp_path)
    original = sqlite3.connect
    reads = []

    def read_only(database, **kwargs):
        assert database.endswith("fixture.db?mode=ro") and kwargs == {"uri": True}
        db = original(database, **kwargs)
        db.set_trace_callback(reads.append)
        return db

    monkeypatch.setattr(sqlite3, "connect", read_only)
    calls = tmp_path / "calls.jsonl"
    calls.write_text("")
    with pytest.raises(ValueError):
        metrics.snapshot(path, calls, calls_path=calls)
    assert "PRAGMA query_only=ON" in reads
    assert not any(sql.lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE")) for sql in reads)
    assert calls.read_text() == ""
