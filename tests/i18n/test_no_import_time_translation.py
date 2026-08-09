"""No module or class body may evaluate a translation.

``_()`` resolves the catalogue when it is called. A call at module or class
scope runs at *import* time -- possibly before ``i18n.install()`` has chosen a
language -- and freezes whatever was active then into a constant. The result is
a single label stuck in the wrong language, with nothing in the logs to explain
it, and it only reproduces when import order happens to change.

The fix is to move the call into the function that uses the value, or to use
``i18n.lazy()`` when a constant genuinely has to hold a translation.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "src" / "zebtrack"

# lazy() is the sanctioned escape hatch: it defers resolution to first read, so
# evaluating it at import time is exactly what it is for.
EAGER_TRANSLATION_FUNCTIONS = frozenset({"_", "gettext", "ngettext", "translate"})


def _called_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _find_eager_calls(tree: ast.Module) -> list[tuple[int, str]]:
    """Return (line, name) for translation calls in module or class scope."""
    offenders: list[tuple[int, str]] = []

    def walk(node: ast.AST, *, in_deferred_scope: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
                # Anything inside a function body runs when called, not on import.
                # Default arguments and decorators do run at import, so those are
                # walked in the enclosing scope.
                for default in getattr(child.args, "defaults", []) or []:
                    walk_expr(default, in_deferred_scope=in_deferred_scope)
                for decorator in getattr(child, "decorator_list", []) or []:
                    walk_expr(decorator, in_deferred_scope=in_deferred_scope)
                walk(child, in_deferred_scope=True)
                continue

            if isinstance(child, ast.ClassDef):
                # A class body executes at import time, like module scope.
                walk(child, in_deferred_scope=False)
                continue

            if not in_deferred_scope:
                walk_expr(child, in_deferred_scope=in_deferred_scope)

            walk(child, in_deferred_scope=in_deferred_scope)

    def walk_expr(node: ast.AST, *, in_deferred_scope: bool) -> None:
        if in_deferred_scope:
            return
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                name = _called_name(sub.func)
                if name in EAGER_TRANSLATION_FUNCTIONS:
                    offenders.append((sub.lineno, name))

    walk(tree, in_deferred_scope=False)
    # ast.walk inside walk_expr can revisit nodes; collapse duplicates.
    return sorted(set(offenders))


def _python_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def test_package_has_python_files() -> None:
    """Guard against the scan silently covering nothing."""
    assert len(_python_files()) > 100


def test_no_translation_is_evaluated_at_import_time() -> None:
    offenders: list[str] = []

    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for line, name in _find_eager_calls(tree):
            offenders.append(f"  {path.relative_to(REPO_ROOT).as_posix()}:{line}: {name}(...)")

    if offenders:
        listing = "\n".join(offenders)
        pytest.fail(
            "Translation evaluated at import time (module or class body):\n"
            f"{listing}\n\n"
            "The language may not be installed yet, so the value would freeze in "
            "whatever language happened to be active. Move the call into the "
            "function that uses it — turning the constant into a small accessor "
            "function is the usual fix — or use zebtrack.i18n.lazy()."
        )
