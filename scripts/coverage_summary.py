"""Per-package coverage summary and per-package floors, read from a Cobertura XML.

Usage::

    python scripts/coverage_summary.py                       # reads coverage.xml
    python scripts/coverage_summary.py coverage-core.xml
    python scripts/coverage_summary.py coverage-core.xml --fail-under plugins=85

The global ``--cov-fail-under`` gate is one number for ~55 000 statements, so a
package can lose every test it has without moving it. ``--fail-under`` pins a
floor on one package (sub-packages included): the gain a focused test campaign
buys cannot be handed back behind the global average.

Numbers are recomputed from the ``<line>`` elements rather than read from the
``line-rate`` attributes, so a package is always the sum of its own files and a
prefix such as ``core`` aggregates ``core.detection``, ``core.project`` and so on.

Exit codes: 0 every floor holds, 1 a package is under its floor, 2 the request
cannot be trusted (unreadable XML, malformed floor, or a floor on a package the
report does not contain — a typo must not pass as "nothing to check").
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import PurePosixPath

ROOT_PACKAGE = "."
_CONDITION_RE = re.compile(r"\((\d+)/(\d+)\)")


@dataclass
class Counts:
    """Line and branch tallies for one file or one aggregate of files."""

    statements: int = 0
    covered: int = 0
    branches: int = 0
    branches_covered: int = 0

    def add(self, other: Counts) -> None:
        self.statements += other.statements
        self.covered += other.covered
        self.branches += other.branches
        self.branches_covered += other.branches_covered

    @property
    def missed(self) -> int:
        return self.statements - self.covered

    @property
    def line_rate(self) -> float:
        """Line coverage in percent; an empty aggregate counts as fully covered."""
        if self.statements == 0:
            return 100.0
        return 100.0 * self.covered / self.statements

    @property
    def branch_rate(self) -> float | None:
        """Branch coverage in percent, or ``None`` when the run measured no branches."""
        if self.branches == 0:
            return None
        return 100.0 * self.branches_covered / self.branches


def normalize_filename(filename: str) -> str:
    """Return *filename* relative to the ``zebtrack`` package, with ``/`` separators.

    coverage.py writes paths relative to the measured source, which is the
    package itself under ``--cov=zebtrack`` (``plugins/base.py``) and the
    repository under other invocations (``src/zebtrack/plugins/base.py``).
    """
    parts = PurePosixPath(filename.replace("\\", "/")).parts
    if "zebtrack" in parts:
        index = len(parts) - 1 - parts[::-1].index("zebtrack")
        parts = parts[index + 1 :]
    return "/".join(parts)


def package_of(relative_filename: str) -> str:
    """Return the dotted package of a normalized filename (``.`` for top-level files)."""
    parent = PurePosixPath(relative_filename).parent
    if str(parent) in ("", "."):
        return ROOT_PACKAGE
    return ".".join(parent.parts)


def read_file_counts(xml_path: str) -> dict[str, Counts]:
    """Parse a Cobertura report into ``{normalized filename: Counts}``."""
    root = ET.parse(xml_path).getroot()
    files: dict[str, Counts] = {}
    for cls in root.iter("class"):
        filename = cls.attrib.get("filename")
        if not filename:
            continue
        counts = files.setdefault(normalize_filename(filename), Counts())
        for line in cls.iter("line"):
            counts.statements += 1
            if int(line.attrib.get("hits", "0")) > 0:
                counts.covered += 1
            if line.attrib.get("branch") == "true":
                match = _CONDITION_RE.search(line.attrib.get("condition-coverage", ""))
                if match:
                    counts.branches_covered += int(match.group(1))
                    counts.branches += int(match.group(2))
    return files


def aggregate_by_package(files: dict[str, Counts]) -> dict[str, Counts]:
    """Sum file counts into their own package (no roll-up into parents)."""
    packages: dict[str, Counts] = {}
    for filename, counts in files.items():
        packages.setdefault(package_of(filename), Counts()).add(counts)
    return packages


def aggregate_prefix(files: dict[str, Counts], package: str) -> Counts | None:
    """Sum every file in *package* and its sub-packages; ``None`` if there is none."""
    total = Counts()
    found = False
    for filename, counts in files.items():
        own = package_of(filename)
        if own == package or (package != ROOT_PACKAGE and own.startswith(package + ".")):
            total.add(counts)
            found = True
    return total if found else None


def parse_floor(spec: str) -> tuple[str, float]:
    """Parse ``PACKAGE=PERCENT``; raise ``ValueError`` on anything else."""
    package, separator, raw = spec.partition("=")
    package = package.strip().replace("/", ".")
    if not separator or not package:
        raise ValueError(f"expected PACKAGE=PERCENT, got {spec!r}")
    floor = float(raw)
    if not 0.0 <= floor <= 100.0:
        raise ValueError(f"floor out of range in {spec!r}")
    return package, floor


def check_floors(
    files: dict[str, Counts], floors: list[tuple[str, float]]
) -> tuple[list[str], list[str]]:
    """Return ``(failures, unknown_packages)`` for the requested floors."""
    failures: list[str] = []
    unknown: list[str] = []
    for package, floor in floors:
        counts = aggregate_prefix(files, package)
        if counts is None:
            unknown.append(package)
            continue
        if counts.line_rate < floor:
            failures.append(
                f"{package}: {counts.line_rate:.2f}% line coverage is under the "
                f"{floor:.2f}% floor ({counts.missed} of {counts.statements} statements missed)"
            )
    return failures, unknown


def _format_row(name: str, counts: Counts) -> str:
    branch = counts.branch_rate
    branch_text = f"{branch:6.1f}%" if branch is not None else "     - "
    return (
        f"  {counts.line_rate:6.1f}%  {branch_text}  "
        f"{counts.statements:6d}  {counts.missed:6d}  {name}"
    )


def render(files: dict[str, Counts], below: float) -> str:
    """Build the human-readable report."""
    total = Counts()
    for counts in files.values():
        total.add(counts)
    lines = [
        f"Overall line coverage: {total.line_rate:.2f}% "
        f"({total.covered}/{total.statements} statements)",
    ]
    if total.branch_rate is not None:
        lines.append(
            f"Overall branch coverage: {total.branch_rate:.2f}% "
            f"({total.branches_covered}/{total.branches} branches)"
        )
    lines += ["", "    line   branch   stmts    miss  package"]
    packages = aggregate_by_package(files)
    for name in sorted(packages, key=lambda key: packages[key].line_rate):
        lines.append(_format_row(name, packages[name]))
    lines += ["", f"--- Files under {below:g}% line coverage ---"]
    for name in sorted(files, key=lambda key: files[key].line_rate):
        if files[name].line_rate >= below:
            break
        lines.append(_format_row(name, files[name]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("xml", nargs="?", default="coverage.xml", help="Cobertura XML to read")
    parser.add_argument(
        "--fail-under",
        action="append",
        default=[],
        metavar="PACKAGE=PERCENT",
        help="fail when PACKAGE (sub-packages included) is under PERCENT line coverage",
    )
    parser.add_argument(
        "--below",
        type=float,
        default=30.0,
        help="list files under this line coverage (default: 30)",
    )
    args = parser.parse_args(argv)

    try:
        floors = [parse_floor(spec) for spec in args.fail_under]
    except ValueError as exc:
        print(f"coverage_summary: {exc}", file=sys.stderr)
        return 2
    try:
        files = read_file_counts(args.xml)
    except (OSError, ET.ParseError) as exc:
        print(f"coverage_summary: cannot read {args.xml}: {exc}", file=sys.stderr)
        return 2

    print(render(files, args.below))

    failures, unknown = check_floors(files, floors)
    if unknown:
        print(
            "coverage_summary: no measured file in package(s): " + ", ".join(unknown),
            file=sys.stderr,
        )
        return 2
    if failures:
        print("", file=sys.stderr)
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
