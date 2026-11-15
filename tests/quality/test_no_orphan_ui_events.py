"""Every ``UIEvents`` member must have both ends wired, and be used at all.

``EventBusV2.publish`` opens with ``if not handlers: return``. Publishing to an
event nobody subscribed is not an error, not a warning, not even a debug line --
it is indistinguishable from success at every call site. That makes the bus a
one-way mirror: the publisher believes it delivered a message, and the user sees
nothing at all.

This is not hypothetical. ``UIEvents.SHOW_ERROR`` and ``UIEvents.UI_SHOW_ERROR``
are two distinct members of the same enum; only the ``UI_`` one was ever
subscribed. Five call sites -- project_lifecycle_coordinator,
project_workflow_adapter, analysis_pipeline_runner, video_context_factory and
analysis_control_view_model -- published user-facing failures to the other one.
The visible symptom was the project wizard: finish five steps, click "Create
Project", and the window closes with no project and no message, because the
"Invalid Configuration" text explaining exactly what was wrong went to
``SHOW_ERROR`` and was dropped. ``CONFIG_VALIDATION_ERROR`` had the same shape
one layer up: the Advanced Settings tab published it whenever a field failed to
parse, so saving with an empty field was a button that did nothing.

Three directions are checked, each with its own grandfather list:

* published, never subscribed (``ALLOWED_ORPHANS``) -- the message is dropped;
* subscribed, never published (``ALLOWED_UNPUBLISHED``) -- the handler is code
  nothing can reach, and whoever reads it believes it runs;
* never referenced outside ``event_bus_v2.py`` (``ALLOWED_UNREFERENCED``) -- a
  name that invites the next author to publish into the void.

A fourth check forbids publishing a string literal: the bus keys subscribers by
enum member, so ``_publish_event("ZONES_CONFIGURED")`` reached nobody, and four
such calls sat in ``DetectorSetupCoordinator`` for as long as it existed.

Every list only ever SHRINKS. Each one fails on an entry that no longer matches
its condition (stale) and on a name that is not a ``UIEvents`` member (typo),
because an exemption that outlives its reason hides the next regression on that
same event. Adding a new entry is the one thing this test exists to prevent. If
a new event genuinely has no consumer yet, do not publish it yet.

What counts as publishing and subscribing
-----------------------------------------
The scan is static (AST), so it has to know every way the codebase reaches the
bus. Publishing: ``publish``, ``publish_event``, ``emit_event``,
``_publish_event`` (``BaseCoordinator`` and three look-alikes),
``_publish_model_event`` and ``_publish_arduino_ui``, with the member passed
bare or wrapped in ``Event(UIEvents.X, ...)`` / ``Event(type=UIEvents.X)``.
Subscribing: ``subscribe``, ``register_handler``, ``register_direct_handler``
and ``BaseWidget.bind_callback``.

The event argument is resolved one step further than a literal member: a local
name is followed to every value assigned to it in the same function
(``event = UIEvents.A`` ... ``publish_event(event, ...)``), including both arms
of a conditional expression, and a loop variable is followed to the collection
it iterates, inside the function or as a module/class attribute
(``for name in self._EVENTS_TO_HANDLE: bus.subscribe(name, ...)``). A
parameter forwarded by a wrapper is not resolved; the wrapper's callers are
scanned instead.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from zebtrack.ui.event_bus_v2 import UIEvents

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "src" / "zebtrack"
ENUM_MODULE = PACKAGE_ROOT / "ui" / "event_bus_v2.py"

# Methods that register a reaction to an event. ``register_handler`` and
# ``register_direct_handler`` are EventDispatcher's wrappers around
# ``EventBusV2.subscribe``; ``bind_callback`` is BaseWidget's.
SUBSCRIBE_CALLS = frozenset(
    {"subscribe", "register_handler", "register_direct_handler", "bind_callback"}
)

# Methods that put an event on the bus, directly or through a thin wrapper.
PUBLISH_CALLS = frozenset(
    {
        "publish",
        "publish_event",
        "emit_event",
        "_publish_event",
        "_publish_model_event",
        "_publish_arduino_ui",
    }
)

# Keyword names under which the wrappers above accept the event.
EVENT_KEYWORDS = ("event_type", "event", "event_name")

# Published today with nobody listening. NEVER add to this list.
ALLOWED_ORPHANS = frozenset(
    {
        # -- notificações redundantes, ao lado de um callback direto que funciona --
        "BEHAVIORAL_CONFIG_GEOTAXIS_TOGGLED",
        "BEHAVIORAL_CONFIG_PERSPECTIVE_CHANGED",
        "BEHAVIORAL_CONFIG_VALUES_CHANGED",
        "CONFIG_ROI_RULE_CHANGED",
        "PROCESSING_EXPORT_SUMMARIES",
        "PROJECT_ITEM_DOUBLE_CLICK",
        "REPORTS_GENERATE_PARTIAL",
        # -- telemetria de ciclo de vida sem consumidor de UI --
        "FRAME_DISPLAYED",
        "FRAME_ERROR",
        "RECORDING_STARTED",
        "VIDEO_METADATA_UPDATED",
        "ZONE_MULTI_AUTO_DETECT_FAILED",
    }
)

# Subscribed today with nobody publishing: the handler cannot run. NEVER add.
# Classification (delete / wire / keep) in docs/audits/2026-11_A1_events.md.
ALLOWED_UNPUBLISHED = frozenset(
    {
        "ANALYSIS_TASK_STATUS_UPDATED",
        "CALIBRATION_COPY_TO_PROJECT",
        "CALIBRATION_SAVE_TO_PROJECT",
        "DETECTOR_UPDATE_PARAMETERS",
        "EXTERNAL_TRIGGER_NOTICE",
        "MODEL_ADD_WEIGHT",
        "MODEL_CLEAR_OPENVINO_CACHE",
        "MODEL_VALIDATE_WEIGHTS",
        "NAVIGATE_TO_WELCOME",
        "PROCESSING_GENERATE_TRAJECTORIES",
        "PROCESSING_STATS_UPDATED",
        "RECORDING_TOGGLE",
        "SOCIAL_SUMMARY_UPDATED",
        "UI_NAVIGATE_FROM_ANALYSIS_VIEW",
        # o único publicador era o ControlPanelWidget morto (A2-D-009): o handler em
        # video_selector_tree_manager.py já não rodava antes da remoção
        "UI_REQUEST_PROCESS_VIDEOS",
        "UI_SETUP_INTERACTIVE_POLYGON",
        "VIDEO_LOADED",
        "ZONE_APPLY_ROI_SETTINGS",
        "ZONE_AQUARIUM_CONFIG_UPDATED",
        "ZONE_MULTI_AUTO_DETECT",
        "ZONE_SAVE_MANUAL_ARENA",
        "ZONE_SET_ARENA_POLYGON",
    }
)

# Never referenced outside event_bus_v2.py. NEVER add.
ALLOWED_UNREFERENCED = frozenset(
    {
        "ANALYSIS_COMPLETED",
        "ANALYSIS_STARTED",
        "APP_CLOSE",
        "ARDUINO_LOG_EVENT",
        "ARDUINO_SETUP",
        "CALIBRATION_RUN_LIVE",
        # o único publicador era o ControlPanelWidget morto, apagado em 2026-11 (A2-D-009)
        "CONTROL_INTERVAL_CHANGED",
        "CONTROL_PREVIEW_TOGGLED",
        "DETECTOR_SETUP",
        "DETECTOR_SETUP_ZONES",
        "DETECTOR_UPDATE_ZONES",
        "DISPLAY_VIDEO_FRAME",
        "MODEL_UPDATE_OPENVINO_STATUS",
        "NAVIGATE_TO_ANALYSIS",
        "NAVIGATE_TO_PROJECT",
        "PROGRESS_UPDATE",
        "PROJECT_APPLY_SETTINGS",
        "PROJECT_CREATED",
        "RECORDING_TRIGGER",
        "REPORTS_GENERATE_UNIFIED",
        "TRACKING_COMPLETE",
        "UI_SET_AQUARIUM_SELECTOR_VISIBLE",
        "UI_SHOW_AQUARIUM_ASSIGNMENT_DIALOG",
        "UI_SHOW_AQUARIUM_COUNT_DIALOG",
        "UI_UPDATE_AQUARIUM_SELECTOR",
        "VIDEO_RECONFIGURE_SUBJECTS",
        "WIZARD_CREATE_PROJECT",
        "ZONE_APPLY_ROI_TEMPLATE",
        "ZONE_AQUARIUM_CONFIG_CONFIRMED",
        "ZONE_AQUARIUM_COUNT_CONFIRMED",
        "ZONE_CHANGE_ROI_COLOR",
        "ZONE_IMPORT_AND_APPLY_ROI_TEMPLATE",
        "ZONE_MULTI_DETECT_COMPLETED",
        "ZONE_REMOVE_SELECTED_ROI",
        "ZONE_RENAME_SELECTED_ROI",
        "ZONE_SAVE_ROI_TEMPLATE",
        "ZONE_SELECTED_V2",
        "ZONE_SHOW_AQUARIUM_COUNT_DIALOG",
        "ZONE_START_DRAW_ARENA",
        "ZONE_UPDATE_ARENA",
    }
)

# Files whose string-literal publishes are tolerated. Empty since the dead
# ``ProjectCoordinator`` was deleted (audit A2-04). NEVER add.
STRING_PUBLISH_EXEMPT_FILES: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


@dataclass
class Scan:
    """What the whole package does with the bus, keyed by member name."""

    published: dict[str, set[str]] = field(default_factory=dict)
    subscribed: dict[str, set[str]] = field(default_factory=dict)
    referenced: set[str] = field(default_factory=set)
    # ``file:line`` of every publish call whose event is a string literal.
    string_publishes: list[str] = field(default_factory=list)


def _member_of(node: ast.AST) -> str | None:
    """``UIEvents.FOO`` (or ``x.UIEvents.FOO``) -> ``"FOO"``; anything else -> None."""
    if not isinstance(node, ast.Attribute):
        return None
    owner = node.value
    if isinstance(owner, ast.Name) and owner.id == "UIEvents":
        return node.attr
    if isinstance(owner, ast.Attribute) and owner.attr == "UIEvents":
        return node.attr
    return None


def _members_in(node: ast.AST | None) -> set[str]:
    """Every ``UIEvents`` member mentioned anywhere under *node*."""
    if node is None:
        return set()
    return {name for sub in ast.walk(node) if (name := _member_of(sub))}


def _attr_or_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


class _Module:
    """One parsed module plus the lookups the resolver needs."""

    def __init__(self, path: Path, root: Path) -> None:
        self.path = path
        self.rel = path.relative_to(root).as_posix()
        self.tree = ast.parse(path.read_text(encoding="utf-8"))
        # Module- and class-level ``NAME = <expr>`` bindings: the collections a
        # subscription loop may iterate (``_EVENTS_TO_HANDLE``).
        self.collections: dict[str, list[ast.expr]] = {}
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Module | ast.ClassDef):
                for stmt in node.body:
                    for name, value in _bindings(stmt):
                        self.collections.setdefault(name, []).append(value)

    def scopes(self) -> Iterator[tuple[ast.AST, dict[str, list[ast.expr]]]]:
        """Yield ``(call, local bindings of its innermost function)`` for every call."""
        yield from self._walk(self.tree, {})

    def _walk(
        self, node: ast.AST, local: dict[str, list[ast.expr]]
    ) -> Iterator[tuple[ast.AST, dict[str, list[ast.expr]]]]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
                yield from self._walk(child, _local_bindings(child))
                continue
            if isinstance(child, ast.Call):
                yield child, local
            yield from self._walk(child, local)


def _bindings(stmt: ast.AST) -> Iterator[tuple[str, ast.expr]]:
    """``(name, value)`` pairs a single statement binds; ``for`` binds its iterable."""
    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            if isinstance(target, ast.Name):
                yield target.id, stmt.value
    elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        if isinstance(stmt.target, ast.Name):
            yield stmt.target.id, stmt.value
    elif isinstance(stmt, ast.For | ast.AsyncFor | ast.comprehension):
        target = stmt.target
        # ``for event, handler in mapping.items()``: the event is the first slot.
        if isinstance(target, ast.Tuple) and target.elts:
            target = target.elts[0]
        if isinstance(target, ast.Name):
            yield target.id, ast.Starred(value=stmt.iter)  # marker: "an element of"


def _local_bindings(func: ast.AST) -> dict[str, list[ast.expr]]:
    local: dict[str, list[ast.expr]] = {}
    for node in ast.walk(func):
        for name, value in _bindings(node):
            local.setdefault(name, []).append(value)
    return local


def _resolve(
    expr: ast.AST,
    local: dict[str, list[ast.expr]],
    module: _Module,
    seen: frozenset[str] = frozenset(),
) -> tuple[set[str], bool]:
    """Members an event expression can evaluate to, and whether it is a string literal."""
    if isinstance(expr, ast.Constant):
        return set(), isinstance(expr.value, str)
    if (member := _member_of(expr)) is not None:
        return {member}, False
    if isinstance(expr, ast.IfExp):
        body, body_str = _resolve(expr.body, local, module, seen)
        other, other_str = _resolve(expr.orelse, local, module, seen)
        return body | other, body_str or other_str
    if isinstance(expr, ast.Call) and _attr_or_name(expr.func) == "Event":
        inner = expr.args[0] if expr.args else None
        for kw in expr.keywords:
            if kw.arg == "type":
                inner = kw.value
        return _resolve(inner, local, module, seen) if inner is not None else (set(), False)
    if isinstance(expr, ast.Starred):  # an element of a collection
        return _resolve_collection(expr.value, local, module, seen), False
    if isinstance(expr, ast.Name) and expr.id not in seen:
        found: set[str] = set()
        literal = False
        for value in local.get(expr.id, []):
            members, is_str = _resolve(value, local, module, seen | {expr.id})
            found |= members
            literal = literal or is_str
        return found, literal
    return set(), False


def _resolve_collection(
    expr: ast.AST,
    local: dict[str, list[ast.expr]],
    module: _Module,
    seen: frozenset[str],
) -> set[str]:
    """Members held by the collection a loop iterates."""
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute):
        if expr.func.attr in {"items", "keys"}:
            expr = expr.func.value
    if isinstance(expr, ast.Tuple | ast.List | ast.Set | ast.Dict):
        return _members_in(expr)
    name = _attr_or_name(expr)
    if name is None or name in seen:
        return set()
    sources = local.get(name, []) if isinstance(expr, ast.Name) else []
    sources = sources or module.collections.get(name, [])
    found: set[str] = set()
    for value in sources:
        found |= _members_in(value)
    return found


def _event_argument(call: ast.Call) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg in EVENT_KEYWORDS:
            return kw.value
    return call.args[0] if call.args else None


def _scan_module(path: Path, root: Path, scan: Scan) -> None:
    module = _Module(path, root)
    if path != ENUM_MODULE:
        scan.referenced |= _members_in(module.tree)

    for call, local in module.scopes():
        assert isinstance(call, ast.Call)
        method = _attr_or_name(call.func)
        if method not in PUBLISH_CALLS and method not in SUBSCRIBE_CALLS:
            continue
        argument = _event_argument(call)
        if argument is None:
            continue
        members, is_string = _resolve(argument, local, module)
        if method in PUBLISH_CALLS:
            if is_string:
                scan.string_publishes.append(f"{module.rel}:{call.lineno}")
            for name in members:
                scan.published.setdefault(name, set()).add(module.rel)
        else:
            for name in members:
                scan.subscribed.setdefault(name, set()).add(module.rel)


def scan_paths(paths: Iterable[Path], root: Path = REPO_ROOT) -> Scan:
    """Scan *paths*; locations in the result are relative to *root*."""
    scan = Scan()
    for path in sorted(paths):
        _scan_module(path, root, scan)
    return scan


@cache
def _package_scan() -> Scan:
    return scan_paths(PACKAGE_ROOT.rglob("*.py"))


VALID = frozenset(member.name for member in UIEvents)


def _format(events: dict[str, set[str]]) -> str:
    return "\n".join(
        f"  UIEvents.{name}  <- {', '.join(sorted(sources))}"
        for name, sources in sorted(events.items())
    )


# ---------------------------------------------------------------------------
# Direction 1: published, never subscribed
# ---------------------------------------------------------------------------


def test_no_published_event_lacks_a_subscriber() -> None:
    """Every published ``UIEvents`` member must be subscribed somewhere."""
    scan = _package_scan()
    orphans = {
        name: sources
        for name, sources in scan.published.items()
        if name in VALID and name not in scan.subscribed and name not in ALLOWED_ORPHANS
    }

    assert not orphans, (
        "Estes eventos são publicados e ninguém assina. EventBusV2.publish "
        "descarta em silêncio, então a mensagem simplesmente não chega:\n"
        + _format(orphans)
        + "\n\nAssine o evento ou pare de publicá-lo. NÃO acrescente a ALLOWED_ORPHANS."
    )


def test_allowlist_has_no_stale_entries() -> None:
    """An allowlisted event that gained a subscriber, or lost its publisher, leaves."""
    scan = _package_scan()
    stale = sorted(
        name for name in ALLOWED_ORPHANS if name in scan.subscribed or name not in scan.published
    )

    assert not stale, (
        "Estes eventos não são mais 'publicados sem assinante' e não precisam de "
        f"isenção. Remova de ALLOWED_ORPHANS: {', '.join(stale)}"
    )


def test_allowlist_only_names_real_events() -> None:
    """A typo in the allowlist would silence an event that does not exist."""
    unknown = sorted(ALLOWED_ORPHANS - VALID)

    assert not unknown, (
        "ALLOWED_ORPHANS cita nomes que não existem em UIEvents "
        f"(renomeados ou com erro de digitação): {', '.join(unknown)}"
    )


# ---------------------------------------------------------------------------
# Direction 2: subscribed, never published
# ---------------------------------------------------------------------------


def test_no_subscribed_event_lacks_a_publisher() -> None:
    """A handler for an event nobody publishes is code that cannot run."""
    scan = _package_scan()
    unreachable = {
        name: sources
        for name, sources in scan.subscribed.items()
        if name in VALID and name not in scan.published and name not in ALLOWED_UNPUBLISHED
    }

    assert not unreachable, (
        "Estes eventos têm assinante e ninguém publica: o handler nunca roda.\n"
        + _format(unreachable)
        + "\n\nPublique o evento ou remova o handler. NÃO acrescente a ALLOWED_UNPUBLISHED."
    )


def test_unpublished_allowlist_has_no_stale_entries() -> None:
    scan = _package_scan()
    stale = sorted(
        name
        for name in ALLOWED_UNPUBLISHED
        if name in scan.published or name not in scan.subscribed
    )

    assert not stale, (
        "Estes eventos não são mais 'assinados sem publicador'. "
        f"Remova de ALLOWED_UNPUBLISHED: {', '.join(stale)}"
    )


def test_unpublished_allowlist_only_names_real_events() -> None:
    unknown = sorted(ALLOWED_UNPUBLISHED - VALID)

    assert not unknown, (
        f"ALLOWED_UNPUBLISHED cita nomes que não existem em UIEvents: {', '.join(unknown)}"
    )


# ---------------------------------------------------------------------------
# Direction 3: never referenced outside event_bus_v2.py
# ---------------------------------------------------------------------------


def test_every_member_is_referenced_outside_the_enum() -> None:
    """A member nobody names is an invitation to publish into the void."""
    scan = _package_scan()
    unused = sorted(VALID - scan.referenced - ALLOWED_UNREFERENCED)

    assert not unused, (
        "Estes membros de UIEvents não são citados fora de event_bus_v2.py: "
        f"{', '.join(unused)}\n"
        "Use-os (publicar E assinar) ou apague-os. NÃO acrescente a ALLOWED_UNREFERENCED."
    )


def test_unreferenced_allowlist_has_no_stale_entries() -> None:
    scan = _package_scan()
    stale = sorted(ALLOWED_UNREFERENCED & scan.referenced)

    assert not stale, (
        f"Estes membros passaram a ser citados. Remova de ALLOWED_UNREFERENCED: {', '.join(stale)}"
    )


def test_unreferenced_allowlist_only_names_real_events() -> None:
    unknown = sorted(ALLOWED_UNREFERENCED - VALID)

    assert not unknown, (
        f"ALLOWED_UNREFERENCED cita nomes que não existem em UIEvents: {', '.join(unknown)}"
    )


# ---------------------------------------------------------------------------
# String literals
# ---------------------------------------------------------------------------


def _string_site_file(site: str) -> str:
    return site.rsplit(":", 1)[0]


def test_no_event_is_published_as_a_string() -> None:
    """The bus keys subscribers by member: a string reaches nobody."""
    sites = [
        site
        for site in _package_scan().string_publishes
        if _string_site_file(site) not in STRING_PUBLISH_EXEMPT_FILES
    ]

    assert not sites, (
        "Publicação com string literal no lugar de um membro de UIEvents "
        "(nenhum assinante pode recebê-la):\n  " + "\n  ".join(sites)
    )


def test_string_publish_exemptions_are_still_needed() -> None:
    """An exempt file that was deleted or fixed must leave the list."""
    offending = {_string_site_file(site) for site in _package_scan().string_publishes}
    stale = sorted(STRING_PUBLISH_EXEMPT_FILES - offending)

    assert not stale, (
        "Estes arquivos não publicam mais string literal. "
        f"Remova de STRING_PUBLISH_EXEMPT_FILES: {', '.join(stale)}"
    )


# ---------------------------------------------------------------------------
# Pinned pairs and the scanner's own reach
# ---------------------------------------------------------------------------


def test_show_error_aliases_are_subscribed() -> None:
    """The exact pair that made the wizard fail in silence stays wired.

    Pinned by name rather than left to the generic scan above: ``SHOW_ERROR``
    and ``UI_SHOW_ERROR`` are interchangeable to a reader and were not to the
    bus, which is precisely why the bug survived review.
    """
    subscribed = _package_scan().subscribed

    for name in ("SHOW_ERROR", "UI_SHOW_ERROR", "SHOW_INFO", "UI_SHOW_INFO", "SET_STATUS"):
        assert name in subscribed, f"UIEvents.{name} voltou a ficar sem assinante."


def test_uievents_is_never_imported_under_another_name() -> None:
    """The scan recognises members by the owner name ``UIEvents``.

    ``from zebtrack.ui.event_bus_v2 import UIEvents as E`` would make every
    ``E.FOO`` invisible to all three directions at once, so the alias is refused
    here instead of being half-supported by the scanner.
    """
    aliased = [
        f"{path.relative_to(REPO_ROOT).as_posix()}:{node.lineno}"
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_bytes()))
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name == "UIEvents" and alias.asname not in (None, "UIEvents")
    ]

    assert not aliased, (
        "UIEvents importado com outro nome; a varredura de eventos fica cega a ele:\n  "
        + "\n  ".join(aliased)
    )


def _scan_source(tmp_path: Path, source: str) -> Scan:
    module = tmp_path / "probe.py"
    module.write_bytes(source.encode("utf-8"))
    return scan_paths([module], root=tmp_path)


def test_scanner_follows_every_publish_and_subscribe_form(tmp_path: Path) -> None:
    """Each form the codebase uses is seen; a scanner blind to one hides its orphans."""
    scan = _scan_source(
        tmp_path,
        """
