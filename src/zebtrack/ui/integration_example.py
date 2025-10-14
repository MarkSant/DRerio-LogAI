"""
Exemplo de integração dos novos componentes UI no ApplicationGUI.

Este arquivo demonstra como integrar os componentes modulares criados no Step 6
na ApplicationGUI existente, substituindo a criação inline de widgets.
"""

import tkinter as tk
from tkinter import ttk

from zebtrack.ui.components import (
    ControlPanelWidget,
    VideoDisplayWidget,
    ZoneControlsWidget,
)
from zebtrack.ui.event_bus import EventBus


class IntegrationExample:
    """
    Exemplo de como integrar os componentes no ApplicationGUI.

    Este exemplo mostra os padrões de integração que devem ser seguidos
    ao substituir código inline por componentes modulares.
    """

    def __init__(self, root, controller, event_bus: EventBus):
        self.root = root
        self.controller = controller
        self.event_bus = event_bus

        # Criar notebook para tabs
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True)

        # Exemplos de integração
        self._example_1_video_display()
        self._example_2_zone_controls()
        self._example_3_control_panel()
        self._example_4_combined_tab()

    def _example_1_video_display(self):
        """
        Exemplo 1: Integrar VideoDisplayWidget

        ANTES (código inline):
        ---------------------
        self.roi_canvas = Canvas(parent, bg="gray")
        self.roi_canvas.pack(expand=True, fill="both")
        # ... 100+ linhas de lógica de display

        DEPOIS (usando componente):
        ---------------------------
        """
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Exemplo 1: Video Display")

        # Criar o widget de display de vídeo
        self.video_display = VideoDisplayWidget(
            tab, event_bus=self.event_bus, width=800, height=600, bg="gray"
        )
        self.video_display.pack(fill="both", expand=True)

        # Subscrever eventos do componente
        if self.event_bus:
            self.event_bus.subscribe("frame.loaded", self._on_frame_loaded)
            self.event_bus.subscribe("frame.error", self._on_frame_error)

        # Usar API pública para carregar frame
        # self.video_display.load_frame("/path/to/video.mp4", frame_number=0)

        # Label informativo
        ttk.Label(
            tab,
            text="VideoDisplayWidget substitui o Canvas inline com lógica de scaling",
            padding=10,
        ).pack(side="bottom")

    def _example_2_zone_controls(self):
        """
        Exemplo 2: Integrar ZoneControlsWidget

        ANTES (código inline):
        ---------------------
        # 500+ linhas criando:
        # - Botões de desenho
        # - Lista de zonas
        # - Seletor de vídeo
        # - Templates de ROI
        # - Configurações de inclusão

        DEPOIS (usando componente):
        ---------------------------
        """
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Exemplo 2: Zone Controls")

        # Criar o widget de controles de zona
        self.zone_controls = ZoneControlsWidget(tab, event_bus=self.event_bus)
        self.zone_controls.pack(fill="both", expand=True, padx=10, pady=10)

        # Subscrever eventos do componente
        if self.event_bus:
            self.event_bus.subscribe("zone.auto_detect_clicked", self._on_auto_detect)
            self.event_bus.subscribe("zone.draw_main_polygon", self._on_draw_main_polygon)
            self.event_bus.subscribe("zone.draw_roi", self._on_draw_roi)
            self.event_bus.subscribe("zone.template_apply", self._on_apply_template)

        # Usar API pública para controlar estado
        # self.zone_controls.set_draw_roi_enabled(True)
        # self.zone_controls.update_template_list(["Template 1", "Template 2"])

        # Label informativo
        ttk.Label(
            tab,
            text="ZoneControlsWidget substitui 500+ linhas de código inline",
            padding=10,
        ).pack(side="bottom")

    def _example_3_control_panel(self):
        """
        Exemplo 3: Integrar ControlPanelWidget

        ANTES (código inline):
        ---------------------
        self.start_rec_btn = Button(parent, text="Iniciar", command=...)
        self.stop_rec_btn = Button(parent, text="Parar", command=...)
        # ... lógica de estado dos botões espalhada

        DEPOIS (usando componente):
        ---------------------------
        """
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Exemplo 3: Control Panel")

        # Criar o widget de painel de controle
        self.control_panel = ControlPanelWidget(tab, event_bus=self.event_bus)
        self.control_panel.pack(fill="x", padx=20, pady=20)

        # Subscrever eventos do componente
        if self.event_bus:
            self.event_bus.subscribe("control.start_recording", self._on_start_recording)
            self.event_bus.subscribe("control.stop_recording", self._on_stop_recording)
            self.event_bus.subscribe("control.process_video", self._on_process_video)

        # Usar API pública para atualizar estado
        # self.control_panel.set_recording_state(is_recording=True)
        # self.control_panel.set_processing_enabled(enabled=False)

        # Label informativo
        ttk.Label(
            tab, text="ControlPanelWidget centraliza controles de gravação", padding=10
        ).pack()

    def _example_4_combined_tab(self):
        """
        Exemplo 4: Combinar múltiplos componentes em uma tab

        Demonstra como compor componentes para criar UIs complexas.
        """
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Exemplo 4: Combined")

        # Layout: Video display + Zone controls lado a lado
        paned_window = ttk.PanedWindow(tab, orient="horizontal")
        paned_window.pack(fill="both", expand=True, padx=5, pady=5)

        # Painel esquerdo: Zone Controls
        left_panel = ttk.Frame(paned_window)
        paned_window.add(left_panel, weight=1)

        self.zone_controls_combined = ZoneControlsWidget(left_panel, event_bus=self.event_bus)
        self.zone_controls_combined.pack(fill="both", expand=True)

        # Painel direito: Video Display
        right_panel = ttk.Frame(paned_window)
        paned_window.add(right_panel, weight=3)

        self.video_display_combined = VideoDisplayWidget(
            right_panel, event_bus=self.event_bus, width=640, height=480
        )
        self.video_display_combined.pack(fill="both", expand=True)

        # Label informativo
        info_frame = ttk.Frame(tab)
        info_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(
            info_frame,
            text="Componentes podem ser combinados facilmente usando layouts",
            font=("TkDefaultFont", 9, "italic"),
        ).pack()

    # Event handlers que delegam para o controller

    def _on_frame_loaded(self, data: dict):
        """Handle frame loaded event."""
        print(f"Frame loaded: {data}")
        # self.controller.on_frame_loaded(data)

    def _on_frame_error(self, data: dict):
        """Handle frame error event."""
        print(f"Frame error: {data}")
        # self.controller.show_error("Erro ao carregar frame", data.get("error"))

    def _on_auto_detect(self, data: dict):
        """Handle auto-detect clicked event."""
        print(f"Auto-detect clicked: {data}")
        # self.controller.auto_detect_arena(data["stabilization_frames"])

    def _on_draw_main_polygon(self, data: dict):
        """Handle draw main polygon event."""
        print("Draw main polygon clicked")
        # self.controller.start_zone_drawing("main_arena")

    def _on_draw_roi(self, data: dict):
        """Handle draw ROI event."""
        print("Draw ROI clicked")
        # self.controller.start_zone_drawing("roi")

    def _on_apply_template(self, data: dict):
        """Handle apply template event."""
        print(f"Apply template: {data}")
        # self.controller.apply_roi_template(data["template_name"])

    def _on_start_recording(self, data: dict):
        """Handle start recording event."""
        print("Start recording clicked")
        # self.controller.start_recording()

    def _on_stop_recording(self, data: dict):
        """Handle stop recording event."""
        print("Stop recording clicked")
        # self.controller.stop_recording()

    def _on_process_video(self, data: dict):
        """Handle process video event."""
        print("Process video clicked")
        # self.controller.process_video()


def main():
    """
    Executar o exemplo de integração.

    Para testar:
    poetry run python -m zebtrack.ui.integration_example
    """
    root = tk.Tk()
    root.title("Exemplo de Integração - Componentes UI")
    root.geometry("1200x800")

    # Criar event bus mock
    event_bus = EventBus()

    # Criar controller mock (ou usar o real)
    controller = None  # Mock

    # Criar exemplo
    _app = IntegrationExample(root, controller, event_bus)  # noqa: F841

    # Iniciar event bus polling (se usando event bus real)
    # event_bus.start_polling(root)

    root.mainloop()


if __name__ == "__main__":
    main()
