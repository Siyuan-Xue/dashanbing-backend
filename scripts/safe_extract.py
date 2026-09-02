"""Extract a trusted asset tarball only after rejecting unsafe member paths/types."""

import argparse
import sys
import tarfile
from pathlib import Path, PurePosixPath


def safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(archive, mode="r:gz") as source:
        members = source.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise RuntimeError(f"Unsafe archive path: {member.name}")
            if not (member.isdir() or member.isfile()):
                raise RuntimeError(f"Unsupported archive member type: {member.name}")
            target = (root / Path(*path.parts)).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"Archive member escapes destination: {member.name}")
        for member in members:
            options = {"filter": "data"} if sys.version_info >= (3, 12) else {}
            source.extract(member, root, set_attrs=False, numeric_owner=False, **options)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    safe_extract(args.archive, args.destination)
