#!/usr/bin/env python3
"""Build the GitHub Wiki tree from ``docs/wiki/``.

The wiki is a separate git repository, so a plain copy breaks every link that
points outside ``docs/wiki/`` -- eleven of them today, to `CONTRIBUTING.md`,
`LICENSE`, `docs/reference/metrics.md` and friends. Those become absolute URLs
into the main repository; links that stay inside the folder are left alone,
because the wiki keeps the same layout.

``INDEX.md`` becomes ``Home.md``: a GitHub wiki shows the page named ``Home`` as
its landing page, and without one the wiki opens on whatever it feels like.

Usage::

    python scripts/build_wiki.py --check          # report, write nothing
    python scripts/build_wiki.py --out <dir>      # build into <dir>

Exit codes: 0 on success, 1 when ``--check`` finds something to report.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WIKI_SOURCE = REPO_ROOT / "docs" / "wiki"
BLOB_BASE = "https://github.com/MarkSant/DRerio-LogAI/blob/main"

LANDING_PAGE = "INDEX.md"
LANDING_TARGET = "Home.md"

_LINK = re.compile(r"(\[[^\]]*\]\()([^)\s]+)(\))")

GENERATED_BANNER = (
    "<!-- Generated from docs/wiki/ by scripts/build_wiki.py. Do not edit here:\n"
    "     edits belong in the repository, or the next sync overwrites them. -->\n\n"
)


def _rewrite_target(target: str, page: Path) -> tuple[str, bool]:
    """Return the rewritten link and whether it had to leave the wiki.

    *page* is the source path relative to ``docs/wiki``; it decides what a
    relative link resolves against.
    """
    if target.startswith(("http://", "https://", "#", "mailto:")):
        return target, False

    anchor = ""
    if "#" in target:
        target, anchor = target.split("#", 1)
        anchor = "#" + anchor
    if not target:
        return anchor, False

    resolved = (WIKI_SOURCE / page.parent / target).resolve()
    try:
        resolved.relative_to(WIKI_SOURCE.resolve())
    except ValueError:
        # Escapes the wiki: point at the file in the main repository instead.
        relative = resolved.relative_to(REPO_ROOT.resolve()).as_posix()
        return f"{BLOB_BASE}/{relative}{anchor}", True

    # Stays inside: the wiki keeps the same layout, so the link still works.
    # Only the landing page is renamed.
    if resolved.name == LANDING_PAGE:
        target = target[: -len(LANDING_PAGE)] + LANDING_TARGET
    return target + anchor, False


def build(out_dir: Path | None, *, check: bool) -> int:
    if not WIKI_SOURCE.is_dir():
        print(f"error: {WIKI_SOURCE} not found", file=sys.stderr)
        return 1

    externalised: list[tuple[str, str]] = []
    pages = 0
    assets = 0

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)

    for source in sorted(WIKI_SOURCE.rglob("*")):
        if source.is_dir():
            continue
        relative = source.relative_to(WIKI_SOURCE)

        if source.suffix.lower() != ".md":
            assets += 1
            if out_dir is not None:
                destination = out_dir / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            continue

        text = source.read_text(encoding="utf-8")

        def replace(match: re.Match[str], _page: Path = relative) -> str:
            new_target, left = _rewrite_target(match.group(2), _page)
            if left:
                externalised.append((_page.as_posix(), match.group(2)))
            return f"{match.group(1)}{new_target}{match.group(3)}"

        text = _LINK.sub(replace, text)
        pages += 1

        if out_dir is not None:
            name = LANDING_TARGET if relative.name == LANDING_PAGE else relative.name
            destination = out_dir / relative.parent / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(GENERATED_BANNER + text, encoding="utf-8", newline="\n")

    print(f"pages: {pages} | assets: {assets}")
    print(f"links rewritten to absolute URLs: {len(externalised)}")
    for page, target in externalised:
        print(f"  {page} -> {target}")

    if out_dir is not None:
        print(f"written to {out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_wiki",
        description="Build the GitHub Wiki tree from docs/wiki/.",
    )
    parser.add_argument("--out", type=Path, default=None, help="Directory to build into.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report what would be built and rewritten, writing nothing.",
    )
    args = parser.parse_args(argv)

    if args.check and args.out is not None:
        parser.error("--check writes nothing; do not pass --out with it")
    if not args.check and args.out is None:
        parser.error("pass --out <dir>, or --check to report only")

    return build(args.out, check=args.check)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
