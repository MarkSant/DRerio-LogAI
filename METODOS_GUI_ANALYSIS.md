# Análise Completa dos 34 Métodos de gui.py

## Importações e Dependências Globais

```python
import copy
import hashlib
import os
import queue
import re
import subprocess
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from tkinter import (
    BooleanVar, Button, Canvas, Frame, Label, Menu, StringVar,
    Toplevel, filedialog, messagebox, simpledialog, ttk,
)
from tkinter import font as tkfont
from typing import Any

import cv2
import numpy as np
import structlog
import yaml
from PIL import Image, ImageTk
from pydantic import ValidationError

import zebtrack.settings as settings_module
from zebtrack.core.detector import ZoneData
from zebtrack.core.processing_mode import ProcessingMode, ProcessingReport
from zebtrack.io.camera import Camera
from zebtrack.ui.components import (
    AnalysisDisplayWidget, ArduinoDashboardWidget, CanvasManager,
    ConfigEditorWidget, EventDispatcher, MenuManager, ProjectOverviewWidget,
    StateSynchronizer, VideoDisplayWidget, ZoneControlsWidget,
)
from zebtrack.ui.dialogs import (
    CalibrationDialog, CenterPeripheryDialog, ColorSelectionDialog,
    MissingMetadataDialog, PendingVideosDialog, SaveROITemplateDialog,
    SingleVideoConfigDialog, StartRecordingDialog, SubjectSelectionDialog,
    TemplateDialog,
)
from zebtrack.ui.event_bus import EventBus, EventType
from zebtrack.ui.events import Events
from zebtrack.ui.window_utils import reset_geometry_if_not_maximized
from zebtrack.utils import polygon_centroid, snap_point_to_axes
```

---

## 1. _build_status_icon_legend

**Linhas:** 426-436
**Assinatura:** `def _build_status_icon_legend(self, *, include_summary: bool = False) -> str:`
**Tipo:** Utilitário de formatação
**Complexidade:** Baixa (5 linhas lógicas)

### Código Completo
```python
def _build_status_icon_legend(self, *, include_summary: bool = False) -> str:
    """Compose a compact legend string for the status glyphs."""
    legend_parts = [
        f"{STATUS_SYMBOLS['arena']} ✓ Arena",
        f"{STATUS_SYMBOLS['rois']} ✓ ROIs",
        f"{STATUS_SYMBOLS['trajectory']} ✓ Trajetória",
    ]
    if include_summary:
        legend_parts.append(f"{STATUS_SYMBOLS['summary']} ✓ Sumário")
    legend_parts.append("✗ Ausente")
    return "Legenda: " + " | ".join(legend_parts)
```

### Dependências
- `STATUS_SYMBOLS` (dicionário global definido em topo do arquivo)

---

## 2. _create_welcome_frame

**Linhas:** 592-617
**Assinatura:** `def _create_welcome_frame(self):`
**Tipo:** Construtor UI
**Complexidade:** Média (10 linhas)

### Código Completo
```python
def _create_welcome_frame(self):
    """Creates the initial UI for project selection and model configuration."""
    # Reset title to default (no project)
    self._update_window_title()

    self._cleanup_single_analysis_button()
    # CRITICAL: Force process all pending GUI events before cleanup
    # This ensures all scheduled callbacks are executed
    self.root.update_idletasks()

    # Reset + destroy analysis-related widgets
    self._reset_analysis_widgets()

    # Force final GUI update before creating welcome frame
    self.root.update_idletasks()

    reset_geometry_if_not_maximized(self.root)
    self.welcome_frame = ttk.Frame(self.root, padding="10")
    self.welcome_frame.pack(expand=True, fill="both")

    # --- Logo Image ---
    self._display_welcome_logo()

    # Project actions and model status widgets
    self._build_project_actions(self.welcome_frame)
    self._build_model_status(self.welcome_frame)
```

### Dependências
- Chama: `_update_window_title()`, `_cleanup_single_analysis_button()`, `_reset_analysis_widgets()`, `_display_welcome_logo()`, `_build_project_actions()`, `_build_model_status()`
- Usa: `self.root`, `self.welcome_frame`
- Import: `reset_geometry_if_not_maximized` (zebtrack.ui.window_utils)

---

## 3. _build_project_actions

**Linhas:** 632-656
**Assinatura:** `def _build_project_actions(self, parent) -> None:`
**Tipo:** Construtor UI de controles
**Complexidade:** Baixa (4 botões)

### Código Completo
```python
def _build_project_actions(self, parent) -> None:
    """Create the project actions controls in the welcome frame."""
    project_actions_frame = ttk.LabelFrame(parent, text="Ações do Projeto", padding=10)
    project_actions_frame.pack(fill="x", pady=10, expand=True)

    ttk.Button(
        project_actions_frame,
        text="Calibração Global (Pesos e Diagnóstico)...",
        command=self._open_global_calibration_window,
    ).pack(fill="x", padx=10, pady=5)
    ttk.Button(
        project_actions_frame,
        text="Analisar Vídeo Único",
        command=self._on_analyze_single_video_clicked,
    ).pack(fill="x", padx=10, pady=5)
    ttk.Button(
        project_actions_frame,
        text="Criar Novo Projeto",
        command=self._create_project_workflow,
    ).pack(fill="x", padx=10, pady=5)
    ttk.Button(
        project_actions_frame,
        text="Abrir Projeto Existente",
        command=self._open_project_workflow,
    ).pack(fill="x", padx=10, pady=5)
```

