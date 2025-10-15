"""
Step 5: Confirmation & Summary Dialog

Shows final summary of all wizard steps and allows project name/location configuration.
Validates all settings before enabling project creation.
"""

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
    filedialog,
    messagebox,
    simpledialog,
)
from tkinter import (
    font as tkfont,
)

import structlog

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
        self.template_info_label = None

    def build_ui(self):
        """Build confirmation step UI."""
        # Title
        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(self, text="Confirmação e Criação do Projeto", font=title_font)
        title.pack(pady=(0, 10))

        subtitle = Label(
            self,
            text="Revise as configurações e crie seu projeto.",
            fg="gray",
            wraplength=500,
        )
        subtitle.pack(pady=(0, 20))

        self.template_info_label = Label(
            self,
            textvariable=self.template_info_var,
            fg="#555555",
            wraplength=500,
            justify="left",
        )
        self.template_info_label.pack_forget()
        self._update_template_banner()

        # Project name
        name_frame = Frame(self)
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
        location_frame = Frame(self)
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
        summary_frame = LabelFrame(self, text="Resumo do Projeto", padx=10, pady=10)
        summary_frame.pack(fill="x", pady=(0, 10))

        self.summary_label = Label(
            summary_frame,
            text="",
            justify="left",
            anchor="nw",
            wraplength=900,
            height=18,
        )
        self.summary_label.pack(fill="x")

        # Template button
        template_btn_frame = Frame(self)
        template_btn_frame.pack(fill="x", pady=(10, 0))

        Button(
            template_btn_frame,
            text="💾 Salvar como Template",
            command=self._save_as_template,
            width=25,
        ).pack(side="right")

        # Help text
        help_text = Label(
            self,
            text=(
                "💡 Dica: Verifique todas as configurações antes de criar o "
                "projeto. Você pode salvar como template para reutilizar."
            ),
            fg="gray",
            wraplength=500,
            justify="left",
        )
        help_text.pack(pady=(10, 0))

    def on_show(self):
        """Called when step becomes visible - generate summary."""
        self._generate_default_project_name()
        self._generate_summary()
        self._update_template_banner()

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
        self.summary_label.config(text=self.summary_text)

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
        lines.append("")
        lines.append("📹 Configuração ao Vivo:")
        camera_index = self.wizard_data.get("camera_index", 0)
        lines.append(f"  • Câmera: Índice {camera_index}")

        if self.wizard_data.get("use_arduino"):
            arduino_port = self.wizard_data.get("arduino_port", "N/A")
            lines.append(f"  • Arduino: {arduino_port}")

        if self.wizard_data.get("use_timed_recording"):
            duration = self.wizard_data.get("recording_duration_s", 0)
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            lines.append(f"  • Gravação temporizada: {minutes}min {seconds}s")

        if self.wizard_data.get("use_countdown"):
            countdown = self.wizard_data.get("countdown_duration_s", 0)
            lines.append(f"  • Contagem regressiva: {countdown}s")

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
        lines.append(f"  • Dimensões: {width} × {height} cm")

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
        parquet_summary = self.wizard_data.get("parquet_summary", {})
        if not parquet_summary:
            return

        lines.append("")
        lines.append("📦 Parquets Existentes:")
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
        if project_path.exists():
            return (False, f"Já existe um projeto com esse nome em: {location}")

        # Validate that we have videos
        video_count = self.wizard_data.get("video_count", 0)
        if video_count == 0:
            return (False, "Nenhum vídeo selecionado. Volte e selecione vídeos.")

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

        return {
            "project_name": project_name,
            "project_path": project_path,
        }

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
