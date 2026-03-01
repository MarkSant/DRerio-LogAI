"""
Script de teste manual para verificar o layout do painel esquerdo
Execute com: poetry run python scripts/test_panel_width.py
"""

import os
import sys
import tkinter as tk
from tkinter import ttk

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from zebtrack.ui.components.zone_controls import ZoneControlsWidget
from zebtrack.ui.event_bus import EventBus  # type: ignore[import-untyped]


def create_test_window():
    """Create a test window mimicking the zone tab layout"""
    root = tk.Tk()
    root.title("Teste de Largura do Painel - ZebTrack")
    root.geometry("1400x800")

    # Create main paned window
    main_pane = ttk.PanedWindow(root, orient="horizontal")
    main_pane.pack(expand=True, fill="both", padx=10, pady=10)

    # Left panel
    left_panel = ttk.Frame(main_pane, padding=5, relief="groove", borderwidth=2)
    main_pane.add(left_panel, weight=1)

    # Create zone controls
    event_bus = EventBus()
    zone_controls = ZoneControlsWidget(left_panel, event_bus=event_bus)
    zone_controls.pack(fill="both", expand=True)

    # Add test button to fixed frame (simulating single video analysis button)
    test_button = ttk.Button(
        zone_controls.fixed_button_frame,
        text="Iniciar Análise de Vídeo Único",
    )
    test_button.pack(side="bottom", fill="x", pady=5)

    # Right panel (video display)
    right_panel = ttk.Frame(main_pane, padding=5, relief="sunken", borderwidth=2)
    main_pane.add(right_panel, weight=4)

    # Add a canvas to simulate video display
    canvas = tk.Canvas(right_panel, bg="gray", width=800, height=600)
    canvas.pack(expand=True, fill="both")

    # Bind configure event to maintain minimum width
    def _on_pane_configure(event=None):
        try:
            current_pos = main_pane.sashpos(0)
            if current_pos < 560:
                main_pane.sashpos(0, 560)
        except Exception:
            pass

    main_pane.bind("<Configure>", _on_pane_configure)

    # Set initial sash position AFTER widgets are created
    def _set_initial_sash():
        try:
            main_pane.update_idletasks()
            main_pane.sashpos(0, 600)
            print("✓ Sash position set to 600px")
        except Exception as e:
            print(f"✗ Failed to set sash position: {e}")

    # Try multiple times
    for delay in [10, 50, 100, 200]:
        main_pane.after(delay, _set_initial_sash)

    # Add info label
    info_frame = ttk.Frame(root)
    info_frame.pack(side="bottom", fill="x", padx=10, pady=5)

    ttk.Label(
        info_frame,
        text=(
            "Verifique se o botão 'Aplicar' está visível e os textos "
            "estão centralizados no painel esquerdo"
        ),
        foreground="blue",
    ).pack()

    # Add current width display
    width_var = tk.StringVar(value="Largura: calculando...")
    width_label = ttk.Label(info_frame, textvariable=width_var)
    width_label.pack()

    def update_width():
        try:
            pos = main_pane.sashpos(0)
            width_var.set(f"Largura do painel esquerdo: {pos}px (mínimo: 560px, ideal: 600px)")
        except Exception:
            pass
        root.after(100, update_width)

    root.after(100, update_width)

    root.mainloop()


if __name__ == "__main__":
    print("Iniciando teste de largura do painel...")
    print("- Mínimo esperado: 560px")
    print("- Ideal: 600px")
    print("-" * 60)
    create_test_window()