### Dependências
- Parâmetro `parent`: ttk.Frame ou similar
- Chama: `_open_global_calibration_window()`, `_on_analyze_single_video_clicked()`, `_create_project_workflow()`, `_open_project_workflow()`

---

## 4. _build_model_status

**Linhas:** 658-674
**Assinatura:** `def _build_model_status(self, parent) -> None:`
**Tipo:** Construtor UI de status
**Complexidade:** Baixa (3 labels)

### Código Completo
```python
def _build_model_status(self, parent) -> None:
    """Create the model status display in the welcome frame."""
    model_status_frame = ttk.LabelFrame(parent, text="Estado do Modelo de Detecção", padding=10)
    model_status_frame.pack(fill="x", pady=10, expand=True)
    ttk.Label(
        model_status_frame,
        textvariable=self._active_weight_display_var,
    ).pack(anchor="w")
    ttk.Label(
        model_status_frame,
        textvariable=self._openvino_display_var,
    ).pack(anchor="w", pady=(4, 0))
    ttk.Label(
        model_status_frame,
        textvariable=self._gpu_hardware_display_var,
        foreground="gray",
    ).pack(anchor="w", pady=(4, 0))
```

### Dependências
- Parâmetro `parent`: ttk.Frame ou similar
- Usa: `self._active_weight_display_var`, `self._openvino_display_var`, `self._gpu_hardware_display_var`

---

## 5. _create_main_control_frame

**Linhas:** 882-922
**Assinatura:** `def _create_main_control_frame(self):`
**Tipo:** Construtor UI principal
**Complexidade:** Média-Alta (41 linhas)

### Código Completo
```python
def _create_main_control_frame(self):
    """Creates the main UI with tabs for controlling the app."""
    if self.welcome_frame:
        self.welcome_frame.destroy()
    reset_geometry_if_not_maximized(self.root)

    self.notebook = ttk.Notebook(self.root, style="Zebtrack.TNotebook")
    self.notebook.pack(expand=True, fill="both", padx=5, pady=5)

    # Bind tab change event to hide analysis overlay when switching tabs
    self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    # Create the tabs
    self._create_main_controls_tab()
    if self.controller.project_manager.get_project_type() == "live":
        self._create_progress_grid_tab()
    self._create_roi_analysis_tab()
    self._create_processing_reports_tab()  # New unified tab
    self._create_analysis_tab_widget()
    self._create_configuration_tab_widget()

    # Status frame below the notebook
    project_type_str = self.controller.project_manager.get_project_type()
    if project_type_str == "live":
        project_type_display = "Ao Vivo"
    elif project_type_str == "pre-recorded":
        project_type_display = "Pré-gravado"
    else:
        project_type_display = project_type_str

    status_text = (
        f"Projeto: {self.controller.project_manager.get_project_name()} "
        f"({project_type_display})"
    )
    self.status_var.set(status_text)
    status_frame = Frame(self.root)
    status_frame.pack(pady=5, fill="x", padx=10, side="bottom")
    Label(status_frame, textvariable=self.status_var).pack()

    # Ensure analysis UI starts hidden
    self.hide_progress_bar()
```

### Dependências
- Chama: `reset_geometry_if_not_maximized()`, `_on_tab_changed()`, `_create_main_controls_tab()`, `_create_progress_grid_tab()`, `_create_roi_analysis_tab()`, `_create_processing_reports_tab()`, `_create_analysis_tab_widget()`, `_create_configuration_tab_widget()`, `hide_progress_bar()`
- Usa: `self.welcome_frame`, `self.notebook`, `self.root`, `self.controller`, `self.status_var`

---

## 6. _create_configuration_tab_widget

**Linhas:** 924-951
**Assinatura:** `def _create_configuration_tab_widget(self) -> None:`
**Tipo:** Construtor UI de abas
**Complexidade:** Média (28 linhas)

### Código Completo
```python
def _create_configuration_tab_widget(self) -> None:
    """Creates the configuration tab using ConfigEditorWidget."""
    if not self.notebook:
        return

    # Create widget
    self.config_editor_widget = ConfigEditorWidget(
        self.notebook,
        event_bus=self.event_bus,
    )

    # Add to notebook
    self.notebook.add(self.config_editor_widget, text="Config. Avançadas")

    # Connect events
    if self.event_bus:
        self._event_bus_handlers["config.save_requested"] = (
            lambda data: self._on_save_global_config_from_widget(data["values"])
        )
        self._event_bus_handlers["config.reset_requested"] = (
            lambda data: self._on_reset_global_config_form_widget()
        )
        self._event_bus_handlers["config.roi_rule_changed"] = (
            lambda data: self._on_roi_rule_change_widget(data["rule"])
        )

    # Load current values
    self._reload_config_editor_values_widget()
```

### Dependências
- Usa: `self.notebook`, `self.event_bus`, `self._event_bus_handlers`
- Chama: `_reload_config_editor_values_widget()`
- Callbacks: `_on_save_global_config_from_widget()`, `_on_reset_global_config_form_widget()`, `_on_roi_rule_change_widget()`
- Import: `ConfigEditorWidget` (zebtrack.ui.components)

---

## 7. _reload_config_editor_values_widget

**Linhas:** 953-1002
**Assinatura:** `def _reload_config_editor_values_widget(self) -> None:`
**Tipo:** Carregador de estado
**Complexidade:** Média-Alta (50 linhas)

