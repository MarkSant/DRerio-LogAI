"""No new writes into the shared ``Settings`` object without a decision.

The defect this guards
----------------------
``Settings`` is one object for the life of the app, shared by all four video
flows. The ad-hoc dialogs write the user's per-run choices into it and never
restore them, so a flow that runs LATER in the same session inherits the earlier
flow's numbers. PR #524 measured it on a real project: running a single video
and then analysing a project changed **7 of 9 analysis parameters** — freezing
time, sharp turns, distance and speed — silently.

That was closed on the READER side (``build_project_settings_snapshot`` answers
from a pristine baseline). The WRITER side was never closed, and it cannot be
closed by a rule: some of these assignments are legitimate, because a dialog
updating the shared object is how the other UI tabs stay consistent during a
session.

So this is a tripwire, not a prohibition. It fails when a NEW assignment
appears, which forces the question to be answered in the PR that creates the
exposure instead of weeks later, in an analysis, by a researcher wondering why
two runs of the same video disagree.

Why an AST scan and not a runtime check
---------------------------------------
The write happens on a Pydantic sub-model, in a Tk callback, on a code path that
needs a camera and a display. A runtime assertion would have to reach all of
that. The assignment itself is visible in the source, and that is the property
worth pinning.

Companion tests: ``tests/integration/test_flow_isolation.py`` checks what the
writes DO; this file notices that a write has appeared at all.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "zebtrack"
ALLOWLIST_PATH = Path(__file__).parent / "shared_settings_allowlist.txt"

#: The attribute names that hold an injected ``Settings``. ``self.settings`` is
#: the convention across the codebase; ``self.settings_obj`` appears where the
#: constructor parameter name was kept.
SETTINGS_ATTRS = frozenset({"settings", "settings_obj"})

#: The dialogs whose writes are the actual historical cause. Pinned separately
#: so the allowlist cannot quietly lose the entries that matter most — a
#: truncated file would otherwise look like an improvement.
KNOWN_POLLUTERS = (
    "src/zebtrack/ui/dialogs/live_analysis_dialog.py",
    "src/zebtrack/ui/dialogs/single_video_config_dialog.py",
)


def _attribute_chain(node: ast.expr) -> list[str]:
    """Flatten ``self.a.b.c`` into ``["self", "a", "b", "c"]``.

    Returns a chain that does not start with ``self`` when the base is not a
    plain name (a subscript or a call); callers discard those.
    """
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return list(reversed(parts))


def _assignment_targets(node: ast.AST) -> list[ast.expr]:
    """Targets of any assignment form that can write a value.

    ``ast.AnnAssign`` is included deliberately. An annotated assignment is a
    different node type, and a scan that walks only ``Assign``/``AugAssign``
    goes blind the moment someone writes ``self.settings.x.y: int = 3`` — a
    blind spot that has already bitten the AST guards in this directory.
    """
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, ast.AugAssign):
        return [node.target]
    if isinstance(node, ast.AnnAssign) and node.value is not None:
        return [node.target]
    return []


def collect_shared_settings_writes() -> set[str]:
    """Every ``self.settings.<group>.<field> = ...`` in production code.

    Returns:
        Entries shaped ``"<posix path>::<group>.<field>"``.
    """
    found: set[str] = set()
    for path in sorted(SRC_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        relative = path.relative_to(REPO_ROOT).as_posix()

        for node in ast.walk(tree):
            for target in _assignment_targets(node):
                if not isinstance(target, ast.Attribute):
                    continue
                chain = _attribute_chain(target)
                # self . <settings attr> . <group> . <field>  -> at least 4
                if len(chain) < 4 or chain[0] != "self":
                    continue
                if chain[1] not in SETTINGS_ATTRS:
                    continue
                found.add(f"{relative}::{'.'.join(chain[2:])}")
    return found


def read_allowlist() -> set[str]:
    """Allowlist entries, ignoring comments and blank lines."""
    entries: set[str] = set()
    for line in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            entries.add(stripped)
    return entries


def test_no_unlisted_shared_settings_mutation() -> None:
    """A new write into the shared settings must be a conscious decision."""
    unexpected = sorted(collect_shared_settings_writes() - read_allowlist())

    assert not unexpected, (
        "New assignment(s) into the SHARED Settings object:\n\n  "
        + "\n  ".join(unexpected)
        + "\n\nThis object outlives the flow that writes it. Whatever you just "
        "set stays set for every later flow in the same app session, which is "
        "how PR #524 changed 7 of 9 analysis parameters on a real project.\n\n"
        "Decide which of these applies, then act:\n"
        "  (a) The readers of this field go through "
        "build_project_settings_snapshot(), or genuinely want the live value.\n"
        "      -> add the line to tests/quality/shared_settings_allowlist.txt.\n"
        "  (b) They do not.\n"
        "      -> route the reader through the snapshot builder, or restore the "
        "field when the flow ends, before adding anything to the allowlist.\n\n"
        "tests/integration/test_flow_isolation.py shows how to prove which it is."
    )


def test_allowlist_has_no_stale_entries() -> None:
    """The allowlist shrinks when code improves; it must not rot.

    Without this, a line survives its assignment forever and the file slowly
    stops describing the codebase — the failure mode
    ``tests/quality/hollow_tests_allowlist.txt`` is also guarded against.
    """
    stale = sorted(read_allowlist() - collect_shared_settings_writes())

    assert not stale, (
        "Allowlist entries with no matching assignment any more:\n\n  "
        + "\n  ".join(stale)
        + "\n\nThe write is gone — delete these lines from "
        "tests/quality/shared_settings_allowlist.txt."
    )


def test_known_polluters_are_still_covered() -> None:
    """The two ad-hoc dialogs must still be represented.

    They are the historical cause. If the allowlist ever lost their entries,
    every other test here would keep passing while the guard covered nothing.
    """
    allowlist = read_allowlist()
    for polluter in KNOWN_POLLUTERS:
        entries = {entry for entry in allowlist if entry.startswith(f"{polluter}::")}
        assert entries, (
            f"{polluter} has no allowlist entries. Either it genuinely stopped "
            "writing into the shared Settings — in which case remove it from "
            "KNOWN_POLLUTERS and celebrate — or the allowlist was truncated."
        )


def test_scanner_sees_an_annotated_assignment() -> None:
    """The scanner itself must not be blind to ``AnnAssign``.

    A guard is only as good as its parser. This drives the real collector logic
    over a snippet whose only write is annotated, which is the exact shape an
    ``Assign``-only walk would miss.
    """
    snippet = (
        "class C:\n    def m(self) -> None:\n        self.settings.tracking.flag: bool = True\n"
    )
    tree = ast.parse(snippet)

    targets = [t for node in ast.walk(tree) for t in _assignment_targets(node)]
    chains = [_attribute_chain(t) for t in targets if isinstance(t, ast.Attribute)]

    assert ["self", "settings", "tracking", "flag"] in chains
