#!/usr/bin/env python3
"""Compile gettext translation catalogs for DRerio LogAI.

The script locates every ``*.po`` file under ``src/zebtrack/locales`` and
produces the corresponding binary ``*.mo`` file, matching the expectations of
``gettext.translation`` used by the reporting pipeline.

It is safe to run repeatedly; output files are overwritten in place.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import polib

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCALES_ROOT = REPO_ROOT / "src" / "zebtrack" / "locales"


def compile_catalog(po_file: Path) -> Path:
    """Compile a .po catalog to its binary .mo counterpart."""
    catalog = polib.pofile(po_file)
    if not catalog:  # Sanity guard to avoid empty outputs
        raise RuntimeError(f"Translation file '{po_file}' is empty or invalid.")

    mo_path = po_file.with_suffix(".mo")
    mo_path.parent.mkdir(parents=True, exist_ok=True)
    catalog.save_as_mofile(str(mo_path))
    return mo_path


def discover_po_files(root: Path) -> list[Path]:
    return sorted(root.glob("**/*.po"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--locales-root",
        type=Path,
        default=LOCALES_ROOT,
        help=("Root directory containing locale subfolders (default: src/zebtrack/locales)."),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # Force UTF-8 for stdout and stderr on Windows to avoid charmap errors
    if sys.platform == "win32":
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

    args = parse_args(argv)
    if not args.locales_root.exists():
        print(
            f"[WARNING] Locales directory '{args.locales_root}' not found - nothing to compile.",
            file=sys.stderr,
        )
        return 0

    po_files = discover_po_files(args.locales_root)
    if not po_files:
        print(
            f"[WARNING] No .po files discovered under '{args.locales_root}'.",
            file=sys.stderr,
        )
        return 0

    for po_file in po_files:
        mo_path = compile_catalog(po_file)
        print(
            "[SUCCESS] Compiled "
            f"{po_file.relative_to(args.locales_root)} "
            f"-> {mo_path.relative_to(args.locales_root)}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
