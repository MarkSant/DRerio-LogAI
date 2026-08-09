"""The shipped catalogues must be complete and match their sources.

Two failure modes this catches, both silent at runtime because gettext falls
back to the msgid instead of raising:

* an empty ``msgstr`` -- the string quietly stays English for Portuguese users;
* a ``.po`` edited without recompiling -- the ``.mo`` is what actually ships, so
  the fix appears to have been made and has no effect.
"""

from __future__ import annotations

from pathlib import Path

import polib
import pytest

from zebtrack import i18n

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCALES_DIR = REPO_ROOT / "src" / "zebtrack" / "locales"
DOMAINS = ("zebtrack", "reporter")
TARGET_LANGUAGE = "pt_BR"


def _po_path(domain: str) -> Path:
    return LOCALES_DIR / TARGET_LANGUAGE / "LC_MESSAGES" / f"{domain}.po"


@pytest.mark.parametrize("domain", DOMAINS)
def test_catalogue_and_compiled_file_exist(domain: str) -> None:
    assert _po_path(domain).exists(), f"missing {domain}.po"
    assert _po_path(domain).with_suffix(".mo").exists(), (
        f"missing {domain}.mo — run scripts/compile_translations.py"
    )


@pytest.mark.parametrize("domain", DOMAINS)
def test_every_entry_is_translated_and_not_fuzzy(domain: str) -> None:
    catalog = polib.pofile(str(_po_path(domain)))

    untranslated = [e.msgid for e in catalog if not e.msgstr.strip() and not e.obsolete]
    fuzzy = [e.msgid for e in catalog if "fuzzy" in e.flags and not e.obsolete]

    assert not untranslated, (
        f"{len(untranslated)} untranslated entries in {domain}.po: {untranslated[:5]}\n"
        "Record the Portuguese in src/zebtrack/locales/_pairs/ and run "
        "scripts/update_translations.py."
    )
    assert not fuzzy, (
        f"{len(fuzzy)} fuzzy entries in {domain}.po: {fuzzy[:5]}\n"
        "Babel guessed these by similarity — confirm and clear the fuzzy flag."
    )


@pytest.mark.parametrize("domain", DOMAINS)
def test_compiled_catalogue_is_up_to_date(domain: str) -> None:
    """Recompiling the .po must reproduce the committed .mo byte for byte."""
    po_path = _po_path(domain)
    mo_path = po_path.with_suffix(".mo")

    expected = polib.pofile(str(po_path)).to_binary()
    actual = mo_path.read_bytes()

    assert actual == expected, (
        f"{domain}.mo is stale — the .po was edited without recompiling. "
        "Run `poetry run python scripts/compile_translations.py`."
    )


@pytest.mark.parametrize("domain", DOMAINS)
def test_template_exists_and_covers_the_catalogue(domain: str) -> None:
    """Every msgid extracted from the source must exist in the catalogue."""
    pot_path = LOCALES_DIR / f"{domain}.pot"
    assert pot_path.exists(), f"missing {domain}.pot — run scripts/update_translations.py"

    template_ids = {e.msgid for e in polib.pofile(str(pot_path))}
    catalog_ids = {e.msgid for e in polib.pofile(str(_po_path(domain))) if not e.obsolete}

    missing = template_ids - catalog_ids
    assert not missing, (
        f"{len(missing)} msgid(s) in {domain}.pot but not in {domain}.po: "
        f"{sorted(missing)[:5]}\nRun scripts/update_translations.py."
    )


def test_language_dialog_is_never_translated() -> None:
    """The first-launch chooser must read before a language has been chosen."""
    source = (REPO_ROOT / "src" / "zebtrack" / "ui" / "language_dialog.py").read_text(
        encoding="utf-8"
    )
    assert "i18n: file-exempt" in source
    assert "English" in source and "Português" in source


def test_locales_ship_inside_the_package() -> None:
    """gettext reads these at runtime; they must not be dev-only files."""
    assert LOCALES_DIR.is_dir()
    assert LOCALES_DIR.is_relative_to(REPO_ROOT / "src" / "zebtrack")
    assert i18n.LOCALES_DIR == LOCALES_DIR
