"""
Step 5: Confirmation & Summary Dialog.

Shows final summary of all wizard steps and allows project name/location configuration.
Validates all settings before enabling project creation.
"""

import copy
import os
import re
from pathlib import Path
from tkinter import (
    Button,
    Entry,
    Frame,
    Label,
    LabelFrame,
    StringVar,
    Text,
    filedialog,
    messagebox,
    simpledialog,
)
from tkinter import (
    font as tkfont,
)

import structlog

from zebtrack.ui.window_utils import create_scrollbar
from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import ImportAction, ProjectType, WizardStepID
from zebtrack.ui.wizard.templates import TemplateManager, format_template_banner

log = structlog.get_logger()


class ConfirmationStep(WizardStep):
    """
    Confirmation step - final review and project creation.

    Processing:
        1. Load all wizard data from previous steps
        2. Generate summary
        3. Allow project name/location editing
        4. Validate before enabling creation
        5. Return final project configuration

    Output:
        {
            "project_name": str,
            "project_path": str,  # Full path including project name
            # All previous wizard data is preserved
        }
    """

    def __init__(self, parent, wizard_data: dict):
        """Initialize confirmation step."""
        super().__init__(parent, wizard_data)
        self.step_id = WizardStepID.CONFIRMATION

        # State
        self.project_name_var = StringVar(value="")
        self.project_location_var = StringVar(value=str(Path.home() / "Documents"))
        self.summary_text = ""
        self.template_manager = TemplateManager()
        self.template_info_var = StringVar(value="")
        self.template_info_label: Label | None = None
        self._responsive_labels: list[Label] = []

    def build_ui(self):
        """Build confirmation step UI with scrollable summary text."""
        background_color = self.cget("background")

        # Main container (fixed header + scrollable summary + fixed buttons)
        self.content_container = Frame(self, bg=background_color)
        self.content_container.pack(fill="both", expand=True, padx=16, pady=12)

        # Title
        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(
            self.content_container,
            text="Confirmação e Criação do Projeto",
            font=title_font,
            bg=background_color,
        )
        title.pack(pady=(0, 10))

        subtitle = Label(
            self.content_container,
            text="Revise as configurações e crie seu projeto.",
            fg="gray",
            wraplength=720,
            bg=background_color,
        )
        subtitle.pack(pady=(0, 20))
        self._responsive_labels.append(subtitle)

        self.template_info_label = Label(
            self.content_container,
            textvariable=self.template_info_var,
            fg="#555555",
            wraplength=720,
            justify="left",
            bg=background_color,
        )
        self.template_info_label.pack_forget()
        if self.template_info_label:  # Conditional append for type safety
            self._responsive_labels.append(self.template_info_label)
        self._update_template_banner()

        # Project name
        name_frame = Frame(self.content_container, bg=background_color)
        name_frame.pack(fill="x", pady=(0, 10))

        Label(
            name_frame,
            text="Nome do Projeto:",
            width=20,
            anchor="w",
        ).pack(side="left")
        Entry(name_frame, textvariable=self.project_name_var, width=40).pack(
            side="left",
            padx=(5, 0),
            fill="x",
            expand=True,
        )

        # Project location
        location_frame = Frame(self.content_container, bg=background_color)
        location_frame.pack(fill="x", pady=(0, 15))

        Label(
            location_frame,
            text="Localização:",
            width=20,
            anchor="w",
        ).pack(side="left")
        Entry(location_frame, textvariable=self.project_location_var, width=30).pack(
            side="left",
            padx=(5, 5),
            fill="x",
            expand=True,
        )
        Button(
            location_frame,
            text="Procurar...",
            command=self._browse_location,
        ).pack(side="left")

        # Summary (with controlled height to prevent button occlusion)
        summary_frame = LabelFrame(
            self.content_container, text="Resumo do Projeto", padx=10, pady=10
        )
        summary_frame.pack(fill="both", expand=True, pady=(0, 10), padx=4)

        summary_container = Frame(summary_frame)
        summary_container.pack(fill="both", expand=True)

        self.summary_textbox = Text(
            summary_container,
            height=20,
            wrap="word",
            state="disabled",
            relief="flat",
        )
        self.summary_textbox.configure(width=0)
        self.summary_textbox.pack(side="left", fill="both", expand=True)

        summary_scrollbar = create_scrollbar(
            summary_container,
            orient="vertical",
            command=self.summary_textbox.yview,
        )
        self.summary_textbox.configure(yscrollcommand=summary_scrollbar.set)
        summary_scrollbar.pack(side="right", fill="y")

        # Template button
        template_btn_frame = Frame(self.content_container, bg=background_color)
        template_btn_frame.pack(fill="x", pady=(10, 0))

        Button(
            template_btn_frame,
            text="💾 Salvar como Template",
            command=self._save_as_template,
            width=25,
        ).pack(side="right")

        # Help text
        help_text = Label(
            self.content_container,
            text=(
                "💡 Dica: Verifique todas as configurações antes de criar o "
                "projeto. Você pode salvar como template para reutilizar."
            ),
            fg="gray",
            wraplength=720,
            justify="left",
            bg=background_color,
        )
        help_text.pack(pady=(10, 0))
        self._responsive_labels.append(help_text)

        self.after(0, self._initial_wrap_refresh)

    def on_show(self):
        """Execute actions when step becomes visible - generate summary."""
        self._generate_default_project_name()
        self._generate_summary()
        self._update_template_banner()

    def _initial_wrap_refresh(self) -> None:
        """Refresh wraplengths based on current widget width."""
        if not self.winfo_exists():
            return
        width = self.winfo_width()
        if width:
            self._update_wraplengths(width)

    def _update_wraplengths(self, canvas_width: int) -> None:
        usable = max(canvas_width - 60, 480)
        for label in self._responsive_labels:
            if label and label.winfo_exists():
                label.configure(wraplength=usable)

    def _generate_default_project_name(self):
        """Generate default project name based on project type."""
        if self.project_name_var.get():
            return  # Already has a name

        project_type = self.wizard_data.get("project_type", ProjectType.EXPERIMENTAL.value)

        if project_type == ProjectType.EXPERIMENTAL.value:
            # Use detected groups if available
            detected_design = self.wizard_data.get("detected_design")
            if detected_design and detected_design.get("groups"):
                groups = detected_design["groups"]
                name = f"Experimento_{groups[0]}"
            else:
                name = "Projeto_Experimental"
        else:
            name = "Projeto_Exploratorio"

        # Add timestamp to make unique
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d")
        name = f"{name}_{timestamp}"

        self.project_name_var.set(name)

    def _browse_location(self):
        """Open directory browser for project location."""
        directory = filedialog.askdirectory(
            title="Selecione a Pasta do Projeto",
            initialdir=self.project_location_var.get(),
        )
        if directory:
            self.project_location_var.set(directory)

    def _generate_summary(self):
        """Generate summary text from all wizard data (refactored)."""
        lines: list[str] = []

        # Template metadata
        self._append_template_info(lines)

        # Project type
        project_type = self.wizard_data.get("project_type", "experimental")
        is_live = project_type == ProjectType.LIVE.value
        self._append_project_type(lines, project_type)

        # Live-specific configuration
        if is_live:
            self._append_live_configuration(lines)
        else:
            # Pre-recorded specifics
            self._append_detected_design(lines)
            self._append_custom_regex_info(lines)
            self._append_detection_settings(lines)
            self._append_folder_preview(lines)

        # Calibration
        self._append_calibration(lines)

        # Processing plan and parquet/import summaries (pre-recorded only)
        if not is_live:
            self._append_processing_plan(lines)
            self._append_parquet_summary(lines)
            self._append_import_configuration(lines)
            self._append_roi_strategy(lines)

        self.summary_text = "\n".join(lines)
        if hasattr(self, "summary_textbox") and self.summary_textbox:
            self.summary_textbox.configure(state="normal")
            self.summary_textbox.delete("1.0", "end")
            self.summary_textbox.insert("1.0", self.summary_text)
            self.summary_textbox.configure(state="disabled")
            self.summary_textbox.yview_moveto(0.0)

    def on_hide(self):
        """Execute actions when step is hidden (no special cleanup needed now)."""
        pass

    # ------------------------------------------------------------------
    # Summary helper methods (split from _generate_summary)
    # ------------------------------------------------------------------
    def _append_template_info(self, lines: list[str]) -> None:
        metadata = self.wizard_data.get("template_metadata")
        if not metadata:
            return

        lines.append("📝 Template Carregado:")
        banner_text = format_template_banner(metadata)
        if banner_text:
            lines.append(f"  • {banner_text.replace('Template carregado: ', '')}")
        if metadata.get("created_at"):
            lines.append(f"  • Criado em: {metadata['created_at']}")
        if metadata.get("schema_version"):
            lines.append(f"  • Versão do template: {metadata['schema_version']}")
        lines.append("")

    def _append_project_type(self, lines: list[str], project_type: str) -> None:
        lines.append("📋 Tipo de Projeto:")
        type_names = {
            ProjectType.EXPERIMENTAL.value: "Experimental (pré-gravado)",
            ProjectType.EXPLORATORY.value: "Exploratório (pré-gravado)",
            ProjectType.LIVE.value: "Ao Vivo (tempo real)",
        }
        lines.append(f"  • {type_names.get(project_type, project_type.capitalize())}")

    def _append_live_configuration(self, lines: list[str]) -> None:
        # Experimental Design
        experiment_days = self.wizard_data.get("experiment_days")
        num_groups = self.wizard_data.get("num_groups")
        subjects_per_group = self.wizard_data.get("subjects_per_group")
        group_names = self.wizard_data.get("group_names", [])

        if experiment_days or num_groups or subjects_per_group:
            lines.append("")
            lines.append("🔬 Design Experimental:")
            if num_groups and subjects_per_group and experiment_days:
                total_sessions = num_groups * subjects_per_group * experiment_days
                total_animals = num_groups * subjects_per_group
                lines.append(
                    f"  • {num_groups} grupos x {experiment_days} dias x "
                    f"{subjects_per_group} animais/grupo"
                )
                lines.append(f"  • Total: {total_sessions} gravações ({total_animals} animais)")
            if group_names:
                group_list = ", ".join(group_names)
                lines.append(f"  • Grupos: {group_list}")

        # Camera & Hardware
        lines.append("")
        lines.append("📹 Hardware:")
        camera_index = self.wizard_data.get("camera_index", 0)
        camera_friendly_name = self.wizard_data.get("camera_friendly_name", "")
        if camera_friendly_name:
            lines.append(f"  • Câmera: {camera_friendly_name} (índice {camera_index})")
        else:
            lines.append(f"  • Câmera: Índice {camera_index}")

        if self.wizard_data.get("use_arduino"):
            arduino_port = self.wizard_data.get("arduino_port", "N/A")
            lines.append(f"  • Arduino: {arduino_port}")
            if self.wizard_data.get("external_trigger_mode"):
                lines.append("  • Modo: Gatilho Externo (External Trigger) ✓")

        # Recording Settings
        if self.wizard_data.get("use_timed_recording") or self.wizard_data.get("use_countdown"):
            lines.append("")
            lines.append("⏱️ Configurações de Gravação:")
            if self.wizard_data.get("use_timed_recording"):
                duration = self.wizard_data.get("recording_duration_s", 0)
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                lines.append(f"  • Gravação temporizada: {minutes}min {seconds}s")
            if self.wizard_data.get("use_countdown"):
                countdown = self.wizard_data.get("countdown_duration_s", 0)
                lines.append(f"  • Contagem regressiva: {countdown}s")

        # Processing Intervals
        analysis_interval = self.wizard_data.get("analysis_interval_frames")
        display_interval = self.wizard_data.get("display_interval_frames")
        if analysis_interval or display_interval:
            lines.append("")
            lines.append("⚙️ Intervalos de Processamento:")
            if analysis_interval:
                lines.append(f"  • Análise: a cada {analysis_interval} frames")
            if display_interval:
                lines.append(f"  • Exibição: a cada {display_interval} frames")

        # Model Selection
        weight_assignments = self.wizard_data.get("weight_assignments")
        detector_params = self.wizard_data.get("detector_parameters")
        if weight_assignments or detector_params:
            lines.append("")
            lines.append("🎯 Configuração de Detecção:")
            if weight_assignments:
                aquarium_weight = weight_assignments.get("aquarium")
                animal_weight = weight_assignments.get("animal")
                if aquarium_weight:
                    lines.append(f"  • Peso aquário: {aquarium_weight}")
                if animal_weight:
                    lines.append(f"  • Peso animais: {animal_weight}")
            if detector_params:
                conf = detector_params.get("confidence_threshold")
                nms = detector_params.get("nms_threshold")
                track = detector_params.get("track_threshold")
                match = detector_params.get("match_threshold")
                if conf is not None:
                    lines.append(
                        f"  • Thresholds: conf={conf:.2f}, NMS={nms:.2f}, "
                        f"track={track:.2f}, match={match:.2f}"
                    )

    def _append_detected_design(self, lines: list[str]) -> None:
        detected_design = self.wizard_data.get("detected_design")
        if not detected_design:
            return

        lines.append("")
        lines.append("🔍 Design Detectado / Design:")
        groups = detected_design.get("groups", [])
        days = detected_design.get("days", [])
        confidence = detected_design.get("confidence", 0)

        if groups:
            preview = ", ".join(groups[:3])
            suffix = "..." if len(groups) > 3 else ""
            lines.append(f"  • Grupos: {len(groups)} ({preview}{suffix})")

        if days:
            lines.append(f"  • Dias: {len(days)}")

        lines.append(f"  • Confiança: {confidence:.0%}")

    def _append_custom_regex_info(self, lines: list[str]) -> None:
        patterns = self.wizard_data.get("custom_regex_patterns") or {}
        if not any(patterns.values()):
            return

        label_map = {
            "group_pattern": "Grupos",
            "day_pattern": "Dias",
            "subject_pattern": "Sujeitos",
        }

        lines.append("")
        lines.append("🧩 Regex Personalizada:")
        for key, label in label_map.items():
            value = patterns.get(key)
            if value:
                lines.append(f"  • {label}: {value}")
            else:
                lines.append(f"  • {label}: —")

    def _append_detection_settings(self, lines: list[str]) -> None:
        model_selection = self.wizard_data.get("model_selection") or {}
        weight_assignments = self.wizard_data.get("weight_assignments") or {}
        detector_params = self.wizard_data.get("detector_parameters") or {}
        use_openvino = self.wizard_data.get("use_openvino")

        if not (
            model_selection or weight_assignments or detector_params or use_openvino is not None
        ):
            return

        method_labels = {
            "seg": "Segmentação (seg)",
            "det": "Detecção (det)",
        }

        lines.append("")
        lines.append("🎯 Configurações de Detecção:")

        aquarium_method = model_selection.get("aquarium_method")
        animal_method = model_selection.get("animal_method")
        if aquarium_method or animal_method:
            if aquarium_method:
                aquarium_label = method_labels.get(aquarium_method, aquarium_method)
                lines.append(f"  • Método aquário: {aquarium_label}")
            if animal_method:
                animal_label = method_labels.get(animal_method, animal_method)
                lines.append(f"  • Método animais: {animal_label}")

        if weight_assignments:
            aquarium_weight = weight_assignments.get("aquarium")
            animal_weight = weight_assignments.get("animal")
            if aquarium_weight:
                lines.append(f"  • Peso aquário: {aquarium_weight}")
            if animal_weight:
                lines.append(f"  • Peso animais: {animal_weight}")

        if use_openvino is not None:
            status = "Ativado" if use_openvino else "Desativado"
            lines.append(f"  • OpenVINO: {status}")

        if detector_params:
            conf = detector_params.get("confidence_threshold")
            nms = detector_params.get("nms_threshold")
            track = detector_params.get("track_threshold")
            match = detector_params.get("match_threshold")
            if all(value is not None for value in (conf, nms, track, match)):
                lines.append(
                    f"  • Thresholds: conf={conf:.2f}, NMS={nms:.2f}, "
                    f"track={track:.2f}, match={match:.2f}"
                )
            else:
                threshold_bits = []
                if conf is not None:
                    threshold_bits.append(f"conf={conf:.2f}")
                if nms is not None:
                    threshold_bits.append(f"NMS={nms:.2f}")
                if track is not None:
                    threshold_bits.append(f"track={track:.2f}")
                if match is not None:
                    threshold_bits.append(f"match={match:.2f}")
                if threshold_bits:
                    lines.append(f"  • Thresholds: {', '.join(threshold_bits)}")

    def _append_folder_preview(self, lines: list[str]) -> None:
        video_count = self.wizard_data.get("video_count", 0)
        if video_count > 0:
            lines.append(f"  • Total de Vídeos: {video_count}")

        folder_preview = self.wizard_data.get("folder_preview") or []
        if folder_preview:
            lines.append("")
            lines.append("🌳 Estrutura de Pastas (prévia):")
            for entry in folder_preview[:2]:
                lines.extend(self._render_folder_preview(entry))

            remaining = len(folder_preview) - 2
            if remaining > 0:
                lines.append(f"  • (+ {remaining} seleção(ões) adicional(is))")

    def _append_calibration(self, lines: list[str]) -> None:
        lines.append("")
        lines.append("📏 Calibração Física:")
        num_aquariums = self.wizard_data.get("num_aquariums", 1)
        animals_per_aquarium = self.wizard_data.get("animals_per_aquarium", 1)
        width = self.wizard_data.get("aquarium_width_cm", 10.0)
        height = self.wizard_data.get("aquarium_height_cm", 10.0)

        lines.append(f"  • Aquários: {num_aquariums}")
        lines.append(f"  • Animais por aquário: {animals_per_aquarium}")
        lines.append(f"  • Dimensões: {width} x {height} cm")

    def _append_processing_plan(self, lines: list[str]) -> None:
        lines.append("")
        lines.append("⚙️ Plano de Processamento:")
        import_config = self.wizard_data.get("import_config", [])

        if not import_config:
            return

        action_counts: dict[str, int] = {}
        for config in import_config:
            action = config.get("action", ImportAction.FULL.value)
            action_counts[action] = action_counts.get(action, 0) + 1

        action_names = {
            ImportAction.SKIP.value: "Skip (dados completos)",
            ImportAction.IMPORT_ZONES.value: "Import Zones + rastrear",
            ImportAction.PARTIAL.value: "Partial (arena apenas)",
            ImportAction.FULL.value: "Full (processar do zero)",
        }

        for action, count in sorted(action_counts.items()):
            name = action_names.get(action, action)
            lines.append(f"  • {count} vídeo(s): {name}")

        # Estimate processing time (rough estimate: 5 min per video to process)
        videos_to_process = sum(
            1 for c in import_config if c.get("action") not in [ImportAction.SKIP.value]
        )

        if videos_to_process > 0:
            estimated_minutes = videos_to_process * 5
            lines.append("")
            lines.append(f"⏱️ Tempo Estimado: ~{estimated_minutes} minutos")
            lines.append(f"  ({videos_to_process} vídeo(s) para processar)")

    def _append_parquet_summary(self, lines: list[str]) -> None:
        # Show parquet summary whenever data exists (scope optional for legacy flows)
        parquet_summary = self.wizard_data.get("parquet_summary", {})
        if not parquet_summary:
            return

        parquet_import_scope = self.wizard_data.get("parquet_import_scope")

        lines.append("")
        lines.append("📦 Parquets Existentes:")
        if parquet_import_scope:
            lines.append(f"  • Escopo: {parquet_import_scope}")
        arena_total = parquet_summary.get("total_arena", 0)
        rois_total = parquet_summary.get("total_rois", 0)
        trajectory_total = parquet_summary.get("total_trajectory", 0)
        complete_total = parquet_summary.get("total_complete", 0)
        lines.append(f"  • Arena: {arena_total}")
        lines.append(f"  • ROIs: {rois_total}")
        lines.append(f"  • Trajetória: {trajectory_total}")
        lines.append(f"  • Completos: {complete_total}")

    def _append_import_configuration(self, lines: list[str]) -> None:
        import_config = self.wizard_data.get("import_config", [])
        if not import_config:
            return

        importing_arena = any(cfg.get("import_arena", False) for cfg in import_config)
        importing_rois = any(cfg.get("import_rois", False) for cfg in import_config)
        importing_trajectory = any(cfg.get("import_trajectory", False) for cfg in import_config)

        if importing_arena or importing_rois or importing_trajectory:
            lines.append("")
            lines.append("📥 Configuração de Importação:")
            if importing_arena:
                arena_count = sum(1 for c in import_config if c.get("import_arena"))
                lines.append(f"  ✅ Arena: {arena_count} vídeo(s)")
            if importing_rois:
                rois_count = sum(1 for c in import_config if c.get("import_rois"))
                lines.append(f"  ✅ ROIs: {rois_count} vídeo(s)")
            if importing_trajectory:
                traj_count = sum(1 for c in import_config if c.get("import_trajectory"))
                lines.append(f"  ✅ Trajetória: {traj_count} vídeo(s)")

    def _append_roi_strategy(self, lines: list[str]) -> None:
        import_config = self.wizard_data.get("import_config", [])
        if import_config:
            importing_rois = any(cfg.get("import_rois", False) for cfg in import_config)
        else:
            importing_rois = False

        if not importing_rois:
            return

        roi_strategy = self.wizard_data.get("roi_merge_strategy", "replace")
        strategy_names = {
            "replace": "Substituir ROIs existentes",
            "merge": "Mesclar (manter ambos)",
            "manual": "Resolução manual de conflitos",
        }
        lines.append("")
        lines.append("🔀 Estratégia de ROIs:")
        lines.append(f"  • {strategy_names.get(roi_strategy, roi_strategy)}")

    def _render_folder_preview(self, entry: dict) -> list[str]:
        """Convert folder preview structure into formatted summary lines."""
        label = entry.get("label") or entry.get("path") or "(seleção)"
        counts = entry.get("counts", {})
        folders = counts.get("folders", 0)
        files = counts.get("files", 0)

        summary_bits: list[str] = []
        if folders:
            summary_bits.append(f"{folders} pasta(s)")
        if files:
            summary_bits.append(f"{files} arquivo(s)")

        summary_text = ", ".join(summary_bits) if summary_bits else "vazio"
        lines = [f"  • {label}: {summary_text}"]

        def walk(nodes: list[dict], depth: int) -> None:
            if depth >= 2:
                return

            max_children = 2 if depth == 0 else 1
            child_count = len(nodes)
            for index, node in enumerate(nodes[:max_children]):
                prefix = "    " * (depth + 1)
                node_label = node.get("label") or node.get("path") or "(item)"
                lines.append(f"{prefix}- {node_label}")
                walk(node.get("children", []), depth + 1)

                if index == max_children - 1 and child_count > max_children:
                    lines.append(f"{prefix}…")

        walk(entry.get("nodes", []), 0)

        if entry.get("truncated"):
            lines.append("    … Prévia limitada (detalhes completos na etapa 2)")

        return lines

    def _save_as_template(self):
        """Save current wizard configuration as a template."""
        # Ask for template name
        template_name = simpledialog.askstring(
            "Salvar Template",
            "Digite um nome para o template:",
            parent=self,
        )

        if not template_name:
            return  # User cancelled

        suggested_filename = (
            self.template_manager._sanitize_name(template_name) or "template"
        ) + ".json"

        file_path = filedialog.asksaveasfilename(
            title="Salvar Template do Wizard",
            defaultextension=".json",
            filetypes=[("Templates do Wizard", "*.json"), ("JSON", "*.json")],
            initialdir=str(self.template_manager.templates_dir),
            initialfile=suggested_filename,
        )

        if not file_path:
            return

        # Save template
        success = self.template_manager.save_template(
            template_name,
            self.wizard_data,
            destination_path=file_path,
        )

        if success:
            template_message = (
                f"Template '{template_name}' salvo com sucesso!\n\n"
                f"Arquivo: {file_path}\n\n"
                "Você poderá carregar este template no futuro "
                "para criar projetos similares rapidamente."
            )
            messagebox.showinfo(
                "Template Salvo",
                template_message,
                parent=self,
            )
            log.info("wizard.template_saved", name=template_name)
        else:
            messagebox.showerror(
                "Erro ao Salvar",
                f"Não foi possível salvar o template '{template_name}'.\n\n"
                f"Verifique os logs para mais detalhes.",
                parent=self,
            )

    def validate(self) -> tuple[bool, str]:
        """
        Validate confirmation step.

        Returns:
            tuple[bool, str]: (True, "") if all validations pass
        """
        # Validate project name
        project_name = self.project_name_var.get().strip()

        if not project_name:
            return (False, "Por favor, informe um nome para o projeto.")

        # Check valid characters (alphanumeric, underscore, hyphen, space)
        if not re.match(r"^[A-Za-z0-9_\- ]+$", project_name):
            message = (
                "Nome do projeto contém caracteres inválidos. "
                "Use apenas letras, números, espaços, '_' e '-'."
            )
            return (False, message)

        # Validate location
        location = self.project_location_var.get().strip()

        if not location:
            return (False, "Por favor, selecione uma localização para o projeto.")

        if not os.path.exists(location):
            return (False, f"Localização não existe: {location}")

        if not os.access(location, os.W_OK):
            return (False, f"Sem permissão de escrita na localização: {location}")

        # Check if project directory already exists
        project_path = Path(location) / project_name
        try:
            project_exists = project_path.exists()
        except OSError:
            return (False, "Nome do projeto é muito longo para o sistema de arquivos.")

        if project_exists:
            try:
                if project_path.is_file():
                    return (False, f"Já existe um arquivo com esse nome em: {location}")
            except OSError:
                return (False, "Nome do projeto é muito longo para o sistema de arquivos.")

            # Allow reusing an empty directory so long as it has no content
            try:
                has_contents = any(project_path.iterdir())
            except OSError:
                has_contents = True

            if has_contents:
                return (
                    False,
                    f"Já existe um projeto com esse nome em: {location}",
                )

        # Validate sources: prerecorded projects require selected videos;
        # live projects require camera config
        project_type = self.wizard_data.get("project_type", ProjectType.EXPERIMENTAL.value)

        if project_type != ProjectType.LIVE.value:
            video_count = self.wizard_data.get("video_count", 0)
            if video_count == 0:
                return (False, "Nenhum vídeo selecionado. Volte e selecione vídeos.")
        else:
            if "camera_index" not in self.wizard_data:
                return (
                    False,
                    "Configure a câmera na etapa anterior antes de criar o projeto.",
                )

        return (True, "")

    def get_data(self) -> dict:
        """
        Extract confirmation data.

        Returns:
            dict: Final project configuration with keys:
                - project_name (str)
                - project_path (str): Full path including project name
        """
        project_name = self.project_name_var.get().strip()
        location = self.project_location_var.get().strip()
        project_path = str(Path(location) / project_name)

        base_data: dict = {}
        if isinstance(self.wizard_data, dict):
            base_data = copy.deepcopy(self.wizard_data)

        base_data.update(
            {
                "project_name": project_name,
                "project_path": project_path,
                "project_location": location,
            }
        )

        return base_data

    def set_data(self, data: dict):
        """
        Restore UI from data (for back navigation).

        Args:
            data: Previously collected confirmation data
        """
        if "project_name" in data:
            self.project_name_var.set(data["project_name"])

        if "project_path" in data:
            # Extract location from full path
            project_path = Path(data["project_path"])
            if project_path.parent.exists():
                self.project_location_var.set(str(project_path.parent))

        # Regenerate summary
        self._generate_summary()
        self._update_template_banner()

    def _update_template_banner(self):
        metadata = self.wizard_data.get("template_metadata")
        banner_text = format_template_banner(metadata)

        if banner_text:
            self.template_info_var.set(banner_text)
            if self.template_info_label and not self.template_info_label.winfo_ismapped():
                self.template_info_label.pack(pady=(0, 15))
        else:
            self.template_info_var.set("")
            if self.template_info_label and self.template_info_label.winfo_ismapped():
                self.template_info_label.pack_forget()