### Código Completo
```python
def _reload_config_editor_values_widget(self) -> None:
    """Load current settings into ConfigEditorWidget."""
    current = settings_module.settings
    if current is None:
        try:
            current = settings_module.load_settings()
            settings_module.settings = current
        except Exception as exc:  # pragma: no cover - defensive UI feedback
            self.show_error("Erro", f"Não foi possível carregar config.yaml: {exc}")
            return

    values = {
        "video_processing": {
            "fps": self._extract_setting(current, ("video_processing", "fps"), 30),
            "processing_interval": self._extract_setting(
                current, ("video_processing", "processing_interval"), 10
            ),
            "processing_offset": self._extract_setting(
                current, ("video_processing", "processing_offset"), 0
            ),
        },
        "trajectory_smoothing": {
            "window_length": self._extract_setting(
                current, ("trajectory_smoothing", "window_length"), 7
            ),
            "polyorder": self._extract_setting(
                current, ("trajectory_smoothing", "polyorder"), 3
            ),
        },
        "recorder": {
            "flush_interval_seconds": self._extract_setting(
                current, ("recorder", "flush_interval_seconds"), 5.0
            ),
            "flush_row_threshold": self._extract_setting(
                current, ("recorder", "flush_row_threshold"), 500
            ),
        },
        "roi_inclusion_rule": self._extract_setting(
            current, ("roi_inclusion_rule",), "centroid_in"
        ),
        "roi_buffer_radius_value": self._extract_setting(
            current, ("roi_buffer_radius_value",), 0.0
        ),
        "roi_min_bbox_overlap_ratio": self._extract_setting(
            current, ("roi_min_bbox_overlap_ratio",), 0.5
        ),
    }

    if self.config_editor_widget:
        self.config_editor_widget.set_values(values)
```

### Dependências
- Chama: `_extract_setting()`, `show_error()`
- Usa: `settings_module`, `self.config_editor_widget`
- Import: `settings_module` (zebtrack.settings)

---

## 8. _on_reset_global_config_form_widget

**Linhas:** 1004-1010
**Assinatura:** `def _on_reset_global_config_form_widget(self) -> None:`
**Tipo:** Handler de evento
**Complexidade:** Baixa (3 linhas)

### Código Completo
```python
def _on_reset_global_config_form_widget(self) -> None:
    """Reset ConfigEditorWidget form fields to reflect current settings object."""
    self._reload_config_editor_values_widget()
    self.show_info(
        "Formulário recarregado",
        "Valores restaurados para refletir as configurações atuais.",
    )
```

### Dependências
- Chama: `_reload_config_editor_values_widget()`, `show_info()`

---

## 9. _on_save_global_config_from_widget

**Linhas:** 1012-1097
**Assinatura:** `def _on_save_global_config_from_widget(self, values: dict) -> None:`
**Tipo:** Handler de evento + persistência
**Complexidade:** Alta (85 linhas)

### Código Completo (Parcial - muito grande)
```python
def _on_save_global_config_from_widget(self, values: dict) -> None:
    """Validate and save config from ConfigEditorWidget values."""
    try:
        # Extract values (already parsed by widget)
        fps = values["video_processing"]["fps"]
        processing_interval = values["video_processing"]["processing_interval"]
        processing_offset = values["video_processing"]["processing_offset"]
        flush_interval = values["recorder"]["flush_interval_seconds"]
        flush_rows = values["recorder"]["flush_row_threshold"]
        window_length = values["trajectory_smoothing"]["window_length"]
        polyorder = values["trajectory_smoothing"]["polyorder"]

        # Validate
        if fps <= 0:
            raise ValueError("FPS deve ser maior que 0.")
        if processing_interval <= 0:
            raise ValueError("O intervalo de processamento deve ser maior que 0.")
        if processing_offset < 0:
            raise ValueError("O offset deve ser maior ou igual a 0.")
        if flush_interval < 0:
            raise ValueError("O intervalo de flush deve ser >= 0.")
        if flush_rows < 1:
            raise ValueError("O limite de linhas para flush deve ser >= 1.")
        if window_length < 3 or window_length % 2 == 0:
            raise ValueError("Window length deve ser ímpar e pelo menos 3.")
        if polyorder < 1:
            raise ValueError("Polyorder deve ser pelo menos 1.")

    except ValueError as exc:
        self.show_error("Erro de Validação", str(exc))
        return

    # ... (continua com escrita em YAML e persistência)
```

### Dependências
- Chama: `_reload_config_editor_values_widget()`, `show_error()`, `show_info()`
- Usa: `settings_module`, `self.settings`, `Path`
- Import: `yaml`, `Path` (pathlib), `ValidationError` (pydantic)

---

## 10. _create_main_controls_tab

**Linhas:** 1105-1221
**Assinatura:** `def _create_main_controls_tab(self):`
**Tipo:** Construtor UI de abas
**Complexidade:** Alta (117 linhas)

### Resumo
Cria a aba de controle principal com:
- Botões de ação (iniciar/parar gravação ou processar vídeos)
- Configurações de intervalos (pré-gravado)
- Status do modelo de detecção
- ArduinoDashboardWidget (ao vivo)
- ProjectOverviewWidget

### Principais Dependências
- Chama: `_create_project_overview_panel()`, `_request_overview_refresh()`
- Usa: `self.notebook`, `self.main_controls_frame`, `self.controller`, `self.event_dispatcher`
- Import: `ArduinoDashboardWidget`, `Button` (tkinter)

---

## 11. _create_project_overview_panel

**Linhas:** 1223-1272
**Assinatura:** `def _create_project_overview_panel(self, parent: ttk.Frame) -> None:`
**Tipo:** Construtor UI de painel
**Complexidade:** Média-Alta (50 linhas)

