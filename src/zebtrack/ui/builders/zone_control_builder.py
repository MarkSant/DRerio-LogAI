"""
Zone Control Builder for creating zone configuration and drawing widgets.

Extracted from WidgetFactory to separate concern of zone control construction.
"""

import os
from datetime import datetime
from tkinter import BooleanVar
from typing import TYPE_CHECKING

import structlog

from zebtrack.ui import payloads

if TYPE_CHECKING:
    from zebtrack.ui.components.zone_context_panel import ZoneContextPanel

log = structlog.get_logger()


class ZoneControlBuilder:
    """
    Builder for creating zone configuration and drawing widgets.
    """

    def __init__(self, gui, event_bus_v2=None):
        """
        Initialize ZoneControlBuilder.

        Args:
            gui: Reference to ApplicationGUI instance
            event_bus_v2: EventBusV2 instance for v4.0 Event-Driven Architecture (optional)
        """
        self.gui = gui
        self.event_bus_v2 = event_bus_v2
        # Etapa 4 — Zone tab context panel. Never populated: the widget-building
        # code path that used to construct it (create_zone_control_widgets) was
        # dead (the real Zones tab is built by ZoneControlsWidget, not this
        # class) and was removed. Kept as a typed placeholder rather than wiring
        # ZoneContextPanel into the live tab, which is a separate decision.
        self.zone_context_panel: ZoneContextPanel | None = None
        # Audit Erro 4 (2026-05-25): opt-in flag that the user toggles before
        # Concluir to ask ZebTrack to reuse the current polygon as a template
        # in the next auto-detection runs. Lazily created in
        # ``_ensure_reuse_template_var`` because BooleanVar() requires a
        # default Tk root (headless unit tests instantiate the builder
        # without a real Tk).
        self._reuse_arena_template_var: BooleanVar | None = None

    def _ensure_reuse_template_var(self) -> BooleanVar:
        """Lazily create the reuse-template BooleanVar.

        Returns the existing instance or constructs one bound to the GUI
        root window (which exists by the time the widget tree is built).
        """
        if self._reuse_arena_template_var is None:
            master = getattr(self.gui, "root", None)
            self._reuse_arena_template_var = BooleanVar(master=master, value=False)
        return self._reuse_arena_template_var

    @property
    def reuse_arena_template_var(self) -> BooleanVar | None:
        """Public accessor — returns ``None`` until the widget is built."""
        return self._reuse_arena_template_var

    def _on_roi_rule_change(self, event=None) -> None:
        """Toggle visibility of ROI parameter frames based on the selected rule.

        This handles the <<ComboboxSelected>> event from the ROI rule combobox
        and the initial display setup at build time.
        """
        rule = self.gui.roi_inclusion_rule_var.get()

        # Hide all parameter frames first
        if hasattr(self.gui, "radius_frame") and self.gui.radius_frame:
            self.gui.radius_frame.pack_forget()
        if hasattr(self.gui, "overlap_frame") and self.gui.overlap_frame:
            self.gui.overlap_frame.pack_forget()

        if rule == "centroid_in":
            help_text = (
                "Considera dentro quando o centróide do animal está dentro do "
                "polígono da ROI. Simples e rápido; pode perder entradas parciais "
                "(ex.: cabeça entra primeiro)."
            )
        elif rule == "centroid_in_on_buffered_roi":
            if self.gui.radius_frame:
                self.gui.radius_frame.pack(fill="x", pady=2)
            help_text = (
                "Igual ao centróide, porém com ROI dilatada por r para capturar "
                "entradas parciais (ex.: cabeça). r em cm se houver calibração; "
                "senão em px."
            )
        elif rule == "bbox_intersects":
            if self.gui.overlap_frame:
                self.gui.overlap_frame.pack(fill="x", pady=2)
            if hasattr(self.gui, "overlap_help_label") and self.gui.overlap_help_label:
                self.gui.overlap_help_label.config(
                    text="A detecção é considerada dentro da ROI quando a fração "
                    "de área do bbox contida na ROI atinge este valor."
                )
            help_text = (
                "Considera dentro quando o retângulo do animal (bbox) sobrepõe "
                "a ROI ao menos pela fração definida. Captura entradas parciais; "
                "pode superestimar em bordas."
            )
        elif rule == "seg_overlap":
            if self.gui.overlap_frame:
                self.gui.overlap_frame.pack(fill="x", pady=2)
            if hasattr(self.gui, "overlap_help_label") and self.gui.overlap_help_label:
                self.gui.overlap_help_label.config(
                    text="Requer dados de máscara. Se não houver, selecione outra regra."
                )
            help_text = (
                "Considera dentro com base na sobreposição da máscara do animal "
                "com a ROI. Requer segmentação; mais preciso e mais custoso."
            )
        else:
            help_text = ""

        if hasattr(self.gui, "rule_help_label") and self.gui.rule_help_label:
            self.gui.rule_help_label.config(text=help_text)

    def _emit_apply_roi_settings(self) -> None:
        """Emit ZONE_APPLY_ROI_SETTINGS with the ROI rule selected in the UI.

        Antes ia para ``DETECTOR_UPDATE_PARAMETERS``, que descarta ``rule``/
        ``buffer_radius``/``overlap_ratio`` sem persistir nada.

        Os campos vão CRUS: ``float()`` aqui estoura com texto inválido dentro
        do callback do Tk. Quem valida é ``resolve_roi_rule``.
        """
        from zebtrack.ui import payloads
        from zebtrack.ui.event_bus_v2 import Event, UIEvents

        if self.event_bus_v2:
            self.event_bus_v2.publish(
                Event(
                    type=UIEvents.ZONE_APPLY_ROI_SETTINGS,
                    data=payloads.RoiSettingsApplyPayload(
                        rule=self.gui.roi_inclusion_rule_var.get(),
                        buffer_radius=self.gui.roi_buffer_radius_var.get(),
                        overlap_ratio=self.gui.roi_overlap_ratio_var.get(),
                    ),
                    source="ZoneControlBuilder._emit_apply_roi_settings",
                )
            )
        else:
            log.warning("zone_control_builder.apply_roi_settings.no_event_bus")

    def _refresh_video_tree_dual_mode(self, filter_text: str | None = None):
        """Refresh video tree via Event Bus.

        Args:
            filter_text: Optional filter text for video tree
        """
        # NEW PATH - Event-Driven Architecture v4.0
        if self.event_bus_v2:
            from zebtrack.ui import payloads
            from zebtrack.ui.event_bus_v2 import Event, UIEvents

            self.event_bus_v2.publish(
                Event(
                    type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                    data=payloads.VideoTreeRefreshRequestedPayload(filter_text=filter_text),
                    source="ZoneControlBuilder._refresh_video_tree_dual_mode",
                )
            )
        else:
            log.warning("zone_control_builder.refresh_tree.no_event_bus")

    def _apply_arena_template_choice(self) -> None:
        """Persist or drop the arena template based on the user's checkbox.

        Audit Erro 4 (2026-05-25): the "Reaproveitar este polígono em
        próximas autodetecções" checkbox is the explicit opt-in gate. When
        checked at Concluir time, copy the currently active arena polygon
        into ``project_data["arena_template"]`` so the next call to
        ``live_calibration_coordinator.run_live_calibration`` can seed the
        preview with it instead of running detection from scratch. When
        unchecked, drop any pre-existing template so it doesn't leak into
        the next video.
        """
        controller = getattr(self.gui, "controller", None)
        if controller is None or controller.project_manager is None:
            return

        pm = controller.project_manager
        project_data = getattr(pm, "project_data", None)
        if not isinstance(project_data, dict):
            return

        # The lazy var may still be None if the user opened/closed the project
        # without the zone controls ever being built (defensive fallback).
        reuse_var = self._reuse_arena_template_var
        reuse = bool(reuse_var.get()) if reuse_var is not None else False

        if not reuse:
            if project_data.pop("arena_template", None) is not None:
                log.info("zone_control_builder.arena_template.discarded")
            return

        # Pull the latest confirmed polygon from the active zone data.
        try:
            zone_data = pm.get_zone_data()
        except Exception:
            log.debug("zone_control_builder.arena_template.load_failed", exc_info=True)
            return

        polygon = list(getattr(zone_data, "polygon", []) or [])
        if not polygon:
            log.info("zone_control_builder.arena_template.skip_empty_polygon")
            project_data.pop("arena_template", None)
            return

        project_data["arena_template"] = {
            "polygon": [list(point) for point in polygon],
            "created_at": datetime.now().isoformat(),
        }
        log.info(
            "zone_control_builder.arena_template.saved",
            points=len(polygon),
        )

    def _on_conclude_video(self):
        """Handle 'Concluir Edição do Vídeo' button click."""
        # 1. Save Project (Persist flags and data)
        if hasattr(self.gui, "controller") and self.gui.controller.project_manager:
            try:
                self._apply_arena_template_choice()
                self.gui.controller.project_manager.save_project()
            except Exception as e:
                # In Single Video Mode, project might not be created yet.
                # This is expected and safe to ignore for "Conclude" action which mostly updates UI.
                if "ProjectInvalidError" in str(
                    type(e).__name__
                ) or "caminho do projeto não definido" in str(e):
                    log.debug("zone_control_builder.save_project.skipped", reason=str(e))
                else:
                    log.error("zone_control_builder.save_project.failed", error=str(e))

        # Clear the dirty flag — zones are now fully committed
        if hasattr(self.gui, "_zones_dirty"):
            self.gui._zones_dirty = False

        self._refresh_video_tree_dual_mode()

        from zebtrack.ui.event_bus_v2 import Event, UIEvents

        # Tracks whether we committed an interactive edit below. When we do,
        # ZONE_SAVE_ARENA → ZONES_UPDATED already schedules an overview refresh
        # (with POST-save flags), so we must NOT force our own — that would
        # rebuild the grid with pre-save data and duplicate the work.
        zone_saved = False

        if hasattr(self.gui, "event_bus") and self.gui.event_bus:
            # 2. Commit an in-progress interactive edit, but ONLY when one is
            # actually active. ZONE_SAVE_ARENA → CanvasManager.save_arena() falls
            # back to save_manual_arena(edited_polygon_points) when no zone is
            # being edited; in the live auto-detect flow edited_polygon_points is
            # empty, so emitting it unconditionally would overwrite the freshly
            # detected polygon with an empty one. Gate on the same flag save_arena
            # itself reads (CanvasManager.current_editing_zone).
            canvas_manager = getattr(self.gui, "canvas_manager", None)
            editing_active = bool(
                getattr(canvas_manager, "current_editing_zone", None)
                or getattr(self.gui, "current_editing_zone", None)
            )
            has_edited_points = bool(getattr(self.gui, "edited_polygon_points", None))
            if editing_active and has_edited_points:
                self.gui.event_bus.publish(
                    Event(type=UIEvents.ZONE_SAVE_ARENA, data=payloads.EmptyPayload())
                )
                zone_saved = True
                log.info("zone_control_builder.conclude_video.zone_saved_event_emitted")

        # Refresh the main-control per-video grid (project overview). The tree
        # refresh above only rebuilds the drawing-tab selector; the overview is a
        # separate view. Skip when we published ZONE_SAVE_ARENA above: that path
        # emits ZONES_UPDATED, whose handler already schedules an overview
        # refresh with the POST-save flags — forcing one here would rebuild with
        # pre-save data and duplicate the work.
        if not zone_saved:
            video_selector_manager = getattr(self.gui, "video_selector_manager", None)
            if video_selector_manager is not None:
                try:
                    video_selector_manager.request_overview_refresh(
                        reason="zones_concluded", force=True
                    )
                except Exception as exc:  # except Exception justified: must not break Concluir
                    log.debug(
                        "zone_control_builder.conclude_video.overview_refresh_failed",
                        error=str(exc),
                        exc_info=True,
                    )

        # 4. Optional: Feedback
        if hasattr(self.gui, "set_status"):
            self.gui.set_status("Edição concluída. Dados salvos e indicadores atualizados.")

        # 5. Next-step guidance for live projects.
        self._show_conclude_next_step_guidance()

    def _show_conclude_next_step_guidance(self) -> None:
        """Point the user to the next action after committing zone edits.

        "Concluir" only saves zone/ROI/Arduino-binding data — it never starts
        a recording. When a live session is already deferred waiting on this
        confirmation, the "⏳ Sessão pendente" banner built by ``ZoneControls``
        already tells the user to click "▶️ Iniciar Gravação" there, so we
        skip this to avoid a redundant dialog. Otherwise (proactive zone setup
        with no pending session) there is currently no other cue in the UI, so
        point the user at the "Controle Principal" tab. Only applies to live
        projects — pre-recorded projects have their own explicit "Iniciar
        Análise" / "Enviar Vídeo Selecionado para Análise" buttons.
        """
        zone_controls = getattr(self.gui, "zone_controls", None)
        if zone_controls is not None and zone_controls.has_pending_live_session():
            return

        project_manager = getattr(getattr(self.gui, "controller", None), "project_manager", None)
        get_project_type = getattr(project_manager, "get_project_type", None)
        if get_project_type is None or get_project_type() != "live":
            return

        dialog_manager = getattr(self.gui, "dialog_manager", None)
        if dialog_manager is None:
            return
        dialog_manager.show_info(
            "Zonas Concluídas",
            "Zonas, ROIs e comandos Arduino salvos.\n\n"
            'Para iniciar a gravação ao vivo, vá até a aba "Controle Principal" '
            'e clique em "Iniciar Gravação".',
        )

    def _on_send_selected_video_to_analysis(self) -> None:
        """Open analysis configuration for the real video selected in the zone tree."""
        tree = getattr(self.gui, "video_selector_tree", None)
        selection = tree.selection() if tree is not None else ()
        if tree is None or not selection:
            self.gui.dialog_manager.show_warning(
                "Nenhum Vídeo Selecionado",
                "Selecione um vídeo gravado na lista antes de enviá-lo para análise.",
            )
            return

        tags = tree.item(selection[0], "tags") or ()
        video_path = str(tags[0]) if tags else ""
        is_video_entry = video_path and video_path not in {"group", "day", "subject"}
        if not is_video_entry or not os.path.isfile(video_path):
            self.gui.dialog_manager.show_info(
                "Vídeo Indisponível",
                "Apenas vídeos gravados podem ser enviados para análise. "
                "Sessões planejadas precisam ser gravadas primeiro.",
            )
            return

        zone_controls = getattr(self.gui, "zone_controls", None)
        if zone_controls and zone_controls.has_pending_live_session():
            self.gui.dialog_manager.show_info(
                "Gravação Pendente",
                "Inicie ou cancele a gravação pendente antes de enviar outro vídeo para análise.",
            )
            return

        event_dispatcher = getattr(self.gui, "event_dispatcher", None)
        if event_dispatcher is None:
            log.error("zone_control_builder.send_to_analysis.no_event_dispatcher")
            return

        event_dispatcher.handle_analyze_single_video_clicked(video_path=video_path)
