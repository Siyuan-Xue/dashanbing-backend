import io
import tarfile
from pathlib import Path

import pytest

from scripts.safe_extract import safe_extract


def test_safe_extract_accepts_regular_files_and_rejects_traversal(tmp_path: Path):
    good = tmp_path / "good.tar.gz"
    with tarfile.open(good, "w:gz") as archive:
        payload = b"model"
        member = tarfile.TarInfo("models/weight.bin")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
    safe_extract(good, tmp_path / "good")
    assert (tmp_path / "good" / "models" / "weight.bin").read_bytes() == b"model"

    evil = tmp_path / "evil.tar.gz"
    with tarfile.open(evil, "w:gz") as archive:
        member = tarfile.TarInfo("../escaped.bin")
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(RuntimeError, match="Unsafe archive path"):
        safe_extract(evil, tmp_path / "evil")
    assert not (tmp_path / "escaped.bin").exists()
