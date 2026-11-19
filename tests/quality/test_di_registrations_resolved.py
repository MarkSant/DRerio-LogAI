"""Every container registration in ``di_registrations.py`` is resolved somewhere (A3, TASK-087).

The A3 audit found twelve registrations nobody resolved: eleven
``container.register(X, instance=...)`` lines and a ``ProjectService`` factory.
The same objects were wired into the coordinators by hand, so the container
held a second copy that only LOOKED authoritative. Three ``ProjectService``
instances lived side by side, and a reader editing the registration believed
they were changing what the app used. The campaign deleted them (A3-02); this
test keeps a new one from appearing.

A registration counts as used when its key -- the first argument of
``container.register(...)`` -- is also the first argument of a resolve call
anywhere in ``src/zebtrack``: ``_resolve(container, X)`` (the typed helper in
``di_registrations.py``) or ``<anything>.resolve(X)``. Keys are compared as
source text (``Settings``, ``LazyRef``), which is how both sides spell them.

``ALLOWED_UNRESOLVED`` only ever SHRINKS. The campaign believed it had removed
every decorative registration; this guard found two more on its first run
(2026-11-19). Both are listed with that reason until the maintainer decides
their deletion (register row A3-02). An entry that becomes resolved, or whose
registration disappears, fails as stale. If a registration is genuinely needed
only by a test, register it in the test.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "src" / "zebtrack"
REGISTRATIONS = PACKAGE_ROOT / "core" / "di_registrations.py"

# Shrink-only. Empty since #728: the two decorative registrations found on 2026-11-19
# (``Settings`` and ``RecorderFactory``, never resolved) were deleted.
ALLOWED_UNRESOLVED: dict[str, str] = {}


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def registered_keys(source: str) -> dict[str, int]:
    """``container.register(X, ...)`` keys in ``source``, with their first line."""
    keys: dict[str, int] = {}
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "register"
            and node.args
        ):
            key = ast.unparse(node.args[0])
            keys.setdefault(key, node.lineno)
    return keys


def resolved_keys(sources: Iterable[str]) -> set[str]:
    """Keys passed to ``_resolve(container, X)`` or ``<obj>.resolve(X)``."""
    keys: set[str] = set()
    for source in sources:
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name == "_resolve" and len(node.args) >= 2:
                keys.add(ast.unparse(node.args[1]))
            elif name == "resolve" and isinstance(node.func, ast.Attribute) and node.args:
                keys.add(ast.unparse(node.args[0]))
    return keys


def unresolved(registrations: str, sources: Iterable[str]) -> dict[str, int]:
    used = resolved_keys(sources)
    return {key: line for key, line in registered_keys(registrations).items() if key not in used}


def _package_sources() -> list[str]:
    return [path.read_text(encoding="utf-8") for path in sorted(PACKAGE_ROOT.rglob("*.py"))]


def test_every_registration_is_resolved_somewhere_in_src() -> None:
    registrations = REGISTRATIONS.read_text(encoding="utf-8")
    assert registered_keys(registrations), "found no container.register(...) call at all"
    missing = {
        key: line
        for key, line in unresolved(registrations, _package_sources()).items()
        if key not in ALLOWED_UNRESOLVED
    }
    assert not missing, (
        "registered in the DI container but never resolved in src/zebtrack "
        "(a decorative registration: the object is wired by hand somewhere else, "
        "and the container copy only looks authoritative):\n"
        + "\n".join(
            f"  {key} (di_registrations.py:{line})" for key, line in sorted(missing.items())
        )
    )


def test_allowed_unresolved_has_no_stale_entries() -> None:
    still_unresolved = unresolved(REGISTRATIONS.read_text(encoding="utf-8"), _package_sources())
    stale = sorted(set(ALLOWED_UNRESOLVED) - set(still_unresolved))
    assert not stale, f"no longer an unresolved registration; drop from ALLOWED_UNRESOLVED: {stale}"


# --- the scanner itself -------------------------------------------------------


def test_registered_keys_reads_the_first_argument_of_register() -> None:
    source = (
        "container.register(Settings, instance=s)\n"
        "container.register(\n    WeightManager,\n    factory=lambda: WeightManager(),\n)\n"
        "other.register_handler(Foo)\n"
    )
    assert registered_keys(source) == {"Settings": 1, "WeightManager": 2}


def test_resolved_keys_accepts_both_spellings_of_a_resolve() -> None:
    sources = [
        "x = _resolve(container, ModelService)\n",
        "y = self.container.resolve(ProjectManager)\n",
        "z = resolve(NotAContainerCall)\n",
    ]
    assert resolved_keys(sources) == {"ModelService", "ProjectManager"}


def test_unresolved_names_the_decorative_registration() -> None:
    registrations = (
        "container.register(A, instance=a)\n"
        "container.register(B, factory=lambda: B(_resolve(container, A)))\n"
    )
    assert unresolved(registrations, [registrations]) == {"B": 2}
