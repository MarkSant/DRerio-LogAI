"""Developer automation helpers for ZebTrack-AI.

Provides a tiny CLI that chains common lint/test pipelines so routine
quality gates can run with a single command. The script is intentionally
lightweight (pure stdlib) so it works anywhere Poetry can invoke the
project's virtualenv.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


@dataclass
class Step:
    """Represents an executable step in a suite."""

    name: str
    args: Sequence[str]
    tags: tuple[str, ...] = ()


def _build_suite(name: str, include_lint: bool, changed_tests: list[str]) -> list[Step]:
    """Return the ordered steps for a given suite name."""

    suites: dict[str, list[Step]] = {
        "fast": [
            Step(
                "Lint (ruff)",
                [PYTHON, "-m", "ruff", "check", "."],
                tags=("lint",),
            ),
            Step(
                "Pytest quick suite",
                [PYTHON, "-m", "pytest", "-q"],
                tags=("tests",),
            ),
        ],
        "full": [
            Step(
                "Lint (ruff)",
                [PYTHON, "-m", "ruff", "check", "."],
                tags=("lint",),
            ),
            Step(
                "Full pytest suite",
                [PYTHON, "-m", "pytest", "-n0"],
                tags=("tests",),
            ),
        ],
        "gui": [
            Step(
                "GUI pytest suite",
                [PYTHON, "-m", "pytest", "-m", "gui", "-n0"],
                tags=("tests",),
            ),
        ],
        "coverage": [
            Step(
                "Lint (ruff)",
                [PYTHON, "-m", "ruff", "check", "."],
                tags=("lint",),
            ),
            Step(
                "Pytest with coverage",
                [
                    PYTHON,
                    "-m",
                    "pytest",
                    "--cov=zebtrack",
                    "--cov-report=html",
                ],
                tags=("tests",),
            ),
        ],
    }

    steps = suites.get(name)
    if steps is None:
        raise ValueError(f"Unknown suite '{name}'. Available: {', '.join(sorted(suites))}")

    materialized: list[Step] = []
    for step in steps:
        if not include_lint and "lint" in step.tags:
            continue
        materialized.append(step)

    if changed_tests:
        materialized.append(
            Step(
                "Pytest (changed tests)",
                [PYTHON, "-m", "pytest", *changed_tests],
                tags=("tests",),
            )
        )

    return materialized


def _detect_changed_tests() -> list[str]:
    """Return a sorted list of changed test paths relative to project root."""

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=False,
            text=True,
        )
    except FileNotFoundError:
        return []

    candidates: set[str] = set()
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if path.startswith("tests/") and path.endswith(".py"):
            candidates.add(path)
    return sorted(candidates)


def _run_step(step: Step, dry_run: bool) -> int:
    """Execute a step and return its exit code."""

    printable = " ".join(step.args)
    print(f"\n→ {step.name}\n   $ {printable}")

    if dry_run:
        return 0

    completed = subprocess.run(step.args, cwd=PROJECT_ROOT)
    return completed.returncode


def _parse_args(raw_args: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Developer automation helper")
    parser.add_argument(
        "suite",
        nargs="?",
        default="fast",
        help="Suite to execute (fast, full, gui, coverage)",
    )
    parser.add_argument(
        "--skip-lint",
        action="store_true",
        help="Skip lint steps inside the chosen suite",
    )
    parser.add_argument(
        "--changed-tests",
        action="store_true",
        help="Append pytest run for local changes under tests/",
    )
    parser.add_argument(
        "--tests",
        nargs="*",
        default=[],
        help="Extra pytest targets to append (files, dirs, node ids)",
    )
    parser.add_argument(
        "--pytest-cmd",
        action="append",
        default=[],
        metavar="ARGS",
        help=(
            "Append a raw pytest invocation. Provide the argument string, e.g. `-m gui -n0`. "
            "Can be passed multiple times to queue several commands."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print steps without executing them",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Do not stop when a step fails",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available suites",
    )
    return parser.parse_args(raw_args)


def _list_suites() -> None:
    print("Available suites:")
    for suite in ["fast", "full", "gui", "coverage"]:
        print(f"  - {suite}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    if args.list:
        _list_suites()
        return 0

    changed = _detect_changed_tests() if args.changed_tests else []
    steps = _build_suite(args.suite, include_lint=not args.skip_lint, changed_tests=changed)

    if args.tests:
        steps.append(
            Step(
                "Pytest (explicit targets)",
                [PYTHON, "-m", "pytest", *args.tests],
                tags=("tests",),
            )
        )

    for raw_cmd in args.pytest_cmd:
        extra_args = shlex.split(raw_cmd)
        if not extra_args:
            continue
        steps.append(
            Step(
                f"Pytest (custom: {raw_cmd})",
                [PYTHON, "-m", "pytest", *extra_args],
                tags=("tests",),
            )
        )

    failures: list[str] = []
    for step in steps:
        code = _run_step(step, args.dry_run)
        if code != 0:
            failures.append(f"{step.name} (exit {code})")
            if not args.keep_going:
                break

    if failures:
        print("\nAutomation finished with failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nAutomation finished successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
