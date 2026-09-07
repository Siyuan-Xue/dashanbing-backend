#!/usr/bin/env python3
"""Start a dedicated acceptance server using existing read-only model/video inputs.

Never points the application at the source runtime or database. The optional
provider file contributes GLM_API_KEY only; all other settings are explicit.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def isolate_samples(source: Path, target: Path):
    source = source.resolve(strict=True)
    if target.exists():
        raise ValueError("Choose an absent isolated sample directory")
    if source == target or source in target.resolve().parents:
        raise ValueError("Source samples must remain outside the test directory")
    # Files are linked individually. Cache destinations and every directory are
    # new, so media preparation cannot add files to a production sample directory.
    for directory in (source / "test_data_v3", source / "outputs" / "v3"):
        for path in directory.rglob("*"):
            destination = target / path.relative_to(source)
            if path.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            elif path.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                if path.suffix.lower() in {".json", ".md"}:
                    shutil.copyfile(path, destination)
                else:
                    destination.symlink_to(path.resolve())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-root", type=Path, required=True)
    parser.add_argument("--sample-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--provider-env-file", type=Path)
    parser.add_argument("--port", type=int, default=8014)
    parser.add_argument("--min-free-gb", type=float, default=20)
    parser.add_argument("--execute-isolated-test", action="store_true")
    args = parser.parse_args()
    if not args.execute_isolated_test:
        parser.error("Explicit --execute-isolated-test acknowledgment required")
    if not 1024 <= args.port <= 65535 or args.min_free_gb < 0:
        parser.error("Invalid port or free-space reserve")
    root = args.test_root.resolve()
    source = args.sample_root.resolve(strict=True)
    models = args.model_root.resolve(strict=True)
    if root.exists() or any(p == root or root in p.parents or p in root.parents for p in (source, models)):
        parser.error("Choose a new test root separate from model and sample sources")
    os.umask(0o077)
    root.mkdir(parents=True)
    isolate_samples(source, root / "samples")
    from scripts.run_closeout_preview import build_fixture
    fixture = build_fixture(root / "runtime", root / "samples")
    key = ""
    if args.provider_env_file:
        from dotenv import dotenv_values
        key = dotenv_values(args.provider_env_file.resolve(strict=True)).get("GLM_API_KEY") or ""
    from pydantic import SecretStr
    settings = fixture.state.settings.model_copy(update={
        "model_root": models, "simulation_mode": False, "worker_enabled": True,
        "analyst_worker_enabled": bool(key), "glm_api_key": SecretStr(key),
        "analyst_concurrency": 8, "min_free_storage_gb": args.min_free_gb,
    })
    fixture.state.engine.dispose()
    from app.main import create_app
    from scripts.closeout_glm_metrics import install
    install(root / "output")
    app = create_app(settings=settings)
    (root / "environment.json").write_text(json.dumps({
        "isolated": True, "gpu_worker": True, "glm_configured": bool(key),
        "ai_concurrency": 8, "storage_reserve_gb": args.min_free_gb,
        "source_media_and_weights": "existing read-only files", "database": "new synthetic accounts only",
    }, indent=2))
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
