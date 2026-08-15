"""Ratchet: the package must not gain new Portuguese literals.

The migration is finished, so the list is simply ``src/zebtrack``: every file,
including files that do not exist yet.

Note what this does and does not prove. ``i18n_scan`` detects Portuguese by its
ACCENTED characters, so unaccented Portuguese — ``Salvar``, ``Nenhum video``,
``Remover``, ``dias`` — passes straight through it and through this test. Batch
5e found four such strings inside ``core/recording/``, a package that had been
listed here since batch 3a. Green here means "no accented Portuguese"; it does
not mean "no Portuguese".
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

MIGRATED_PATHS: tuple[str, ...] = ("src/zebtrack",)


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
