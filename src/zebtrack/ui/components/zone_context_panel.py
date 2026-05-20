"""Zone tab context panel (Etapa 4).

Compact LabelFrame that summarises, in the Zones tab, the inputs feeding the
current calibration:

1. Active source (file name OR ``"Câmera ao vivo (idx N)"`` for live projects).
2. Aquarium-detection model path + method (``det`` / ``seg``).
3. Provenance badge for the main polygon — ``auto`` (green),
   ``manual`` (orange) or ``"Não definido"`` (gray) when no polygon exists.

The panel subscribes to ``LIVE_POLYGON_SOURCE_CHANGED`` (live calibration
mutations), ``UI_DISPLAY_VIDEO_FRAME`` (active video changes) and
``PROJECT_OPENED`` (project reload — re-resolves the aquarium model path).
Handlers always marshal updates onto the Tk main thread via ``root.after(0, …)``
because the event bus publishes synchronously on the calling thread (which
may be a worker).
"""

from __future__ import annotations

from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.ui.event_bus_v2 import UIEvents

if TYPE_CHECKING:
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.services.weight_manager import WeightManager
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


_BADGE_STYLES: dict[str, tuple[str, str, str]] = {
    # source → (label, foreground, background)
    "auto": ("Auto-detectado", "white", "#2e7d32"),  # green
    "manual": ("Editado manualmente", "white", "#ef6c00"),  # orange
    "none": ("Não definido", "white", "#757575"),  # gray
}


class _Sentinel:
    """Singleton sentinel used by ``ZoneContextPanel.update`` to distinguish
    "leave unchanged" from "explicitly clear to None"."""

    __slots__ = ()


_SENTINEL_DEFAULT = _Sentinel()


