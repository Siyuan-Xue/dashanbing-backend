"""Exercise the same fresh-process import order as the GPU worker."""
import os
from pathlib import Path
import subprocess
import sys


def test_runner_configures_task_paths_before_importing_research_backends(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("BASKETBALL_") and key != "YOLO_CONFIG_DIR"}
    result = subprocess.run(
        [sys.executable, "-c", """
import sys
from pathlib import Path
from research_engine import product_runner
task, models = map(Path, sys.argv[1:])
product_runner.configure_runtime(task, models)
from src import config
from src.identity.backends import model_path
assert config.MODELS == models.resolve(), (config.MODELS, models)
assert config.DATA == (task / 'data').resolve(), (config.DATA, task)
assert model_path('models/reid/osnet_x1_0_msmt17.pth') == models / 'reid/osnet_x1_0_msmt17.pth'
from src.privacy.db import DB_PATH
assert Path(DB_PATH).is_relative_to(task), DB_PATH
""", str(tmp_path / "task"), str(tmp_path / "weights")],
        cwd=root, env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
