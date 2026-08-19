#!/usr/bin/env python3
"""Prove the test suite can fail: break the code on purpose and check it notices.

Coverage says a line RAN. It never says an assertion would have caught the line
being wrong. An audit of PRs #482-#509 found four test files whose 30 tests
executed ``weight_manager`` end to end and killed 0 of 5 deliberate defects --
100 % of the lines, 0 % of the behaviour.

This runner applies the curated defects in ``scripts/mutation_catalog.yaml`` one
at a time and reports which ones the suite fails to notice. A SURVIVOR is a hole
in the tests, not a bug in the code.

Usage::

    python scripts/mutation_check.py --all
    python scripts/mutation_check.py --module mask_capture
    python scripts/mutation_check.py --list
    python scripts/mutation_check.py --all --json report.json

Exit codes: 0 = every mutation killed, 1 = at least one survivor, 2 = the run
could not be trusted (dirty baseline, ambiguous patch, missing file).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "scripts" / "mutation_catalog.yaml"

# pytest prints "3 failed, 12 passed in 4.20s". Coverage totals and rerun lines
# also contain numbers, so anchor on the words pytest uses for outcomes.
_OUTCOME_RE = re.compile(r"(\d+) (passed|failed|error|errors)")


@dataclass
class MutationResult:
    module: str
    mutation_id: str
    description: str
    killed: bool
    failures: int
    note: str = ""


@dataclass
class ModuleReport:
    name: str
    results: list[MutationResult] = field(default_factory=list)
    skipped_reason: str = ""

    @property
    def survivors(self) -> list[MutationResult]:
        return [r for r in self.results if not r.killed]


def _run_pytest(test_paths: list[str]) -> tuple[int, int, str]:
    """Run pytest on ``test_paths``; return (failures, passes, raw output).

    ``--no-cov`` is not optional. The coverage gate used to live in the
    ``addopts`` of pytest.ini, which made pytest exit non-zero on EVERY partial
    run -- so an exit-code-based runner reported all mutations killed and the
    whole check was worthless. That is why this parses outcome counts instead of
    trusting the exit status, even now that the gate has moved to CI.
    """
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", *test_paths, "-q", "--no-cov", "-p", "no:randomly"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    failures = 0
    passes = 0
    for count, word in _OUTCOME_RE.findall(output):
        if word == "passed":
            passes = int(count)
        else:
            failures += int(count)
    return failures, passes, output


def _apply(source: Path, find: str, replace: str) -> bytes:
    """Patch ``source`` in place and return the ORIGINAL bytes for restoration.

    Byte I/O, not text I/O, and deliberately so. ``read_text``/``write_text``
    translate newlines: on Windows every restored file came back with CRLF where
    the repository stores LF, so a run that changed nothing still left four
    source files dirty in git. Round-tripping bytes keeps the file identical.

    Refuses an ambiguous patch: if ``find`` matches more than once, which
    occurrence got mutated would depend on file layout, and the result would not
    be reproducible across refactors.
    """
    original = source.read_bytes()
    # Match against the same newline convention the file actually uses.
    needle = find.encode("utf-8")
    if b"\r\n" in original:
        needle = needle.replace(b"\n", b"\r\n")
    occurrences = original.count(needle)
    if occurrences != 1:
        raise ValueError(
            f"pattern must appear exactly once in {source.name}, found {occurrences}:\n  {find!r}"
        )
    substitute = replace.encode("utf-8")
    if b"\r\n" in original:
        substitute = substitute.replace(b"\n", b"\r\n")
    source.write_bytes(original.replace(needle, substitute, 1))
    return original


def _check_module(name: str, spec: dict[str, Any], *, verbose: bool) -> ModuleReport:
    report = ModuleReport(name=name)

    source = REPO_ROOT / spec["source"]
    if not source.exists():
        report.skipped_reason = f"source not found: {spec['source']}"
        return report

    mutations = spec.get("mutations") or []
    if not mutations:
        report.skipped_reason = "no mutations defined yet"
        return report

    test_paths = [str(REPO_ROOT / t) for t in spec["tests"] if (REPO_ROOT / t).exists()]
    if not test_paths:
        report.skipped_reason = "none of the listed test files exist"
        return report

    print(f"\n=== {name}  ({len(mutations)} mutations, {len(test_paths)} test files)")

    baseline_failures, baseline_passes, baseline_output = _run_pytest(test_paths)
    if baseline_failures:
        report.skipped_reason = (
            f"baseline is not green ({baseline_failures} failing) -- "
            "fix the suite before trusting mutation results"
        )
        if verbose:
            print(baseline_output)
        print(f"  SKIPPED: {report.skipped_reason}")
        return report
    print(f"  baseline: {baseline_passes} passed")

    for mutation in mutations:
        original: bytes | None = None
        try:
            original = _apply(source, mutation["find"], mutation["replace"])
            failures, _passes, output = _run_pytest(test_paths)
            killed = failures > 0
            result = MutationResult(
                module=name,
                mutation_id=mutation["id"],
                description=mutation["description"],
                killed=killed,
                failures=failures,
            )
            if verbose and not killed:
                print(output)
        except ValueError as exc:
            result = MutationResult(
                module=name,
                mutation_id=mutation.get("id", "?"),
                description=mutation.get("description", ""),
                killed=False,
                failures=0,
                note=str(exc),
            )
        finally:
            # Restore unconditionally. An interrupted run that leaves the tree
            # mutated is far worse than a failed check.
            if original is not None:
                source.write_bytes(original)

        report.results.append(result)
        mark = "KILLED  " if result.killed else "SURVIVED"
        detail = f" ({result.failures} failing)" if result.killed else ""
        print(f"  {mark} {result.mutation_id}{detail} -- {result.description}")
        if result.note:
            print(f"           ! {result.note}")

    return report


def _verify_tree_restored(specs: dict[str, Any]) -> list[str]:
    """Return sources git still reports as modified, so a leak cannot go unseen."""
    sources = [spec["source"] for spec in specs.values()]
    completed = subprocess.run(
        ["git", "status", "--porcelain", "--", *sources],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return [line[3:].strip() for line in completed.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--all", action="store_true", help="run every module in the catalogue")
    parser.add_argument("--module", action="append", default=[], help="run one module (repeatable)")
    parser.add_argument("--list", action="store_true", help="list the catalogue and exit")
    parser.add_argument("--json", type=Path, help="write a machine-readable report here")
    parser.add_argument("--verbose", action="store_true", help="print pytest output for survivors")
    args = parser.parse_args()

    catalog = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    specs: dict[str, Any] = catalog["modules"]

    if args.list:
        for name, spec in specs.items():
            mutations = spec.get("mutations") or []
            print(f"{name:32s} {len(mutations):2d} mutations  {spec['source']}")
            for mutation in mutations:
                print(f"    - {mutation['id']}: {mutation['description']}")
        return 0

    if args.module:
        unknown = [m for m in args.module if m not in specs]
        if unknown:
            print(f"unknown module(s): {', '.join(unknown)}", file=sys.stderr)
            return 2
        selected = {m: specs[m] for m in args.module}
    elif args.all:
        selected = specs
    else:
        parser.print_help()
        return 2

    reports = [_check_module(name, spec, verbose=args.verbose) for name, spec in selected.items()]

    total = sum(len(r.results) for r in reports)
    killed = sum(1 for r in reports for result in r.results if result.killed)
    survivors = [result for r in reports for result in r.survivors]

    print("\n" + "=" * 72)
    score = f"{killed}/{total}" if total else "0/0"
    percent = f" ({killed / total * 100:.0f}%)" if total else ""
    print(f"MUTATION SCORE: {score}{percent}")

    for report in reports:
        if report.skipped_reason:
            print(f"  skipped {report.name}: {report.skipped_reason}")

    if survivors:
        print(f"\n{len(survivors)} SURVIVOR(S) -- these defects ship undetected:")
        for result in survivors:
            print(f"  {result.module}::{result.mutation_id} -- {result.description}")
            if result.note:
                print(f"      {result.note}")
        print("\nEach survivor is a missing test. Add the test; do not delete the mutation.")

    leaked = _verify_tree_restored(selected)
    if leaked:
        print(f"\n!! source files left modified: {', '.join(leaked)}", file=sys.stderr)
        print("!! restore them with: git checkout --", *leaked, file=sys.stderr)
        return 2

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "score": {"killed": killed, "total": total},
                    "results": [
                        {
                            "module": result.module,
                            "mutation": result.mutation_id,
                            "description": result.description,
                            "killed": result.killed,
                            "note": result.note,
                        }
                        for report in reports
                        for result in report.results
                    ],
                    "skipped": {r.name: r.skipped_reason for r in reports if r.skipped_reason},
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    return 1 if survivors else 0


if __name__ == "__main__":
    raise SystemExit(main())
