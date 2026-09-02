"""Configuration loading utilities."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / "configs"
DATA = Path(os.environ.get("BASKETBALL_DATA_ROOT", ROOT / "data")).resolve()
MODELS = Path(os.environ.get("BASKETBALL_MODEL_ROOT", ROOT / "models")).resolve()


def load_models_config() -> dict[str, Any]:
    path = CONFIGS / "models.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def model_path(relative: str) -> Path:
    path = Path(relative)
    parts = path.parts[1:] if path.parts and path.parts[0] == "models" else path.parts
    return MODELS.joinpath(*parts)


def strict_runtime() -> bool:
    return os.environ.get("BASKETBALL_STRICT_RUNTIME", "0").lower() in {"1", "true", "yes"}


def load_yaml(name: str) -> dict[str, Any]:
    path = CONFIGS / name
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def data_path(*parts: str) -> Path:
    p = DATA.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
