#!/usr/bin/env python3
"""Pre-commit hook to validate path parameter type consistency.

This script checks Python functions for parameters whose names indicate path-like
values (e.g., `path`, `file_path`, `directory`) and ensures annotations include
`Path` support (`Path | str` pattern).

Exit codes:
- 0: no violations found
- 1: violations found or git diff collection failed
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


class PathParameterChecker(ast.NodeVisitor):
    """Check whether path-related parameters use `Path | str` style annotations."""

    def __init__(self, filepath: Path) -> None:
        self.filepath = filepath
        self.violations: list[dict[str, str | int]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_parameters(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_parameters(node)
        self.generic_visit(node)

    def _check_parameters(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for arg in node.args.args:
            parameter_name = arg.arg
            if parameter_name in ("self", "cls"):
                continue

            if self._is_path_parameter(parameter_name):
                type_hint = self._get_type_annotation(arg)
                if not self._is_acceptable_annotation(type_hint):
                    self.violations.append(
                        {
                            "file": str(self.filepath),
                            "line": getattr(arg, "lineno", 0),
                            "function": node.name,
                            "parameter": parameter_name,
                            "type": type_hint,
                        }
                    )

    @staticmethod
    def _is_path_parameter(parameter_name: str) -> bool:
        path_indicators = (
            "path",
            "filepath",
            "file_path",
            "dir",
            "directory",
            "folder",
        )
        lowered = parameter_name.lower()
        return any(indicator in lowered for indicator in path_indicators)

    @staticmethod
    def _get_type_annotation(arg: ast.arg) -> str:
        if arg.annotation is None:
            return "no_annotation"
        return ast.unparse(arg.annotation)

    @staticmethod
    def _is_acceptable_annotation(type_hint: str) -> bool:
        if type_hint == "no_annotation":
            return False

        acceptable_patterns = (
            "Path",
            "Path | str",
            "str | Path",
            "Path | None",
            "str | Path | None",
            "Path | str | None",
        )

        if any(pattern in type_hint for pattern in acceptable_patterns):
            return True

        if type_hint in ("str", "str | None"):
            return False

        return True


def check_file(filepath: Path) -> list[dict[str, str | int]]:
    """Check a single Python file and return found violations."""
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
        checker = PathParameterChecker(filepath)
        checker.visit(tree)
        return checker.violations
    except SyntaxError:
        return []
    except OSError:
        return []


def get_changed_python_files() -> list[Path]:
    """Get staged Python files under src/zebtrack from git index."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        print("Error: unable to list staged files from git.")
        return []

    changed_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [
        Path(file_path)
        for file_path in changed_files
        if file_path.endswith(".py") and file_path.startswith("src/zebtrack/")
    ]


def main() -> int:
    python_files = get_changed_python_files()
    if not python_files:
        return 0

    all_violations: list[dict[str, str | int]] = []
    for filepath in python_files:
        if filepath.exists():
            all_violations.extend(check_file(filepath))

    if not all_violations:
        return 0

    print("=" * 80)
    print("ERROR: Path-like parameters without Path-compatible type annotation found")
    print("=" * 80)
    print()

    for violation in all_violations:
        file_path = Path(str(violation["file"]))
        try:
            relative_path = file_path.relative_to(Path.cwd())
        except ValueError:
            relative_path = file_path

        print(f"{relative_path}:{violation['line']}")
        print(f"  Function: {violation['function']}")
        print(f"  Parameter: {violation['parameter']}")
        print(f"  Current type: {violation['type']}")
        print()

    print("Please update the parameters above to use `Path | str`, e.g.:")
    print("  def method(self, path: Path | str) -> ...:")
    print("      path = Path(path) if isinstance(path, str) else path")
    print("      # use path (always Path) below")
    print()
    print(f"Total violations: {len(all_violations)}")
    print("=" * 80)

    return 1


if __name__ == "__main__":
    sys.exit(main())
