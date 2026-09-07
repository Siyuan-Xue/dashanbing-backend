import importlib
import json

import pytest


@pytest.fixture
def gpu():
    return importlib.import_module("scripts.measure_gpu_acceptance")


def fake_api(gpu, *, ready=True, mode="gpu", fail=False, timestamps=True):
    calls = []

    def transport(method, url, token, payload, timeout):
        calls.append((method, url, payload))
        if url.endswith("/system/readiness"):
            return 200, {"ready": ready, "mode": mode, "checks": [{"detail": "SYNTHETIC-SECRET"}]}
        if url.endswith("/presets"):
            return 200, [{"id": preset} for preset in gpu.PRESETS]
        if method == "POST":
            return 201, {"id": "fixture-task", "status": "queued"}
        result = {"id": "fixture-task", "status": "failed" if fail else "completed",
                  "error_message": "SYNTHETIC-SECRET"}
        if timestamps:
            result.update(submitted_at="2026-01-01T00:00:00Z", started_at="2026-01-01T00:00:02Z",
                          completed_at="2026-01-01T00:00:05Z")
        return 200, result

    return transport, calls


def test_four_presets_both_modes_samples_and_metadata(gpu):
    transport, calls = fake_api(gpu)
    report = gpu.measure("https://fixture.invalid", "fake", engine_version="fixture-1", samples=2,
                         transport=transport)
    assert len(report["outcomes"]) == 16
    assert len([call for call in calls if call[0] == "POST"]) == 16
    assert {item["mode"] for item in report["outcomes"]} == {"quick", "full"}
    assert {item["preset"] for item in report["outcomes"]} == set(gpu.PRESETS)
    for item in report["outcomes"]:
        assert item["queue_seconds"] == 2
        assert item["runtime_seconds"] == 3
        assert item["vram_peak_mb"] is None
        assert item["vram_status"] == "unavailable"
    assert report["engine_version"] == "fixture-1"
    assert report["version_source"] == "operator_provided"
    assert "SYNTHETIC-SECRET" not in json.dumps(report)


@pytest.mark.parametrize("ready,mode", [(False, "gpu"), (True, "simulation")])
def test_missing_real_gpu_never_submits_or_becomes_pass(gpu, ready, mode):
    transport, calls = fake_api(gpu, ready=ready, mode=mode)
    report = gpu.measure("https://fixture.invalid", "fake", engine_version="fixture", transport=transport)
    assert report["status"] == "unavailable"
    assert all(item["status"] == "unavailable" for item in report["outcomes"])
    assert not any(call[0] == "POST" for call in calls)


def test_failed_tasks_and_missing_timings_stay_visible(gpu):
    transport, _ = fake_api(gpu, fail=True, timestamps=False)
    report = gpu.measure("https://fixture.invalid", "fake", engine_version="fixture", transport=transport)
    assert report["errors"] == 8
    assert all(item["status"] == "failed" and item["runtime_seconds"] is None for item in report["outcomes"])
    assert report["runtime_seconds"]["count"] == 0


def test_mock_separate_and_dry_run_network_free(gpu, capsys, monkeypatch):
    transport, _ = fake_api(gpu, mode="simulation")
    report = gpu.measure("https://fixture.invalid", "fake", engine_version="fixture", transport=transport,
                         evidence_kind="mock")
    assert report["evidence_kind"] == "mock"
    assert report["gpu_measured"] is False
    assert gpu.main(["--base-url", "https://fixture.invalid", "--credentials-env", "MISSING_FIXTURE_ENV",
                     "--engine-version", "fixture"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "planned"


def test_poll_deadline_preserves_task_id_without_cancel_or_retry(gpu):
    transport, calls = fake_api(gpu)

    def pending(method, url, token, payload, timeout):
        if "/tasks/fixture-task" in url:
            return 200, {"id": "fixture-task", "status": "queued"}
        return transport(method, url, token, payload, timeout)

    report = gpu.measure("https://fixture.invalid", "fake", engine_version="fixture", transport=pending,
                         task_timeout=0.005, poll_interval=0.001)
    assert all(item["status"] == "timeout" and item["task_id"] == "fixture-task" for item in report["outcomes"])
    assert not any("cancel" in call[1] or "retry" in call[1] for call in calls)


def test_presets_are_the_existing_catalog_and_submit_errors_are_preserved(gpu):
    assert gpu.PRESETS == ("quick-demo", "mixed-actions", "verified-outcome", "layup-demo")
    transport, calls = fake_api(gpu)

    def fail_submit(method, url, token, payload, timeout):
        if method == "POST":
            return 429, {"detail": "SYNTHETIC-SECRET"}
        return transport(method, url, token, payload, timeout)

    report = gpu.measure("https://fixture.invalid", "fake", engine_version="fixture", transport=fail_submit)
    assert report["errors"] == 8
    assert all(row["http_events"][0]["http_status"] == 429 for row in report["outcomes"])
    assert report["gpu_measured"] is False
    assert "SYNTHETIC-SECRET" not in json.dumps(report)


def test_gpu_execute_requires_test_acknowledgment(gpu, capsys):
    assert gpu.main(["--base-url", "https://fixture.invalid", "--credentials-env", "MISSING_FIXTURE_ENV",
                     "--engine-version", "fixture", "--execute"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "unavailable"
    assert report["error"] == "isolated_test_environment_acknowledgment_required"


def test_invalid_server_timestamps_remain_unavailable(gpu):
    assert gpu.elapsed_between("2026-01-01T00:00:02Z", "2026-01-01T00:00:01Z") is None
    assert gpu.elapsed_between("2026-01-01T00:00:01", "2026-01-01T00:00:02") is None
    assert gpu.elapsed_between("invalid", "invalid") is None
