"""Every public reporter has a production caller (#662).

``HtmlReporter`` was exported from ``zebtrack.analysis.reporters`` and called
only by its own tests: no app flow ever wrote the ``.html``, so the ``KeyError``
of #639 broke the export on every freezing episode and nobody noticed. A reporter
nobody calls is exactly where such a bug hides, so a name in the package's
``__all__`` must be referenced by code OUTSIDE the package.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import zebtrack
from zebtrack.analysis import reporters

pytestmark = pytest.mark.unit

_SRC = Path(zebtrack.__file__).resolve().parent
_PACKAGE_DIR = Path(reporters.__file__).resolve().parent

# Known orphans, each with its own issue. This list only ever shrinks: wire the
# reporter into a flow or delete it, never add a name here to turn the test green.
_KNOWN_ORPHANS: dict[str, str] = {}


def _names_referenced_outside_package() -> set[str]:
    """Identifiers imported or used by any ``zebtrack`` module outside the package."""
    found: set[str] = set()
    for path in _SRC.rglob("*.py"):
        if _PACKAGE_DIR in path.resolve().parents:
            continue
        tree = ast.parse(path.read_bytes(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                found.add(node.id)
            elif isinstance(node, ast.Attribute):
                found.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                found.update(alias.name for alias in node.names)
    return found


def test_every_public_reporter_has_a_production_caller() -> None:
    referenced = _names_referenced_outside_package()

    orphans = sorted(
        name for name in reporters.__all__ if name not in referenced and name not in _KNOWN_ORPHANS
    )

    assert orphans == [], (
        f"{orphans} are exported by zebtrack.analysis.reporters but no app flow "
        "calls them: wire them into a report flow or remove them (#662)."
    )


def test_known_orphans_are_still_orphans() -> None:
    """An allowlisted name that gained a caller must leave the allowlist."""
    referenced = _names_referenced_outside_package()

    stale = sorted(name for name in _KNOWN_ORPHANS if name in referenced)

    assert stale == [], f"{stale} now have a production caller; drop them from _KNOWN_ORPHANS."


def test_the_scan_sees_real_callers() -> None:
    """Guard the guard: the walker must find a reporter the app really calls."""
    assert "WordReporter" in _names_referenced_outside_package()
