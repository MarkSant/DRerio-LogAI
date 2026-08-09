"""Merge recorded English-msgid -> original-Portuguese pairs into the pt_BR catalogue.

The migration to English source strings is a *move*, not a translation job: when
``"Salvar projeto"`` in the code becomes ``_("Save project")``, the Portuguese
text is not lost, it relocates to the catalogue as
``msgid "Save project" / msgstr "Salvar projeto"``. Nobody has to translate
anything, and the round trip stays verifiable.

While rewriting a batch, record each pair in
``src/zebtrack/locales/_pairs/<batch>.json``::

    {
      "Save project": "Salvar projeto",
      "Select video": "Selecionar vídeo"
    }

Then this script writes them into ``pt_BR/LC_MESSAGES/<domain>.po``. The pair
files are committed, so a later msgid rename can be traced back to the original
Portuguese, and a reviewer can machine-check that the ``.po`` diff is the exact
inverse of the source diff.

Existing non-empty translations are never overwritten -- a hand-corrected
``msgstr`` outranks a mechanically recorded one.

Usage::

    python scripts/i18n_pairs.py                       # merge every pair file
    python scripts/i18n_pairs.py --batch pr1-entrypoints
    python scripts/i18n_pairs.py --check               # report, change nothing
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import polib

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = REPO_ROOT / "src" / "zebtrack" / "locales"
PAIRS_DIR = LOCALES_DIR / "_pairs"
TARGET_LANGUAGE = "pt_BR"
DEFAULT_DOMAIN = "zebtrack"


def load_pairs(batch: str | None = None, domain: str = DEFAULT_DOMAIN) -> dict[str, str]:
    """Load and merge the pair files belonging to *domain* (or just *batch*).

    A pair file declares its catalogue with a ``"_domain"`` key; without one it
    is assumed to belong to the UI domain, which is where the bulk migration
    happens.
    """
    if not PAIRS_DIR.exists():
        return {}

    pattern = f"{batch}.json" if batch else "*.json"
    merged: dict[str, str] = {}
    for pair_file in sorted(PAIRS_DIR.glob(pattern)):
        data = json.loads(pair_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{pair_file}: expected a JSON object of msgid -> translation")
        if data.get("_domain", DEFAULT_DOMAIN) != domain:
            continue
        for msgid, translation in data.items():
            if msgid.startswith("_"):
                # Metadata keys: "_comment" describes the batch, "_domain"
                # routes it. Neither is a msgid.
                continue
            if msgid in merged and merged[msgid] != translation:
                print(
                    f"WARNING: '{msgid}' has conflicting translations across batches; "
                    f"keeping '{merged[msgid]}', ignoring '{translation}'",
                    file=sys.stderr,
                )
                continue
            merged[msgid] = translation
    return merged


def merge_into_catalog(
    pairs: dict[str, str],
    domain: str = DEFAULT_DOMAIN,
    *,
    check_only: bool = False,
) -> tuple[int, int, list[str]]:
    """Write *pairs* into the pt_BR catalogue for *domain*.

    Returns:
        ``(filled, skipped, missing)`` -- entries given a translation, entries
        left alone because they already had one, and msgids present in the pairs
        but absent from the catalogue (usually a msgid edited in code but not in
        the pair file).
    """
    po_path = LOCALES_DIR / TARGET_LANGUAGE / "LC_MESSAGES" / f"{domain}.po"
    if not po_path.exists():
        raise FileNotFoundError(
            f"{po_path} does not exist. Run scripts/update_translations.py first."
        )

    catalog = polib.pofile(str(po_path))
    by_msgid = {entry.msgid: entry for entry in catalog}

    filled = 0
    skipped = 0
    missing: list[str] = []

    for msgid, translation in pairs.items():
        entry = by_msgid.get(msgid)
        if entry is None:
            missing.append(msgid)
            continue

        is_fuzzy = "fuzzy" in entry.flags
        if entry.msgstr.strip() and not is_fuzzy:
            # A real, reviewed translation outranks a mechanically recorded one.
            skipped += 1
            continue

        # A fuzzy msgstr is Babel guessing by string similarity, and it guesses
        # badly: it happily maps "Advanced Settings" onto "Carregando
        # configurações...". It is not a translation to protect -- overwrite it
        # with the literal the code actually used.
        entry.msgstr = translation
        if is_fuzzy:
            entry.flags.remove("fuzzy")
        filled += 1

    if not check_only and filled:
        catalog.save(str(po_path))

    return filled, skipped, missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--batch", help="Merge only this pair file (without .json)")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="Catalogue domain")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report what would change without writing.",
    )
    args = parser.parse_args()

    pairs = load_pairs(args.batch, args.domain)
    if not pairs:
        print(f"No pairs for domain '{args.domain}' in {PAIRS_DIR}")
        return 0

    filled, skipped, missing = merge_into_catalog(pairs, args.domain, check_only=args.check)

    verb = "would fill" if args.check else "filled"
    print(f"{verb} {filled} entries, kept {skipped} existing translations")
    if missing:
        print(f"\n{len(missing)} msgid(s) in pairs but not in the catalogue:", file=sys.stderr)
        for msgid in missing:
            print(f"  - {msgid}", file=sys.stderr)
        print(
            "\nThese usually mean the code says something different from the pair "
            "file. Re-run scripts/update_translations.py, then fix the mismatch.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
