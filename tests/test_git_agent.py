from __future__ import annotations

import os

# Ensure pushes are disabled for tmp repos (no 'origin') BEFORE imports/config
os.environ["VELU_GIT_PUSH"] = "0"

import shutil
import subprocess
import tempfile
from pathlib import Path

from agents.git_agent.agent import GitIntegrationAgent


def _init_repo(tmp: Path) -> None:
    subprocess.check_call(["git", "init", "-b", "dev"], cwd=tmp)
    (tmp / ".gitignore").write_text(".run/\n.venv/\n__pycache__/\n.pytest_cache/\n.env\n")
    (tmp / "configs").mkdir(parents=True, exist_ok=True)

    # copy baseline config if exists; else minimal fallback
    cfg_src = Path("configs/agent.yml")
    if cfg_src.exists():
        (tmp / "configs" / "agent.yml").write_text(cfg_src.read_text())
    else:
        (tmp / "configs" / "agent.yml").write_text(
            "branching:\n  default_target: dev\ncommits:\n  sign: 0\n"
        )

    (tmp / "docs").mkdir(exist_ok=True)
    (tmp / "docs" / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n")
    (tmp / "src").mkdir(exist_ok=True)
    (tmp / "src" / "x.py").write_text("print('x')\n")

    subprocess.check_call(["git", "add", "-A"], cwd=tmp)
    subprocess.check_call(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=t@local",
            "commit",
            "-m",
            "init",
        ],
        cwd=tmp,
    )


def test_feature_commit_smoke() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="velu-git-"))
    try:
        _init_repo(tmp)
        os.environ["VELU_REPO_PATH"] = str(tmp)  # repo resolution
        agent = GitIntegrationAgent()

        # modify file so there’s something to commit
        (tmp / "src" / "x.py").write_text("print('y')\n")

        bname = agent.feature_commit("router", "add ready probe", "")
        assert bname.startswith("feat/")
    finally:
        shutil.rmtree(tmp)
