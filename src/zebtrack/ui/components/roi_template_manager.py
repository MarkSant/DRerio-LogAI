from pathlib import Path
from tkinter import StringVar, filedialog, ttk
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from zebtrack.ui.gui import ApplicationGUI

log = structlog.get_logger()

class ROITemplateManager:
    """Gerencia operações de templates de ROI."""

    def __init__(self, project_manager, gui_parent: "ApplicationGUI", event_bus_v2=None):
        self.project_manager = project_manager
        self.gui = gui_parent
        self.event_bus_v2 = event_bus_v2
        self._cache: list[dict[str, Any]] = []
        self.template_var = StringVar(value="")
        # Delete button reference will be managed via gui or passed in?
        # The plan says self.delete_button = None initially.
        self.delete_button: ttk.Button | None = None

    def refresh_templates(self, clear_selection: bool = False) -> None:
        """
        Carrega templates do project manager e atualiza cache.

        Lida com:
        - Carregamento de templates
        - Validação de arquivo
        - Enriquecimento de nome de exibição
        - Lógica de auto-seleção
        """
        try:
            templates = self.project_manager.list_roi_templates()
        except Exception as exc:
            log.warning("roi_templates.refresh_failed", error=str(exc))
            templates = []

        # Valida e enriquece
        enriched = self._validate_and_enrich_templates(templates)
        self._cache = enriched

        # Atualiza UI
        display_names = [t["display_name"] for t in enriched]
        self._update_combobox_values(display_names)

        # Lida com lógica de seleção
        if clear_selection:
            self._handle_clear_selection(display_names)
        else:
            self._handle_refresh_selection(display_names)

        self._update_delete_button_state()

    def _validate_and_enrich_templates(self, templates: list[dict]) -> list[dict]:
        """Valida templates e adiciona metadados de exibição."""
        enriched = []

        for template in templates:
            if not isinstance(template, dict):
                continue

            # Valida nome
            name = template.get("name", "").strip()
            if not name:
                log.warning("roi_templates.skipping_empty_name", template=template)
                continue

            # Valida arquivo se baseado em arquivo
            if not self._validate_template_file(template):
                continue

            # Enriquece com dados de exibição
            entry = dict(template)
            entry["display_name"] = self._format_display_name(entry)
            entry["identifier"] = self._build_identifier(entry)

            if entry.get("display_name", "").strip():
                enriched.append(entry)

        return enriched

    def _validate_template_file(self, template: dict) -> bool:
        """Valida que arquivo de template existe e é legível."""
        file_path = template.get("file")
        if not file_path:
            return True  # Templates não baseados em arquivo são válidos

        # Corrige problemas comuns de caminho
        path_str = str(file_path)
        if "\\,zebtrack\\" in path_str or "/,zebtrack/" in path_str:
            path_str = path_str.replace("\\,zebtrack\\", "\\.zebtrack\\")
            path_str = path_str.replace("/,zebtrack/", "/.zebtrack/")
            # Update the template dict in place if needed for later use?
            template["file"] = path_str
            # The plan logic implies we just validate here.

        path = Path(path_str)
        if not path.exists() or not path.is_file():
            log.warning("roi_templates.invalid_file", file=path_str)
            return False

        return True

    def _format_display_name(self, template: dict) -> str:
        """Formata nome de exibição para template."""
        name = template.get("name", "")
        location = template.get("location", "")

        if location == "project":
            return f"📁 {name}"
        elif location == "global":
            return f"🌐 {name}"
        else:
            return name

    def _build_identifier(self, template: dict) -> str:
        """Constrói identificador único para template."""
        name = template.get("name", "")
        location = template.get("location", "")
        file_path = template.get("file", "")

        if file_path:
            return f"{location}:{name}:{file_path}"
        else:
            return f"{location}:{name}"

    def apply_template(self) -> bool:
        """Aplica template selecionado ao vídeo ativo."""
        selected = self.get_selected_template()
        if not selected:
            self._show_template_selection_error()
            return False

        active_video = self._get_active_video()
        if not active_video:
            self.gui.show_warning(
                "Vídeo não selecionado",
                "Selecione um vídeo na lista antes de aplicar o template."
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
                self.event_bus_v2.publish(Event(
                    type=UIEvents.ZONES_UPDATED,
                    data={'zone_data': zone_data},
                    source='ROITemplateManager.apply_template'
                ))

            self.gui._refresh_zone_indicators()

            template_name = selected.get("name")
            self.gui.show_info("Template aplicado", f"As zonas foram atualizadas com o template '{template_name}'.")
            self.gui.set_status(f"Template '{template_name}' aplicado ao vídeo em edição.")

            return True
        except Exception as exc:
            log.error("roi_templates.apply_failed", error=str(exc))
            self.gui.show_error("Erro ao aplicar template", str(exc))
            return False

    def delete_template(self) -> bool:
        """Deleta template selecionado."""
        selected = self.get_selected_template()
        if not selected:
            return False

        # Confirma com usuário
        confirm = self.gui.ask_ok_cancel(
            "Confirmar Exclusão",
            f"Deseja realmente excluir o template '{selected['name']}'?"
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
        except Exception as exc:
            log.error("roi_templates.delete_failed", error=str(exc))
            self.gui.show_error("Erro ao excluir template", str(exc))
            return False

    def get_selected_template(self) -> dict | None:
        """Retorna template atualmente selecionado."""
        selected_name = self.template_var.get()
        if not selected_name:
            return None

        for template in self._cache:
            if template.get("display_name") == selected_name:
                return template

        return None

    def _get_active_video(self) -> str | None:
        """Retorna caminho do vídeo ativo."""
        # Try PM active video
        active = self.project_manager.get_active_zone_video()
        if active:
            return active

        # Try pending single video from GUI
        if hasattr(self.gui, "pending_single_video_path"):
            return self.gui.pending_single_video_path

        return None

    def _show_template_selection_error(self):
        """Mostra erro quando nenhum template está selecionado."""
        self.gui.show_warning(
            "Nenhum Template Selecionado",
            "Por favor, selecione um template primeiro."
        )

    def _update_combobox_values(self, display_names: list[str]):
        """Atualiza valores do combobox."""
        # Update path to access widget via zone_controls (Phase 6 fix)
        combobox = self.gui.zone_controls.roi_template_combobox if self.gui.zone_controls else None

        if combobox:
            combobox['values'] = display_names

            if not display_names:
                combobox.configure(state="disabled")
            else:
                combobox.configure(state="readonly")

    def _handle_clear_selection(self, display_names: list[str]):
        """Lida com limpeza de seleção."""
        # Logic from gui.py
        if not display_names:
            self.template_var.set("")
        elif len(display_names) == 1:
             # Auto select if only 1
             self.template_var.set(display_names[0])
        else:
            self.template_var.set("")

    def _handle_refresh_selection(self, display_names: list[str]):
        """Lida com lógica de seleção de atualização."""
        current = self.template_var.get()

        if not display_names:
            self.template_var.set("")
            return

        if current and current in display_names:
            # Mantém seleção atual
            pass
        elif len(display_names) == 1:
            # Auto-seleciona primeiro se único
            self.template_var.set(display_names[0])
        else:
            # Clear if invalid
            self.template_var.set("")

    def _update_delete_button_state(self):
        """Atualiza estado do botão de deletar."""
        # Need to find the button. gui.py creates it dynamically sometimes.
        # Or check gui.delete_template_btn

        btn = getattr(self.gui, 'delete_template_btn', None)
        if not btn:
            # Try self.delete_button if we set it (not currently used in gui.py logic)
            btn = self.delete_button

        if btn:
            selected = self.get_selected_template()
            state = "normal" if selected else "disabled"
            btn['state'] = state

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
        except Exception as exc:
            log.error("roi_templates.import_failed", error=str(exc), file=file_path)
            self.gui.show_error("Erro ao importar", str(exc))
            return

        self.refresh_templates()
        self.select_template_by_metadata(metadata)

        template_name = metadata.get("name", Path(file_path).stem)
        message = (
            f"Template '{template_name}' adicionado à biblioteca.\n\n"
            "Use o botão 'Aplicar' para usar este template."
        )
        self.gui.show_info("Template importado", message)

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
                if (target_slug and entry.get("slug") == target_slug) or \
                   (target_file and entry.get("file") == target_file):
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
            self.gui.show_warning(
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

        dialog_result = self.gui._show_template_save_dialog(
            has_arena=bool(zone_data.polygon),
            has_rois=bool(zone_data.roi_polygons),
            allow_project=allow_project,
            initial_name=initial_name,
        )

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
            self.gui.show_warning("Template inválido", str(exc))
            return
        except Exception as exc:
            log.error("roi_templates.save_failed", error=str(exc))
            self.gui.show_error("Erro ao salvar", str(exc))
            return

        self.refresh_templates()
        self.select_template_by_metadata(metadata)
        self.gui.show_info(
            "Template salvo",
            (f"Template '{metadata.get('name', dialog_result['name'])}' disponível para uso."),
        )
