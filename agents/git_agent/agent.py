from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

# --- lightweight git helpers -------------------------------------------------


def _run(
    cmd: list[str], *, cwd: Path | None = None, env: dict | None = None
) -> tuple[int, str, str]:
    """Run command and return (rc, stdout, stderr)."""
    try:
        cp = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env={**os.environ, **(env or {})} if env else None,
            capture_output=True,  # noqa: S603
            text=True,
            check=False,
        )
        return cp.returncode, cp.stdout, cp.stderr
    except FileNotFoundError as e:
        return 127, "", str(e)


def git(cmd: str, *, cwd: Path) -> tuple[int, str, str]:
    """Run a git command with safe splitting."""
    return _run(["git", *shlex.split(cmd)], cwd=cwd)


def add_all_safe(repo: Path) -> None:
    rc, _out, err = git("add -A", cwd=repo)
    if rc != 0:
        raise RuntimeError(f"git add failed: {err or _out}")


def ensure_git_identity(
    repo: Path, *, name: str = "Velu Bot", email: str = "ops@example.com"
) -> None:
    """Ensure repo has user.name and user.email to avoid 'Author identity unknown'."""
    need_set = False
    rc, out, _ = git("config user.name", cwd=repo)
    if rc != 0 or not out.strip():
        need_set = True
    rc, out, _ = git("config user.email", cwd=repo)
    if rc != 0 or not out.strip():
        need_set = True
    if need_set:
        rc, _o, err = git(f'config user.name "{name}"', cwd=repo)
        if rc != 0:
            raise RuntimeError(f"git config user.name failed: {err}")
        rc, _o, err = git(f'config user.email "{email}"', cwd=repo)
        if rc != 0:
            raise RuntimeError(f"git config user.email failed: {err}")


def commit_all(repo: Path, msg: str, sign: bool) -> None:
    add_all_safe(repo)
    ensure_git_identity(repo)
    sign_flag = "-S" if sign else ""
    rc, _out, err = git(f"commit {sign_flag} -m {shlex.quote(msg)}", cwd=repo)
    if rc != 0:
        if "Author identity unknown" in (err or ""):
            ensure_git_identity(repo)
            rc, _out, err = git(f"commit {sign_flag} -m {shlex.quote(msg)}", cwd=repo)
        if rc != 0:
            raise RuntimeError(err or "git commit failed")


# --- quality helpers ----------------------------------------------------------


def _which(name: str) -> str | None:
    return shutil.which(name)


def _has_tests(repo: Path) -> bool:
    for pat in ("tests/**/*.py", "tests/*.py", "test_*.py", "tests.py"):
        if list(repo.glob(pat)):
            return True
    return False


def run_quality(repo: Path) -> None:
    """
    Run local quality tools if available.
    Default: non-fatal. Opt into strict with GIT_AGENT_STRICT_LINT=1.
    - ruff check .
    - black .        (format, not --check)
    - pytest -q      (ONLY if GIT_AGENT_RUN_PYTEST=1 and tests exist)
    """
    env = os.environ.copy()
    env.pop("API_KEYS", None)

    strict = os.getenv("GIT_AGENT_STRICT_LINT", "0").lower() in {"1", "true", "yes"}

    ruff = _which("ruff")
    if ruff:
        rc, out, err = _run([ruff, "check", "."], cwd=repo)
        if strict and rc != 0:
            raise subprocess.CalledProcessError(rc, [ruff, "check", "."], out, err)

    black = _which("black")
    if black:
        # format in-place so temporary repos pass style
        rc, out, err = _run([black, "."], cwd=repo)
        if strict and rc != 0:
            raise subprocess.CalledProcessError(rc, [black, "."], out, err)

    if os.getenv("GIT_AGENT_RUN_PYTEST", "0").lower() in {"1", "true", "yes"} and _has_tests(repo):
        pt = _which("pytest")
        if pt:
            rc, out, err = _run([pt, "-q"], cwd=repo, env=env)
            if strict and rc != 0:
                raise subprocess.CalledProcessError(rc, [pt, "-q"], out, err)


# --- Agent --------------------------------------------------------------------


class GitIntegrationAgent:
    """
    Minimal git-integration used by tests:
      - resolves repo path (VELU_REPO_PATH or cwd)
      - creates feature branch from 'dev' (fallback to current HEAD)
      - commits all changes with a conventional message
      - runs local quality hooks (non-fatal by default)
      - returns the new branch name
    """

    def __init__(self) -> None:
        self.repo = Path(os.environ.get("VELU_REPO_PATH", ".")).resolve()
        if not (self.repo / ".git").exists():
            raise RuntimeError(f"Not a git repo: {self.repo}")

        self.cfg = type("Cfg", (), {"sign": False})  # simple container

    @staticmethod
    def _slug(text: str) -> str:
        out = []
        for ch in text.lower():
            if ch.isalnum():
                out.append(ch)
            elif ch in (" ", "_", "-", "/"):
                out.append("-")
        slug = "".join(out).strip("-")
        while "--" in slug:
            slug = slug.replace("--", "-")
        return slug or "change"

    def feature_commit(self, scope: str, title: str, body: str) -> str:
        """
        Create a feature branch and commit changes.
        Returns the created branch name.
        """
        scope = (scope or "feat").strip()
        title = (title or "update").strip()
        branch = f"feat/{self._slug(scope)}-{self._slug(title)}"

        # checkout from 'dev' if exists; else create from HEAD
        rc, _out, _err = git("show-ref --verify --quiet refs/heads/dev", cwd=self.repo)
        if rc == 0:
            rc, out, err = git(f"checkout -b {shlex.quote(branch)} dev", cwd=self.repo)
        else:
            rc, out, err = git(f"checkout -b {shlex.quote(branch)}", cwd=self.repo)
        if rc != 0:
            raise RuntimeError(err or out or "git checkout failed")

        msg_lines = [f"feat({scope}): {title}", "", "Generated-by: Velu Agent", ""]
        if body:
            msg_lines.append(body)
        msg = "\n".join(msg_lines)

        commit_all(self.repo, msg, self.cfg.sign)

        # quality hooks (non-fatal unless strict requested)
        run_quality(self.repo)

        return branch
