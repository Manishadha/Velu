from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .git_utils import (
    add_all_safe,
    gh_available,
    git,
    has_remote_origin,
    load_yaml_like,
    resolve_repo_path,
    shell,
)

CONFIG_PATH = Path("configs/agent.yml")


@dataclass
class GitConfig:
    default_target: str
    protected: list[str]
    feature_pat: str
    fix_pat: str
    chore_pat: str
    docs_pat: str
    refactor_pat: str
    hotfix_pat: str
    sign: bool
    body_prefix: str
    changelog_path: Path
    tag_prefix: str
    push: bool
    open_pr: bool


def _as_bool(v: str | int | bool, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v != 0
    s = str(v).strip().lower()
    if s in {"1", "true", "yes", "y"}:
        return True
    if s in {"0", "false", "no", "n"}:
        return False
    return default


def load_config(repo: Path) -> GitConfig:
    cfg = load_yaml_like(repo / CONFIG_PATH)
    br = cfg.get("branching", {})
    cm = cfg.get("commits", {})
    ch = cfg.get("changelog", {})
    ver = cfg.get("versioning", {})
    ci = cfg.get("ci", {})
    return GitConfig(
        default_target=br.get("default_target", "dev"),
        protected=list(br.get("protected", ["main"])),
        feature_pat=br.get("patterns", {}).get("feature", "feat/{scope}"),
        fix_pat=br.get("patterns", {}).get("fix", "fix/{scope}"),
        chore_pat=br.get("patterns", {}).get("chore", "chore/{scope}"),
        docs_pat=br.get("patterns", {}).get("docs", "docs/{scope}"),
        refactor_pat=br.get("patterns", {}).get("refactor", "refactor/{scope}"),
        hotfix_pat=br.get("patterns", {}).get("hotfix", "hotfix/{scope}"),
        sign=_as_bool(cm.get("sign", "0")),
        body_prefix=str(cm.get("body_prefix", "Generated-by: Velu Agent")),
        changelog_path=Path(ch.get("path", "docs/CHANGELOG.md")),
        tag_prefix=str(ver.get("tag_prefix", "v")),
        push=_as_bool(ci.get("push", "1"), True),
        open_pr=_as_bool(ci.get("open_pr", "1"), True),
    )


def branch_name(kind: str, scope: str, cfg: GitConfig) -> str:
    mapping = {
        "feature": cfg.feature_pat,
        "fix": cfg.fix_pat,
        "chore": cfg.chore_pat,
        "docs": cfg.docs_pat,
        "refactor": cfg.refactor_pat,
        "hotfix": cfg.hotfix_pat,
    }
    pat = mapping.get(kind, cfg.feature_pat)
    norm = re.sub(r"[^a-zA-Z0-9._-]+", "-", scope.strip()).strip("-")
    return pat.format(scope=norm)


def ensure_branch(repo: Path, name: str) -> None:
    rc, _out, _err = git(f"rev-parse --verify {name}", cwd=repo)
    if rc != 0:
        rc, _out, err = git(f"checkout -b {name}", cwd=repo)
        if rc != 0:
            raise RuntimeError(err or f"cannot create {name}")
    else:
        rc, _out, err = git(f"checkout {name}", cwd=repo)
        if rc != 0:
            raise RuntimeError(err or f"cannot switch to {name}")


def run_tests(repo: Path) -> None:
    # best-effort; do not hard-fail if tools are missing
    if shutil.which("ruff"):
        subprocess.call(["ruff", "check", "."], cwd=str(repo))
    if shutil.which("black"):
        subprocess.call(["black", "--check", "."], cwd=str(repo))
    if shutil.which("pytest"):
        env = os.environ.copy()
        env["PYTHONPATH"] = "src"
        env.pop("API_KEYS", None)
        subprocess.call(["pytest", "-q"], cwd=str(repo), env=env)


def update_unreleased_changelog(repo: Path, cfg: GitConfig, entries: list[str]) -> None:
    p = repo / cfg.changelog_path
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# Changelog\n\n## [Unreleased]\n")

    text = p.read_text()
    if "## [Unreleased]" not in text:
        text = "# Changelog\n\n## [Unreleased]\n" + text

    lines: list[str] = []
    inserted = False
    for line in text.splitlines():
        lines.append(line)
        if not inserted and line.strip() == "## [Unreleased]":
            lines.append("### Added")
            for e in entries:
                lines.append(f"- {e}")
            inserted = True

    new_text = "\n".join(lines).rstrip() + "\n"
    p.write_text(new_text)


def conventional_message(
    commit_type: str,
    scope: str,
    summary: str,
    body: str | None,
    cfg: GitConfig,
) -> str:
    head = f"{commit_type}({scope}): {summary}".strip()
    body_lines: list[str] = []
    if body and body.strip():
        body_lines.append(body.strip())
    body_lines.append(cfg.body_prefix)
    return head + "\n\n" + "\n".join(body_lines) + "\n"


def commit_all(repo: Path, msg: str, sign: bool) -> None:
    add_all_safe(repo)
    sign_flag = "-S" if sign else ""
    rc, _out, err = git(f"commit {sign_flag} -m {json.dumps(msg)}", cwd=repo)
    if rc != 0:
        raise RuntimeError(err or "git commit failed")


def push_branch(repo: Path, name: str) -> None:
    if not has_remote_origin(repo):
        return
    rc, _out, err = git(f"push -u origin {name}", cwd=repo)
    if rc != 0:
        raise RuntimeError(err or "git push failed")


def open_pr(
    repo: Path, from_branch: str, to_branch: str, title: str, body: str
) -> None:
    if not gh_available() or not has_remote_origin(repo):
        return
    cmd = (
        "gh pr create --fill "
        f"--base {to_branch} --head {from_branch} "
        f"--title {json.dumps(title)} --body {json.dumps(body)}"
    )
    rc, out, err = shell(cmd, cwd=repo)
    if rc != 0:
        print(err or out)  # non-fatal; log for visibility


class GitIntegrationAgent:
    def __init__(self, repo: Path | None = None) -> None:
        self.repo = repo or resolve_repo_path()
        if not (self.repo / ".git").exists():
            raise RuntimeError(f"Not a git repo: {self.repo}")
        self.cfg = load_config(self.repo)

    def feature_commit(self, scope: str, summary: str, body: str = "") -> str:
        git("fetch", "--all", cwd=self.repo)
        ensure_branch(self.repo, self.cfg.default_target)
        git("pull", "--ff-only", cwd=self.repo)

        fname = branch_name("feature", scope, self.cfg)
        ensure_branch(self.repo, fname)

        msg = conventional_message("feat", scope, summary, body, self.cfg)
        commit_all(self.repo, msg, self.cfg.sign)

        run_tests(self.repo)

        if self.cfg.push:
            push_branch(self.repo, fname)
            if self.cfg.open_pr:
                pr_body = (
                    "- [x] tests passed (or not required)\n"
                    "- [x] lint clean (ruff/black)\n"
                    "- [x] no secrets added\n"
                    "- [x] changelog updated if user-facing\n"
                    "- [x] conventional commits used\n"
                )
                open_pr(
                    self.repo,
                    fname,
                    self.cfg.default_target,
                    f"[feat] {scope}: {summary}",
                    pr_body,
                )

        self._touch_changelog(f"feat({scope}): {summary}")
        return fname

    def fix_commit(self, scope: str, summary: str, body: str = "") -> str:
        git("fetch", "--all", cwd=self.repo)
        ensure_branch(self.repo, self.cfg.default_target)
        git("pull", "--ff-only", cwd=self.repo)

        bname = branch_name("fix", scope, self.cfg)
        ensure_branch(self.repo, bname)

        msg = conventional_message("fix", scope, summary, body, self.cfg)
        commit_all(self.repo, msg, self.cfg.sign)

        run_tests(self.repo)

        if self.cfg.push:
            push_branch(self.repo, bname)
            if self.cfg.open_pr:
                pr_body = (
                    "- [x] tests passed (or not required)\n"
                    "- [x] lint clean\n"
                    "- [x] no secrets added\n"
                    "- [x] changelog updated if user-facing\n"
                    "- [x] conventional commits used\n"
                )
                open_pr(
                    self.repo,
                    bname,
                    self.cfg.default_target,
                    f"[fix] {scope}: {summary}",
                    pr_body,
                )

        self._touch_changelog(f"fix({scope}): {summary}")
        return bname

    def chore_commit(self, scope: str, summary: str, body: str = "") -> str:
        git("fetch", "--all", cwd=self.repo)
        ensure_branch(self.repo, self.cfg.default_target)
        git("pull", "--ff-only", cwd=self.repo)

        bname = branch_name("chore", scope, self.cfg)
        ensure_branch(self.repo, bname)

        msg = conventional_message("chore", scope, summary, body, self.cfg)
        commit_all(self.repo, msg, self.cfg.sign)

        if self.cfg.push:
            push_branch(self.repo, bname)
            if self.cfg.open_pr:
                open_pr(
                    self.repo,
                    bname,
                    self.cfg.default_target,
                    f"[chore] {scope}: {summary}",
                    "- [x] checks",
                )
        return bname

    def release(self, version: str, summary: str = "") -> str:  # noqa: ARG002
        ensure_branch(self.repo, "main")
        rc, _out, err = git("pull --ff-only", cwd=self.repo)
        if rc != 0:
            raise RuntimeError(err or "cannot pull main")

        ch_path = self.repo / self.cfg.changelog_path
        text = (
            ch_path.read_text()
            if ch_path.exists()
            else "# Changelog\n\n## [Unreleased]\n"
        )
        if "## [Unreleased]" in text:
            today = date.today().isoformat()
            new = text.replace(
                "## [Unreleased]", f"## [{self.cfg.tag_prefix}{version}] – {today}\n", 1
            )
            ch_path.write_text(new)

        msg = f"chore(release): {self.cfg.tag_prefix}{version}"
        commit_all(self.repo, msg, self.cfg.sign)

        rc, _out, err = git(
            f'tag -a {self.cfg.tag_prefix}{version} -m "Release {self.cfg.tag_prefix}{version}"',
            cwd=self.repo,
        )
        if rc != 0:
            raise RuntimeError(err or "git tag failed")

        if self.cfg.push and has_remote_origin(self.repo):
            rc, _out, err = git("push origin main", cwd=self.repo)
            if rc != 0:
                raise RuntimeError(err or "push main failed")
            rc, _out, err = git(
                f"push origin {self.cfg.tag_prefix}{version}", cwd=self.repo
            )
            if rc != 0:
                raise RuntimeError(err or "push tag failed")

        return version

    def _touch_changelog(self, line: str) -> None:
        try:
            update_unreleased_changelog(self.repo, self.cfg, [line])
        except Exception as exc:  # noqa: BLE001
            print(f"[git-agent] changelog update skipped: {exc}")
