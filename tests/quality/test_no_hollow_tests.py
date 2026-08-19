"""A test that passes without exercising production code is worse than no test.

It costs a line in the coverage report, so the number goes up and the ratchet in
CI accepts it -- but it cannot fail when the code it names breaks. A suite full
of them reads as covered and behaves as untested.

Three shapes are rejected here, each one found in the tree by an audit of the
coverage mega-batches (PRs #482-#509):

``tautology``
    The test builds an instance with ``object.__new__`` (skipping ``__init__``),
    assigns attributes onto it, and asserts those same attributes back. It is a
    round trip through ``setattr``; the class under test never runs.

``hollow-stub``
    Same ``object.__new__`` instance, but no method is ever called on it. Only
    attribute reads. Nothing in the class body executes.

``duplicate-body``
    The same statements appear as a test in two different files. The copy adds
    no reachable line and doubles the edit cost of every future change.

``object.__new__`` itself is legitimate -- Tk widgets often cannot be built in a
headless run -- which is why the first two rules only fire when *no* method of
the stub is ever called. Mutation testing is what proves the rest:
``scripts/mutation_check.py``.

Legacy offenders are listed in ``hollow_tests_allowlist.txt``. That file is meant
to shrink to nothing; entries that no longer match a real test fail this module,
so it cannot rot into a list of names nobody reads.
"""

from __future__ import annotations

import ast
import hashlib
from collections import defaultdict
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = REPO_ROOT / "tests"
ALLOWLIST_PATH = Path(__file__).with_name("hollow_tests_allowlist.txt")

# A one- or two-statement body is too small to be a meaningful duplicate: two
# tests asserting the same single constant are a coincidence, not a copy.
MIN_STATEMENTS_FOR_DUPLICATE = 3


def _load_allowlist() -> set[str]:
    """Return the allowlisted ``path::test_name`` entries.

    Matching is EXACT. The i18n allowlist matches by substring and that has
    already hidden real violations here once -- a short entry silently covered
    every longer name that contained it.
    """
    if not ALLOWLIST_PATH.exists():
        return set()
    entries: set[str] = set()
    for raw in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            entries.add(line)
    return entries


def _test_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
    ]


def _assign_targets(node: ast.AST) -> list[ast.expr]:
    """Targets of an assignment, annotated or not.

    ``step: Any = object.__new__(Cls)`` parses as ``AnnAssign``, not ``Assign``.
    Handling only the latter made this guard blind to 50 of the very tests it
    exists to catch -- every stub in the suite is written with the annotation.
    """
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, ast.AnnAssign):
        return [node.target]
    return []


def _stub_variables(fn: ast.AST) -> set[str]:
    """Names bound to an ``object.__new__(...)`` result inside ``fn``."""
    names: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign | ast.AnnAssign):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "__new__"
            and isinstance(func.value, ast.Name)
            and func.value.id == "object"
        ):
            names.update(t.id for t in _assign_targets(node) if isinstance(t, ast.Name))
    return names


def _calls_method_on(fn: ast.AST, variables: set[str]) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in variables
        for node in ast.walk(fn)
    )


def _attributes_assigned_on(fn: ast.AST, variables: set[str]) -> set[str]:
    return {
        target.attr
        for node in ast.walk(fn)
        if isinstance(node, ast.Assign | ast.AnnAssign)
        for target in _assign_targets(node)
        if isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id in variables
    }


def _attributes_asserted_on(fn: ast.AST, variables: set[str]) -> set[str]:
    return {
        inner.attr
        for node in ast.walk(fn)
        if isinstance(node, ast.Assert)
        for inner in ast.walk(node)
        if isinstance(inner, ast.Attribute)
        and isinstance(inner.value, ast.Name)
        and inner.value.id in variables
    }


