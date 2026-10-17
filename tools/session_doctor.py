"""Report the branch and tree at session start, and anything that has silently switched a guard off.

Claude Code `SessionStart` hook. What it prints becomes context for the agent. With nothing wrong
it prints `git status --short --branch` and nothing else, as the hook always has.

Every guard in this project fails *open* when its tooling is missing — deliberately, because a
broken hook must not block every edit. The price is that a missing tool is invisible: the gate
stops running and nothing says so. This hook is where that becomes visible. It checks:

- **`prek` on PATH.** Without it the edit-time gate, the stop gate and every git hook do nothing.
- **All three git shims** — `pre-commit`, `commit-msg` and `pre-merge-commit`. `prek install`
  alone wires only the first, which silently drops the commit-message check and makes
  `git merge --no-ff` into `main` fail.

It also says when uv is behind its latest release. That is advice, not a guard: the template pins
no uv and is checked against the latest, so an older one is what is likely to differ. The latest
comes from PyPI, which costs one request at session start; offline, or with PyPI slow to answer,
it says nothing about uv.

When something is wrong it replies in JSON instead, so the agent gets the status plus the problem
and its fix, and the user sees the problem as a warning. It never blocks: a session must always be
able to start, including to fix exactly this.
"""

import argparse
import json
import shutil
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path

from gate import Runner, run_subprocess
from hook_payload import find_repo_root, notice

SHIMS = ("pre-commit", "commit-msg", "pre-merge-commit")
STATUS_COMMAND = ["git", "status", "--short", "--branch"]
# Resolves a linked worktree's hooks to the main repository's, and honours `core.hooksPath`.
HOOKS_PATH_COMMAND = ["git", "rev-parse", "--git-path", "hooks"]
INSTALL_SHIMS = "prek install -t pre-commit -t commit-msg -t pre-merge-commit"
UV_VERSION_COMMAND = ["uv", "self", "version", "--short"]
# The latest uv release, from PyPI's JSON API, which needs no token.
UV_RELEASES = "https://pypi.org/pypi/uv/json"
# Short, because the session waits for this hook: past it, uv goes unmentioned.
FETCH_TIMEOUT = 2

Which = Callable[[str], str | None]
Fetch = Callable[[str], bytes]


def fetch_url(url: str) -> bytes:
    """Return the body at `url`, giving up after FETCH_TIMEOUT seconds."""
    # S310 is about file: and custom schemes; the one URL fetched is the https constant above.
    with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT) as response:  # noqa: S310
        return response.read()


def hooks_dir(root: Path, runner: Runner) -> Path | None:
    """Return the directory git runs hooks from, or None if git cannot say."""
    result = runner(HOOKS_PATH_COMMAND, root)
    if not result.ran or result.code != 0 or not result.output:
        return None
    return root / result.output.strip()


def missing_shims(directory: Path) -> list[str]:
    """Return the shims absent from `directory`, in the order they are installed."""
    return [name for name in SHIMS if not (directory / name).is_file()]


def find_problems(root: Path, runner: Runner, which: Which) -> list[str]:
    """Return one line per switched-off guard, each naming its fix."""
    problems: list[str] = []
    if which("prek") is None:
        problems.append(
            "prek is not on PATH, so the edit gate, the stop gate and the git hooks are all off. "
            "Fix: uv tool install prek"
        )
    directory = hooks_dir(root, runner)
    absent = missing_shims(directory) if directory is not None else []
    if absent:
        problems.append(
            f"git hook shim(s) missing: {', '.join(absent)}. Commits skip those checks. "
            f"Fix: {INSTALL_SHIMS}"
        )
    return problems


def version_key(version: str) -> tuple[int, ...] | None:
    """Return `version` as numbers, so that 0.13.0 sorts above 0.9.0; None if it is not one."""
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return None


def latest_uv(fetch: Fetch) -> str | None:
    """Return the newest uv release on PyPI, or None when PyPI cannot be read.

    No advice beats a wrong warning, so each failure is quiet. One handler each, not a tuple:
    ruff rewrites a tuple to the unparenthesised form at py314, which is a syntax error below it.
    """
    try:
        return str(json.loads(fetch(UV_RELEASES))["info"]["version"])
    except OSError:
        return None  # offline, or PyPI slower than FETCH_TIMEOUT
    except ValueError:
        return None  # not JSON
    except LookupError:
        return None  # JSON of another shape


def stale_uv(root: Path, runner: Runner, fetch: Fetch) -> str | None:
    """Return a line saying uv is behind its latest release, or None if it is not or none can say."""
    result = runner(UV_VERSION_COMMAND, root)
    if not result.ran or result.code != 0:
        return None
    running = result.output.strip()
    have = version_key(running)
    if have is None:
        return None
    latest = latest_uv(fetch)
    want = version_key(latest) if latest is not None else None
    if want is None or have >= want:
        return None
    return f"uv {running} is behind the latest release, {latest}. Fix: uv self update"


def _listing(lines: list[str]) -> str:
    """Return `lines` as a markdown list."""
    return "\n".join(f"- {line}" for line in lines)


def render(status: str, problems: list[str], advice: list[str]) -> str:
    """Return what the hook prints: the plain status, or a JSON notice when there is more to say."""
    if not problems and not advice:
        return status
    sections: list[str] = []
    if problems:
        sections.append(f"A guard is switched off:\n{_listing(problems)}")
    if advice:
        sections.append(f"Worth doing:\n{_listing(advice)}")
    report = "\n\n".join(sections)
    context = (
        f"{status}\n\n{report}\n\nTell the user before starting work; they may need to run the fix."
    )
    return notice("SessionStart", context, user_message=report)


def _build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    return argparse.ArgumentParser(
        prog="session_doctor",
        description="Report git status, and any guard whose tooling is missing.",
    )


def main(
    argv: list[str] | None = None,
    runner: Runner = run_subprocess,
    which: Which = shutil.which,
    fetch: Fetch = fetch_url,
) -> int:
    """Entry point. Always returns 0: a session must be able to start, if only to fix this."""
    _build_parser().parse_args(argv)
    root = find_repo_root()
    if root is None:
        return 0
    status = runner(STATUS_COMMAND, root).output
    problems = find_problems(root, runner, which)
    stale = stale_uv(root, runner, fetch)
    advice = [stale] if stale is not None else []
    sys.stdout.write(f"{render(status, problems, advice)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