### Código Completo (Parcial)
```python
def _create_project_overview_panel(self, parent: ttk.Frame) -> None:
    """Create the project overview panel using ProjectOverviewWidget."""
    if not parent:
        return

    if self.project_overview_frame and self.project_overview_frame.winfo_exists():
        try:
            self.project_overview_frame.destroy()
        except Exception:
            pass

    self.project_overview_frame = ttk.LabelFrame(parent, text="Resumo do Projeto", padding=10)
    self.project_overview_frame.pack(fill="both", expand=True, pady=(10, 10))

    # Create the ProjectOverviewWidget
    self.project_overview_widget = ProjectOverviewWidget(
        self.project_overview_frame, event_bus=self.event_bus
    )
    self.project_overview_widget.pack(fill="both", expand=True)

    # Subscribe to widget events
    if self.event_bus:
        self.event_bus.subscribe(
            "project.refresh_requested", self._handle_project_refresh_requested
        )
        self.event_bus.subscribe(
            "project.video_double_click", self._handle_project_video_double_click
        )
        self.event_bus.subscribe(
            "project.video_right_click", self._handle_project_video_right_click
        )
    # ... continua com separador e botão de navegação
```

### Dependências
- Parâmetro `parent`: ttk.Frame
- Usa: `self.event_bus`, `self.project_overview_frame`
- Chama: `_navigate_to_processing_reports_tab()`
- Import: `ProjectOverviewWidget` (zebtrack.ui.components)

---

## 12. _create_roi_analysis_tab

**Linhas:** 1802-1910
**Assinatura:** `def _create_roi_analysis_tab(self):`
**Tipo:** Construtor UI de abas (complexo)
**Complexidade:** MUITO ALTA (109 linhas)

### Resumo Estrutural
```
1. Inicializa estado de desenho (_drawing_mode, _poly_pts_*, etc)
2. Cria frame principal (self.zone_tab_frame)
3. Cria PanedWindow para layout lado-a-lado
4. Painel esquerdo: ZoneControlsWidget
5. Painel direito: VideoDisplayWidget
6. Bind _on_pane_configure para manter mín. de 600px
7. Bind _on_canvas_configure para redimensionamento
8. Create contexto menu
9. Subscribe eventos de ZoneControlsWidget
10. Set inicial sash position
```

### Principais Dependências
- Chama: `_subscribe_zone_component_events()`, `menu_manager.create_roi_context_menu()`
- Usa: `self.notebook`, `self.zone_controls`, `self.video_display`, `self.event_bus`
- Import: `ZoneControlsWidget`, `VideoDisplayWidget` (zebtrack.ui.components)

---

## 13. _on_pane_configure (função interna)

**Linhas:** 1860-1867
**Assinatura:** `def _on_pane_configure(event=None):`
**Tipo:** Callback de evento (definido dentro de `_create_roi_analysis_tab`)
**Complexidade:** Baixa

### Código Completo
```python
def _on_pane_configure(event=None):
    try:
        # Clamp left panel to minimum 600px width to keep all controls visible
        current_pos = main_pane.sashpos(0)
        if current_pos < 600:
            main_pane.sashpos(0, 600)
    except Exception:
        pass  # Ignore errors during resize
```

### Características
- Função local (closure) dentro de `_create_roi_analysis_tab`
- Captura `main_pane` do escopo externo
- Handler para evento `<Configure>` do PanedWindow

---

## 14. _on_canvas_configure

**Linhas:** 1962-1988
**Assinatura:** `def _on_canvas_configure(self, event=None):`
**Tipo:** Handler de evento Tkinter
**Complexidade:** Média

### Código Completo
```python
def _on_canvas_configure(self, event=None):
    """Handle canvas resize events to properly scale and center the image."""
    # Skip if this is not the main roi_canvas being resized
    if event and event.widget != self.roi_canvas:
        return

    if not hasattr(self, "_raw_bg_image") or not self._raw_bg_image:
        if hasattr(self, "_original_image") and self._original_image:
            self._raw_bg_image = self._original_image
        else:
            return

    # Get the current canvas dimensions
    canvas_width = self.roi_canvas.winfo_width()
    canvas_height = self.roi_canvas.winfo_height()

    if canvas_width <= 1 or canvas_height <= 1:
        return

    # Re-scale and center the background image using the new method
    try:
        self.canvas_manager._draw_bg_image_to_canvas()
        # After updating the background, redraw any zones that exist
        if hasattr(self, "controller") and self.controller:
            self.canvas_manager.redraw_zones_from_project_data()
    except Exception as e:
        log.warning("gui.canvas.configure_error", error=str(e))
```

### Dependências
- Usa: `self.roi_canvas`, `self.canvas_manager`, `self.controller`
- Chama: `canvas_manager._draw_bg_image_to_canvas()`, `canvas_manager.redraw_zones_from_project_data()`

---

## 15. _create_zone_control_widgets

**Linhas:** 1990-2374
**Assinatura:** `def _create_zone_control_widgets(self):`
**Tipo:** Construtor UI (MUITO GRANDE - 385 linhas!)
**Complexidade:** MUITO ALTA