class ZoneContextPanel:
    """Compact context panel for the Zone tab.

    Construction is deferred: callers instantiate the panel, then call
    :meth:`build` with the parent Tk container. This keeps unit tests cheap
    (they can drive update logic without touching Tk at all).
    """

    def __init__(
        self,
        *,
        event_bus: EventBusV2 | None,
        project_manager: ProjectManager | None,
        weight_manager: WeightManager | None,
        root: Any | None,
    ) -> None:
        self._event_bus = event_bus
        self._project_manager = project_manager
        self._weight_manager = weight_manager
        self._root = root

        # State cached between event firings.
        self._active_source: str = "—"
        self._model_caption: str = "—"
        self._polygon_source: str | None = None

        # Tk widgets created in build().
        self.frame: ttk.LabelFrame | None = None
        self._source_label: ttk.Label | None = None
        self._model_label: ttk.Label | None = None
        self._badge_label: ttk.Label | None = None

        self._subscribed = False

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def build(self, parent: Any) -> ttk.LabelFrame:
        """Build the LabelFrame and attach it under ``parent``.

        Returns the created ``ttk.LabelFrame`` so callers can ``pack`` /
        ``grid`` it themselves if they need custom layout (the default
        wiring in ``ZoneControlBuilder`` packs at the top of the tab).
        """
        self.frame = ttk.LabelFrame(parent, text="Contexto da Calibração", padding=8)

        # Row 0 — active source
        self._source_label = ttk.Label(
            self.frame,
            text=self._format_source_line(self._active_source),
            anchor="w",
            justify="left",
            wraplength=320,
        )
        self._source_label.pack(fill="x", pady=(0, 2))

        # Row 1 — model caption
        self._model_label = ttk.Label(
            self.frame,
            text=self._format_model_line(self._model_caption),
            anchor="w",
            justify="left",
            wraplength=320,
        )
        self._model_label.pack(fill="x", pady=(0, 4))

        # Row 2 — provenance badge
        badge_text, fg, bg = _badge_visuals(self._polygon_source)
        self._badge_label = ttk.Label(
            self.frame,
            text=badge_text,
            foreground=fg,
            background=bg,
            padding=(8, 2),
            anchor="center",
        )
        self._badge_label.pack(anchor="w")

        # Seed initial state from project (best-effort — no exceptions out).
        self.refresh_from_project()

        if self._event_bus is not None and not self._subscribed:
            self._event_bus.subscribe(
                UIEvents.LIVE_POLYGON_SOURCE_CHANGED, self._on_polygon_source_event
            )
            self._event_bus.subscribe(UIEvents.UI_DISPLAY_VIDEO_FRAME, self._on_video_frame_event)
            self._event_bus.subscribe(UIEvents.PROJECT_OPENED, self._on_project_opened)
            self._subscribed = True

        return self.frame

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(
        self,
        *,
        active_source: str | None = None,
        model_caption: str | None = None,
        polygon_source: str | None | _Sentinel = _SENTINEL_DEFAULT,
    ) -> None:
        """Refresh any of the three rows.

        ``polygon_source`` is treated with a sentinel so callers can
        distinguish "leave unchanged" from "explicitly clear to None".
        """
        if active_source is not None:
            self._active_source = active_source
            if self._source_label is not None:
                self._source_label.config(text=self._format_source_line(active_source))

        if model_caption is not None:
            self._model_caption = model_caption
            if self._model_label is not None:
                self._model_label.config(text=self._format_model_line(model_caption))

        if polygon_source is not _SENTINEL_DEFAULT:
            self._polygon_source = polygon_source  # type: ignore[assignment]
            if self._badge_label is not None:
                badge_text, fg, bg = _badge_visuals(self._polygon_source)
                self._badge_label.config(text=badge_text, foreground=fg, background=bg)

    def refresh_from_project(self) -> None:
        """Re-resolve project-derived fields (active source + model caption)."""
        self._active_source = self._compute_active_source()
        self._model_caption = self._compute_model_caption()
        if self._source_label is not None:
            self._source_label.config(text=self._format_source_line(self._active_source))
        if self._model_label is not None:
            self._model_label.config(text=self._format_model_line(self._model_caption))

        # Seed polygon source from the project's existing zone data so the
        # badge survives a project reload even before the next calibration.
        if self._project_manager is not None:
            try:
                zone_data = self._project_manager.get_zone_data()
                if zone_data and getattr(zone_data, "polygon", None):
                    meta = getattr(zone_data, "metadata", {}) or {}
                    method = meta.get("detection_method")
                    if method in ("auto", "manual"):
                        self.update(polygon_source=method)
            except Exception as exc:
                log.debug("zone_context_panel.refresh.zone_data_unavailable", error=str(exc))

    # ------------------------------------------------------------------
    # Event handlers (may run on a worker thread)
    # ------------------------------------------------------------------

    def _on_polygon_source_event(self, payload: Any) -> None:
        source = getattr(payload, "source", None)
        self._dispatch_on_ui(lambda: self.update(polygon_source=source))

    def _on_video_frame_event(self, payload: Any) -> None:
        video_path = getattr(payload, "video_path", None)
        active = self._format_active_source_from_path(video_path)
        self._dispatch_on_ui(lambda: self.update(active_source=active))

    def _on_project_opened(self, _payload: Any) -> None:
        self._dispatch_on_ui(self.refresh_from_project)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _dispatch_on_ui(self, fn: Any) -> None:
        """Run ``fn`` on the Tk main thread (defensive: silent no-op if no root)."""
        root = self._root
        if root is not None and hasattr(root, "after"):
            try:
                root.after(0, fn)
                return
            except Exception as exc:
                log.debug("zone_context_panel.dispatch.after_failed", error=str(exc))
        # Last-resort fallback for test contexts without a real root.
        try:
            fn()
        except Exception as exc:
            log.debug("zone_context_panel.dispatch.inline_failed", error=str(exc))

    def _compute_active_source(self) -> str:
        pm = self._project_manager
        if pm is None:
            return "—"
        try:
            if pm.get_project_type() == "live":
                project_data = pm.project_data or {}
                idx = project_data.get("camera_index")
                if idx is None:
                    return "Câmera ao vivo"
                return f"Câmera ao vivo (idx {idx})"
        except Exception as exc:
            log.debug("zone_context_panel.active_source.project_type_failed", error=str(exc))
        return "—"

    def _compute_model_caption(self) -> str:
        pm = self._project_manager
        wm = self._weight_manager
        if pm is None or wm is None:
            return "—"
        project_data = pm.project_data or {}
        method = "det"
        if "model_selection" in project_data:
            method = project_data["model_selection"].get("aquarium_method", method)
        perspective: str | None = None
        # Canonical key set by ``ProjectWorkflowService._persist_project_data``
        # — read that first. Fall back to the nested ``calibration
        # .behavioral_analysis`` layout used by some legacy project files /
        # templates so older saved projects still surface the right model.
        try:
            bc = project_data.get("behavioral_config") or {}
            perspective = bc.get("aquarium_perspective") or None
            if perspective is None:
                cal = project_data.get("calibration") or {}
                ba = cal.get("behavioral_analysis") or {}
                perspective = ba.get("aquarium_perspective") or None
        except AttributeError:
            perspective = None
        try:
            path = wm.get_weight_path_by_method(
                method=method, task="aquarium", perspective=perspective
            )
        except Exception as exc:
            log.debug("zone_context_panel.model_caption.weight_lookup_failed", error=str(exc))
            return "—"
        if not path:
            return f"sem modelo · método {method}"
        return f"{Path(str(path)).name} · método {method}"

    def _format_active_source_from_path(self, video_path: Path | str | None) -> str:
        if not video_path:
            return self._active_source or "—"
        path = Path(video_path) if isinstance(video_path, str) else video_path
        base = path.name
        if not base:
            return str(path)
        # Reference frames used during live calibration shouldn't masquerade as
        # the user's file selection.
        if base == "live_camera_reference_frame.png":
            return self._compute_active_source() or "Câmera ao vivo"
        return base

    @staticmethod
    def _format_source_line(value: str) -> str:
        return f"Fonte ativa: {value}"

    @staticmethod
    def _format_model_line(value: str) -> str:
        return f"Modelo do aquário: {value}"


def _badge_visuals(source: str | None) -> tuple[str, str, str]:
    """Map a polygon source tag to (text, foreground, background)."""
    if source == "auto":
        return _BADGE_STYLES["auto"]
    if source == "manual":
        return _BADGE_STYLES["manual"]
    return _BADGE_STYLES["none"]