class Probe:
    _EVENTS_TO_HANDLE = (UIEvents.TUPLE_SUB,)

    def run(self, failed):
        self._publish_event(UIEvents.WRAPPED)
        self._publish_model_event(UIEvents.MODEL)
        self._publish_arduino_ui(UIEvents.ARDUINO, {})
        bus.publish(Event(UIEvents.POSITIONAL))
        bus.publish(Event(type=UIEvents.KEYWORD))
        self.emit_event(event_type=UIEvents.BY_KEYWORD)
        chosen = UIEvents.WARN if failed else UIEvents.INFO
        self._publish_event(chosen, None)
        if failed:
            event = UIEvents.BRANCH_A
        else:
            event = UIEvents.BRANCH_B
        dispatcher.publish_event(event, None)
        self._publish_event("A_STRING")
        for name in self._EVENTS_TO_HANDLE:
            bus.subscribe(name, handler)
        for ev, handler in {UIEvents.MAPPED: f}.items():
            bus.subscribe(ev, handler)
        self.bind_callback(UIEvents.BOUND, handler)
        register_direct_handler(UIEvents.DIRECT, handler)
""",
    )

    assert set(scan.published) == {
        "WRAPPED",
        "MODEL",
        "ARDUINO",
        "POSITIONAL",
        "KEYWORD",
        "BY_KEYWORD",
        "WARN",
        "INFO",
        "BRANCH_A",
        "BRANCH_B",
    }
    assert set(scan.subscribed) == {"TUPLE_SUB", "MAPPED", "BOUND", "DIRECT"}
    assert scan.string_publishes == ["probe.py:19"]
