from __future__ import annotations

import os
import re
import shlex
import subprocess  # nosec B404: used with shell=False and static args
from pathlib import Path

FORBIDDEN_PATTERNS = [
    r"\.run(/|$)",
    r"\.venv(/|$)",
    r"__pycache__(/|$)",
    r"\.pytest_cache(/|$)",
    r"\.env$",
    r"^dist(/|$)",
    r"^build(/|$)",
    r"^data(/|$)",
    r"\.DS_Store$",
    r"\.ipynb_checkpoints(/|$)",
]


def shell(cmd: str, cwd: Path | None = None, env: dict | None = None) -> tuple[int, str, str]:
    completed = subprocess.run(  # nosec B603
        shlex.split(cmd),
        cwd=str(cwd) if cwd else None,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout, completed.stderr


def looks_like_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def resolve_repo_path() -> Path:
    env_path = os.environ.get("VELU_REPO_PATH")
    if env_path:
        p = Path(os.path.expanduser(env_path)).resolve()
        if looks_like_git_repo(p):
            return p

    pwd = Path(os.getcwd()).resolve()
    if looks_like_git_repo(pwd):
        return pwd

    fallback = Path(os.path.expanduser("~/Downloads/velu")).resolve()
    return fallback


def has_remote_origin(cwd: Path) -> bool:
    rc, _out, _err = git("remote get-url origin", cwd=cwd)
    return rc == 0


def git(*args: str, cwd: Path | None = None, env: dict | None = None) -> tuple[int, str, str]:
    return shell("git " + " ".join(args), cwd=cwd, env=env)


def current_branch(cwd: Path) -> str:
    rc, out, err = git("rev-parse --abbrev-ref HEAD", cwd=cwd)
    if rc != 0:
        raise RuntimeError(err or "git branch error")
    return out


def ensure_clean_worktree(cwd: Path) -> str:
    rc, out, err = git("status --porcelain", cwd=cwd)
    if rc != 0:
        raise RuntimeError(err or "git status error")
    # allow untracked; we’ll add selectively
    return out


def _matches_forbidden(path: str) -> bool:
    return any(re.search(pat, path) for pat in FORBIDDEN_PATTERNS)


def _unstage_forbidden(cwd: Path) -> None:
    bad = [p for p in staged_paths(cwd) if _matches_forbidden(p)]
    if bad:
        git("reset -q " + " ".join(shlex.quote(p) for p in bad), cwd=cwd)


def _purge_cached_forbidden(cwd: Path) -> None:
    # remove tracked forbidden files from index (keep on disk)
    rc, out, err = git("ls-files", cwd=cwd)
    if rc != 0:
        return
    cached = [p for p in out.splitlines() if p.strip()]
    bad = [p for p in cached if _matches_forbidden(p)]
    if bad:
        git("rm -r --cached --quiet " + " ".join(shlex.quote(p) for p in bad), cwd=cwd)


def forbid_paths(paths: list[str]) -> None:
    for p in paths:
        for pat in FORBIDDEN_PATTERNS:
            if re.search(pat, p):
                raise RuntimeError(f"Forbidden path staged: {p}")


def staged_paths(cwd: Path) -> list[str]:
    rc, out, err = git("diff --cached --name-only", cwd=cwd)
    if rc != 0:
        raise RuntimeError(err or "git diff error")
    return [p for p in out.splitlines() if p.strip()]


def add_all_safe(cwd: Path) -> None:
    rc, out, err = git("ls-files -o -m --exclude-standard", cwd=cwd)
    if rc != 0:
        raise RuntimeError(err or "git ls-files error")

    candidates = [p for p in out.splitlines() if p.strip()]
    safe: list[str] = []
    for p in candidates:
        if (cwd / p).is_dir():
            continue  # never stage directories
        if _matches_forbidden(p):
            continue  # skip forbidden
        safe.append(p)

    if safe:
        chunk = 100
        for i in range(0, len(safe), chunk):
            args = " ".join(shlex.quote(x) for x in safe[i : i + chunk])
            rc, _, err = git("add " + args, cwd=cwd)
            if rc != 0:
                raise RuntimeError(err or "git add error")

    # scrub anything that slipped in
    _unstage_forbidden(cwd)
    _purge_cached_forbidden(cwd)


def ensure_identity_env() -> None:
    os.environ.setdefault("GIT_AUTHOR_NAME", "Velu Agent")
    os.environ.setdefault("GIT_AUTHOR_EMAIL", "velu-agent@local")
    os.environ.setdefault("GIT_COMMITTER_NAME", "Velu Agent")
    os.environ.setdefault("GIT_COMMITTER_EMAIL", "velu-agent@local")


def gh_available() -> bool:
    rc, _, _ = shell("gh --version")
    return rc == 0


def load_yaml_like(path: Path) -> dict:
    """
    Simple YAML-subset loader (keys/strings only).
    Supports ${ENV:-default} expansion.
    """
    data: dict = {}
    if not path.exists():
        return data

    content = path.read_text()
    cur_map = data
    stack: list[tuple[int, dict]] = [(-1, cur_map)]

    for raw in content.splitlines():
        line = raw.rstrip("\n")
        if not line.strip() or line.strip().startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" "))
        while stack and indent <= stack[-1][0]:
            stack.pop()

        key, sep, val = line.strip().partition(":")
        if not sep:
            continue

        val = val.strip()
        if val == "":
            new_map: dict = {}
            stack[-1][1][key] = new_map
            stack.append((indent, new_map))
            continue

        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        if val.startswith("'") and val.endswith("'"):
            val = val[1:-1]

        # ${ENV:-default}
        def expand(v: str) -> str:
            m = re.match(r"\$\{([A-Z0-9_]+)(:-([^}]*))?\}", v)
            if m:
                envk = m.group(1)
                dflt = m.group(3) or ""
                return os.environ.get(envk, dflt)
            return v

        val = expand(val)
        stack[-1][1][key] = val

    return data
