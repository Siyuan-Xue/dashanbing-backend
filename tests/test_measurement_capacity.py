"""No external requests: inject a transport over synthetic response objects."""
import importlib
import json
import threading

import pytest


@pytest.fixture
def capacity():
    return importlib.import_module("scripts.measure_capacity")


def test_nearest_rank_percentiles_and_empty_data(capacity):
    assert capacity.distribution([]) == {"count": 0, "p50": None, "p95": None, "p99": None}
    assert capacity.distribution(list(range(1, 101))) == {"count": 100, "p50": 50, "p95": 95, "p99": 99}


def test_all_concurrency_levels_preserve_errors(capacity):
    lock = threading.Lock()
    count = 0

    def transport(method, url, token, payload, timeout):
        nonlocal count
        with lock:
            count += 1
            current = count
        if current % 4 == 0:
            raise TimeoutError("SYNTHETIC-SECRET must not appear")
        return 503 if current % 3 == 0 else 200, {"secret": "SYNTHETIC-SECRET"}

    report = capacity.measure("http://fixture.invalid", "/api/v1/presets", [f"fake-{i}" for i in range(20)],
                              samples=2, transport=transport, evidence_kind="mock")
    assert [row["users"] for row in report["runs"]] == [1, 5, 10, 20]
    assert report["evidence_kind"] == "mock"
    for run in report["runs"]:
        assert len(run["outcomes"]) == run["users"] * 2
        assert run["errors"] == sum(not item["ok"] for item in run["outcomes"])
        assert run["latency_ms"]["count"] == len(run["outcomes"])
        assert run["wall_seconds"] >= 0
    assert any(run["errors"] for run in report["runs"])
    assert "SYNTHETIC-SECRET" not in json.dumps(report)
    assert "passed" not in report


def test_unique_credentials_and_explicit_safe_url(capacity, monkeypatch):
    monkeypatch.setenv("FIXTURE_CREDENTIALS", json.dumps([{"token": f"fake-{i}"} for i in range(20)]))
    assert len(capacity.load_tokens("FIXTURE_CREDENTIALS", "http://127.0.0.1:9999")) == 20
    for url in ["", "file:///tmp/foo", "https://user:secret@example.com", "https://example.com?token=secret"]:
        with pytest.raises(capacity.MeasurementError):
            capacity.validate_base_url(url)
    with pytest.raises(capacity.MeasurementError):
        capacity.measure("http://fixture.invalid", "/api/v1/presets", ["same"] * 20)


def test_dry_run_does_not_load_credentials_or_connect(capacity, capsys, monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("dry-run performed I/O")

    monkeypatch.setattr(capacity, "load_tokens", fail)
    monkeypatch.setattr(capacity, "http_request", fail)
    assert capacity.main(["--base-url", "http://fixture.invalid", "--path", "/api/v1/presets",
                          "--credentials-env", "MISSING_FIXTURE_ENV"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "planned"
    assert report["runs"] == []


def test_missing_credentials_is_unavailable_not_pass(capacity, monkeypatch, capsys):
    monkeypatch.delenv("MISSING_FIXTURE_ENV", raising=False)
    assert capacity.main(["--base-url", "http://fixture.invalid", "--path", "/api/v1/presets",
                          "--credentials-env", "MISSING_FIXTURE_ENV", "--execute", "--test-environment"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "unavailable"


def test_credentials_login_failure_is_redacted(capacity, monkeypatch):
    monkeypatch.setenv("FIXTURE_CREDENTIALS", '[{"username":"fake","password":"SYNTHETIC-SECRET"}]')
    with pytest.raises(capacity.MeasurementError) as exc:
        capacity.load_tokens("FIXTURE_CREDENTIALS", "https://fixture.invalid",
                             transport=lambda *args: (401, {"detail": "SYNTHETIC-SECRET"}))
    assert "SYNTHETIC-SECRET" not in str(exc.value)


def test_transport_does_not_follow_redirects_or_read_error_bodies(capacity, monkeypatch):
    from io import BytesIO
    from urllib.error import HTTPError

    body = BytesIO(b"SYNTHETIC-SECRET")
    handlers_seen = []

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == "https://fixture.invalid/api/v1/presets"
            assert request.get_header("Authorization") == "Bearer fake-token"
            raise HTTPError(request.full_url, 302, "secret", {"Location": "https://elsewhere.invalid"}, body)

    def opener(*handlers):
        handlers_seen.extend(handlers)
        return Opener()

    monkeypatch.setattr(capacity, "build_opener", opener)
    assert capacity.http_request("GET", "https://fixture.invalid/api/v1/presets", "fake-token", None, 1) == (302, None)
    assert body.closed
    redirect = next(handler for handler in handlers_seen if isinstance(handler, capacity.NoRedirect))
    assert redirect.redirect_request(None, None, 302, "", {}, "https://elsewhere.invalid") is None
    assert any(isinstance(handler, capacity.ProxyHandler) and handler.proxies == {} for handler in handlers_seen)


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_invalid_measurement_limits_are_refused(capacity, value):
    with pytest.raises(capacity.MeasurementError):
        capacity.measure("https://fixture.invalid", "/api/v1/presets", [f"fake-{i}" for i in range(20)], timeout=value)
