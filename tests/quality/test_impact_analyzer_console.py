"""The impact analyzer is mandatory before every change, so it must survive any console."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "impact_analyzer.py"


def _run(encoding: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONIOENCODING": encoding}
    env.pop("PYTHONUTF8", None)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "file", "src/zebtrack/settings.py"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        timeout=120,
        check=False,
    )


def test_report_prints_on_a_cp1252_console() -> None:
    proc = _run("cp1252")
    stderr = proc.stderr.decode("cp1252", errors="replace")
    assert proc.returncode == 0, stderr
    stdout = proc.stdout.decode("cp1252")
    assert "IMPACT ANALYSIS: FILE" in stdout
    assert "settings.py" in stdout
    # The emoji cp1252 cannot hold are escaped, not dropped.
    assert "\\U0001f4e6 DIRECT DEPENDENTS" in stdout


def test_report_is_unchanged_on_a_utf8_console() -> None:
    proc = _run("utf-8")
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    assert "\U0001f4e6 DIRECT DEPENDENTS" in proc.stdout.decode("utf-8")