### Estrutura Geral
```
1. _create_zone_summary_cards_section() (indicadores)
2. Ações de Desenho (4 botões)
   - Detectar Aquário (Auto)
   - Desenhar Polígono Principal
   - Desenhar Área de Interesse
   - Ver Análise em Progresso
3. Opções de Análise de Vídeo Único
   - ROI choice (none/manual/template)
   - Intervalos (análise/exibição)
4. Templates de ROI (combobox, aplicar, salvar, importar, deletar)
5. Seletor de Vídeo
   - Busca/filtro
   - Treeview hierárquico
6. Zona List (Treeview)
   - Botões Salvar/Descartar
7. Painel de Inclusão em ROI
   - Seletor de regra (centroid_in, buffered, bbox_intersects, seg_overlap)
   - Campos de parâmetros (raio, overlap)
   - Ajuda contextual
```

### Nota Importante
Método é chamado via componente ZoneControlsWidget - o código antigo é mantido para referência mas não está sendo usado!

---

## 16. _create_zone_summary_cards_section

**Linhas:** 2376-2448
**Assinatura:** `def _create_zone_summary_cards_section(self) -> None:`
**Tipo:** Construtor UI de cards
**Complexidade:** Média-Alta

### Código Completo (Parcial)
```python
def _create_zone_summary_cards_section(self) -> None:
    """Renderiza os cartões com indicadores numéricos da etapa de zonas."""
    if not getattr(self, "zone_controls_frame", None):
        return

    if self.zone_summary_frame and self.zone_summary_frame.winfo_exists():
        try:
            self.zone_summary_frame.destroy()
        except Exception:
            pass

    self.zone_summary_cards = {}
    self.zone_summary_frame = ttk.LabelFrame(
        self.zone_controls_frame,
        text=f"{STATUS_SYMBOLS['summary']} Indicadores de Preparação",
        padding=10,
    )
    self.zone_summary_frame.pack(fill="x", pady=(0, 5))

    cards_container = ttk.Frame(self.zone_summary_frame)
    cards_container.pack(fill="x")

    card_specs = [
        ("arena_missing", f"{STATUS_SYMBOLS['arena']} Arenas pendentes"),
        ("rois_missing", f"{STATUS_SYMBOLS['rois']} ROIs pendentes"),
        ("ready_for_processing", f"{STATUS_SYMBOLS['summary']} Prontos para trajetórias"),
    ]

    for idx, (key, title) in enumerate(card_specs):
        card = ttk.Frame(cards_container, padding=10, relief="ridge", borderwidth=1)
        card.grid(row=0, column=idx, padx=5, pady=5, sticky="nsew")
        cards_container.columnconfigure(idx, weight=1)

        value_var = StringVar(value="0")
        detail_var = StringVar(value="Nenhum vídeo listado")
        # ... continua com labels
```

### Dependências
- Usa: `self.zone_controls_frame`, `self.zone_summary_cards`, `STATUS_SYMBOLS`
- Chama: `_update_zone_summary_cards()`, `_get_zone_summary_helper_text()`

---

## 17. _create_pipeline_processing_tab

**Linhas:** 2450-2575
**Assinatura:** `def _create_pipeline_processing_tab(self) -> None:`
**Tipo:** Construtor UI (LEGADO)
**Complexidade:** Alta

### Nota
**Este método é LEGADO** - substituído por `_create_processing_reports_tab()`. Mantido para referência.

---

## 18. _create_analysis_tab_widget

**Linhas:** 2967-3001
**Assinatura:** `def _create_analysis_tab_widget(self):`
**Tipo:** Construtor UI de abas (delegado para componente)
**Complexidade:** Média

### Código Completo
```python
def _create_analysis_tab_widget(self):
    """Creates the analysis tab using the AnalysisDisplayWidget."""
    if not self.notebook:
        return

    # Create the widget
    self.analysis_display_widget = AnalysisDisplayWidget(
        self.notebook,
        event_bus=self.event_bus,
        available_track_options=list(self._available_track_options),
    )

    # Add to notebook
    self.notebook.add(self.analysis_display_widget, text="Análise de Vídeo")

    # Connect widget events to GUI handlers
    if self.event_bus:
        self._event_bus_handlers["analysis.track_selected"] = (
            lambda data: self._on_track_selection_changed()
        )
        self._event_bus_handlers["analysis.cancel_requested"] = (
            lambda data: self.event_dispatcher.publish_event(
                Events.VIDEO_CANCEL_ANALYSIS, {}
            )
        )

    # Set up backward compatibility aliases
    self.video_label = self.analysis_display_widget.video_label
    self.progress_frame = self.analysis_display_widget.progress_frame
    self.progress_bar = self.analysis_display_widget.progress_bar
    self.progress_labels = self.analysis_display_widget.progress_labels
    self.cancel_proc_btn = self.analysis_display_widget.cancel_btn
    self.track_selector_var = self.analysis_display_widget.track_selector_var
    self.track_selector_widget = self.analysis_display_widget.track_selector_widget
    self.social_summary_var = self.analysis_display_widget.social_summary_var
```

### Dependências
- Usa: `self.notebook`, `self.event_bus`, `self.event_dispatcher`
- Import: `AnalysisDisplayWidget` (zebtrack.ui.components)
- Callbacks: `_on_track_selection_changed()`

---

## 19. _create_scrollable_controls_frame

**Linhas:** 3003-3032
**Assinatura:** `def _create_scrollable_controls_frame(self, parent):`
**Tipo:** Construtor UI helper
**Complexidade:** Média

