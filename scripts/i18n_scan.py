"""Find user-facing Portuguese string literals that still need extracting.

Read-only. Produces the worklist for a migration batch, and backs the guard test
``tests/i18n/test_no_untranslated_literals.py`` -- both use the same code so the
tool and the gate can never disagree about what counts as a violation.

Usage::

    python scripts/i18n_scan.py src/zebtrack/ui/components
    python scripts/i18n_scan.py src/zebtrack --format=count

Output is ``path:line:col<TAB>text``, one finding per line.

What counts as a finding: a string literal containing Portuguese-specific
characters that is (a) not a docstring, (b) not already an argument of
``_()``/``gettext()``/``lazy()``/``ngettext()``, (c) not matched by
``scripts/i18n_allowlist.txt``, and (d) not a structlog event name or a logging
keyword argument -- log text is for developers and stays English/untranslated.

The heuristic is accent-based, so it finds "Não foi possível" but not a
Portuguese sentence that happens to use no accents ("Salvar projeto"). It is a
floor, not a ceiling: it catches the bulk mechanically and never blocks on the
remainder.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_PATH = Path(__file__).resolve().parent / "i18n_allowlist.txt"

# Characters that only appear in Portuguese (not English) text.
PORTUGUESE_CHARS = frozenset("áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ")

# Callables whose string arguments are already translated.
TRANSLATION_FUNCTIONS = frozenset({"_", "gettext", "ngettext", "lazy", "translate"})

# Callables whose string arguments are developer-facing, never user-facing.
LOGGING_FUNCTIONS = frozenset({"debug", "info", "warning", "error", "critical", "exception"})

# A file containing this marker is skipped entirely. Reserved for modules whose
# Portuguese is deliberate and permanent -- currently only the first-launch
# language chooser, which must be readable before a language has been chosen.
FILE_EXEMPT_MARKER = "i18n: file-exempt"


@dataclass(frozen=True)
class Finding:
    """One untranslated Portuguese literal."""

    path: Path
    line: int
    col: int
    text: str

    def format(self, *, relative_to: Path | None = None) -> str:
        path = self.path
        if relative_to is not None:
            try:
                path = self.path.relative_to(relative_to)
            except ValueError:
                pass
        return f"{path.as_posix()}:{self.line}:{self.col}\t{self.text}"


def load_allowlist(path: Path = ALLOWLIST_PATH) -> tuple[str, ...]:
    """Read the never-translate patterns, ignoring comments and blank lines."""
    if not path.exists():
        return ()
    lines = path.read_text(encoding="utf-8").splitlines()
    return tuple(
        stripped for line in lines if (stripped := line.strip()) and not stripped.startswith("#")
    )


def is_portuguese(text: str) -> bool:
    """True when *text* carries a Portuguese-specific character."""
    return any(char in PORTUGUESE_CHARS for char in text)


def is_allowlisted(text: str, allowlist: tuple[str, ...]) -> bool:
    """True when *text* contains any never-translate token."""
    return any(pattern in text for pattern in allowlist)


class _LiteralVisitor(ast.NodeVisitor):
    """Collect Portuguese literals, skipping the contexts that are exempt."""

    def __init__(self, path: Path, allowlist: tuple[str, ...]) -> None:
        self.path = path
        self.allowlist = allowlist
        self.findings: list[Finding] = []
        self._exempt: set[int] = set()

    # -- exemption bookkeeping ------------------------------------------------
    def _exempt_node(self, node: ast.AST) -> None:
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                self._exempt.add(id(child))

    def _exempt_docstring(self, node: ast.Module | ast.ClassDef | ast.FunctionDef) -> None:
        body = getattr(node, "body", None)
        if not body:
            return
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                self._exempt.add(id(first.value))

    def visit_Expr(self, node: ast.Expr) -> None:
        """Exempt every bare string statement, not just the leading docstring.

        A string that is an expression-statement is evaluated and thrown away —
        it can never reach a widget. The only reason to write one is
        documentation: PEP 258 attribute docstrings (the paragraph under an enum
        member or a class attribute) are exactly this shape, and the project
        deliberately keeps its Portuguese prose. Exempting only ``body[0]``
        reported those as untranslated interface strings.
        """
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            self._exempt.add(id(node.value))
        self.generic_visit(node)

    # -- visitors -------------------------------------------------------------
    def visit_Module(self, node: ast.Module) -> None:
        self._exempt_docstring(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._exempt_docstring(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._exempt_docstring(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._exempt_docstring(node)  # type: ignore[arg-type]
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _called_name(node.func)

        if name in TRANSLATION_FUNCTIONS:
            # Already translated: the msgid may legitimately be anything.
            for arg in node.args:
                self._exempt_node(arg)
        elif name in LOGGING_FUNCTIONS:
            # Structlog: event name plus kwargs, all developer-facing.
            self._exempt_node(node)

        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if not isinstance(node.value, str) or id(node) in self._exempt:
            return
        if not is_portuguese(node.value):
            return
        if is_allowlisted(node.value, self.allowlist):
            return
        self.findings.append(
            Finding(
                path=self.path,
                line=node.lineno,
                col=node.col_offset,
                text=node.value.replace("\n", "\\n"),
            )
        )


def _called_name(func: ast.expr) -> str | None:
    """Return the bare callable name for ``f(...)`` and ``obj.f(...)``."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def scan_file(path: Path, allowlist: tuple[str, ...]) -> list[Finding]:
    """Scan one Python file."""
    source = path.read_text(encoding="utf-8")
    if FILE_EXEMPT_MARKER in source:
        return []

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        print(f"{path}: skipped, syntax error: {exc}", file=sys.stderr)
        return []

    visitor = _LiteralVisitor(path, allowlist)
    visitor.visit(tree)
    return visitor.findings


def scan_paths(paths: list[Path], allowlist: tuple[str, ...] | None = None) -> list[Finding]:
    """Scan files and directories, recursing into directories."""
    if allowlist is None:
        allowlist = load_allowlist()

    findings: list[Finding] = []
    for target in paths:
        if target.is_file() and target.suffix == ".py":
            findings.extend(scan_file(target, allowlist))
        elif target.is_dir():
            for python_file in sorted(target.rglob("*.py")):
                findings.extend(scan_file(python_file, allowlist))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("paths", nargs="+", type=Path, help="Files or directories to scan")
    parser.add_argument(
        "--format",
        choices=("list", "count"),
        default="list",
        help="'list' prints every finding; 'count' prints a per-file tally.",
    )
    args = parser.parse_args()

    findings = scan_paths(args.paths)

    if args.format == "count":
        tally: dict[Path, int] = {}
        for finding in findings:
            tally[finding.path] = tally.get(finding.path, 0) + 1
        for path, count in sorted(tally.items(), key=lambda item: (-item[1], str(item[0]))):
            try:
                shown = path.relative_to(REPO_ROOT)
            except ValueError:
                shown = path
            print(f"{count:5d}  {shown.as_posix()}")
        print(f"\nTOTAL: {len(findings)} literals in {len(tally)} files")
    else:
        for finding in findings:
            print(finding.format(relative_to=REPO_ROOT))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
