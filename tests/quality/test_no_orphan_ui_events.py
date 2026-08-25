"""No ``UIEvents`` member may be published without a subscriber.

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

The fix is always the same: subscribe the member, or stop publishing it. A
handler that merely logs does not count -- the point is that some component
reacts.

Events in ``ALLOWED_ORPHANS`` are grandfathered. That list only ever SHRINKS.
Two kinds live there today, and they want opposite treatment:

* Published by a widget that is itself never instantiated (``ControlPanelWidget``,
  ``AnalysisControlsWidget``). These are residue -- delete the widget and the
  entry goes with it.
* Redundant notifications published beside a direct callback that already does
  the work (``processing_reports`` buttons). Harmless, but they make the bus
  look busier than it is.

Adding a new entry is the one thing this test exists to prevent. If a new event
genuinely has no consumer yet, do not publish it yet.
"""

from __future__ import annotations

import ast
from pathlib import Path

from zebtrack.ui.event_bus_v2 import UIEvents

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "src" / "zebtrack"

# Methods that register a reaction to an event. ``register_handler`` and
# ``register_direct_handler`` are EventDispatcher's own wrappers around
# ``EventBusV2.subscribe``; they count exactly the same.
SUBSCRIBE_CALLS = frozenset({"subscribe", "register_handler", "register_direct_handler"})

# Methods that put an event on the bus. ``publish`` takes either a bare member
# or an ``Event(type=...)``; both forms are collected below.
PUBLISH_CALLS = frozenset({"publish", "publish_event", "emit_event"})

# Events published today with nobody listening. NEVER add to this list.
ALLOWED_ORPHANS = frozenset(
    {
        # -- publicados por widgets que nunca são instanciados (código morto) --
        "CONTROL_INTERVAL_CHANGED",
        "CONTROL_PREVIEW_TOGGLED",
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
        "LIVE_RECORDING_PENDING",
        "LIVE_SESSION_STARTED",
        "LIVE_SESSION_STOPPED",
        "PROJECT_CREATED",
        "RECORDING_STARTED",
        "VIDEO_METADATA_UPDATED",
        "ZONE_MULTI_AUTO_DETECT_FAILED",
    }
)


def _event_name(node: ast.expr) -> str | None:
    """Return the ``UIEvents`` member name referenced by *node*, if any.

    Accepts both ``UIEvents.FOO`` and a bare ``FOO`` already imported into the
    module namespace; the caller filters against the real enum afterwards, so a
    false positive here costs nothing.
    """
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _collect(path: Path) -> tuple[set[str], dict[str, set[str]]]:
    """Return ``(subscribed, published)`` event names found in one module.

    ``published`` maps the event name to the file it was published from, so the
    failure message can point at the call site instead of just naming the event.
    """
    subscribed: set[str] = set()
    published: dict[str, set[str]] = {}

    tree = ast.parse(path.read_text(encoding="utf-8"))
    rel = path.relative_to(REPO_ROOT).as_posix()

    for node in ast.walk(tree):
        # Tuples of events fed to a subscription loop (MainViewModelRuntime's
        # ``_EVENTS_TO_HANDLE``) are subscriptions too -- the loop that consumes
        # them is one ``subscribe`` call for many events, so matching only the
        # call would report every member of the tuple as an orphan.
        if isinstance(node, ast.Assign):
            targets = {_event_name(t) for t in node.targets}
            if "_EVENTS_TO_HANDLE" in targets:
                for sub in ast.walk(node.value):
                    name = _event_name(sub) if isinstance(sub, ast.Attribute) else None
                    if name:
                        subscribed.add(name)
            continue

        if not isinstance(node, ast.Call):
            continue

        func = node.func
        attr = func.attr if isinstance(func, ast.Attribute) else None

        if attr in SUBSCRIBE_CALLS and node.args:
            name = _event_name(node.args[0])
            if name:
                subscribed.add(name)
            continue

        if attr in PUBLISH_CALLS:
            for name in _published_names(node):
                published.setdefault(name, set()).add(rel)

    return subscribed, published


def _published_names(call: ast.Call) -> set[str]:
    """Event names put on the bus by a single ``publish``-family call.

    Two forms in the codebase: ``publish(UIEvents.FOO, payload)`` and
    ``publish(Event(type=UIEvents.FOO, ...))``. The second hides the member one
    level down, inside a keyword of a nested call.
    """
    names: set[str] = set()

    if call.args:
        direct = _event_name(call.args[0])
        if direct:
            names.add(direct)

        first = call.args[0]
        if isinstance(first, ast.Call):
            for kw in first.keywords:
                if kw.arg == "type":
                    nested = _event_name(kw.value)
                    if nested:
                        names.add(nested)

    return names


def test_no_published_event_lacks_a_subscriber() -> None:
    """Every published ``UIEvents`` member must be subscribed somewhere."""
    valid = {member.name for member in UIEvents}

    subscribed: set[str] = set()
    published: dict[str, set[str]] = {}

    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        module_subscribed, module_published = _collect(path)
        subscribed |= module_subscribed
        for name, sources in module_published.items():
            published.setdefault(name, set()).update(sources)

    orphans = {
        name: sources
        for name, sources in published.items()
        if name in valid and name not in subscribed and name not in ALLOWED_ORPHANS
    }

    assert not orphans, (
        "Estes eventos são publicados e ninguém assina. EventBusV2.publish "
        "descarta em silêncio, então a mensagem simplesmente não chega:\n"
        + "\n".join(
            f"  UIEvents.{name}  <- {', '.join(sorted(sources))}"
            for name, sources in sorted(orphans.items())
        )
        + "\n\nAssine o evento ou pare de publicá-lo. NÃO acrescente a ALLOWED_ORPHANS."
    )


def test_allowlist_has_no_stale_entries() -> None:
    """An allowlisted event that gained a subscriber must leave the list.

    Without this the allowlist would only grow stale: an event fixed in passing
    keeps its exemption, and the next regression on that same event goes
    unnoticed because the guard was told to look away.
    """
    subscribed: set[str] = set()
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        module_subscribed, _module_published = _collect(path)
        subscribed |= module_subscribed

    stale = sorted(ALLOWED_ORPHANS & subscribed)

    assert not stale, (
        "Estes eventos ganharam assinante e não precisam mais de isenção. "
        f"Remova de ALLOWED_ORPHANS: {', '.join(stale)}"
    )


def test_allowlist_only_names_real_events() -> None:
    """A typo in the allowlist would silence an event that does not exist."""
    valid = {member.name for member in UIEvents}
    unknown = sorted(ALLOWED_ORPHANS - valid)

    assert not unknown, (
        "ALLOWED_ORPHANS cita nomes que não existem em UIEvents "
        f"(renomeados ou com erro de digitação): {', '.join(unknown)}"
    )


def test_show_error_aliases_are_subscribed() -> None:
    """The exact pair that made the wizard fail in silence stays wired.

    Pinned by name rather than left to the generic scan above: ``SHOW_ERROR``
    and ``UI_SHOW_ERROR`` are interchangeable to a reader and were not to the
    bus, which is precisely why the bug survived review.
    """
    subscribed: set[str] = set()
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        module_subscribed, _module_published = _collect(path)
        subscribed |= module_subscribed

    for name in ("SHOW_ERROR", "UI_SHOW_ERROR", "SHOW_INFO", "UI_SHOW_INFO", "SET_STATUS"):
        assert name in subscribed, f"UIEvents.{name} voltou a ficar sem assinante."
