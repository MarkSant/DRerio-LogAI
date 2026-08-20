"""No function may bind ``_`` locally in a module that imports the gettext alias.

``from zebtrack.i18n import _`` binds the translation callable at module scope.
Python decides scope per FUNCTION, not per line: one ``detections, _ = ...``
anywhere in a body makes ``_`` local for the WHOLE function, so every ``_("...")``
in it reads the discarded value instead of the catalogue. The failure surfaces as
``TypeError: 'NoneType' object is not callable`` raised far from the assignment
that caused it, and only once someone translates a string in that same function --
which is why it survives review and passes every unit test of the parts involved.

This is not hypothetical. ``processing_worker._process_single_video`` discarded the
annotated frame into ``_``; the ``_("Processing...")`` progress message ~130 lines
below then crashed *every* pre-recorded analysis. The live modules had already been
hardened against the identical trap, so the two flows drifted apart silently.

The fix is always the same and always local: name the throwaway (``_annotated``,
``_track_id``, ``_warmup_frame``). A leading underscore still tells ruff and the
reader it is unused, without touching the gettext name.

Comprehensions, lambdas and nested functions have their own scope and cannot leak
into the enclosing one, so only each function's own body is inspected.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "src" / "zebtrack"

GETTEXT_IMPORT = "from zebtrack.i18n import"


# Nodes that open a namespace of their own. A binding inside one of these cannot
# shadow ``_`` for the function being inspected, so the walk stops at them; each
# nested function is inspected separately by the ``ast.walk`` in ``_offenders_in``.
NESTED_SCOPE_NODES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


def _bindings_in_own_scope(node: ast.AST) -> list[int]:
    """Return the lines where ``_`` is assigned within this scope only.

    The guard is on entry, not on the children, so a nested scope is skipped
    wherever it appears -- including when it *is* the statement being walked.
    """
    if isinstance(node, NESTED_SCOPE_NODES):
        return []
    lines: list[int] = []
    if isinstance(node, ast.Name) and node.id == "_" and isinstance(node.ctx, ast.Store):
        lines.append(node.lineno)
    for child in ast.iter_child_nodes(node):
        lines.extend(_bindings_in_own_scope(child))
    return lines


def _offenders_in(source: str) -> list[tuple[str, int]]:
    """Return (function name, line) for every local binding of ``_``."""
    offenders: list[tuple[str, int]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for statement in node.body:
            offenders.extend((node.name, line) for line in _bindings_in_own_scope(statement))
    return offenders


def test_no_function_shadows_the_gettext_alias() -> None:
    """Every module importing ``_`` keeps it callable in every function."""
    failures: list[str] = []

    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if GETTEXT_IMPORT not in source:
            continue
        for function_name, line in _offenders_in(source):
            relative = path.relative_to(REPO_ROOT)
            failures.append(f"{relative}:{line} in {function_name}()")

    assert not failures, (
        "These functions bind `_` locally in a module that imports the gettext "
        "alias, which makes `_` local for the whole function and turns any "
        '`_("...")` in it into a call on the discarded value:\n  '
        + "\n  ".join(failures)
        + "\n\nName the throwaway instead: `_annotated`, `_track_id`, `_warmup_frame`."
    )
