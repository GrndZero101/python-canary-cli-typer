"""Tests for the SessionStart hook that reports switched-off guards and a stale uv.

git, uv, PATH lookups and PyPI are injected, so nothing here shells out or reaches the network.
"""

import functools
import json
import urllib.error
from collections.abc import Sequence
from pathlib import Path

import pytest
from gate import GateResult
from session_doctor import (
    INSTALL_SHIMS,
    SHIMS,
    UV_RELEASES,
    UV_VERSION_COMMAND,
    latest_uv,
    main,
    missing_shims,
    render,
)

STATUS = "## feat/x...origin/feat/x"
UV = "0.13.1"


def _git(hooks: str, command: Sequence[str], cwd: Path, uv: str = UV) -> GateResult:
    """Answer `git status` with STATUS, `git rev-parse --git-path hooks` with `hooks`, and
    `uv self version --short` with `uv`.
    """
    del cwd
    if list(command) == UV_VERSION_COMMAND:
        return GateResult(code=0, output=f"{uv}\n")
    if "rev-parse" in command:
        return GateResult(code=0, output=hooks)
    return GateResult(code=0, output=STATUS)


def _pypi(latest: str, url: str) -> bytes:
    """Answer PyPI's JSON API with `latest` as uv's newest release."""
    assert url == UV_RELEASES
    return json.dumps({"info": {"version": latest}}).encode()


def _offline(url: str) -> bytes:
    raise urllib.error.URLError(url)


def _serve(body: bytes, url: str) -> bytes:
    del url
    return body


_current = functools.partial(_pypi, UV)


def _found(name: str) -> str | None:
    return f"/usr/bin/{name}"


def _not_found(name: str) -> str | None:
    del name
    return None


def _repo(root: Path, monkeypatch: pytest.MonkeyPatch, shims: Sequence[str] = SHIMS) -> None:
    hooks = root / ".git" / "hooks"
    hooks.mkdir(parents=True)
    for name in shims:
        (hooks / name).write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.chdir(root)


def test_a_healthy_project_prints_only_the_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo(tmp_path, monkeypatch)
    runner = functools.partial(_git, str(Path(".git") / "hooks"))
    assert main([], runner=runner, which=_found, fetch=_current) == 0
    assert capsys.readouterr().out == f"{STATUS}\n"


def test_missing_prek_is_reported_with_its_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo(tmp_path, monkeypatch)
    runner = functools.partial(_git, str(Path(".git") / "hooks"))
    assert main([], runner=runner, which=_not_found, fetch=_current) == 0
    reply = json.loads(capsys.readouterr().out)
    assert "uv tool install prek" in reply["systemMessage"]
    assert STATUS in reply["hookSpecificOutput"]["additionalContext"]


def test_a_missing_shim_is_named_with_the_command_that_installs_all_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`prek install` alone wires pre-commit only — the commonest way to end up here."""
    _repo(tmp_path, monkeypatch, shims=["pre-commit"])
    runner = functools.partial(_git, str(Path(".git") / "hooks"))
    main([], runner=runner, which=_found, fetch=_current)
    message = json.loads(capsys.readouterr().out)["systemMessage"]
    assert "commit-msg, pre-merge-commit" in message
    assert INSTALL_SHIMS in message


def test_missing_shims_keeps_install_order(tmp_path: Path) -> None:
    (tmp_path / "commit-msg").write_text("", encoding="utf-8")
    assert missing_shims(tmp_path) == ["pre-commit", "pre-merge-commit"]


def test_render_is_plain_text_without_problems() -> None:
    assert render("## main", [], []) == "## main"


def test_outside_a_repository_it_says_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = functools.partial(_git, ".git/hooks")
    assert main([], runner=runner, which=_not_found, fetch=_current) == 0
    assert not capsys.readouterr().out


# --- a stale uv ---------------------------------------------------------------------------


def _hooks_runner(uv: str = UV) -> functools.partial[GateResult]:
    return functools.partial(_git, str(Path(".git") / "hooks"), uv=uv)


def test_a_uv_behind_the_latest_is_advice_naming_the_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo(tmp_path, monkeypatch)
    fetch = functools.partial(_pypi, "0.14.0")
    assert main([], runner=_hooks_runner(), which=_found, fetch=fetch) == 0
    reply = json.loads(capsys.readouterr().out)
    message = reply["systemMessage"]
    assert f"uv {UV} is behind the latest release, 0.14.0" in message
    assert "uv self update" in message
    assert "guard" not in message, "a stale uv is advice, not a switched-off guard"


@pytest.mark.parametrize(
    ("running", "latest"),
    [(UV, UV), ("0.13.0", "0.9.10"), ("0.14.0.dev1", "0.14.0")],
    ids=["current", "numeric-not-string-order", "not-a-plain-version"],
)
def test_a_uv_not_behind_or_not_comparable_says_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    running: str,
    latest: str,
) -> None:
    _repo(tmp_path, monkeypatch)
    fetch = functools.partial(_pypi, latest)
    main([], runner=_hooks_runner(running), which=_found, fetch=fetch)
    assert capsys.readouterr().out == f"{STATUS}\n"


def test_offline_it_says_nothing_about_uv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo(tmp_path, monkeypatch)
    main([], runner=_hooks_runner(), which=_found, fetch=_offline)
    assert capsys.readouterr().out == f"{STATUS}\n"


@pytest.mark.parametrize("body", [b"<html>", b"{}", b'{"info": {}}'])
def test_latest_uv_is_none_for_an_answer_it_cannot_read(body: bytes) -> None:
    assert latest_uv(functools.partial(_serve, body)) is None


def test_a_stale_uv_is_reported_beside_a_switched_off_guard() -> None:
    reply = json.loads(render("## main", ["prek is not on PATH"], ["uv 0.1.0 is behind"]))
    assert reply["systemMessage"] == (
        "A guard is switched off:\n- prek is not on PATH\n\nWorth doing:\n- uv 0.1.0 is behind"
    )
