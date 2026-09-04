from __future__ import annotations

import os
import shutil
from pathlib import Path


def link_or_copy_file(source: Path, destination: Path) -> Path:
    """Reuse file data on one filesystem and copy only when linking is unavailable."""
    source = Path(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)
    return destination
