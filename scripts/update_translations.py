#!/usr/bin/env python3
"""Refresh translation catalogues end to end.

Run this after adding, changing or removing any ``_("...")`` string::

    poetry run python scripts/update_translations.py

It performs four steps, in order:

1. ``pybabel extract`` -- rebuild ``locales/<domain>.pot`` from the source.
2. ``pybabel update`` (or ``init`` the first time) -- merge the template into
   ``locales/pt_BR/LC_MESSAGES/<domain>.po``, preserving existing translations
   and marking removed strings obsolete.
3. ``scripts/i18n_pairs.py`` -- fill empty entries from the recorded
   English->Portuguese pair files, so a bulk migration needs no manual typing.
4. ``scripts/compile_translations.py`` -- regenerate every ``.mo``.

There is no ``en`` catalogue and there never will be: English is the source
language, so a missing translation *is* the English text.

After running, open the ``.po`` and fill any ``msgstr ""`` that step 3 could not.
Run the script again to recompile.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCALES_DIR = REPO_ROOT / "src" / "zebtrack" / "locales"
BABEL_CONFIG = REPO_ROOT / "babel.cfg"
TARGET_LANGUAGE = "pt_BR"

# Domains and the source subtree each one extracts from.
DOMAINS: dict[str, str] = {
    "zebtrack": "src/zebtrack",
    "reporter": "src/zebtrack/analysis/reporters",
}

KEYWORDS = ("_", "gettext", "lazy", "ngettext:1,2", "translate")

PROJECT = "DRerio LogAI"


def _run(command: list[str]) -> None:
    print(f"$ {' '.join(command)}")
    result = subprocess.run(command, cwd=REPO_ROOT, check=False)
    if result.returncode != 0:
        raise SystemExit(f"Command failed with exit code {result.returncode}")


def extract(domain: str, source: str) -> Path:
    """Rebuild the .pot template for *domain*."""
    pot_path = LOCALES_DIR / f"{domain}.pot"
    command = [
        sys.executable,
        "-m",
        "babel.messages.frontend",
        "extract",
        "--mapping-file",
        str(BABEL_CONFIG),
        "--output-file",
        str(pot_path),
        "--project",
        PROJECT,
        "--copyright-holder",
        PROJECT,
        "--add-comments",
        "i18n",
    ]
    for keyword in KEYWORDS:
        command.extend(["--keyword", keyword])
    if domain == "zebtrack":
        # The reporters subtree has its own domain; without this its msgids
        # would be duplicated into both catalogues and translated twice.
        command.extend(["--ignore-dirs", "reporters"])
    command.append(source)
    _run(command)
    return pot_path


def update_or_init(domain: str, pot_path: Path) -> None:
    """Merge the template into the pt_BR catalogue, creating it if absent."""
    po_path = LOCALES_DIR / TARGET_LANGUAGE / "LC_MESSAGES" / f"{domain}.po"

    if po_path.exists():
        subcommand = "update"
        # --no-fuzzy-matching: without it Babel seeds each new msgid's msgstr
        # from whatever existing entry looks similar, marks it fuzzy, and
        # records the old text in a "#|" previous-msgid comment. i18n_pairs.py
        # throws those guesses away regardless (it overwrites fuzzy msgstr from
        # the _pairs files), so the only thing they produce is risk: when the
        # guessed msgid spans several lines Babel wraps that "#|" comment in
        # the middle of a quoted string, and polib then refuses to parse the
        # catalogue at all.
        extra = ["--previous", "--no-fuzzy-matching"]
    else:
        subcommand = "init"
        extra = []
        po_path.parent.mkdir(parents=True, exist_ok=True)

    _run(
        [
            sys.executable,
            "-m",
            "babel.messages.frontend",
            subcommand,
            "--input-file",
            str(pot_path),
            "--output-dir",
            str(LOCALES_DIR),
            "--locale",
            TARGET_LANGUAGE,
            "--domain",
            domain,
            *extra,
        ]
    )


def merge_pairs(domain: str) -> None:
    """Fill empty translations from the recorded pair files for *domain*."""
    _run([sys.executable, str(REPO_ROOT / "scripts" / "i18n_pairs.py"), "--domain", domain])


def compile_all() -> None:
    _run([sys.executable, str(REPO_ROOT / "scripts" / "compile_translations.py")])


def report_untranslated() -> int:
    """List entries still lacking a translation. Returns how many there are."""
    import polib

    total = 0
    for domain in DOMAINS:
        po_path = LOCALES_DIR / TARGET_LANGUAGE / "LC_MESSAGES" / f"{domain}.po"
        if not po_path.exists():
            continue
        catalog = polib.pofile(str(po_path))
        untranslated = [
            entry for entry in catalog if not entry.msgstr.strip() and not entry.obsolete
        ]
        if untranslated:
            print(f"\n{len(untranslated)} untranslated in {domain}.po:")
            for entry in untranslated[:20]:
                print(f"  - {entry.msgid}")
            if len(untranslated) > 20:
                print(f"  ... and {len(untranslated) - 20} more")
        total += len(untranslated)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--domain",
        choices=sorted(DOMAINS),
        help="Only refresh this domain (default: all).",
    )
    args = parser.parse_args()

    domains = {args.domain: DOMAINS[args.domain]} if args.domain else DOMAINS

    for domain, source in domains.items():
        print(f"\n=== {domain} ({source}) ===")
        pot_path = extract(domain, source)
        update_or_init(domain, pot_path)
        merge_pairs(domain)

    compile_all()

    remaining = report_untranslated()
    if remaining:
        print(
            f"\n{remaining} string(s) still need a Portuguese translation. "
            "Fill them in the .po and run this script again."
        )
    else:
        print("\nAll catalogues are complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