def _classify_stub_test(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Return the violation kind for a stub-based test, or None if it is fine."""
    variables = _stub_variables(fn)
    if not variables or _calls_method_on(fn, variables):
        return None

    asserted = _attributes_asserted_on(fn, variables)
    if asserted and asserted <= _attributes_assigned_on(fn, variables):
        return "tautology"
    return "hollow-stub"


def _significant_body(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    """The body without its docstring."""
    return [
        stmt
        for stmt in fn.body
        if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
    ]


def _body_fingerprint(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    body = _significant_body(fn)
    if len(body) < MIN_STATEMENTS_FOR_DUPLICATE:
        return None
    source = "\n".join(ast.unparse(stmt) for stmt in body)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _test_files() -> list[Path]:
    return sorted(TESTS_ROOT.rglob("test_*.py"))


def _scan() -> tuple[dict[str, str], list[list[str]]]:
    """Return (violations by ``path::name``, duplicate groups)."""
    violations: dict[str, str] = {}
    fingerprints: dict[str, list[str]] = defaultdict(list)

    for path in _test_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:  # pragma: no cover - a broken test file fails elsewhere
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        for fn in _test_functions(tree):
            node_id = f"{relative}::{fn.name}"
            kind = _classify_stub_test(fn)
            if kind is not None:
                violations[node_id] = kind
            fingerprint = _body_fingerprint(fn)
            if fingerprint is not None:
                fingerprints[fingerprint].append(node_id)

    duplicate_groups = [
        sorted(group)
        for group in fingerprints.values()
        # Two tests in the SAME file may legitimately share a body via
        # parametrisation left un-parametrised; only cross-file copies count.
        if len({node_id.rsplit("::", 1)[0] for node_id in group}) > 1
    ]
    return violations, duplicate_groups


def test_scan_actually_covers_the_suite() -> None:
    """Guard against the scan silently covering nothing."""
    assert len(_test_files()) > 100


def test_allowlist_has_no_stale_entries() -> None:
    """Every allowlisted node must still be a real violation.

    An entry that no longer matches means the test was fixed, renamed, or
    deleted. Leaving it behind turns the allowlist into a file nobody trusts.
    """
    allowlist = _load_allowlist()
    if not allowlist:
        return

    violations, duplicate_groups = _scan()
    known = set(violations)
    for group in duplicate_groups:
        known.update(group)

    stale = sorted(allowlist - known)
    if stale:
        listing = "\n".join(f"  {entry}" for entry in stale)
        pytest.fail(
            f"{len(stale)} allowlist entries no longer match a violation:\n{listing}\n\n"
            f"Delete them from {ALLOWLIST_PATH.name}."
        )


def test_no_tests_pass_without_exercising_production_code() -> None:
    violations, _ = _scan()
    allowlist = _load_allowlist()

    offenders = sorted(
        (node_id, kind) for node_id, kind in violations.items() if node_id not in allowlist
    )
    if offenders:
        listing = "\n".join(f"  [{kind}] {node_id}" for node_id, kind in offenders)
        pytest.fail(
            f"{len(offenders)} test(s) assert nothing about production code:\n{listing}\n\n"
            "A 'tautology' asserts back the attributes the test itself just set; a "
            "'hollow-stub' never calls a method on the object.__new__ instance it "
            "built. Either drive a real method on the object, or delete the test -- "
            "it cannot fail when the code it names breaks."
        )


def test_no_test_body_is_duplicated_across_files() -> None:
    _, duplicate_groups = _scan()
    allowlist = _load_allowlist()

    offenders = [
        group for group in duplicate_groups if not all(node_id in allowlist for node_id in group)
    ]
    if offenders:
        listing = "\n".join(
            "  " + "\n  = ".join(group) for group in sorted(offenders, key=lambda g: g[0])
        )
        pytest.fail(
            f"{len(offenders)} test bodies are byte-identical across files:\n{listing}\n\n"
            "Keep one copy. A duplicate adds no reachable line and doubles the "
            "cost of every future change to the code it covers."
        )