### Código Completo
```python
def _create_scrollable_controls_frame(self, parent):
    """Create a scrollable frame for the zone controls."""
    # Create a canvas and scrollbar for scrolling
    self.controls_canvas = Canvas(parent, highlightthickness=0)
    self.controls_scrollbar = ttk.Scrollbar(
        parent, orient="vertical", command=self.controls_canvas.yview
    )

    # Create the main scrollable frame inside the canvas
    self.zone_controls_frame = ttk.Frame(self.controls_canvas)

    # Create a frame for the fixed button at the bottom
    self.fixed_button_frame = ttk.Frame(parent)

    # Configure canvas scrolling
    self.controls_canvas.configure(yscrollcommand=self.controls_scrollbar.set)

    # Pack the scrollbar and canvas
    self.controls_scrollbar.pack(side="right", fill="y")
    self.fixed_button_frame.pack(side="bottom", fill="x", padx=5, pady=5)
    self.controls_canvas.pack(side="left", fill="both", expand=True)

    # Create window in canvas for the scrollable frame
    self.controls_canvas_window = self.controls_canvas.create_window(
        0, 0, anchor="nw", window=self.zone_controls_frame
    )

    # Bind events for proper scrolling behavior
    self.zone_controls_frame.bind("<Configure>", self._on_frame_configure)
    self.controls_canvas.bind("<Configure>", self._on_canvas_configure_scroll)
    self._bind_mousewheel()
```

### Dependências
- Parâmetro `parent`: Frame
- Chama: `_on_frame_configure()`, `_on_canvas_configure_scroll()`, `_bind_mousewheel()`
- Usa: `self.controls_canvas`, `self.controls_scrollbar`, `self.zone_controls_frame`

---

## 20. _on_frame_configure

**Linhas:** 3035-3037
**Assinatura:** `def _on_frame_configure(self, event=None):`
**Tipo:** Handler de evento
**Complexidade:** Muito Baixa (1 linha)

### Código Completo
```python
def _on_frame_configure(self, event=None):
    """Update scroll region when frame size changes."""
    self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox("all"))
```

---

## 21. _on_canvas_configure_scroll

**Linhas:** 3039-3042
**Assinatura:** `def _on_canvas_configure_scroll(self, event=None):`
**Tipo:** Handler de evento
**Complexidade:** Baixa (2 linhas)

### Código Completo
```python
def _on_canvas_configure_scroll(self, event=None):
    """Update frame width when canvas size changes."""
    canvas_width = event.width if event else self.controls_canvas.winfo_width()
    self.controls_canvas.itemconfig(self.controls_canvas_window, width=canvas_width)
```

---

## 22. _build_day_title

**Linhas:** 3443-3458
**Assinatura:** `def _build_day_title(self, day_value, metadata: dict | None = None) -> str:`
**Tipo:** Utilitário de formatação
**Complexidade:** Média

### Código Completo
```python
def _build_day_title(self, day_value, metadata: dict | None = None) -> str:
    metadata = metadata or {}
    candidate = metadata.get("day_label") or ""
    if not candidate and metadata.get("day") is not None:
        candidate = self._format_day_display(metadata.get("day"))
    if not candidate:
        candidate = self._format_day_display(day_value)
    if not candidate:
        base_value = day_value if day_value not in (None, "") else None
        candidate = str(base_value) if base_value is not None else "Sem Dia"
    candidate_str = str(candidate).strip()
    if not candidate_str:
        candidate_str = "Sem Dia"
    if candidate_str.lower() == "sem dia":
        return "Sem Dia"
    return f"Dia {candidate_str}"
```

### Dependências
- Chama: `_format_day_display()`
- Parâmetros: `day_value` (int/str/None), `metadata` (dict|None)

---

## 23. _build_video_hierarchy_data

**Linhas:** 3460-3524
**Assinatura:** `def _build_video_hierarchy_data(self, all_videos: list[dict], search_text: str) -> dict[str, dict]:`
**Tipo:** Processador de dados
**Complexidade:** Média-Alta (65 linhas)

### Estrutura
```
Entrada: lista de vídeos + texto de busca
Processamento:
  1. Normaliza texto de busca
  2. Para cada vídeo:
     - Extrai metadata (group, day, subject)
     - Verifica flags (arena, rois, trajectory, complete, summary)
     - Filtra por texto de busca
     - Organiza em hierarquia: group -> days -> videos
Saída: dict[group_id -> {display, days: dict[day_id -> [videos]]}]
```

### Principais Dependências
- Chama: `_format_day_display()`
- Usa: `os.path.basename()`

---

## 24. _build_video_hierarchy_snapshot

**Linhas:** 3526-3582
**Assinatura:** `def _build_video_hierarchy_snapshot(self) -> list[dict]:`
**Tipo:** Processador de dados
**Complexidade:** Média-Alta (57 linhas)

### Estrutura
```
Cria snapshot hierárquico para exibição em árvore:
  - Grupos (🏷️ label)
    - Dias (📅 Dia N)
      - Vídeos (🐟 Sujeito XX)
        - status_label: "✓✗" para cada tipo (arena/rois/trajectory)

Retorno: lista de estruturas dict com labels e children
```

### Dependências
- Chama: `_build_video_hierarchy_data()`, `_build_day_title()`, `_format_subject_label()`, `_format_status_token()`, `_video_sort_key()`
- Usa: `self.controller`

---

## 25. _create_reports_tab

**Linhas:** 3902-3965
**Assinatura:** `def _create_reports_tab(self):`
**Tipo:** Construtor UI (LEGADO)
**Complexidade:** Alta

### Nota
**LEGADO** - Substituído por `_create_processing_reports_tab()`. Mantido para referência histórica.

---

## 26. _create_processing_reports_tab

**Linhas:** 3967-4009
**Assinatura:** `def _create_processing_reports_tab(self) -> None:`
**Tipo:** Construtor UI de abas (NOVO)
**Complexidade:** Média

