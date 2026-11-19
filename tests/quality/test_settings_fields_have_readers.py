"""Every ``Settings`` field has a reader in ``src`` (A7, TASK-087).

The A7 audit found six ``Settings`` fields nothing reads (five confirmed). Two
of them are documented to users as switches -- ``ui_features.
use_wizard_for_project_creation`` ("set it to bring the old dialog back") and
``performance.max_parallel_videos`` (in CLAUDE.md and the FAQ) -- so a
researcher who sets them changes nothing and is never told. A field without a
reader is a promise the app does not keep.

The tree is walked through ``model_fields`` from ``Settings`` down, into every
nested model (including models inside ``Optional``, ``list`` and ``dict``). A
field is READ when its name appears anywhere in ``src/zebtrack`` as an
attribute load (``x.name``), the second argument of ``getattr``/``hasattr``,
a subscript key (``d["name"]``) or a ``.get("name")`` key. Its own definition is
an annotated name, not an attribute, so it never counts.

Matching is by NAME, as in the audit: a field whose name is shared with
something that is read elsewhere looks read. The guard is therefore blind to
those, and sharp on the case that matters -- a name nobody reads at all.

``ALLOWED_UNREAD`` holds the fields of A7-01. They stay: ``Settings`` is
``extra="forbid"``, so removing a field makes every ``config.local.yaml`` that
still names it fail at start-up. The list only SHRINKS: an entry that gains a
reader, or whose field is gone, fails as stale. The two fields this guard found
on its first run (A7-02: ``performance.enable_parallel_analysis`` and
``performance.memory_mode``, written by the startup benchmark and read by
nothing) were wired up in #725 through ``utils/performance_policy.py``.

An assignment such as ``settings.performance.memory_mode = "low"`` is a STORE,
not a reader: writing a value nobody reads is exactly what A7-02 is.
"""

from __future__ import annotations

import ast
import types
import typing
from collections.abc import Iterable, Iterator
from pathlib import Path

import pytest
from pydantic import BaseModel

from zebtrack.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "src" / "zebtrack"

_FORBID_REASON = (
    "no reader (A7-01). Kept: Settings is extra='forbid', so removing the field breaks "
    "every config.local.yaml that still names it"
)
ALLOWED_UNREAD: dict[str, str] = {
    "live_analysis.auto_stop_on_limit": _FORBID_REASON,
    "live_analysis.show_countdown": _FORBID_REASON,
    "ui_features.use_wizard_for_project_creation": _FORBID_REASON
    + "; the docs still present it as a switch",
    "performance.max_parallel_videos": _FORBID_REASON + "; CLAUDE.md and the FAQ document it",
}


def _models_in(annotation: object) -> Iterator[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        yield annotation
        return
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        yield from _models_in(typing.get_args(annotation)[0])
        return
    if origin is not None or isinstance(annotation, types.UnionType):
        for arg in typing.get_args(annotation):
            yield from _models_in(arg)


def field_paths(model: type[BaseModel], prefix: str = "") -> dict[str, str]:
    """Dotted path of every field in the model tree -> the field's own name."""
    paths: dict[str, str] = {}
    for name, info in model.model_fields.items():
        path = f"{prefix}{name}"
        paths[path] = name
        for nested in _models_in(info.annotation):
            if nested is not model:
                paths.update(field_paths(nested, prefix=f"{path}."))
    return paths


def read_names(sources: Iterable[str]) -> set[str]:
    """Names read in ``sources`` as attribute, getattr argument or string key."""
    names: set[str] = set()
    for source in sources:
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                names.add(node.attr)
            elif isinstance(node, ast.Assign | ast.AnnAssign) and isinstance(
                node.value, ast.Constant
            ):
                # A key constant (``_KEY_ENTER: Final[str] = "roi_flutter_enter_frames"``)
                # is how roi_rule_resolver reads the ROI fields by name.
                if isinstance(node.value.value, str):
                    names.add(node.value.value)
            elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
                if isinstance(node.slice.value, str):
                    names.add(node.slice.value)
            elif isinstance(node, ast.Call) and node.args:
                func = node.func
                callee = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if callee in {"getattr", "hasattr"} and len(node.args) >= 2:
                    key = node.args[1]
                elif callee == "get" and isinstance(func, ast.Attribute):
                    key = node.args[0]
                else:
                    continue
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    names.add(key.value)
    return names


def unread_fields(model: type[BaseModel], sources: Iterable[str]) -> set[str]:
    read = read_names(sources)
    return {path for path, name in field_paths(model).items() if name not in read}


def _package_sources() -> list[str]:
    return [path.read_text(encoding="utf-8") for path in sorted(PACKAGE_ROOT.rglob("*.py"))]


def test_every_settings_field_has_a_reader() -> None:
    unread = unread_fields(Settings, _package_sources()) - set(ALLOWED_UNREAD)
    assert not unread, (
        "Settings fields that nothing in src/zebtrack reads (a setting the user can "
        "change and the app ignores). Wire them up or remove them -- and remember that "
        "removing one breaks config.local.yaml files that still name it:\n"
        + "\n".join(f"  {path}" for path in sorted(unread))
    )


def test_allowed_unread_has_no_stale_entries() -> None:
    unread = unread_fields(Settings, _package_sources())
    stale = sorted(set(ALLOWED_UNREAD) - unread)
    assert not stale, f"these fields now have a reader or are gone; drop them: {stale}"


def test_the_tree_reaches_nested_sections() -> None:
    paths = field_paths(Settings)
    assert len(paths) > 100
    assert set(ALLOWED_UNREAD) <= set(paths)


# --- the scanner itself -------------------------------------------------------


class _Leaf(BaseModel):
    used: int = 0
    forgotten: int = 0
    by_getattr: int = 0
    by_key: int = 0


class _Root(BaseModel):
    section: _Leaf = _Leaf()
    maybe: _Leaf | None = None
    many: list[_Leaf] = []


def test_field_paths_walks_optional_and_list_sections() -> None:
    paths = field_paths(_Root)
    assert {"section.forgotten", "maybe.used", "many.by_key"} <= set(paths)
    assert paths["section.forgotten"] == "forgotten"


@pytest.mark.parametrize(
    "reader",
    [
        "settings.section.used",
        "getattr(settings.section, 'used', 0)",
        "data['used']",
        "data.get('used')",
        "None\n_KEY: Final[str] = 'used'",
    ],
)
def test_read_names_sees_every_kind_of_reader(reader: str) -> None:
    assert "used" in read_names([f"value = {reader}\n"])


def test_an_assignment_or_a_definition_is_not_a_reader() -> None:
    source = "class M:\n    used: int = 0\n\nsettings.section.used = 3\n"
    assert "used" not in read_names([source])


def test_unread_fields_lists_every_path_of_a_name_nobody_reads() -> None:
    sources = [
        "a = s.section.used + s.maybe.used + len(s.many)\n",
        "b = getattr(s.section, 'by_getattr')\n",
        "c = d['by_key']\n",
    ]
    assert unread_fields(_Root, sources) == {
        "section.forgotten",
        "maybe.forgotten",
        "many.forgotten",
    }
