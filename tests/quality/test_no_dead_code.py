"""No NEW unused definition may land in ``src/zebtrack`` (A2 ratchet, TASK-087).

The A2 audit of 2026-11 found ``ProjectCoordinator`` (681 lines, never
instantiated), a mock analyzer returning random data in production, and 218
definitions named only once. The deletion pass removed ~3 350 lines. Nothing
stopped the next one: dead code costs nothing on the day it is written, and it
is the reader who pays, believing the handler runs.

This test runs ``vulture`` over ``src/zebtrack`` (tests are NOT scanned, so a
name only a test uses counts as dead in production) and compares the findings
with ``vulture_whitelist.txt``:

* a finding that is not on the list fails -- a new unused function, method,
  class, attribute, variable or unreachable block;
* an entry that vulture no longer reports fails too (stale), because an
  exemption that outlives its code would hide the next definition of that name.

The list only ever SHRINKS. Each entry sits under a ``[tag] reason`` header that
says why it stays: reached by Pydantic or Tk, a schema field read by
serialization, a name reached through ``getattr``, or a baseline candidate that
was never reviewed and whose deletion is the maintainer's decision.

Keys are ``<path>::<kind>::<qualified name>``, with no line number, so editing
the surrounding file does not churn the list. The qualified name is the chain of
enclosing classes (and, for local variables, functions), so a method that shares
its name with a live one elsewhere is still its own entry.

When this fails on a NEW finding: delete the dead code, or -- if something
reaches it dynamically -- make that reach visible (a real call, a typed
registry) before considering an entry. When it fails on a STALE entry: delete
the line.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest
import vulture  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "src" / "zebtrack"
WHITELIST = Path(__file__).with_name("vulture_whitelist.txt")

_SCOPES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass(frozen=True)
class Finding:
    key: str
    line: int
    confidence: int


def _starts(node: ast.AST) -> set[int]:
    decorators = getattr(node, "decorator_list", [])
    return {node.lineno, *(d.lineno for d in decorators)}  # type: ignore[attr-defined]


def _enclosing(tree: ast.Module, line: int, name: str) -> list[ast.AST]:
    """Scopes that contain ``line``, outermost first, minus the definition itself."""
    chain: list[ast.AST] = []
    for node in ast.walk(tree):
        if not isinstance(node, _SCOPES):
            continue
        first = min(_starts(node))
        last = node.end_lineno or node.lineno
        if not first <= line <= last:
            continue
        if node.name == name and line in _starts(node):
            continue  # the reported definition, not a scope around it
        chain.append(node)
    chain.sort(key=lambda node: min(_starts(node)))
    return chain


def _qualname(tree: ast.Module, kind: str, name: str, line: int) -> str:
    chain = _enclosing(tree, line, name)
    if kind == "attribute":
        # ``self.x = ...`` belongs to the class, whichever method assigns it.
        chain = [node for node in chain if isinstance(node, ast.ClassDef)]
    if kind == "unreachable_code":
        name = f"<unreachable after {name}>"
    return ".".join([*(node.name for node in chain), name])  # type: ignore[attr-defined]


def scan(paths: Iterable[Path], root: Path = REPO_ROOT) -> dict[str, Finding]:
    """Run vulture over ``paths`` and key each finding (first line wins)."""
    paths = list(paths)
    checker = vulture.Vulture()
    checker.scavenge([str(path) for path in paths])
    trees: dict[Path, ast.Module] = {}
    findings: dict[str, Finding] = {}
    for item in checker.get_unused_code():
        path = Path(item.filename).resolve()
        if path not in trees:
            trees[path] = ast.parse(path.read_text(encoding="utf-8"))
        qualname = _qualname(trees[path], item.typ, item.name, item.first_lineno)
        key = f"{path.relative_to(root).as_posix()}::{item.typ}::{qualname}"
        if key not in findings or item.first_lineno < findings[key].line:
            findings[key] = Finding(key, item.first_lineno, item.confidence)
    return findings


class WhitelistError(ValueError):
    """The whitelist file is malformed."""


def parse_whitelist(text: str) -> dict[str, str]:
    """Map every entry to the reason of the ``[tag] reason`` section it sits in."""
    entries: dict[str, str] = {}
    reason: str | None = None
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            tag, _, text_reason = line.partition("]")
            if len(tag) < 2 or not text_reason.strip():
                raise WhitelistError(f"line {number}: a section needs '[tag] reason'")
            reason = f"{tag}] {text_reason.strip()}"
            continue
        if reason is None:
            raise WhitelistError(f"line {number}: entry {line!r} is outside any section")
        if line.count("::") != 2:
            raise WhitelistError(f"line {number}: {line!r} is not '<path>::<kind>::<name>'")
        if line in entries:
            raise WhitelistError(f"line {number}: {line!r} is listed twice")
        entries[line] = reason
    return entries


@cache
def _package_findings() -> dict[str, Finding]:
    return scan([PACKAGE_ROOT])


@cache
def _whitelist() -> dict[str, str]:
    return parse_whitelist(WHITELIST.read_text(encoding="utf-8"))


def test_no_new_unused_definition_in_src() -> None:
    new = sorted(set(_package_findings()) - set(_whitelist()))
    detail = "\n".join(
        f"  {key}  (line {_package_findings()[key].line}, "
        f"{_package_findings()[key].confidence}% confidence)"
        for key in new
    )
    assert not new, (
        f"vulture found {len(new)} unused definition(s) not in "
        f"{WHITELIST.name}:\n{detail}\n"
        "Delete the dead code. If something reaches it dynamically, make that reach "
        "visible before adding an entry -- this list only shrinks."
    )


def test_whitelist_has_no_stale_entries() -> None:
    stale = sorted(set(_whitelist()) - set(_package_findings()))
    assert not stale, (
        f"{len(stale)} whitelist entr(y/ies) no longer reported by vulture; delete "
        f"them from {WHITELIST.name}:\n" + "\n".join(f"  {key}" for key in stale)
    )


def test_every_section_states_a_reason() -> None:
    reasons = set(_whitelist().values())
    assert reasons, "the whitelist parsed to no entries at all"
    assert all(len(reason.split("]", 1)[1].strip()) >= 20 for reason in reasons)


# --- the scanner itself -------------------------------------------------------


def _write(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_scan_reports_an_unused_function_and_spares_a_used_one(tmp_path: Path) -> None:
    _write(
        tmp_path / "pkg" / "mod.py",
        "def used():\n    return 1\n\n\ndef forgotten():\n    return 2\n\n\nused()\n",
    )
    findings = scan([tmp_path / "pkg"], root=tmp_path)
    assert set(findings) == {"pkg/mod.py::function::forgotten"}
    assert findings["pkg/mod.py::function::forgotten"].line == 5


def test_scan_keys_members_by_their_class(tmp_path: Path) -> None:
    _write(
        tmp_path / "pkg" / "mod.py",
        "class A:\n"
        "    def __init__(self):\n"
        "        self.written_only = 1\n"
        "\n"
        "    def shared(self):\n"
        "        return 1\n"
        "\n"
        "    def lonely(self):\n"
        "        return 2\n"
        "\n"
        "\n"
        "A().shared()\n",
    )
    findings = scan([tmp_path / "pkg"], root=tmp_path)
    assert set(findings) == {
        "pkg/mod.py::attribute::A.written_only",
        "pkg/mod.py::method::A.lonely",
    }


def test_scan_keys_unreachable_code_by_its_function(tmp_path: Path) -> None:
    _write(
        tmp_path / "pkg" / "mod.py",
        "def f():\n    return 1\n    print('never')\n\n\nf()\n",
    )
    findings = scan([tmp_path / "pkg"], root=tmp_path)
    assert set(findings) == {"pkg/mod.py::unreachable_code::f.<unreachable after return>"}


def test_parse_whitelist_attaches_the_section_reason() -> None:
    text = (
        "# comment\n"
        "[tk-hook] Tk calls it from simpledialog.Dialog\n"
        "src/a.py::method::D.apply\n"
        "\n"
        "[pydantic] Pydantic reads it when the model is built\n"
        "src/b.py::variable::M.model_config\n"
    )
    assert parse_whitelist(text) == {
        "src/a.py::method::D.apply": "[tk-hook] Tk calls it from simpledialog.Dialog",
        "src/b.py::variable::M.model_config": (
            "[pydantic] Pydantic reads it when the model is built"
        ),
    }


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("src/a.py::function::f\n", "outside any section"),
        ("[tag]\nsrc/a.py::function::f\n", "'[tag] reason'"),
        ("[t] a reason long enough\nsrc/a.py::function::f\nsrc/a.py::function::f\n", "twice"),
        ("[t] a reason long enough\nsrc/a.py:function:f\n", "is not"),
    ],
)
def test_parse_whitelist_rejects_malformed_text(text: str, message: str) -> None:
    with pytest.raises(WhitelistError, match=re.escape(message)):
        parse_whitelist(text)
