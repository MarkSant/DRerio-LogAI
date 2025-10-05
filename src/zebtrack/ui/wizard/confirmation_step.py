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
    font as tkfont,
)

import structlog

from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import ImportAction, ProjectType, WizardStepID

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

    def build_ui(self):
        """Build confirmation step UI."""
        # Title
        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(
            self, text="Confirmação e Criação do Projeto", font=title_font
        )
        title.pack(pady=(0, 10))

        subtitle = Label(
            self,
            text="Revise as configurações e crie seu projeto.",
            fg="gray",
            wraplength=500,
        )
        subtitle.pack(pady=(0, 20))

        # Project name
        name_frame = Frame(self)
        name_frame.pack(fill="x", pady=(0, 10))

        Label(name_frame, text="Nome do Projeto:", width=20, anchor="w").pack(side="left")
        Entry(name_frame, textvariable=self.project_name_var, width=40).pack(
            side="left", padx=(5, 0), fill="x", expand=True
        )

        # Project location
        location_frame = Frame(self)
        location_frame.pack(fill="x", pady=(0, 15))

        Label(location_frame, text="Localização:", width=20, anchor="w").pack(side="left")
        Entry(location_frame, textvariable=self.project_location_var, width=30).pack(
            side="left", padx=(5, 5), fill="x", expand=True
        )
        Button(location_frame, text="Procurar...", command=self._browse_location).pack(side="left")

        # Summary
        summary_frame = LabelFrame(self, text="Resumo do Projeto", padx=10, pady=10)
        summary_frame.pack(fill="both", expand=True, pady=(0, 10))

        self.summary_label = Label(
            summary_frame,
            text="",
            justify="left",
            anchor="nw",
            wraplength=500,
        )
        self.summary_label.pack(fill="both", expand=True)

        # Help text
        help_text = Label(
            self,
            text="💡 Dica: Verifique todas as configurações antes de criar o projeto.",
            fg="gray",
            wraplength=500,
            justify="left",
        )
        help_text.pack(pady=(10, 0))

    def on_show(self):
        """Called when step becomes visible - generate summary."""
        self._generate_default_project_name()
        self._generate_summary()

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
        """Generate summary text from all wizard data."""
        lines = []

        # Design summary
        lines.append("📋 Design:")
        project_type = self.wizard_data.get("project_type", "experimental")
        lines.append(f"  • Tipo: {project_type.capitalize()}")

        detected_design = self.wizard_data.get("detected_design")
        if detected_design:
            groups = detected_design.get("groups", [])
            days = detected_design.get("days", [])
            confidence = detected_design.get("confidence", 0)

            if groups:
                lines.append(f"  • Grupos: {len(groups)} ({', '.join(groups[:3])}{'...' if len(groups) > 3 else ''})")

            if days:
                lines.append(f"  • Dias: {len(days)}")

            lines.append(f"  • Confiança de Detecção: {confidence:.0%}")

        video_count = self.wizard_data.get("video_count", 0)
        lines.append(f"  • Total de Vídeos: {video_count}")

        lines.append("")

        # Processing plan summary
        lines.append("⚙️ Plano de Processamento:")
        import_config = self.wizard_data.get("import_config", [])

        if import_config:
            action_counts = {}
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
                1 for c in import_config
                if c.get("action") not in [ImportAction.SKIP.value]
            )

            if videos_to_process > 0:
                estimated_minutes = videos_to_process * 5
                lines.append("")
                lines.append(f"⏱️ Tempo Estimado: ~{estimated_minutes} minutos")
                lines.append(f"  ({videos_to_process} vídeo(s) para processar)")

        lines.append("")

        # Parquet summary
        parquet_summary = self.wizard_data.get("parquet_summary", {})
        if parquet_summary:
            lines.append("📦 Parquets Existentes:")
            lines.append(f"  • Arena: {parquet_summary.get('total_arena', 0)}")
            lines.append(f"  • ROIs: {parquet_summary.get('total_rois', 0)}")
            lines.append(f"  • Trajetória: {parquet_summary.get('total_trajectory', 0)}")
            lines.append(f"  • Completos: {parquet_summary.get('total_complete', 0)}")

        lines.append("")

        # Import configuration summary (show what will be imported)
        import_config = self.wizard_data.get("import_config", [])
        if import_config:
            importing_arena = any(cfg.get("import_arena", False) for cfg in import_config)
            importing_rois = any(cfg.get("import_rois", False) for cfg in import_config)
            importing_trajectory = any(cfg.get("import_trajectory", False) for cfg in import_config)

            if importing_arena or importing_rois or importing_trajectory:
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

                lines.append("")

        # ROI merge strategy (only show if importing ROIs)
        importing_rois = any(cfg.get("import_rois", False) for cfg in import_config) if import_config else False

        if importing_rois:
            roi_strategy = self.wizard_data.get("roi_merge_strategy", "replace")
            strategy_names = {
                "replace": "Substituir ROIs existentes",
                "merge": "Mesclar (manter ambos)",
                "manual": "Resolução manual de conflitos",
            }
            lines.append("🔀 Estratégia de ROIs:")
            lines.append(f"  • {strategy_names.get(roi_strategy, roi_strategy)}")

        self.summary_text = "\n".join(lines)
        self.summary_label.config(text=self.summary_text)

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
        if not re.match(r'^[A-Za-z0-9_\- ]+$', project_name):
            return (False, "Nome do projeto contém caracteres inválidos. Use apenas letras, números, espaços, '_' e '-'.")

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
