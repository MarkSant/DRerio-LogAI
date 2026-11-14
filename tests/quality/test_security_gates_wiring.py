"""CI and the pre-push hook run the same security gates (#648).

``bandit`` and ``pip-audit`` used to run only in CI, so a push could be green
locally and turn CI red. These tests read the two configurations and fail if
either loses a gate, or if ``ci.yml`` grows its own inline pip-audit exceptions
again instead of reading ``scripts/pip_audit_ignores.txt``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.unit


def test_ci_runs_the_shared_script_and_keeps_no_inline_exceptions():
    """The drift guard: CI and the pre-push hook read the same exception list."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "--ignore-vuln" not in workflow
    steps = [
        step.get("run", "")
        for job in yaml.safe_load(workflow)["jobs"].values()
        for step in job.get("steps", [])
    ]
    assert any(
        "scripts/run_pip_audit.py" in run and "--fail-on-error" in run and "--no-cache" in run
        for run in steps
    )


def test_the_pre_push_hooks_run_both_security_gates():
    config = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = {
        hook["id"]: hook
        for repo in config["repos"]
        if repo["repo"] == "local"
        for hook in repo["hooks"]
    }

    assert "scripts/run_pip_audit.py" in hooks["pip-audit"]["entry"]
    assert hooks["pip-audit"]["stages"] == ["pre-push"]
    assert re.search(r"bandit\b.*-r src/zebtrack.*-ll", hooks["bandit"]["entry"])
    assert hooks["bandit"]["stages"] == ["pre-push"]
