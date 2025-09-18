#!/usr/bin/env python3
"""
Simple script to demonstrate the UI changes for frame intervals.
This will create a mock GUI to show the new controls.
"""

import sys
import os
sys.path.insert(0, 'src')

import tkinter as tk
from tkinter import ttk, StringVar

# Mock the minimum needed imports
class MockSettings:
    class VideoProcessing:
        processing_interval = 10
    video_processing = VideoProcessing()

class MockController:
    class MockProjectManager:
        def get_project_type(self):
            return "pre-recorded"
    project_manager = MockProjectManager()

# Create the main window
root = tk.Tk()
root.title("ZebTrack-AI - Frame Intervals UI Demo")
root.geometry("600x400")

# Create notebook
notebook = ttk.Notebook(root)
notebook.pack(expand=True, fill="both", padx=5, pady=5)

# Create interval variables (as per new implementation)
analysis_interval_var = StringVar(value="10")
display_interval_var = StringVar(value="10")

# Create main controls tab (Project workflow)
main_controls_frame = ttk.Frame(notebook, padding="10")
notebook.add(main_controls_frame, text="Controle Principal")

# Add the main button
ttk.Button(
    main_controls_frame,
    text="Adicionar e Processar Novos Vídeos/Pastas...",
    state="disabled"  # Disabled for demo
).pack(pady=10, padx=10, fill="x")

# Project-wide interval settings
intervals_frame = ttk.LabelFrame(
    main_controls_frame, text="Intervalos de Processamento", padding=10
)
intervals_frame.pack(fill="x", pady=10, padx=10)

# Analysis interval
analysis_label_frame = ttk.Frame(intervals_frame)
analysis_label_frame.pack(fill="x", pady=2)
ttk.Label(analysis_label_frame, text="Intervalo de Análise (frames):").pack(side="left")
ttk.Entry(
    analysis_label_frame, textvariable=analysis_interval_var, width=10
).pack(side="right")

# Display interval  
display_label_frame = ttk.Frame(intervals_frame)
display_label_frame.pack(fill="x", pady=2)
ttk.Label(display_label_frame, text="Intervalo de Exibição (frames):").pack(side="left")
ttk.Entry(
    display_label_frame, textvariable=display_interval_var, width=10
).pack(side="right")

# Create zones tab (Single Video workflow)
zone_tab_frame = ttk.Frame(notebook, padding="10")
notebook.add(zone_tab_frame, text="Configuração de Zonas")

# Create zone controls frame
zone_controls_frame = ttk.LabelFrame(zone_tab_frame, text="Controles", padding=10)
zone_controls_frame.pack(side="right", fill="y", padx=5)

# Single Analysis Options Frame
single_analysis_options_frame = ttk.LabelFrame(
    zone_controls_frame,
    text="Opções de Análise de Vídeo Único",
    padding=10,
)
single_analysis_options_frame.pack(fill="x", pady=5)

# ROI options (existing)
roi_choice_var = StringVar(value="none")
ttk.Label(single_analysis_options_frame, text="Opções de ROI:").pack(anchor="w")
ttk.Radiobutton(
    single_analysis_options_frame, text="Não usar ROIs",
    variable=roi_choice_var, value="none"
).pack(anchor="w", padx=10)
ttk.Radiobutton(
    single_analysis_options_frame, text="Desenhar ROIs manualmente",
    variable=roi_choice_var, value="manual"
).pack(anchor="w", padx=10)
ttk.Radiobutton(
    single_analysis_options_frame, text="Usar ROIs de template",
    variable=roi_choice_var, value="template"
).pack(anchor="w", padx=10)

# NEW: Frame intervals for analysis and display
ttk.Label(
    single_analysis_options_frame, text="Intervalo de Análise (frames):"
).pack(anchor="w", pady=(10, 0))
ttk.Entry(
    single_analysis_options_frame,
    textvariable=analysis_interval_var,
    width=10,
).pack(anchor="w", padx=10)

ttk.Label(
    single_analysis_options_frame, text="Intervalo de Exibição (frames):"
).pack(anchor="w", pady=(5, 0))
ttk.Entry(
    single_analysis_options_frame,
    textvariable=display_interval_var,
    width=10,
).pack(anchor="w", padx=10)

# Add some explanation
explanation_frame = ttk.LabelFrame(root, text="Explicação das Mudanças", padding=10)
explanation_frame.pack(fill="x", padx=5, pady=5)

explanation_text = """
✅ Removido: Loop alternativo de processamento (_file_processing_loop)
✅ Adicionado: Controles de intervalo em ambos os fluxos (Projeto e Vídeo Único)
✅ Intervalo de Análise: A cada N frames, executa detecção e salva dados
✅ Intervalo de Exibição: A cada M frames processados, atualiza a interface
✅ Intervalos são salvos no projeto e restaurados ao reabrir
✅ Valores padrão: 10 frames para ambos os intervalos
"""

ttk.Label(explanation_frame, text=explanation_text, font=("Arial", 9)).pack(anchor="w")

print("UI Demo started. The new interval controls are visible in both tabs.")
print("- Main Controls tab: Project-wide settings")  
print("- Zones Configuration tab: Single video settings")
print("Both use the same variables and default to 10 frames.")

# Start the event loop
try:
    root.mainloop()
except KeyboardInterrupt:
    print("Demo stopped.")