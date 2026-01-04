"""Live Camera Mode Selection Dialog.

Shows hardware capability report and mode selection options when
requested aquarium count exceeds hardware capabilities.

Version: 2.2.0
"""

from tkinter import (
    Button,
    Frame,
    Label,
    Radiobutton,
    StringVar,
    Toplevel,
)
from tkinter import (
    font as tkfont,
)
from typing import Callable

import structlog

from zebtrack.core.live_camera_mode import LiveCameraMode, LiveCameraModeRecommendation
from zebtrack.utils.hardware_capability import (
    HardwareCapabilityReport,
    MultiAquariumCapability,
)

log = structlog.get_logger()


class LiveCameraModeSelectionDialog(Toplevel):
    """Dialog for selecting live camera processing mode based on hardware.

    Displays:
    - Hardware capability summary
    - Requested vs supported aquarium count
    - Recommended mode with description
    - Fallback mode options
    - Accept/Cancel actions

    Example:
        def on_selected(mode: LiveCameraMode) -> None:
            print(f"User selected: {mode.name}")

        dialog = LiveCameraModeSelectionDialog(
            parent=root,
            requested_aquariums=4,
            hardware_report=report,
            recommendation=recommendation,
            on_mode_selected=on_selected,
        )
    """

    # Mode descriptions (Portuguese)
    MODE_DESCRIPTIONS = {
        LiveCameraMode.MULTI_AQUARIUM_REALTIME: (
            "Processamento Paralelo em Tempo Real\n"
            "• Detecta 2-6 aquários simultaneamente\n"
            "• Requer GPU e ≥4 cores de CPU\n"
            "• Maior throughput, ideal para experimentos grandes"
        ),
        LiveCameraMode.SINGLE_AQUARIUM_REALTIME: (
            "Aquário Único em Tempo Real\n"
            "• Processa 1 aquário por vez\n"
            "• Requer ≥2 cores de CPU\n"
            "• Ideal para sistemas com recursos limitados"
        ),
        LiveCameraMode.SEQUENTIAL_AQUARIUM: (
            "Sessões Sequenciais\n"
            "• Grava N sessões separadas, uma de cada vez\n"
            "• Processa cada aquário em tempo real\n"
            "• Requer intervenção manual entre sessões"
        ),
        LiveCameraMode.RECORD_ONLY: (
            "Apenas Gravação (Offline)\n"
            "• Grava vídeo sem processamento em tempo real\n"
            "• Análise posterior com todos os recursos\n"
            "• Sempre possível, sem requisitos de hardware"
        ),
    }

    def __init__(
        self,
        parent,
        requested_aquariums: int,
        hardware_report: HardwareCapabilityReport,
        recommendation: LiveCameraModeRecommendation,
        on_mode_selected: Callable[[LiveCameraMode], None],
    ):
        """Initialize mode selection dialog.

        Args:
            parent: Parent Tkinter widget
            requested_aquariums: Number of aquariums user wants to process
            hardware_report: Hardware capability assessment
            recommendation: Mode recommendation from LiveCameraModeSelector
            on_mode_selected: Callback with selected mode
        """
        super().__init__(parent)

        self.requested_aquariums = requested_aquariums
        self.hardware_report = hardware_report
        self.recommendation = recommendation
        self.on_mode_selected = on_mode_selected
        self.selected_mode: LiveCameraMode | None = None

        # UI state
        self.mode_var = StringVar(value=recommendation.recommended_mode.name)

        # Configure dialog
        self.title("Seleção de Modo de Processamento")
        self.geometry("700x650")
        self.resizable(False, False)

        # Make modal
        self.transient(parent)
        self.grab_set()

        # Build UI
        self._build_ui()

        # Center on parent
        self._center_on_parent(parent)

        log.info(
            "live_camera_mode_dialog.opened",
            requested_aquariums=requested_aquariums,
            recommended_mode=recommendation.recommended_mode.name,
        )

    def _build_ui(self) -> None:
        """Build dialog UI."""
        # Title
        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(
            self,
            text="⚠️ Ajuste de Modo de Processamento Necessário",
            font=title_font,
            fg="#D84315",
        )
        title.pack(pady=(15, 10))

        # Warning message
        warning_msg = (
            f"Seu sistema não suporta processamento em tempo real "
            f"de {self.requested_aquariums} aquários simultaneamente.\n\n"
            f"Revise as opções abaixo e selecione o modo adequado."
        )
        warning_label = Label(
            self,
            text=warning_msg,
            wraplength=650,
            justify="left",
            fg="#555555",
        )
        warning_label.pack(pady=(0, 15), padx=20)

        # Hardware summary
        self._build_hardware_summary()

        # Mode selection
        self._build_mode_selection()

        # Actions
        self._build_actions()

    def _build_hardware_summary(self) -> None:
        """Build hardware capability summary section."""
        frame = Frame(self, relief="groove", borderwidth=2, bg="#F5F5F5")
        frame.pack(fill="x", padx=20, pady=(0, 15))

        header = Label(
            frame,
            text="📊 Resumo de Hardware",
            font=tkfont.Font(size=11, weight="bold"),
            bg="#F5F5F5",
        )
        header.pack(pady=(10, 5))

        # Capability tier
        capability_colors = {
            MultiAquariumCapability.EXCELLENT: "#4CAF50",
            MultiAquariumCapability.VERY_GOOD: "#8BC34A",
            MultiAquariumCapability.GOOD: "#FFC107",
            MultiAquariumCapability.LIMITED: "#FF9800",
            MultiAquariumCapability.INSUFFICIENT: "#F44336",
        }
        capability_label = Label(
            frame,
            text=f"Capacidade: {self.hardware_report.capability.name}",
            font=tkfont.Font(size=10, weight="bold"),
            fg=capability_colors.get(self.hardware_report.capability, "#555555"),
            bg="#F5F5F5",
        )
        capability_label.pack(pady=2)

        # Hardware details
        details = (
            f"CPU: {self.hardware_report.cpu_cores} cores "
            f"({self.hardware_report.cpu_usage_percent:.0f}% uso)\n"
            f"RAM: {self.hardware_report.available_memory_gb:.1f} GB disponível "
            f"de {self.hardware_report.total_memory_gb:.1f} GB\n"
            f"GPU: {'✓ ' + self.hardware_report.gpu_name if self.hardware_report.has_gpu else '✗ Não detectada'}\n"
            f"Aquários Suportados: {self.hardware_report.max_aquariums_recommended}\n"
            f"Tempo Real: {'✓ Sim' if self.hardware_report.can_process_realtime else '✗ Não'}"
        )
        details_label = Label(
            frame,
            text=details,
            justify="left",
            bg="#F5F5F5",
            fg="#333333",
        )
        details_label.pack(pady=(5, 10), padx=15)

    def _build_mode_selection(self) -> None:
        """Build mode selection section."""
        frame = Frame(self)
        frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        header = Label(
            frame,
            text="🎯 Selecione o Modo de Processamento",
            font=tkfont.Font(size=11, weight="bold"),
        )
        header.pack(pady=(0, 10))

        # Recommended mode (highlighted)
        rec_frame = Frame(frame, relief="solid", borderwidth=2, bg="#E8F5E9")
        rec_frame.pack(fill="x", pady=(0, 10))

        Radiobutton(
            rec_frame,
            text=f"✨ {self._mode_display_name(self.recommendation.recommended_mode)} (Recomendado)",
            variable=self.mode_var,
            value=self.recommendation.recommended_mode.name,
            font=tkfont.Font(weight="bold"),
            bg="#E8F5E9",
            activebackground="#E8F5E9",
            command=self._on_mode_changed,
        ).pack(anchor="w", padx=10, pady=5)

        rec_desc = Label(
            rec_frame,
            text=self.MODE_DESCRIPTIONS[self.recommendation.recommended_mode],
            justify="left",
            wraplength=620,
            bg="#E8F5E9",
            fg="#555555",
        )
        rec_desc.pack(anchor="w", padx=30, pady=(0, 10))

        # Fallback modes
        if self.recommendation.fallback_modes:
            fallback_label = Label(
                frame,
                text="Alternativas:",
                font=tkfont.Font(size=10, weight="bold"),
            )
            fallback_label.pack(anchor="w", pady=(5, 5))

            for mode in self.recommendation.fallback_modes:
                mode_frame = Frame(frame, relief="groove", borderwidth=1)
                mode_frame.pack(fill="x", pady=2)

                Radiobutton(
                    mode_frame,
                    text=self._mode_display_name(mode),
                    variable=self.mode_var,
                    value=mode.name,
                    command=self._on_mode_changed,
                ).pack(anchor="w", padx=10, pady=5)

                mode_desc = Label(
                    mode_frame,
                    text=self.MODE_DESCRIPTIONS[mode],
                    justify="left",
                    wraplength=620,
                    fg="#555555",
                )
                mode_desc.pack(anchor="w", padx=30, pady=(0, 10))

    def _build_actions(self) -> None:
        """Build action buttons."""
        button_frame = Frame(self)
        button_frame.pack(pady=15)

        Button(
            button_frame,
            text="✓ Confirmar Seleção",
            command=self._on_confirm,
            width=20,
            bg="#4CAF50",
            fg="white",
            font=tkfont.Font(weight="bold"),
        ).pack(side="left", padx=5)

        Button(
            button_frame,
            text="✗ Cancelar",
            command=self._on_cancel,
            width=20,
        ).pack(side="left", padx=5)

    def _mode_display_name(self, mode: LiveCameraMode) -> str:
        """Get Portuguese display name for mode."""
        names = {
            LiveCameraMode.MULTI_AQUARIUM_REALTIME: "Multi-Aquário Paralelo",
            LiveCameraMode.SINGLE_AQUARIUM_REALTIME: "Aquário Único",
            LiveCameraMode.SEQUENTIAL_AQUARIUM: "Sessões Sequenciais",
            LiveCameraMode.RECORD_ONLY: "Apenas Gravação",
        }
        return names.get(mode, mode.name)

    def _on_mode_changed(self) -> None:
        """Handle mode selection change."""
        selected = self.mode_var.get()
        log.debug("live_camera_mode_dialog.mode_changed", mode=selected)

    def _on_confirm(self) -> None:
        """Confirm mode selection."""
        selected_name = self.mode_var.get()
        self.selected_mode = LiveCameraMode[selected_name]

        log.info(
            "live_camera_mode_dialog.confirmed",
            selected_mode=self.selected_mode.name,
        )

        # Invoke callback
        if self.on_mode_selected:
            self.on_mode_selected(self.selected_mode)

        self.destroy()

    def _on_cancel(self) -> None:
        """Cancel dialog without selecting mode."""
        log.info("live_camera_mode_dialog.cancelled")
        self.selected_mode = None
        self.destroy()

    def _center_on_parent(self, parent) -> None:
        """Center dialog on parent window."""
        self.update_idletasks()

        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()

        dialog_width = self.winfo_width()
        dialog_height = self.winfo_height()

        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2

        self.geometry(f"+{x}+{y}")
