#!/usr/bin/env python3
"""Run an explicit, isolated UI/HTTP measurement fixture, never the production DB.

Credentials are generated into a private file inside the selected runtime directory
and are deliberately not printed. Video and GLM workers remain disabled.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
import json
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def build_fixture(runtime: Path, sample_root: Path, *, resume=False):
    from sqlmodel import Session, select
    from app.config import AppSettings
    from app.main import create_app
    from app.models import Analysis, User
    from app.analyst_models import TrainingProfile
    from app.database import create_tables
    from app.security import create_access_token, hash_password
    from app.services.identities import ensure_user_identities

    runtime = runtime.resolve()
    if runtime == ROOT / "runtime" or runtime == ROOT:
        raise ValueError("Use a new isolated subdirectory, not the application runtime")
    credentials_path = runtime / "fixture-credentials.json"
    if runtime.exists() and any(runtime.iterdir()) and not (resume and credentials_path.is_file()):
        raise ValueError("Fixture directory is not empty, choose a new path or explicitly resume")
    os.umask(0o077)
    runtime.mkdir(parents=True, exist_ok=True)
    if resume and credentials_path.exists():
        credentials = json.loads(credentials_path.read_text())
    else:
        credentials = {
            "fixture": True, "jwt_secret": secrets.token_urlsafe(48),
            "admin": {"username": "review-operator", "password": secrets.token_urlsafe(24)},
            "accounts": [{"username": f"review-player-{i:02d}", "password": secrets.token_urlsafe(24)} for i in range(20)],
        }
    settings = AppSettings(
        _env_file=None, database_url=f"sqlite:///{runtime / 'fixture.db'}",
        runtime_root=runtime, sample_root=sample_root.resolve(),
        admin_username=credentials["admin"]["username"],
        admin_password=credentials["admin"]["password"],
        jwt_secret_key=credentials["jwt_secret"],
        glm_api_key="", worker_enabled=False, analyst_worker_enabled=False,
        simulation_mode=True, auto_create_schema=True, min_free_storage_gb=0,
    )
    app = create_app(settings=settings)
    create_tables(app.state.engine)
    with Session(app.state.engine) as session:
        for index, account in enumerate([credentials["admin"], *credentials["accounts"]]):
            user = session.exec(select(User).where(User.username == account["username"])).first()
            if user is None:
                user = User(username=account["username"], email=f"{account['username']}@example.test",
                            hashed_password=hash_password(account["password"]), role="admin" if index == 0 else "user")
                session.add(user); session.flush()
                ensure_user_identities(session, user)
                if index:
                    for task_number in range(25):
                        session.add(Analysis(
                            title=f"Fixture training {task_number + 1:02d}", owner_id=user.id,
                            mode="quick" if task_number % 2 else "full", status="canceled",
                            stage_message="Fixture only", input_manifest_json="{}", created_via="closeout_fixture",
                        ))
                    if index == 1:
                        session.add(TrainingProfile(owner_id=user.id, kind="player", name="Fixture player", goals="Review training", notes=""))
                        session.add(TrainingProfile(owner_id=user.id, kind="team", name="Fixture team", goals="Team training", notes=""))
                session.commit(); session.refresh(user)
            account["id"] = user.id
            account["token"] = create_access_token(user.username, timedelta(hours=12), secret_key=settings.jwt_secret_key,
                                                    role=user.role, session_version=user.session_version)
    credentials_path.write_text(json.dumps(credentials, indent=2))
    credentials_path.chmod(0o600)
    (runtime / "fixture-manifest.json").write_text(json.dumps({
        "fixture": True, "users": 20, "tasks_per_user": 25,
        "video_worker": False, "glm_worker": False, "sample_root_read_only": str(sample_root.resolve()),
        "purpose": "Isolated UI and HTTP measurement, not a GPU or GLM benchmark",
    }, indent=2))
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--sample-root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8013)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use an unprivileged port")
    app = build_fixture(args.runtime_dir, args.sample_root, resume=args.resume)
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
