"""Tests for ``scripts/run_pip_audit.py``, the shared local/CI pip-audit gate (#648).

The audit itself needs the network, so these tests drive the script through a
fake command runner and check what it DECIDES: which advisories block, which
failures only warn, when the daily cache short-circuits, and that CI and the
ignore file cannot drift apart again (the wiring itself is checked in
``test_security_gates_wiring.py``).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_pip_audit  # noqa: E402
from run_pip_audit import CommandResult  # noqa: E402

pytestmark = pytest.mark.unit

TODAY = dt.date(2026, 11, 13)


def _report(*vulns: tuple[str, list[str]]) -> str:
    return json.dumps(
        {
            "dependencies": [
                {
                    "name": "pillow",
                    "version": "12.3.0",
                    "vulns": [{"id": vid, "aliases": aliases} for vid, aliases in vulns],
                }
            ],
            "fixes": [],
        }
    )


class FakeRunner:
    def __init__(self, audit: CommandResult, export: CommandResult | None = None):
        self.audit = audit
        self.export = export or CommandResult(0, "", "")
        self.calls: list[list[str]] = []

    def __call__(self, cmd):
        cmd = list(cmd)
        self.calls.append(cmd)
        return self.export if cmd[:2] == ["poetry", "export"] else self.audit

    @property
    def audit_calls(self) -> list[list[str]]:
        return [c for c in self.calls if c[:2] != ["poetry", "export"]]


@pytest.fixture
def files(tmp_path):
    ignore = tmp_path / "ignores.txt"
    ignore.write_text("# why\nCVE-1  # trailing note\n\nGHSA-2\n", encoding="utf-8")
    lock = tmp_path / "poetry.lock"
    lock.write_text("lock v1", encoding="utf-8")
    return ignore, lock, tmp_path / "stamp.json"


def _audit(files, runner, **kwargs):
    ignore, lock, cache = files
    return run_pip_audit.audit(
        runner=runner,
        ignore_file=ignore,
        lock_file=lock,
        cache_file=cache,
        today=kwargs.pop("today", TODAY),
        pip_audit_cmd=("pip-audit",),
        **kwargs,
    )


def test_parse_ignore_file_reads_ids_and_skips_comments():
    text = "# header\nCVE-1\n  GHSA-2   # because\n\nCVE-1\n"
    assert run_pip_audit.parse_ignore_file(text) == ["CVE-1", "GHSA-2"]


def test_parse_ignore_file_rejects_two_ids_on_one_line():
    with pytest.raises(ValueError, match="one advisory id per line"):
        run_pip_audit.parse_ignore_file("CVE-1 CVE-2\n")


def test_every_ignored_id_is_passed_to_pip_audit(files):
    runner = FakeRunner(CommandResult(0, _report(), ""))

    assert _audit(files, runner) == 0
    cmd = runner.audit_calls[0]
    assert "--strict" in cmd
    ignored = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--ignore-vuln"]
    assert ignored == ["CVE-1", "GHSA-2"]


def test_an_advisory_without_exception_blocks(files, capsys):
    runner = FakeRunner(CommandResult(1, _report(("CVE-NEW", [])), ""))

    assert _audit(files, runner) == 1
    assert "pillow 12.3.0: CVE-NEW" in capsys.readouterr().err


def test_an_advisory_ignored_through_an_alias_passes(files):
    runner = FakeRunner(CommandResult(0, _report(("PYSEC-9", ["CVE-1"])), ""))

    assert _audit(files, runner) == 0


def test_unreachable_database_warns_and_passes_locally(files, capsys):
    runner = FakeRunner(
        CommandResult(1, "", "requests.exceptions.ConnectionError: Max retries exceeded")
    )

    assert _audit(files, runner) == 0
    assert "WARNING" in capsys.readouterr().err


def test_unreachable_database_fails_in_ci(files):
    runner = FakeRunner(CommandResult(1, "", "ReadTimeout: read timed out"))

    assert _audit(files, runner, fail_on_error=True) == 1


def test_a_non_network_tool_failure_still_blocks(files):
    runner = FakeRunner(
        CommandResult(1, "", "Dependency not found on PyPI and could not be audited")
    )

    assert _audit(files, runner) == 1


def test_a_failed_export_blocks_without_running_the_audit(files):
    runner = FakeRunner(CommandResult(0, _report(), ""), export=CommandResult(1, "", "no plugin"))

    assert _audit(files, runner) == 1
    assert runner.audit_calls == []


def test_a_green_run_is_cached_for_the_day(files):
    first = FakeRunner(CommandResult(0, _report(), ""))
    assert _audit(files, first) == 0

    second = FakeRunner(CommandResult(1, _report(("CVE-NEW", [])), ""))
    assert _audit(files, second) == 0
    assert second.calls == []


@pytest.mark.parametrize("change", ["lock", "ignore", "day", "no_cache"])
def test_the_cache_does_not_outlive_its_inputs(files, change):
    ignore, lock, _cache = files
    assert _audit(files, FakeRunner(CommandResult(0, _report(), ""))) == 0

    kwargs: dict[str, Any] = {}
    if change == "lock":
        lock.write_text("lock v2", encoding="utf-8")
    elif change == "ignore":
        ignore.write_text("CVE-1\n", encoding="utf-8")
    elif change == "day":
        kwargs["today"] = TODAY + dt.timedelta(days=1)
    else:
        kwargs["use_cache"] = False

    blocked = FakeRunner(CommandResult(1, _report(("CVE-NEW", [])), ""))
    assert _audit(files, blocked, **kwargs) == 1


def test_a_red_or_unreachable_run_is_not_cached(files):
    assert _audit(files, FakeRunner(CommandResult(1, "", "ConnectTimeout"))) == 0

    blocked = FakeRunner(CommandResult(1, _report(("CVE-NEW", [])), ""))
    assert _audit(files, blocked) == 1


def test_the_real_ignore_file_parses():
    ids = run_pip_audit.parse_ignore_file(
        (SCRIPTS_DIR / "pip_audit_ignores.txt").read_text(encoding="utf-8")
    )
    assert "CVE-2025-3000" in ids
    assert all(re.fullmatch(r"(CVE|GHSA|PYSEC)-[\w-]+", vid) for vid in ids)