### Código Completo
```python
def _create_processing_reports_tab(self) -> None:
    """
    Creates the unified Processing and Reports tab.

    This tab consolidates functionality from the old "Trajectories and Summaries"
    and "Reports" tabs into a single interface for better UX and reduced redundancy.
    """
    if not self.notebook:
        return

    # Clean up existing tab if present
    if self.processing_reports_tab_frame and self.processing_reports_tab_frame.winfo_exists():
        try:
            self.processing_reports_tab_frame.destroy()
        except Exception:
            pass

    # Create tab frame
    self.processing_reports_tab_frame = ttk.Frame(self.notebook, padding="10")
    self.notebook.add(self.processing_reports_tab_frame, text="Processamento e Relatórios")

    # Import the component
    from zebtrack.ui.components.processing_reports import ProcessingReportsWidget

    # Create the widget with callbacks
    self.processing_reports_widget = ProcessingReportsWidget(
        self.processing_reports_tab_frame,
        event_bus=self.event_bus,
        on_generate_trajectories=self._trigger_batch_trajectory_processing,
        on_export_summaries=self._trigger_parquet_summaries,
        on_generate_partial_report=self._on_processing_reports_generate_partial,
        on_generate_unified_report=self._generate_unified_report,
    )
    self.processing_reports_widget.pack(fill="both", expand=True)

    # Bind double-click event for opening files
    if self.processing_reports_widget.tree:
        self.processing_reports_widget.tree.bind(
            "<Double-Button-1>", self._on_processing_reports_item_double_click
        )

    # Initial refresh
    self._refresh_processing_reports_tab()
```

### Dependências
- Usa: `self.notebook`, `self.event_bus`
- Chama: `_refresh_processing_reports_tab()`
- Import: `ProcessingReportsWidget` (zebtrack.ui.components.processing_reports)

---

## 27. _build_processing_report_artifact_id

**Linhas:** 4307-4311
**Assinatura:** `def _build_processing_report_artifact_id(self, parent_id: str, artifact_path: str) -> str:`
**Tipo:** Utilitário de ID
**Complexidade:** Baixa

### Código Completo
```python
def _build_processing_report_artifact_id(self, parent_id: str, artifact_path: str) -> str:
    """Create a stable item id for report artifacts while avoiding duplicates."""
    digest_source = f"{parent_id}|{artifact_path}".encode("utf-8", "ignore")
    digest = hashlib.sha1(digest_source).hexdigest()[:16]
    return f"file_{digest}"
```

### Dependências
- Import: `hashlib`

---

## 28. _build_report_hierarchy

**Linhas:** 4453-4501
**Assinatura:** `def _build_report_hierarchy(self, all_videos: list[dict], pm) -> dict:`
**Tipo:** Processador de dados
**Complexidade:** Média-Alta (49 linhas)

### Estrutura
```
Similar a _build_video_hierarchy_data, mas com dados adicionais:
  - results_dir
  - parquet_files
  - metadata completa
  - Calcula status completude (arena/rois/trajectory/summary)
```

### Dependências
- Parâmetro `pm`: ProjectManager
- Chama: (nenhum método local)
- Usa: `os.path.basename()`, `os.path.splitext()`

---

## 29. _create_drawing_buttons

**Linhas:** 4983-5010
**Assinatura:** `def _create_drawing_buttons(self):`
**Tipo:** Construtor UI de botões
**Complexidade:** Baixa-Média

### Código Completo
```python
def _create_drawing_buttons(self):
    """Creates floating undo/redo buttons over the canvas."""
    if self._drawing_buttons_frame:
        self._drawing_buttons_frame.destroy()

    # Create a frame that floats over the canvas (top-right corner)
    self._drawing_buttons_frame = ttk.Frame(self.viz_frame, relief="raised", borderwidth=2)

    # Undo button
    undo_btn = ttk.Button(
        self._drawing_buttons_frame,
        text="↶ Desfazer (Ctrl+Z)",
        command=lambda: self._on_drawing_undo(None),
        width=20,
    )
    undo_btn.pack(side="left", padx=2)

    # Redo button
    redo_btn = ttk.Button(
        self._drawing_buttons_frame,
        text="↷ Refazer (Ctrl+Y)",
        command=lambda: self._on_drawing_redo(None),
        width=20,
    )
    redo_btn.pack(side="left", padx=2)

    # Position the frame in top-right corner of canvas
    self._drawing_buttons_frame.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=10)
```

### Dependências
- Usa: `self.viz_frame`, `self._drawing_buttons_frame`
- Chama: `_on_drawing_undo()`, `_on_drawing_redo()`

---

## 30. _build_roi_template_identifier

**Linhas:** 5495-5506
**Assinatura:** `def _build_roi_template_identifier(self, template: dict[str, Any]) -> str:`
**Tipo:** Utilitário de ID
**Complexidade:** Baixa

### Código Completo
```python
def _build_roi_template_identifier(self, template: dict[str, Any]) -> str:
    location = template.get("location", "project")
    slug = template.get("slug") or ""
    file_ref = template.get("file") or ""

    if location == "project" and slug:
        return f"{location}:{slug}"

    if file_ref:
        return f"{location}:{file_ref}"

    return f"{location}:{template.get('name', '')}"
```

### Dependências
- Nenhuma (método puro)

---

## 31. _create_template_rois

**Linhas:** 6546-6606
**Assinatura:** `def _create_template_rois(self):`
**Tipo:** Handler de diálogo + processador
**Complexidade:** Média-Alta (61 linhas)

