"""Keep local deployment configuration out of isolated backend tests."""
import os

import pytest

from app.config import AppSettings


@pytest.fixture(autouse=True)
def isolated_server_settings(monkeypatch):
    # A developer may have configured a real GLM credential for manual acceptance
    # Tests opt in to their own fake key/provider or explicit env file instead
    monkeypatch.setitem(AppSettings.model_config, "env_file", None)
    for name in os.environ:
        if name == "GLM_API_KEY" or name.startswith("BASKETBALL_"):
            monkeypatch.delenv(name)
