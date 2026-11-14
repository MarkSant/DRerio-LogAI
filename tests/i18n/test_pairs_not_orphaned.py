"""Every recorded pair in ``locales/_pairs/`` must still name a catalogue msgid.

``scripts/update_translations.py`` runs ``scripts/i18n_pairs.py`` before it
compiles the ``.mo``, and that step exits 1 on any pair whose msgid is not in
the ``.po`` at all. One stale pair -- left behind when the code that used the
string is deleted and its entry is removed from the catalogue by hand -- stops
the whole refresh before compilation, and the next person to add a string ships
a ``.mo`` without it unless they think to compile by hand (#703).

The check goes through ``merge_into_catalog(check_only=True)``, the very
function the script calls, so the test fails exactly when the script would.
A msgid that ``pybabel update`` merely marked obsolete (``#~``) is still in the
catalogue and does not stop the script; it is not what this guards.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from i18n_pairs import PAIRS_DIR, load_pairs, merge_into_catalog  # noqa: E402

DOMAINS = ("zebtrack", "reporter")


@pytest.mark.parametrize("domain", DOMAINS)
def test_every_pair_msgid_exists_in_the_catalogue(domain: str) -> None:
    _, _, orphans = merge_into_catalog(load_pairs(domain=domain), domain, check_only=True)

    assert not orphans, (
        f"{len(orphans)} pair(s) in {PAIRS_DIR.relative_to(REPO_ROOT)} name a msgid "
        f"missing from the {domain} catalogue: {sorted(orphans)}\n"
        "If the string was reworded, update the pair's msgid; if its code was "
        "removed, remove the pair. Otherwise scripts/update_translations.py stops "
        "before compiling the .mo."
    )


@pytest.mark.parametrize("domain", DOMAINS)
def test_the_guard_reads_real_pairs(domain: str) -> None:
    """An empty pair set would make the guard above pass vacuously."""
    assert load_pairs(domain=domain), f"no {domain} pairs found -- wrong PAIRS_DIR?"
