"""Whoever consumes an event must read keys its payload actually has.

``EventBusV2`` never lets a consumer's key mismatch surface:

* a handler that reads a missing key (``_payload_get(p, "port")``, ``p.get("port")``,
  ``getattr(p, "port", None)``) gets ``None`` and quietly takes its "nothing to do"
  branch;
* a payload splatted into a method (``f(**payload_dict)``) whose signature lacks a
  field raises ``TypeError``, which ``publish`` logs and swallows;
* a publisher that sends a dict with the wrong keys fails coercion into the
  declared dataclass and is delivered as an ``UnknownPayload`` -- which the
  consumer then reads as empty.

None of it is visible to ruff or mypy: the keys are strings and the payload is
splatted. Three real cases were found by this scan, each a button that did
nothing while the UI said it had worked:

* ``MODEL_LOAD_NEW_WEIGHT``: the payload names the file ``weight_path``, the
  runtime splatted it into ``load_new_weight(filepath=...)``. Adding a weight
  from a folder outside the program did nothing.
* ``ARDUINO_PORT_UPDATE_REQUESTED``: the payload declared ``ports``, the dashboard
  sent ``{"port": ...}``. "Recheck ports" logged "Reconnecting..." and never did.
* ``ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG``: the handler read ``available_groups``,
  which no payload carried. The dialog offered hardcoded placeholder groups.

What is checked (statically, against ``_PAYLOAD_TYPES``):

1. every handler subscribed with ``subscribe(UIEvents.X, handler)`` -- the keys it
   reads from its payload parameter (and from a ``_payload_to_dict(p)`` alias) must
   be fields of X's payload dataclass;
2. in ``MainViewModelRuntime`` -- the keys each ``if event_name is UIEvents.X``
   branch reads, and every ``**payload_dict`` splat, whose payload fields must be
   accepted by the receiving method's signature.

A read that is one arm of ``a or b`` is accepted when another arm reads a real
field: that is a deliberate fallback for legacy dict payloads, not drift.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable, Iterator
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

from zebtrack.coordinators.ui_state_coordinator import UIStateController
from zebtrack.core.viewmodels.hardware_status_view_model import HardwareStatusViewModel
from zebtrack.core.viewmodels.project_view_model import ProjectViewModel
from zebtrack.ui.event_bus_v2 import _PAYLOAD_TYPES

SRC = Path(__file__).resolve().parents[2] / "src" / "zebtrack"
RUNTIME = SRC / "core" / "viewmodels" / "main_view_model_runtime.py"

# ``vm.<attr>.<method>(**payload_dict)`` in the runtime -> the class that owns <method>.
RUNTIME_TARGETS: dict[str, type] = {
    "hardware_vm": HardwareStatusViewModel,
    "project_vm": ProjectViewModel,
}
# ``self.<attr>.<same name>(**kwargs)`` pass-throughs a target forwards to.
PASSTHROUGH_TARGETS: dict[str, type] = {"ui_state_controller": UIStateController}

DICT_METHODS = {"get", "items", "keys", "values", "copy", "pop", "setdefault", "update"}
ALIAS_FUNCS = {"_payload_to_dict", "asdict", "vars"}


def _payload_fields() -> dict[str, tuple[str, set[str]]]:
    out = {}
    for event, cls in _PAYLOAD_TYPES.items():
        if is_dataclass(cls):
            out[event.name] = (cls.__name__, {f.name for f in fields(cls)})
    return out


FIELDS = _payload_fields()


def _uievent(node: ast.AST) -> str | None:
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "UIEvents"
    ):
        return node.attr
    return None


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _key_read(node: ast.AST, names: set[str]) -> str | None:
    """The payload key ``node`` reads from one of ``names``, if it is such a read."""
    if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
        if (
            isinstance(node.value, ast.Name)
            and node.value.id in names
            and node.attr not in DICT_METHODS
        ):
            return node.attr
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        if node.value.id in names:
            return _const_str(node.slice)
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id in {"getattr", "_payload_get"}:
            if len(node.args) >= 2 and isinstance(node.args[0], ast.Name):
                if node.args[0].id in names:
                    return _const_str(node.args[1])
        if isinstance(func, ast.Attribute) and func.attr == "get" and node.args:
            if isinstance(func.value, ast.Name) and func.value.id in names:
                return _const_str(node.args[0])
    return None


def _fallback_ok(tree: ast.AST, names: set[str], flds: set[str]) -> set[int]:
    """ids of reads that sit in an ``a or b`` where another arm reads a real field."""
    ok: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            arms = [(arm, _key_read(arm, names)) for arm in node.values]
            if any(key in flds for _, key in arms if key):
                ok.update(id(arm) for arm, key in arms if key and key not in flds)
    return ok


def _bad_reads(tree: ast.AST, names: set[str], flds: set[str]) -> Iterator[tuple[str, int]]:
    excused = _fallback_ok(tree, names, flds)
    for node in ast.walk(tree):
        key = _key_read(node, names)
        if key is not None and key not in flds and id(node) not in excused:
            yield key, getattr(node, "lineno", 0)


def _aliases(fn: ast.AST, param: str) -> set[str]:
    names = {param}
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
            if isinstance(target, ast.Name) and isinstance(value, ast.Call) and value.args:
                func = value.func
                fname = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                first = value.args[0]
                if fname in ALIAS_FUNCS and isinstance(first, ast.Name) and first.id == param:
                    names.add(target.id)
    return names


def _functions(tree: ast.AST) -> dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]]:
    out: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            out.setdefault(node.name, []).append(node)
    return out


def _subscriber_violations() -> list[str]:
    problems = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = _functions(tree)
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "subscribe"
                and len(node.args) >= 2
            ):
                continue
            event = _uievent(node.args[0])
            if event not in FIELDS:
                continue
            cls_name, flds = FIELDS[event]
            handler = node.args[1]
            candidates: list[tuple[ast.AST, str]] = []
            if isinstance(handler, ast.Lambda) and handler.args.args:
                candidates = [(handler, handler.args.args[0].arg)]
            else:
                name = getattr(handler, "attr", None) or getattr(handler, "id", None)
                for fn in functions.get(name or "", []):
                    params = [a.arg for a in fn.args.args if a.arg not in ("self", "cls")]
                    if params:
                        candidates.append((fn, params[0]))
            rel = path.relative_to(SRC.parent)
            for scope, param in candidates:
                for key, line in _bad_reads(scope, _aliases(scope, param), flds):
                    problems.append(
                        f"{rel}:{line} {event}: reads '{key}', {cls_name} has {sorted(flds)}"
                    )
    return problems


def _accepts(fn: Callable[..., Any], npos: int) -> tuple[set[str], set[str], bool]:
    params = [p for p in inspect.signature(fn).parameters.values() if p.name != "self"]
    named = [p for p in params[npos:] if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
    var_kw = any(p.kind is p.VAR_KEYWORD for p in params)
    required = {p.name for p in named if p.default is p.empty}
    return {p.name for p in named}, required, var_kw


def _resolve_passthrough(owner: type, method: str) -> Callable[..., Any] | None:
    """Follow ``def m(self, **kwargs): self.<attr>.m(**kwargs)`` one hop."""
    source = inspect.getsource(getattr(owner, method))
    for attr, cls in PASSTHROUGH_TARGETS.items():
        if f"self.{attr}.{method}(**" in source:
            return getattr(cls, method)
    return None


def _vm_callee(func: ast.AST) -> tuple[type, str] | None:
    """``vm.<attr>.<method>`` -> (owner class, method)."""
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Attribute):
        owner = RUNTIME_TARGETS.get(func.value.attr)
        if owner is not None:
            return owner, func.attr
    return None


def _splat_targets(fn: ast.AST) -> Iterator[tuple[set[str], tuple[type, str], int]]:
    """(events, callee, n positional args) for every ``**payload_dict`` splat in ``fn``."""
    branches: dict[int, str] = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            event = _uievent(node.test.comparators[0]) if node.test.comparators else None
            if event:
                for sub in node.body:
                    for inner in ast.walk(sub):
                        branches[id(inner)] = event
    dicts = [d for d in ast.walk(fn) if isinstance(d, ast.Dict)]
    routed = {  # event -> callee, from ``{UIEvents.X: vm.project_vm.handle_x}``
        _uievent(k): _vm_callee(v)
        for d in dicts
        for k, v in zip(d.keys, d.values, strict=True)
        if k is not None and _uievent(k) and _vm_callee(v)
    }
    selectors = {  # events of a dict that selects a value, not a callee
        _uievent(k)
        for d in dicts
        for k, v in zip(d.keys, d.values, strict=True)
        if k is not None and _uievent(k) and not _vm_callee(v)
    }
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        if not any(
            kw.arg is None and isinstance(kw.value, ast.Name) and kw.value.id == "payload_dict"
            for kw in node.keywords
        ):
            continue
        callee = _vm_callee(node.func)
        if callee is not None:
            events = {branches[id(node)]} if id(node) in branches else selectors
            yield {e for e in events if e}, callee, len(node.args)
        elif isinstance(node.func, ast.Name):
            for event, routed_callee in routed.items():
                if event and routed_callee:
                    yield {event}, routed_callee, len(node.args)


def _runtime_violations() -> list[str]:
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            event = _uievent(node.test.comparators[0]) if node.test.comparators else None
            if event not in FIELDS:
                continue
            cls_name, flds = FIELDS[event]
            body = ast.Module(body=node.body, type_ignores=[])
            for key, line in _bad_reads(body, {"payload_dict", "data"}, flds):
                problems.append(
                    f"main_view_model_runtime.py:{line} {event}: reads '{key}', "
                    f"{cls_name} has {sorted(flds)}"
                )
    for fn in _functions(tree).values():
        for f in fn:
            for events, (owner, method), npos in _splat_targets(f):
                target: Callable[..., Any] = getattr(owner, method)
                names, required, var_kw = _accepts(target, npos)
                if var_kw and not names:
                    forwarded = _resolve_passthrough(owner, method)
                    if forwarded is None:
                        continue
                    target = forwarded
                    names, required, var_kw = _accepts(target, npos)
                for event in sorted(events):
                    if event not in FIELDS:
                        continue
                    cls_name, flds = FIELDS[event]
                    extra = set() if var_kw else flds - names
                    missing = required - flds
                    if extra or missing:
                        problems.append(
                            f"{event}: {cls_name}{sorted(flds)} splatted into "
                            f"{target.__qualname__}{inspect.signature(target)}"
                            f" (rejected: {sorted(extra)}, missing: {sorted(missing)})"
                        )
    return problems


def test_subscribers_read_only_fields_of_their_event_payload() -> None:
    problems = _subscriber_violations()
    assert not problems, "Handlers read keys their payload lacks:\n" + "\n".join(problems)


def test_runtime_reads_and_splats_match_the_payloads() -> None:
    problems = _runtime_violations()
    assert not problems, "MainViewModelRuntime payload drift:\n" + "\n".join(problems)


def test_the_scan_sees_the_runtime_splats() -> None:
    """Guard the guard: if the AST shapes change, the scan must not go silently blind."""
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    found = {
        (owner.__name__, method)
        for fns in _functions(tree).values()
        for f in fns
        for _events, (owner, method), _ in _splat_targets(f)
    }
    assert ("HardwareStatusViewModel", "set_openvino_usage") in found
    assert ("ProjectViewModel", "handle_delete_hierarchy_node") in found
    assert ("ProjectViewModel", "handle_delete_aquarium") in found


def test_the_scan_flags_a_known_drift() -> None:
    """The ``weight_path``/``filepath`` drift of MODEL_LOAD_NEW_WEIGHT must be caught."""
    snippet = ast.parse("def h(p):\n    return _payload_get(p, 'filepath')\n")
    _, flds = FIELDS["MODEL_LOAD_NEW_WEIGHT"]
    assert [k for k, _ in _bad_reads(snippet, {"p"}, flds)] == ["filepath"]
    fallback = ast.parse("def h(p):\n    return p.get('weight_path') or p.get('filepath')\n")
    assert list(_bad_reads(fallback, {"p"}, flds)) == []
