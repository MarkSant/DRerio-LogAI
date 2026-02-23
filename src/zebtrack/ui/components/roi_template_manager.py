from __future__ import annotations

import json
from pathlib import Path
from tkinter import Misc, StringVar, Tcl, TclError, filedialog, ttk
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from zebtrack.ui.components.dialog_manager import DialogManager
    from zebtrack.ui.gui import ApplicationGUI

log = structlog.get_logger()


class _FallbackStringVar:
    def __init__(self, value: str = "") -> None:
        self._value = value

    def get(self) -> str:
        return self._value

    def set(self, value: str) -> None:
        self._value = value


class ROITemplateManager:
    """Manages ROI template operations (load, apply, delete, import, save)."""

    def __init__(
        self,
        project_manager,
        gui_parent: ApplicationGUI,
        event_bus_v2=None,
        *,
        dialog_manager: DialogManager | None = None,
    ):
        self.project_manager = project_manager
        self.gui = gui_parent
        self.event_bus_v2 = event_bus_v2
        self._dialog_manager = dialog_manager
        self._cache: list[dict[str, Any]] = []
        self.template_var: StringVar | _FallbackStringVar
        master = getattr(gui_parent, "root", None) or getattr(gui_parent, "tk", None)
        if not isinstance(master, Misc):
            # Fallback to a Tcl interpreter to avoid default-root failures in headless tests.
            master = Tcl()
        try:
            self.template_var = StringVar(master=master, value="")
        except TclError:
            self.template_var = _FallbackStringVar("")
        # Delete button reference will be managed via gui or passed in?
        # The plan says self.delete_button = None initially.
        self.delete_button: ttk.Button | None = None

    @property
    def dialog_manager(self) -> DialogManager:
        """Return injected DialogManager or fall back to gui.dialog_manager."""
        return self._dialog_manager or self.gui.dialog_manager

    def refresh_templates(self, clear_selection: bool = False) -> None:
        """
        Load templates from the project manager and refresh the cache.

        Handles:
        - Template loading
        - File validation
        - Display name enrichment
        - Auto-selection logic
        """
        try:
            templates = self.project_manager.list_roi_templates()
        except (OSError, ValueError, KeyError) as exc:
            log.warning("roi_templates.refresh_failed", error=str(exc))
            templates = []

        # Validate and enrich
        enriched = self._validate_and_enrich_templates(templates)
        self._cache = enriched

        # Update UI
        display_names = [t["display_name"] for t in enriched]
        self._update_combobox_values(display_names)

        # Handle selection logic
        if clear_selection:
            self._handle_clear_selection(display_names)
        else:
            self._handle_refresh_selection(display_names)

        self._update_delete_button_state()

    def _validate_and_enrich_templates(self, templates: list[dict]) -> list[dict]:
        """Validate templates and add display metadata."""
        enriched = []

        for template in templates:
            if not isinstance(template, dict):
                continue

            # Validate name
            name = template.get("name", "").strip()
            if not name:
                log.warning("roi_templates.skipping_empty_name", template=template)
                continue

            # Validate file if file-based
            if not self._validate_template_file(template):
                continue

            # Enrich with display data
            entry = dict(template)
            entry["display_name"] = self._format_display_name(entry)
            entry["identifier"] = self._build_identifier(entry)

            if entry.get("display_name", "").strip():
                enriched.append(entry)

        return enriched

    def _validate_template_file(self, template: dict) -> bool:
        """Validate that the template file exists and is readable."""
        file_path = template.get("file")
        if not file_path:
            return True  # Non-file-based templates are valid

        # Fix common path issues
        path_str = str(file_path)
        if "\\,zebtrack\\" in path_str or "/,zebtrack/" in path_str:
            path_str = path_str.replace("\\,zebtrack\\", "\\.zebtrack\\")
            path_str = path_str.replace("/,zebtrack/", "/.zebtrack/")
            # Update the template dict in place if needed for later use?
            template["file"] = path_str
            # The plan logic implies we just validate here.

        path = Path(path_str)
        if path.exists() and path.is_file():
            return True

        # Check relative to project path if available
        project_path = getattr(self.project_manager, "project_path", None)
        if project_path:
            project_resolved = Path(project_path) / path_str
            if project_resolved.exists() and project_resolved.is_file():
                return True

        log.warning("roi_templates.invalid_file", file=path_str)
        return False

        return True

    def _format_display_name(self, template: dict) -> str:
        """Format template display name with location indicator."""
        name = template.get("name", "")
        location = template.get("location", "")

        if location == "project":
            return f"📁 {name}"
        elif location == "global":
            return f"🌐 {name}"
        else:
            return name

    def _build_identifier(self, template: dict) -> str:
        """Build a unique identifier for the template."""
        name = template.get("name", "")
        location = template.get("location", "")
        file_path = template.get("file", "")

        if file_path:
            return f"{location}:{name}:{file_path}"
        else:
            return f"{location}:{name}"

    def apply_template(self) -> bool:
        """Apply the selected template to the active video."""
        selected = self.get_selected_template()
        if not selected:
            self._show_template_selection_error()
            return False

        active_video = self._get_active_video()
        if not active_video:
            self.dialog_manager.show_warning(
                "Vídeo não selecionado", "Selecione um vídeo na lista antes de aplicar o template."
            )
            return False

        try:
            zone_data = self.project_manager.load_roi_template(
                selected["name"],
                location=selected.get("location"),
                file_path=selected.get("file"),
            )

            self.project_manager.save_zone_data(
                zone_data,
                video_path=active_video,
                persist=bool(self.project_manager.project_path),
            )

            # Refresh UI
            if active_video:
                self.project_manager.set_active_zone_video(active_video)

            self.gui.controller.setup_detector_zones()
            self.gui.canvas_manager.redraw_zones_from_project_data()

            # NEW PATH - Event-Driven Architecture v4.0
            if self.event_bus_v2:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                self.event_bus_v2.publish(
                    Event(
                        type=UIEvents.ZONES_UPDATED,
                        data={"zone_data": zone_data},
                        source="ROITemplateManager.apply_template",
                    )
                )

            self.gui.canvas_manager.redraw_zones_from_project_data()

            # Force refresh of video list indicators
            if self.event_bus_v2:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                self.event_bus_v2.publish(
                    Event(
                        type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                        data={"reason": "Template Applied", "append_summary": False},
                        source="ROITemplateManager.apply_template",
                    )
                )

            template_name = selected.get("name")
            self.dialog_manager.show_info(
                "Template aplicado", f"As zonas foram atualizadas com o template '{template_name}'."
            )
            self.dialog_manager.show_warning(
                "Revise as zonas aplicadas",
                (
                    "Confira arena/ROIs no vídeo atual antes de iniciar a análise. "
                    "Templates podem precisar de ajustes finos por vídeo."
                ),
            )
            self.gui.set_status(f"Template '{template_name}' aplicado ao vídeo em edição.")

            return True
        except Exception as exc:  # except Exception justified: template apply multi-step pipeline
            log.error("roi_templates.apply_failed", error=str(exc))
            self.dialog_manager.show_error("Erro ao aplicar template", str(exc))
            return False

    def delete_template(self) -> bool:
        """Delete the selected template."""
        selected = self.get_selected_template()
        if not selected:
            return False

        # Confirm with user
        confirm = self.dialog_manager.ask_ok_cancel(
            "Confirmar Exclusão", f"Deseja realmente excluir o template '{selected['name']}'?"
        )
        if not confirm:
            return False

        try:
            self.project_manager.delete_roi_template(
                selected["name"],
                location=selected.get("location"),
                file_path=selected.get("file"),
            )

            self.refresh_templates(clear_selection=True)
            return True
        except (OSError, PermissionError, KeyError) as exc:
            log.error("roi_templates.delete_failed", error=str(exc))
            self.dialog_manager.show_error("Erro ao excluir template", str(exc))
            return False

    def clear_applied_template_drawings(self) -> bool:
        """Clear zone drawings from the active video only.

        This action does not remove templates from the library.
        """
        active_video = self._get_active_video()
        if not active_video:
            self.dialog_manager.show_warning(
                "Vídeo não selecionado",
                "Selecione um vídeo para limpar os desenhos aplicados.",
            )
            return False

        confirm = self.dialog_manager.ask_ok_cancel(
            "Limpar desenho aplicado",
            (
                "Deseja limpar a arena e as ROIs do vídeo atual?\n\n"
                "Esta ação afeta somente o vídeo selecionado e não remove templates da biblioteca."
            ),
        )
        if not confirm:
            return False

        try:
            self.gui.canvas_manager.delete_zones_from_video(active_video)
            self.gui.set_status("Desenhos do vídeo atual foram limpos.")
            return True
        except Exception as exc:  # except Exception justified: canvas + zone multi-step cleanup
            log.error("roi_templates.clear_applied_failed", error=str(exc), video=active_video)
            self.dialog_manager.show_error("Erro ao limpar desenho", str(exc))
            return False

    def get_selected_template(self) -> dict | None:
        """Return the currently selected template, or None."""
        selected_name = self.template_var.get()
        if not selected_name:
            return None

        for template in self._cache:
            if template.get("display_name") == selected_name:
                return template

        return None

    def _get_active_video(self) -> str | None:
        """Return the active video path."""
        # Try PM active video
        active = self.project_manager.get_active_zone_video()
        if active:
            return active

        # Try pending single video from GUI
        if hasattr(self.gui, "pending_single_video_path"):
            return self.gui.pending_single_video_path

        return None

    def _show_template_selection_error(self):
        """Show error when no template is selected."""
        self.dialog_manager.show_warning(
            "Nenhum Template Selecionado", "Por favor, selecione um template primeiro."
        )

    def _update_combobox_values(self, display_names: list[str]):
        """Update combobox values."""
        # Update path to access widget via zone_controls (Phase 6 fix)
        combobox = None
        if getattr(self.gui, "zone_controls", None):
            combobox = getattr(self.gui.zone_controls, "roi_template_combobox", None)
        if combobox is None:
            combobox = getattr(self.gui, "roi_template_combobox", None)

        if combobox:
            combobox["values"] = display_names

            if not display_names:
                combobox.configure(state="disabled")
            else:
                combobox.configure(state="readonly")

    def _handle_clear_selection(self, display_names: list[str]):
        """Handle clearing the selection."""
        # Logic from gui.py
        if not display_names:
            self.template_var.set("")
        elif len(display_names) == 1:
            # Auto select if only 1
            self.template_var.set(display_names[0])
        else:
            self.template_var.set("")

    def _handle_refresh_selection(self, display_names: list[str]):
        """Handle refresh selection logic."""
        current = self.template_var.get()

        if not display_names:
            self.template_var.set("")
            return

        if current and current in display_names:
            # Keep current selection
            pass
        elif len(display_names) == 1:
            # Auto-select first if only one
            self.template_var.set(display_names[0])
        else:
            # Clear if invalid
            self.template_var.set("")

    def _update_delete_button_state(self):
        """Update delete button enabled/disabled state."""
        # Need to find the button. gui.py creates it dynamically sometimes.
        # Or check gui.delete_template_btn

        btn = getattr(self.gui, "delete_template_btn", None)
        if not btn:
            # Try self.delete_button if we set it (not currently used in gui.py logic)
            btn = self.delete_button

        if btn:
            selected = self.get_selected_template()
            state = "normal" if selected else "disabled"
            btn["state"] = state

    def import_template(self) -> None:
        """Import a template file into the library."""
        file_path = filedialog.askopenfilename(
            title="Importar Template de ROI para Biblioteca",
            filetypes=[("Templates de ROI", "*.json"), ("Todos os arquivos", "*.*")],
        )
        if not file_path:
            return

        try:
            metadata = self.project_manager.import_roi_template(file_path)
        except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
            log.error("roi_templates.import_failed", error=str(exc), file=file_path)
            self.dialog_manager.show_error("Erro ao importar", str(exc))
            return

        self.refresh_templates()
        self.select_template_by_metadata(metadata)

        template_name = metadata.get("name", Path(file_path).stem)
        message = (
            f"Template '{template_name}' adicionado à biblioteca.\n\n"
            "Use o botão 'Aplicar' para usar este template."
        )
        self.dialog_manager.show_info("Template importado", message)

    def select_template_by_metadata(self, metadata: dict[str, Any]) -> None:
        """Select a template in the dropdown by matching metadata."""
        # Helper to find the matching display name
        if not self._cache:
            return

        # Strategy matches WidgetFactory.select_roi_template logic
        # 1. Identifier match
        # 2. Name match
        # 3. Slug/File match

        target_name = metadata.get("name", "")
        target_slug = metadata.get("slug", "")
        target_file = metadata.get("file", "")

        matched_display = None

        for entry in self._cache:
            # Identifier logic would require reconstructing identifier from metadata same way
            # But we have names in cache.
            if target_name and entry.get("name") == target_name:
                matched_display = entry.get("display_name")
                break

        if not matched_display and (target_slug or target_file):
            for entry in self._cache:
                if (target_slug and entry.get("slug") == target_slug) or (
                    target_file and entry.get("file") == target_file
                ):
                    matched_display = entry.get("display_name")
                    break

        if matched_display:
            self.template_var.set(matched_display)
            self._update_delete_button_state()

    def save_template(self) -> None:
        """Save ROI template to file."""
        pm = self.project_manager
        if pm is None:
            return

        zone_data = pm.get_zone_data()
        if not zone_data or (not zone_data.polygon and not (zone_data.roi_polygons or [])):
            self.dialog_manager.show_warning(
                "Template incompleto",
                "Desenhe a arena ou pelo menos uma ROI antes de salvar um template.",
            )
            return

        allow_project = bool(getattr(pm, "project_path", None))
        selected_template = self.get_selected_template()
        if selected_template:
            initial_name = selected_template.get("name", "")
        else:
            initial_name = self.template_var.get() or ""

        from zebtrack.ui.dialogs import SaveROITemplateDialog

        dialog = SaveROITemplateDialog(
            self.gui.root,
            default_name=initial_name,
            has_arena=bool(zone_data.polygon),
            has_rois=bool(zone_data.roi_polygons),
            allow_project=allow_project,
        )
        dialog_result = dialog.result if dialog.result else None

        if not dialog_result:
            return

        try:
            metadata = pm.save_roi_template(
                dialog_result["name"],
                zone_data,
                save_arena=dialog_result["save_arena"],
                save_rois=dialog_result["save_rois"],
                save_location=dialog_result["save_location"],
                custom_path=dialog_result.get("custom_path"),
                persist=dialog_result["save_location"] == "project",
            )
        except ValueError as exc:
            self.dialog_manager.show_warning("Template inválido", str(exc))
            return
        except (OSError, PermissionError) as exc:
            log.error("roi_templates.save_failed", error=str(exc))
            self.dialog_manager.show_error("Erro ao salvar", str(exc))
            return

        self.refresh_templates()
        self.select_template_by_metadata(metadata)
        self.dialog_manager.show_info(
            "Template salvo",
            (f"Template '{metadata.get('name', dialog_result['name'])}' disponível para uso."),
        )