### Estrutura
```
1. Abre TemplateDialog para escolher tipo de layout
2. Calcula dimensões da arena
3. Gera ROIs baseado no template:
   - Vertical: lanes horizontais
   - Horizontal: lanes verticais
   - Grid: matriz M x N
4. Adiciona ROIs ao data model
5. Atualiza visualização
```

### Dependências
- Import: `numpy`
- Usa: `self.arena_selector_var`, `self.roi_data`, `self.controller`
- Chama: `_on_arena_select()`
- Dialog: `TemplateDialog`

---

## 32. _create_progress_grid_tab

**Linhas:** 6786-6801
**Assinatura:** `def _create_progress_grid_tab(self):`
**Tipo:** Construtor UI de abas
**Complexidade:** Baixa-Média

### Código Completo
```python
def _create_progress_grid_tab(self):
    """Creates the tab for viewing the experimental progress grid."""
    self.progress_grid_frame = ttk.Frame(self.notebook, padding="10")
    self.notebook.add(self.progress_grid_frame, text="Progresso do Experimento")

    # This frame will hold the actual grid of buttons, which is rendered later
    self.grid_container = ttk.Frame(self.progress_grid_frame)
    self.grid_container.pack(expand=True, fill="both")

    # Add a refresh button
    refresh_button = ttk.Button(
        self.progress_grid_frame,
        text="Atualizar Grade",
        command=self._render_progress_grid,
    )
    refresh_button.pack(side="bottom", pady=10)
```

### Dependências
- Usa: `self.notebook`, `self.progress_grid_frame`, `self.grid_container`
- Chama: `_render_progress_grid()`

---

## 33. _create_project_workflow

**Linhas:** 7139-7162
**Assinatura:** `def _create_project_workflow(self):`
**Tipo:** Handler de UI + delegador
**Complexidade:** Média

### Código Completo
```python
def _create_project_workflow(self):
    """
    Handles the UI part of creating a new project by opening a comprehensive dialog,
    then calls the controller with the collected data.

    Phase 7: Direct wizard data delegation to ProjectWorkflowService.
    No adapter layer needed - service processes wizard output directly.
    """
    from zebtrack.ui.wizard.wizard_dialog import WizardDialog

    wizard = WizardDialog(self.root, settings_obj=self.controller.settings)
    if not wizard.result:
        return  # User cancelled

    # Validate required fields
    required_fields = ["project_path", "project_name", "project_type"]
    missing = [f for f in required_fields if f not in wizard.result]
    if missing:
        self.show_error("Erro no Wizard", f"Campos obrigatórios ausentes: {', '.join(missing)}")
        return

    # Pass wizard data directly to controller (via ProjectWorkflowService)
    # The service now handles data enrichment and processing internally
    self.event_dispatcher.publish_event(Events.WIZARD_CREATE_PROJECT, wizard.result)
```

### Dependências
- Import: `WizardDialog` (zebtrack.ui.wizard.wizard_dialog)
- Usa: `self.root`, `self.controller`, `self.event_dispatcher`
- Chama: `show_error()`

---

## 34. _build_track_options

**Linhas:** 7681-7694
**Assinatura:** `def _build_track_options(self, detections: list[tuple]) -> list[str]:`
**Tipo:** Processador de dados
**Complexidade:** Baixa-Média

### Código Completo
```python
def _build_track_options(self, detections: list[tuple]) -> list[str]:
    observed: set[str] = set()
    for det in detections:
        if len(det) < 6:
            continue
        track_id = det[5]
        if track_id is None:
            continue
        text = str(track_id).strip()
        if text:
            observed.add(text)

    ordered = sorted(observed, key=str)
    return ["Todos", *ordered]
```

### Estrutura de Detecção
```
det[0] = ?
det[1] = ?
det[2] = ?
det[3] = ?
det[4] = ?
det[5] = track_id  (este é o único campo usado)
```

### Dependências
- Nenhuma (método puro)

---

# RESUMO DE PADRÕES ENCONTRADOS

## Padrões de Complexidade
- **Muito Simples (< 5 linhas):** 1, 8, 20, 21, 27, 30, 34
- **Simples (5-20 linhas):** 3, 4, 22, 29, 32, 33
- **Médio (20-60 linhas):** 2, 6, 7, 9, 11, 14, 18, 19, 23, 24, 26, 28, 31
- **Alto (60-120 linhas):** 5, 10, 12, 16, 17, 25
- **Muito Alto (> 120 linhas):** 15 (385 linhas!)

## Padrões de Dependências
- **Alto acoplamento com self:** Maioria dos métodos (15, 19, 25, 26, 28 especialmente)
- **Baixo acoplamento (métodos puros):** 1, 22, 27, 30, 34
- **Delegação a componentes:** 12, 18, 19, 26 (novos padrões MVVM-S)
- **Processadores de dados:** 23, 24, 28, 34

## Oportunidades para WidgetFactory
Métodos que poderiam ser refatorados para um WidgetFactory:
1. `_build_project_actions` - Fácil, 4 botões
2. `_build_model_status` - Fácil, 3 labels
3. `_create_zone_summary_cards_section` - Médio, cards genéricos
4. `_create_project_overview_panel` - Alto, componente integrado
5. `_create_progress_grid_tab` - Médio, container para grid dinâmico
6. `_create_drawing_buttons` - Baixo, 2 botões

## Métodos que NÃO deveriam ser refatorados
- Processadores de dados (23, 24, 28, 34)
- Builders complexos de hierarquia (15, 16, 17, 25)
- Handlers de eventos especializados (2, 5, 12, 26)

