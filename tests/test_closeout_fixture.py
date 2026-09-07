import json
from pathlib import Path

import pytest

from scripts.run_closeout_gpu import isolate_samples
from scripts.run_closeout_preview import build_fixture


def test_gpu_fixture_keeps_cache_writes_outside_source(tmp_path):
    source = tmp_path / "source"
    source_video = source / "test_data_v3" / "0-2.mkv"
    source_video.parent.mkdir(parents=True)
    source_video.write_bytes(b"existing private video")
    report = source / "outputs" / "v3" / "group_04" / "report.json"
    report.parent.mkdir(parents=True)
    report.write_text('{"clips": []}')
    destination = tmp_path / "measurement" / "samples"

    isolate_samples(source, destination)

    assert (destination / source_video.relative_to(source)).resolve() == source_video
    copied_report = destination / report.relative_to(source)
    assert not copied_report.is_symlink()
    copied_report.write_text('{"clips": [1]}')
    (copied_report.parent / "preview.mp4").write_bytes(b"new preview")
    assert json.loads(report.read_text()) == {"clips": []}
    assert not (report.parent / "preview.mp4").exists()


def test_gpu_fixture_rejects_existing_or_nested_output(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError):
        isolate_samples(source, source / "nested")
    target = tmp_path / "existing"
    target.mkdir()
    with pytest.raises(ValueError):
        isolate_samples(source, target)


def test_fixture_refuses_unrelated_runtime(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    marker = runtime / "unrelated.txt"
    marker.write_text("preserve")
    with pytest.raises(ValueError):
        build_fixture(runtime, tmp_path / "samples", resume=True)
    assert marker.read_text() == "preserve"
