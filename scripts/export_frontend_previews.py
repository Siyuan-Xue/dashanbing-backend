"""Export unchanged demo video frames for the public website (requires OpenCV)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-root", type=Path, default=Path("local-assets/sample-bundle/data"))
    parser.add_argument("--output", type=Path, default=Path("frontend/public/assets/previews"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    sync = json.loads((args.sample_root / "test_data_v3/sync/group_04.json").read_text())
    sources = {
        f"quick-cam-{camera}": (f"test_data_v3/4-{camera}.mkv", 6150 + sync["camera_time_offsets_ms"][f"cam_0{camera}"])
        for camera in range(1, 5)
    }
    sources.update({
        "quick-phases": ("outputs/v3/group_04/viz/phases.mp4", 6150),
        "quick-pose": ("outputs/v3/group_04/viz/cam_03_annotated.mp4", 6150),
        "mixed-phases": ("outputs/v3/group_03/viz/phases.mp4", 6000),
        "verified-phases": ("outputs/v3/group_05/viz/phases.mp4", 6000),
        "layup-phases": ("outputs/v3/group_06/viz/phases.mp4", 6000),
    })
    manifest = []
    for name, (relative_path, time_ms) in sources.items():
        capture = cv2.VideoCapture(str(args.sample_root / relative_path))
        capture.set(cv2.CAP_PROP_POS_MSEC, time_ms)
        ok, frame = capture.read()
        actual_ms = capture.get(cv2.CAP_PROP_POS_MSEC)
        capture.release()
        if not ok:
            raise RuntimeError(f"Cannot read {relative_path} at {time_ms} ms")
        destination = args.output / f"{name}.webp"
        # Preserve the full source frame, including the model's own annotations.
        if not cv2.imwrite(str(destination), frame, [cv2.IMWRITE_WEBP_QUALITY, 82]):
            raise RuntimeError(f"Cannot encode {destination}")
        manifest.append({"file": destination.name, "source": relative_path, "time_ms": actual_ms,
                         "width": frame.shape[1], "height": frame.shape[0],
                         "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()})
    (args.output / "sources.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Exported {len(manifest)} original video frames to {args.output}")


if __name__ == "__main__":
    main()
