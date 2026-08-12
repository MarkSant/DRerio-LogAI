"""Ratchet: packages already migrated must not gain new Portuguese literals.

The list below grows one PR at a time. A global check would be red for the whole
migration and would therefore be switched off, which is the same as not having
it. Scoping it to what is already done keeps it green and meaningful from day
one.

When a package is migrated, add it here in the same PR. The final PR replaces
the list with ``src/zebtrack`` and this comment goes away.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

# The scanner is dev tooling, not part of the shipped package, so it lives in
# scripts/ and is imported by path rather than as a zebtrack module.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from i18n_scan import load_allowlist, scan_paths  # noqa: E402

# Migrated in PR1. Extend as later PRs land.
MIGRATED_PATHS: tuple[str, ...] = (
    "src/zebtrack/coordinators/model_diagnostics_coordinator.py",
    "src/zebtrack/core/app_runner.py",
    "src/zebtrack/core/application_bootstrapper.py",
    "src/zebtrack/i18n.py",
    "src/zebtrack/io",
    "src/zebtrack/plugins",
    "src/zebtrack/ui/builders",
    "src/zebtrack/ui/components/global_model_configuration_panel.py",
    "src/zebtrack/ui/components/menu_manager.py",
    "src/zebtrack/ui/components/model_diagnostics_panel.py",
    "src/zebtrack/ui/language_dialog.py",
    "src/zebtrack/ui/project_workflow_adapter.py",
    "src/zebtrack/ui/splash_screen.py",
    "src/zebtrack/utils",
)


@pytest.mark.parametrize("target", MIGRATED_PATHS)
def test_migrated_package_has_no_untranslated_portuguese(target: str) -> None:
    findings = scan_paths([REPO_ROOT / target], load_allowlist())

    if findings:
        listing = "\n".join(f"  {f.format(relative_to=REPO_ROOT)}" for f in findings)
        pytest.fail(
            f"{len(findings)} untranslated Portuguese literal(s) in an already "
            f"migrated path:\n{listing}\n\n"
            "Wrap the string in _() with an English msgid, record the Portuguese "
            "in src/zebtrack/locales/_pairs/, then run "
            "`poetry run python scripts/update_translations.py`.\n"
            "If the string is a persistence contract (a stored value, a path "
            "component, a dict key), add it to scripts/i18n_allowlist.txt instead "
            "— and never translate it."
        )


def test_allowlist_is_non_empty_and_commented() -> None:
    """A silently emptied allowlist would make the ratchet pass by accident."""
    patterns = load_allowlist()
    assert len(patterns) > 20
    for protected in ("Grupo_", "Dia_", "Sujeito_", "por_animal"):
        assert protected in patterns, f"{protected} must stay protected"
