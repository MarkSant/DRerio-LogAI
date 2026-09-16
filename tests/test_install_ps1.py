"""Tests for the helpers in ``install.ps1``.

The installer is what a researcher with no terminal experience runs first, so
its prerequisite handling has to be right on machines nobody here can test on.
These tests dot-source the script -- which defines the helpers and stops before
installing anything -- and drive the helpers in a PowerShell process whose
environment (PATH, APPDATA, POETRY_HOME) is fully controlled.

Windows only: the script targets Windows PowerShell 5.1.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_PS1 = REPO_ROOT / "install.ps1"

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or shutil.which("powershell") is None,
    reason="install.ps1 targets Windows PowerShell",
)


def _run_helpers(script: str, env_overrides: dict[str, str | None]) -> str:
    """Dot-source install.ps1, run *script*, and return its trimmed stdout."""
    env = dict(os.environ)
    for name, value in env_overrides.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    command = f". '{INSTALL_PS1}'; {script}"
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _isolated_path() -> str:
    """A PATH with PowerShell's own folder but no poetry, winget or python."""
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    return os.pathsep.join(
        [
            str(Path(system_root) / "System32"),
            str(Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0"),
        ]
    )


def test_script_parses_without_errors() -> None:
    output = _run_helpers(
        "$errors = $null; "
        "[System.Management.Automation.Language.Parser]::ParseFile("
        f"'{INSTALL_PS1}', [ref]$null, [ref]$errors) | Out-Null; "
        "$errors.Count",
        {},
    )
    assert output == "0"


def test_dot_sourcing_defines_helpers_without_installing(tmp_path: Path) -> None:
    # If the guard failed, the main body would run: it prints the step banner.
    output = _run_helpers(
        "Write-Output ([bool](Get-Command Find-PoetryExecutable -ErrorAction SilentlyContinue))",
        {"PATH": _isolated_path(), "APPDATA": str(tmp_path), "LOCALAPPDATA": str(tmp_path)},
    )
    assert output == "True"


class TestAddPathEntry:
    def test_appends_a_missing_directory(self) -> None:
        output = _run_helpers(r"Add-PathEntry 'C:\a;C:\b' 'C:\tools\bin'", {})
        assert output == r"C:\a;C:\b;C:\tools\bin"

    def test_existing_entry_returns_the_list_unchanged(self) -> None:
        # Different case and a trailing backslash are still the same folder,
        # and the original string must come back untouched so nothing is written.
        output = _run_helpers(r"Add-PathEntry 'C:\A;;c:\tools\BIN\;C:\b' 'C:\tools\bin'", {})
        assert output == r"C:\A;;c:\tools\BIN\;C:\b"

    def test_empty_list_yields_just_the_directory(self) -> None:
        output = _run_helpers(r"Add-PathEntry '' 'C:\tools\bin\'", {})
        assert output == r"C:\tools\bin"

    def test_trailing_separator_is_not_doubled(self) -> None:
        output = _run_helpers(r"Add-PathEntry 'C:\a;' 'C:\b'", {})
        assert output == r"C:\a;C:\b"


class TestFindPoetryExecutable:
    def test_finds_poetry_installed_but_not_on_path(self, tmp_path: Path) -> None:
        poetry = tmp_path / "Python" / "Scripts" / "poetry.exe"
        poetry.parent.mkdir(parents=True)
        poetry.write_bytes(b"")

        output = _run_helpers(
            "Find-PoetryExecutable",
            {"PATH": _isolated_path(), "APPDATA": str(tmp_path), "POETRY_HOME": None},
        )
        assert output == str(poetry)

    def test_poetry_home_takes_precedence_over_appdata(self, tmp_path: Path) -> None:
        appdata_poetry = tmp_path / "appdata" / "Python" / "Scripts" / "poetry.exe"
        home_poetry = tmp_path / "home" / "bin" / "poetry.exe"
        for path in (appdata_poetry, home_poetry):
            path.parent.mkdir(parents=True)
            path.write_bytes(b"")

        output = _run_helpers(
            "Find-PoetryExecutable",
            {
                "PATH": _isolated_path(),
                "APPDATA": str(tmp_path / "appdata"),
                "POETRY_HOME": str(tmp_path / "home"),
            },
        )
        assert output == str(home_poetry)

    def test_returns_nothing_when_poetry_is_absent(self, tmp_path: Path) -> None:
        output = _run_helpers(
            "$found = Find-PoetryExecutable; if ($null -eq $found) { 'none' } else { $found }",
            {"PATH": _isolated_path(), "APPDATA": str(tmp_path), "POETRY_HOME": None},
        )
        assert output == "none"


class TestConfirmOffer:
    def test_declines_when_nobody_can_answer(self) -> None:
        # -NonInteractive makes Read-Host throw; an unattended run must decline
        # rather than install something unasked or hang.
        output = _run_helpers("Confirm-Offer 'Install?'", {})
        assert output.splitlines()[-1] == "False"

    def test_yes_switch_accepts_without_asking(self) -> None:
        output = _run_helpers("$Yes = $true; Confirm-Offer 'Install?'", {})
        assert output.splitlines()[-1] == "True"


def test_python_candidates_include_the_per_user_install_folder(tmp_path: Path) -> None:
    # winget installs Python here, and this session's PATH does not know it yet.
    output = _run_helpers(
        "(Get-PythonCandidates | ForEach-Object { $_.Exe }) -join '|'",
        {"LOCALAPPDATA": str(tmp_path)},
    )
    candidates = output.split("|")
    assert candidates[:3] == ["py", "py", "python"]
    assert str(tmp_path / "Programs" / "Python" / "Python312" / "python.exe") in candidates
