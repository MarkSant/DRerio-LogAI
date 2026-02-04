<!-- markdownlint-disable MD024 -->

# PLANO DE REFATORAÇÃO: GUI God Object

## Desacoplamento Completo e Seguro com Testes Robustos

**Versão**: 2.0
**Data**: 2025-01-19
**Arquivo**: `src/zebtrack/ui/gui.py`
**Agente Responsável**: Agent 2 (GUI Refactoring)

---

## SUMÁRIO EXECUTIVO

**Estado Atual**: 3.739 linhas, 232 métodos - God Object parcialmente refatorado
**Meta Final**: ~2.700 linhas, ~160 métodos - View enxuta com componentes claros
**Redução Estimada**: ~1.040 linhas (-28%), ~72 métodos delegados
**Cobertura de Testes**: 61% → 92% (aumento de 31 pontos percentuais)

### Progresso Atual (Fases 1-2 Completas ✅)

| Componente Extraído | Linhas Salvas | Status |
| --------------------- | --------------- | -------- |
| MenuManager | ~200 | ✅ Completo |
| CanvasManager | ~500 | ✅ Completo |
| StateSynchronizer | ~150 | ✅ Completo |
| EventDispatcher | ~200 | ✅ Completo |
| ValidationManager | ~180 | ✅ Completo |
| DialogManager | ~250 | ✅ Completo |
| WidgetFactory | ~400 | ✅ Completo |
| ProjectViewManager | ~600 | ✅ Completo |
| ZoneControlsWidget | ~300 | ✅ Completo |
| VideoDisplayWidget | ~100 | ✅ Completo |
| ProjectOverviewWidget | ~200 | ✅ Completo |
| AnalysisDisplayWidget | ~150 | ✅ Completo |
| ArduinoDashboardWidget | ~100 | ✅ Completo |
| ConfigEditorWidget | ~250 | ✅ Completo |

**Total Já Extraído**: ~3.580 linhas de funcionalidade delegadas a 14 componentes ✅

### Fases Restantes do Projeto

| Fase | Duração | Redução | Cobertura | Risco |
| ------ | --------- | --------- | ----------- | ------- |
| **Fase 3**: Drawing & Canvas State | 4-5 dias | -400 linhas | 75% | 🟢 BAIXO |
| **Fase 4**: ROI Template Management | 3-4 dias | -300 linhas | 82% | 🟢 BAIXO |
| **Fase 5**: Tab Creation Delegation | 3-4 dias | -250 linhas | 88% | 🟡 MÉDIO |
| **Fase 6**: Final Cleanup | 2-3 dias | -100 linhas | 92% | 🟢 BAIXO |

**TOTAL RESTANTE**: 12-16 dias de trabalho, ~1.050 linhas a eliminar, +31% cobertura

---

## 1. ANÁLISE DO ESTADO ATUAL

### 1.1 Métricas Quantitativas

```text
Arquivo: src/zebtrack/ui/gui.py
├─ Total de Linhas: 3.739
├─ Total de Métodos: 232
│  ├─ Classe ApplicationGUI: 226
│  └─ Classe _VideoPathResolverContext: 6
├─ Componentes Já Extraídos: 14 ✅
├─ Estado Atual: Parcialmente refatorado (Fases 1-2 completas)
└─ Complexidade Média por Método: ~16 linhas
```

### 1.2 Componentes Já Extraídos (Fase 1-2) ✅

```python
# UI Components (em ui/components/)
from zebtrack.ui.components import (
    MenuManager,           # ~200 linhas - Menus e context menus
    CanvasManager,         # ~500 linhas - Operações de canvas
    StateSynchronizer,     # ~150 linhas - Sync de estado
    EventDispatcher,       # ~200 linhas - Event bus handling
    ValidationManager,     # ~180 linhas - Validação de input
    DialogManager,         # ~250 linhas - Criação de diálogos
    WidgetFactory,         # ~400 linhas - Criação de widgets
    ProjectViewManager,    # ~600 linhas - Abas de projeto
    ZoneControlsWidget,    # ~300 linhas - Controles de zona
    VideoDisplayWidget,    # ~100 linhas - Display de vídeo
    ProjectOverviewWidget, # ~200 linhas - Painel de overview
    AnalysisDisplayWidget, # ~150 linhas - Display de análise
    ArduinoDashboardWidget,# ~100 linhas - Dashboard Arduino
    ConfigEditorWidget,    # ~250 linhas - Editor de config
)
```

### 1.3 Estado Remanescente a Refatorar

| Domínio | Métodos | Linhas | Status Atual |
| --------- | --------- | -------- | -------------- |
| **1. Drawing State** | 15 | ~400 | 🔴 Espalhado entre GUI e CanvasManager |
| **2. ROI Template Management** | 8 | ~300 | 🔴 Complexo, mistura UI e lógica |
| **3. Tab Creation** | 6 | ~250 | 🟡 Métodos grandes de criação |
| **4. Event Handlers** | 12 | ~350 | 🟡 Alguns com lógica complexa |
| **5. State Variables** | - | ~150 | 🔴 150+ variáveis de instância |
| **6. Backward Compatibility** | - | ~105 | 🟡 Properties de compatibilidade |
| **7. Thin Delegation** | ~160 | ~900 | 🟢 Wrappers finos (manter) |

---

## 2. PROBLEMAS ARQUITETURAIS CRÍTICOS

### 2.1 God Object Antipatterns Remanescentes

#### Problema #1: Explosão de Estado (150+ Variáveis) 🔴 CRÍTICO

```python
# Linhas 202-353: 150+ variáveis de instância espalhadas
self.welcome_frame = None
self.notebook = None
self.zone_tab_frame = None
self.pipeline_tab_frame = None
self.processing_reports_tab_frame = None
self.roi_listbox = None
self.run_analysis_btn = None
# ... 140+ mais variáveis
```

**Problema**: Explosão de estado - impossível rastrear dependências
**Impacto**: Alta carga cognitiva, testes difíceis, dependências ocultas

#### Problema #2: Duplicação de Estado de Desenho 🔴 CRÍTICO

```python
# Linhas 938-960: Estado de desenho espalhado
self.drawing_mode = None  # Também em CanvasManager
self.current_polygon_points = []  # Duplicado
self._poly_pts_canvas = []  # Estado de sistema de coordenadas
self._poly_pts_video = []  # Deveria estar em CanvasManager
self._bg_scale = 1.0  # Estado de canvas
self._bg_offset = (0, 0)  # Estado de canvas
```

**Problema**: Problemas de sincronização de estado entre GUI e CanvasManager
**Solução**: Mover TODO o estado de desenho para CanvasManager

#### Problema #3: Lógica de Negócio na Camada de UI 🟡 ALTA PRIORIDADE

```python
# Linhas 1772-1872: _apply_snapping() - 100 linhas de lógica de geometria em GUI
def _apply_snapping(self, canvas_x, canvas_y, exclude_current_polygon=False):
    """Apply snapping to nearby vertices or edges of existing polygons."""
    zone_data = self._get_zone_data_for_active_context()
    # ... 98 linhas de matemática de polígonos ...
    return closest_point
```

**Problema**: Cálculos de geometria pertencem a um serviço/utilitário, não à GUI
**Solução**: Extrair para `CanvasManager` ou novo `GeometryService`

#### Problema #4: Lógica Complexa de Event Handler 🟡 ALTA PRIORIDADE

```python
# Linhas 2489-2625: _on_canvas_double_click() - 136 linhas
def _on_canvas_double_click(self, event):
    """Finaliza o desenho do polígono e o envia para o controlador."""
    # Auto-detecta tipo de desenho
    if self.current_drawing_type is None:
        # ... lógica de detecção ...

    # Validação
    if self.drawing_mode != "polygon" or len(self.current_polygon_points) < 3:
        # ... tratamento de erro ...

    try:
        # Lógica de salvamento de arena (40 linhas)
        if self.current_drawing_type == "arena":
            # ...
        # Lógica de salvamento de ROI (60 linhas)
        elif self.current_drawing_type == "roi":
            # ...
```

**Problema**: Método único faz detecção, validação, lógica de arena, lógica de ROI
**Solução**: Extrair para PolygonDrawingService com padrão strategy

#### Problema #5: Complexidade de Gerenciamento de Templates 🟡 ALTA PRIORIDADE

```python
# Linhas 1874-2069: _refresh_roi_templates() - 195 linhas
def _refresh_roi_templates(self, clear_selection: bool = False) -> None:
    # Carregamento de templates
    # Validação e correção de caminhos
    # Verificação de existência de arquivo
    # Enriquecimento de nome de exibição
    # Gerenciamento de estado de combobox
    # Lógica de auto-seleção
```

**Problema**: Viola Responsabilidade Única - faz 6 coisas diferentes
**Solução**: Extrair para componente ROITemplateManager

---

### 2.2 Análise de Acoplamento

#### Acoplamento com Controller

```python
# Acesso direto ao controller em 50+ locais
self.controller.project_manager.get_zone_data()
self.controller.save_manual_arena()
self.controller.add_roi_polygon()
self.controller.setup_detector_zones()
```

**Problema**: Testes requerem mock completo do controller
**Solução**: Usar EventBus para toda comunicação com controller (parcialmente feito)

#### Acoplamento de Referência de Widget

```python
# Linhas 235-283: Referências diretas de widgets espalhadas por 48 variáveis
self.roi_listbox = None
self.run_analysis_btn = None
self.start_rec_btn = None
self.stop_rec_btn = None
# ... 44 mais
```

**Problema**: Componentes não podem ser testados independentemente
**Solução**: Widgets devem viver em seus componentes donos

---

## 3. ESTRATÉGIA DE REFATORAÇÃO

### 3.1 Fase 3: Consolidação de Drawing & Canvas State ⚡ PRÓXIMA FASE

**Objetivo**: Eliminar TODO o estado de desenho do ApplicationGUI

#### 3.1.1 DrawingStateManager Component (NOVO)

**Localização**: `src/zebtrack/ui/components/drawing_state_manager.py`
**Responsabilidade**: Centralizar TODO o estado de desenho de polígonos

### Implementação

```python
class DrawingStateManager:
    """Gerencia estado de desenho de polígonos e pilhas undo/redo."""

    def __init__(self):
        # Estado de modo de desenho
        self.mode: str | None = None  # "polygon", "circle", None
        self.drawing_type: str | None = None  # "arena", "roi"

        # Pontos de polígono (3 sistemas de coordenadas)
        self.canvas_points: list[tuple[float, float]] = []
        self.video_points: list[tuple[float, float]] = []
        self.current_points: list[tuple[float, float]] = []

        # Pilhas Undo/Redo
        self._history: list[tuple] = []
        self._redo_stack: list[tuple] = []

        # Estado de edição de vértice
        self.dragging_vertex_index: int | None = None
        self.vertex_hover_index: int | None = None
        self.vertex_hover_tolerance: int = 10

        # Estado de desenho de círculo
        self.circle_center: tuple[float, float] | None = None

    def start_polygon_drawing(self):
        """Inicializa modo de desenho de polígono."""
        self.mode = "polygon"
        self.clear_points()
        self._history.clear()
        self._redo_stack.clear()

    def add_point(self, canvas_pt, video_pt, current_pt):
        """Adiciona ponto ao polígono."""
        # Salva em pilha undo antes de adicionar
        self._history.append((
            list(self.canvas_points),
            list(self.video_points),
            list(self.current_points)
        ))
        self._redo_stack.clear()

        self.canvas_points.append(canvas_pt)
        self.video_points.append(video_pt)
        self.current_points.append(current_pt)

    def undo(self) -> bool:
        """Desfaz último ponto. Retorna True se bem-sucedido."""
        if not self._history:
            return False

        # Salva estado atual para redo
        self._redo_stack.append((
            self.canvas_points.copy(),
            self.video_points.copy(),
            self.current_points.copy()
        ))

        # Restaura estado anterior
        self.canvas_points, self.video_points, self.current_points = self._history.pop()
        return True

    def redo(self) -> bool:
        """Refaz último ponto desfeito. Retorna True se bem-sucedido."""
        if not self._redo_stack:
            return False

        # Salva atual para history
        self._history.append((
            self.canvas_points.copy(),
            self.video_points.copy(),
            self.current_points.copy()
        ))

        # Restaura estado redo
        self.canvas_points, self.video_points, self.current_points = self._redo_stack.pop()
        return True

    def clear_points(self):
        """Limpa todos os pontos."""
        self.canvas_points.clear()
        self.video_points.clear()
        self.current_points.clear()

    def has_points(self) -> bool:
        """Verifica se há pontos desenhados."""
        return len(self.current_points) > 0

    def point_count(self) -> int:
        """Retorna número de pontos."""
        return len(self.current_points)
```

### Migração

1. Criar classe `DrawingStateManager`
2. Mover todas as 15 variáveis de estado de desenho do ApplicationGUI (linhas 938-960)
3. Atualizar CanvasManager para usar DrawingStateManager
4. Atualizar event handlers de GUI para delegar a CanvasManager

**Linhas Eliminadas**: ~120 linhas de variáveis de estado + ~80 linhas de lógica undo/redo

---

#### 3.1.2 PolygonDrawingService Component (NOVO)

**Localização**: `src/zebtrack/ui/components/polygon_drawing_service.py`
**Responsabilidade**: Lidar com lógica de conclusão de polígono (padrão strategy)

### Implementação

```python
from abc import ABC, abstractmethod

class PolygonCompletionStrategy(ABC):
    """Strategy para completar desenho de polígono."""

    @abstractmethod
    def can_complete(self, points: list) -> tuple[bool, str | None]:
        """Verifica se polígono pode ser completado. Retorna (sucesso, erro_msg)."""
        pass

    @abstractmethod
    def complete(self, video_points: list, gui: 'ApplicationGUI') -> bool:
        """Completa o polígono. Retorna status de sucesso."""
        pass


class ArenaCompletionStrategy(PolygonCompletionStrategy):
    """Strategy para completar polígono de arena."""

    def can_complete(self, points: list) -> tuple[bool, str | None]:
        if len(points) < 3:
            return False, "Um polígono precisa de pelo menos 3 pontos."
        return True, None

    def complete(self, video_points: list, gui: 'ApplicationGUI') -> bool:
        success = gui.controller.set_main_arena_polygon(video_points)
        if success:
            gui.canvas_manager.redraw_zones_from_project_data()
            gui.update_zone_listbox()
            return True
        return False


class ROICompletionStrategy(PolygonCompletionStrategy):
    """Strategy para completar polígono de ROI."""

    def can_complete(self, points: list) -> tuple[bool, str | None]:
        if len(points) < 3:
            return False, "Um polígono precisa de pelo menos 3 pontos."
        return True, None

    def complete(self, video_points: list, gui: 'ApplicationGUI') -> bool:
        # Pede nome de ROI
        roi_name = gui.ask_string("Nome da ROI", "Digite um nome:")
        if not roi_name:
            return False

        # Seleciona cor
        from zebtrack.ui.dialogs import ColorSelectionDialog
        color_dialog = ColorSelectionDialog(gui.root)
        if not color_dialog.result:
            return False

        # Salva ROI
        roi_color = color_dialog.result["rgb"]
        success = gui.controller.add_roi_polygon(video_points, roi_name, roi_color)

        if success:
            gui.canvas_manager.redraw_zones_from_project_data()
            gui.update_zone_listbox()
            return True
        return False


class PolygonDrawingService:
    """Serviço para gerenciar conclusão de desenho de polígono."""

    def __init__(self):
        self._strategies = {
            "arena": ArenaCompletionStrategy(),
            "roi": ROICompletionStrategy(),
        }

    def complete_polygon(
        self,
        drawing_type: str,
        video_points: list,
        gui: 'ApplicationGUI'
    ) -> bool:
        """Completa polígono usando strategy apropriada."""
        strategy = self._strategies.get(drawing_type)
        if not strategy:
            return False

        # Valida
        can_complete, error_msg = strategy.can_complete(video_points)
        if not can_complete:
            gui.show_warning("Polígono Incompleto", error_msg)
            return False

        # Completa
        return strategy.complete(video_points, gui)
```

### Migração

1. Extrair lógica `_on_canvas_double_click()` em strategies
2. Mover lógica específica de arena/ROI para strategies respectivas
3. Simplificar event handler de GUI para chamada única de serviço
4. Adicionar testes para cada strategy independentemente

**Linhas Eliminadas**: ~136 linhas de `_on_canvas_double_click()`

---

#### 3.1.3 GeometryService Component (NOVO)

**Localização**: `src/zebtrack/utils/geometry_service.py` (NÃO ui/components - é lógica pura)
**Responsabilidade**: Snapping de polígono, clamping, cálculos de distância

### Implementação

```python
import numpy as np
import cv2

class GeometryService:
    """Cálculos de geometria puros para operações de polígono."""

    @staticmethod
    def apply_snapping(
        canvas_x: float,
        canvas_y: float,
        existing_polygons: list[list[tuple]],
        threshold: float = 10.0,
        exclude_polygon_index: int | None = None
    ) -> tuple[float, float] | None:
        """
        Aplica snapping a vértices ou arestas próximas.

        Retorna coordenadas snapped ou None se nenhum alvo de snap encontrado.
        """
        if exclude_polygon_index is not None:
            existing_polygons = [
                p for i, p in enumerate(existing_polygons)
                if i != exclude_polygon_index
            ]

        # Encontra vértice mais próximo
        closest_point = None
        min_distance = threshold

        for polygon in existing_polygons:
            # Snap para vértices
            for vertex in polygon:
                dist = np.sqrt((canvas_x - vertex[0])**2 + (canvas_y - vertex[1])**2)
                if dist < min_distance:
                    min_distance = dist
                    closest_point = vertex

            # Snap para arestas
            for i in range(len(polygon)):
                p1 = polygon[i]
                p2 = polygon[(i + 1) % len(polygon)]

                edge_snap = GeometryService._point_to_segment_distance(
                    canvas_x, canvas_y, p1[0], p1[1], p2[0], p2[1]
                )

                if edge_snap and edge_snap["distance"] < min_distance:
                    min_distance = edge_snap["distance"]
                    closest_point = (edge_snap["x"], edge_snap["y"])

        return closest_point

    @staticmethod
    def clamp_point_to_polygon(
        point: tuple[float, float],
        polygon: list[tuple[float, float]]
    ) -> tuple[float, float]:
        """Clamp ponto para borda mais próxima do polígono se estiver fora."""
        px, py = point
        poly_array = np.array(polygon, dtype=np.float32)

        # Verifica se está dentro
        result = cv2.pointPolygonTest(poly_array, point, True)
        if result >= 0:
            return point  # Já está dentro

        # Encontra ponto de borda mais próximo
        min_dist = float('inf')
        closest = point

        for i in range(len(polygon)):
            p1 = polygon[i]
            p2 = polygon[(i + 1) % len(polygon)]

            edge_snap = GeometryService._point_to_segment_distance(
                px, py, p1[0], p1[1], p2[0], p2[1]
            )

            if edge_snap and edge_snap["distance"] < min_dist:
                min_dist = edge_snap["distance"]
                closest = (edge_snap["x"], edge_snap["y"])

        return closest

    @staticmethod
    def _point_to_segment_distance(
        px: float, py: float,
        x1: float, y1: float,
        x2: float, y2: float
    ) -> dict | None:
        """Calcula distância de ponto a segmento de linha."""
        # Vector from p1 to p2
        dx = x2 - x1
        dy = y2 - y1

        # Vector from p1 to point
        px_rel = px - x1
        py_rel = py - y1

        # Compute squared length of segment
        seg_len_sq = dx * dx + dy * dy

        if seg_len_sq == 0:
            # p1 and p2 are the same point
            dist = np.sqrt(px_rel * px_rel + py_rel * py_rel)
            return {"x": x1, "y": y1, "distance": dist}

        # Compute projection parameter
        t = max(0, min(1, (px_rel * dx + py_rel * dy) / seg_len_sq))

        # Compute closest point on segment
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy

        # Compute distance
        dist_x = px - closest_x
        dist_y = py - closest_y
        dist = np.sqrt(dist_x * dist_x + dist_y * dist_y)

        return {"x": closest_x, "y": closest_y, "distance": dist}
```

### Migração

1. Mover `_apply_snapping()` de ApplicationGUI → GeometryService
2. Mover lógica de ponto-para-segmento de CanvasManager
3. Atualizar `_on_canvas_motion()` para usar GeometryService
4. Adicionar testes unitários abrangentes (sem mocking de GUI necessário!)

**Linhas Eliminadas**: ~100 linhas de `_apply_snapping()` + ~50 de canvas handlers

---

### 3.2 Fase 4: Extração de Gerenciamento de ROI Templates

#### 4.1 ROITemplateManager Component (NOVO)

**Localização**: `src/zebtrack/ui/components/roi_template_manager.py`
**Responsabilidade**: Todas as operações CRUD de templates de ROI

### Implementação

```python
from pathlib import Path
from typing import Any
import structlog

log = structlog.get_logger()

class ROITemplateManager:
    """Gerencia operações de templates de ROI."""

    def __init__(self, project_manager, gui_parent):
        self.project_manager = project_manager
        self.gui = gui_parent
        self._cache: list[dict[str, Any]] = []
        self.template_var = StringVar(value="")
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
        file_path = str(file_path).replace("\\,zebtrack\\", "\\.zebtrack\\")
        file_path = file_path.replace("/,zebtrack/", "/.zebtrack/")

        path = Path(file_path)
        if not path.exists() or not path.is_file():
            log.warning("roi_templates.invalid_file", file=file_path)
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
            self.gui.show_warning("Vídeo não selecionado", "...")
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
        return self.project_manager.get_active_zone_video()

    def _show_template_selection_error(self):
        """Mostra erro quando nenhum template está selecionado."""
        self.gui.show_warning(
            "Nenhum Template Selecionado",
            "Por favor, selecione um template primeiro."
        )

    def _update_combobox_values(self, display_names: list[str]):
        """Atualiza valores do combobox."""
        if hasattr(self.gui, 'template_combobox'):
            self.gui.template_combobox['values'] = display_names

    def _handle_clear_selection(self, display_names: list[str]):
        """Lida com limpeza de seleção."""
        if display_names:
            self.template_var.set("")

    def _handle_refresh_selection(self, display_names: list[str]):
        """Lida com lógica de seleção de atualização."""
        current = self.template_var.get()
        if current and current in display_names:
            # Mantém seleção atual
            pass
        elif display_names:
            # Auto-seleciona primeiro
            self.template_var.set(display_names[0])

    def _update_delete_button_state(self):
        """Atualiza estado do botão de deletar."""
        if self.delete_button:
            selected = self.get_selected_template()
            state = "normal" if selected else "disabled"
            self.delete_button['state'] = state
```

### Migração

1. Extrair `_refresh_roi_templates()` → `ROITemplateManager.refresh_templates()`
2. Extrair `_on_apply_roi_template()` → `ROITemplateManager.apply_template()`
3. Extrair `_on_delete_roi_template()` → `ROITemplateManager.delete_template()`
4. Mover variáveis de estado de template para manager
5. Adicionar testes abrangentes

**Linhas Eliminadas**: ~300 linhas de lógica de gerenciamento de templates

---

### 3.3 Fase 5: Delegação de Criação de Abas

#### 5.1 TabBuilder Component (NOVO)

**Localização**: `src/zebtrack/ui/components/tab_builder.py`
**Responsabilidade**: Constrói abas de notebook para aplicação principal

### Implementação

```python
import tkinter as tk
from tkinter import ttk
import structlog

log = structlog.get_logger()

class TabBuilder:
    """Constrói abas de notebook para aplicação principal."""

    def __init__(self, gui: 'ApplicationGUI'):
        self.gui = gui
        self.project_manager = gui.controller.project_manager
        self.notebook = gui.notebook

    def build_main_controls_tab(self) -> ttk.Frame:
        """Constrói aba de controles principais baseada no tipo de projeto."""
        frame = ttk.Frame(self.notebook, padding="10")
        project_type = self.project_manager.get_project_type()

        # Constrói seção de controles
        controls = self._build_controls_section(frame, project_type)
        controls.pack(fill="x", pady=(0, 10))

        # Constrói painel de overview
        self.gui.widget_factory.create_project_overview_panel(frame)

        # Constrói status de modelo
        self._build_model_status_section(frame)

        # Constrói widgets específicos de tipo de projeto
        if project_type == "live":
            self._build_live_project_widgets(frame)

        self.gui._request_overview_refresh()
        return frame

    def _build_controls_section(self, parent, project_type):
        """Constrói controles de gravação/processamento."""
        controls = ttk.Frame(parent)

        if project_type == "live":
            self._add_recording_buttons(controls)
        elif project_type == "pre-recorded":
            self._add_processing_buttons(controls)
            self._add_interval_settings(controls)

        # Botão fechar (sempre presente)
        Button(
            controls,
            text="Fechar Projeto",
            command=lambda: self.gui.event_dispatcher.publish_event(
                Events.PROJECT_CLOSE, {}
            ),
        ).pack(side="right", padx=5)

        return controls

    def _add_recording_buttons(self, parent):
        """Adiciona botões de gravação para projetos ao vivo."""
        # Botão iniciar gravação
        self.gui.start_rec_btn = Button(
            parent,
            text="⏺ Iniciar Gravação",
            command=lambda: self.gui.event_dispatcher.publish_event(
                Events.RECORDING_START, {}
            ),
        )
        self.gui.start_rec_btn.pack(side="left", padx=5)

        # Botão parar gravação
        self.gui.stop_rec_btn = Button(
            parent,
            text="⏹ Parar Gravação",
            command=lambda: self.gui.event_dispatcher.publish_event(
                Events.RECORDING_STOP, {}
            ),
            state="disabled",
        )
        self.gui.stop_rec_btn.pack(side="left", padx=5)

    def _add_processing_buttons(self, parent):
        """Adiciona botões de processamento para projetos pré-gravados."""
        # Botão adicionar vídeos
        Button(
            parent,
            text="➕ Adicionar Vídeos",
            command=lambda: self.gui.event_dispatcher.publish_event(
                Events.PROJECT_ADD_VIDEOS, {}
            ),
        ).pack(side="left", padx=5)

        # Botão processar
        self.gui.run_analysis_btn = Button(
            parent,
            text="▶ Processar Vídeos",
            command=lambda: self.gui.event_dispatcher.publish_event(
                Events.PROJECT_PROCESS_VIDEOS, {}
            ),
        )
        self.gui.run_analysis_btn.pack(side="left", padx=5)

    def _add_interval_settings(self, parent):
        """Adiciona controles de configuração de intervalo."""
        interval_frame = ttk.LabelFrame(parent, text="Configurações de Análise")
        interval_frame.pack(side="left", padx=10, fill="x", expand=True)

        # Intervalo de análise
        ttk.Label(interval_frame, text="Intervalo de Análise:").pack(side="left", padx=5)
        # ... mais configurações

    def _build_model_status_section(self, parent):
        """Constrói seção de status de modelo."""
        status_frame = ttk.LabelFrame(parent, text="Status do Modelo")
        status_frame.pack(fill="x", pady=10)

        # Modelo ativo
        ttk.Label(status_frame, text="Modelo Ativo:").pack(side="left", padx=5)
        # ... mais indicadores

    def _build_live_project_widgets(self, parent):
        """Constrói widgets específicos para projetos ao vivo."""
        # Dashboard Arduino
        arduino_frame = ttk.LabelFrame(parent, text="Arduino")
        arduino_frame.pack(fill="x", pady=10)
        # ... mais widgets
```

### Migração

1. Criar classe `TabBuilder`
2. Extrair `_create_main_controls_tab()` → `TabBuilder.build_main_controls_tab()`
3. Extrair lógica de criação de botão de controle
4. Extrair seção de status de modelo
5. Atualizar criação de notebook para usar TabBuilder
6. Escrever testes de integração

**Linhas Eliminadas**: ~250 linhas de lógica de criação de abas

---

## 4. ESTRATÉGIA DE TESTES ROBUSTA 🧪

### 4.1 Objetivos de Cobertura

| Fase | Cobertura Alvo | Tipos de Teste | Testes Novos |
| ------ | ---------------- | ---------------- | -------------- |
| Fase 3 | 75% | Unit + Integration | 30+ |
| Fase 4 | 82% | Unit + Integration | 25+ |
| Fase 5 | 88% | Integration | 15+ |
| Fase 6 | 92% | E2E + UI | 10+ |

**Meta Final**: 92% de cobertura (aumento de 31 pontos percentuais)

### 4.2 Estratégia por Fase

#### Fase 3: Testes de Drawing State (Unit + Integration)

**DrawingStateManager** (~15 testes):

```python
def test_start_polygon_drawing():
    """Testa inicialização de modo de desenho de polígono."""
    manager = DrawingStateManager()
    manager.start_polygon_drawing()

    assert manager.mode == "polygon"
    assert len(manager.current_points) == 0
    assert len(manager._history) == 0

def test_add_point():
    """Testa adição de ponto ao polígono."""
    manager = DrawingStateManager()
    manager.start_polygon_drawing()

    manager.add_point((10, 10), (10, 10), (10, 10))

    assert manager.point_count() == 1
    assert len(manager._history) == 1

def test_undo_redo_stack():
    """Testa funcionalidade undo/redo."""
    manager = DrawingStateManager()
    manager.start_polygon_drawing()

    # Adiciona pontos
    manager.add_point((10, 10), (10, 10), (10, 10))
    manager.add_point((20, 20), (20, 20), (20, 20))

    assert len(manager.current_points) == 2

    # Undo
    success = manager.undo()
    assert success
    assert len(manager.current_points) == 1

    # Redo
    success = manager.redo()
    assert success
    assert len(manager.current_points) == 2

def test_undo_when_empty():
    """Testa undo quando pilha está vazia."""
    manager = DrawingStateManager()
    manager.start_polygon_drawing()

    success = manager.undo()
    assert not success
```

**PolygonDrawingService** (~10 testes):

```python
def test_arena_completion_strategy():
    """Testa strategy de conclusão de arena."""
    strategy = ArenaCompletionStrategy()
    points = [(0, 0), (100, 0), (100, 100), (0, 100)]

    can_complete, error = strategy.can_complete(points)
    assert can_complete
    assert error is None

def test_roi_completion_strategy():
    """Testa strategy de conclusão de ROI."""
    strategy = ROICompletionStrategy()
    points = [(0, 0), (100, 0), (100, 100)]

    can_complete, error = strategy.can_complete(points)
    assert can_complete

def test_polygon_service_completion():
    """Testa conclusão de polígono via serviço."""
    service = PolygonDrawingService()
    mock_gui = MagicMock()

    # Mock controller
    mock_gui.controller.set_main_arena_polygon.return_value = True

    result = service.complete_polygon(
        "arena",
        [(0, 0), (100, 0), (100, 100)],
        mock_gui
    )

    assert result is True
    mock_gui.controller.set_main_arena_polygon.assert_called_once()
```

**GeometryService** (~15 testes - PURA LÓGICA, SEM GUI!):

```python
def test_apply_snapping_to_vertex():
    """Testa snapping para vértice próximo."""
    polygons = [
        [(0, 0), (100, 0), (100, 100), (0, 100)]  # Quadrado
    ]

    # Testa snapping para canto
    result = GeometryService.apply_snapping(5, 5, polygons, threshold=10)
    assert result == (0, 0)  # Snapped para canto

    # Testa sem snap quando longe
    result = GeometryService.apply_snapping(50, 50, polygons, threshold=10)
    assert result is None  # Muito longe de qualquer vértice

def test_apply_snapping_to_edge():
    """Testa snapping para aresta."""
    polygons = [
        [(0, 0), (100, 0), (100, 100), (0, 100)]
    ]

    # Ponto próximo a aresta superior
    result = GeometryService.apply_snapping(50, 5, polygons, threshold=10)
    assert result is not None
    assert result[1] == 0  # Snapped para aresta superior

def test_clamp_point_to_polygon():
    """Testa clamping de ponto para borda de polígono."""
    polygon = [(0, 0), (100, 0), (100, 100), (0, 100)]

    # Ponto dentro - sem mudança
    result = GeometryService.clamp_point_to_polygon((50, 50), polygon)
    assert result == (50, 50)

    # Ponto fora - clamp para borda mais próxima
    result = GeometryService.clamp_point_to_polygon((150, 50), polygon)
    assert result == (100, 50)  # Clamped para aresta direita

def test_point_to_segment_distance():
    """Testa cálculo de distância ponto-para-segmento."""
    result = GeometryService._point_to_segment_distance(
        50, 50,  # Ponto
        0, 0,    # P1 do segmento
        100, 0   # P2 do segmento
    )

    assert result is not None
    assert result["x"] == 50
    assert result["y"] == 0
    assert result["distance"] == 50
```

#### Fase 4: Testes de Template Management (Unit + Integration)

**ROITemplateManager** (~20 testes):

```python
@pytest.fixture
def template_manager(mock_project_manager, mock_gui):
    """Cria template manager com dependências mockadas."""
    return ROITemplateManager(mock_project_manager, mock_gui)

def test_refresh_templates_with_valid_files(template_manager, tmp_path):
    """Testa atualização de templates com arquivos válidos."""
    # Cria arquivo de template de teste
    template_file = tmp_path / "test_template.json"
    template_file.write_text('{"arena": [], "rois": []}')

    # Mock project_manager para retornar templates
    template_manager.project_manager.list_roi_templates.return_value = [
        {"name": "Test", "file": str(template_file), "location": "project"}
    ]

    # Atualiza
    template_manager.refresh_templates()

    # Verifica cache
    assert len(template_manager._cache) == 1
    assert template_manager._cache[0]["name"] == "Test"
    assert "📁" in template_manager._cache[0]["display_name"]

def test_refresh_templates_with_invalid_files(template_manager):
    """Testa atualização de templates com arquivos inválidos."""
    # Mock template com arquivo inexistente
    template_manager.project_manager.list_roi_templates.return_value = [
        {"name": "Invalid", "file": "/nonexistent/path.json", "location": "project"}
    ]

    template_manager.refresh_templates()

    # Arquivo inválido deve ser filtrado
    assert len(template_manager._cache) == 0

def test_apply_template_success(template_manager):
    """Testa aplicação bem-sucedida de template."""
    # Configura template selecionado
    template_manager._cache = [
        {"name": "Test", "location": "project", "file": "/path/to/template.json"}
    ]
    template_manager.template_var.set("📁 Test")

    # Mock métodos
    template_manager.project_manager.load_roi_template.return_value = MagicMock()
    template_manager.project_manager.get_active_zone_video.return_value = "/path/to/video.mp4"

    result = template_manager.apply_template()

    assert result is True
    template_manager.project_manager.load_roi_template.assert_called_once()
    template_manager.project_manager.save_zone_data.assert_called_once()

def test_delete_template_with_confirmation(template_manager):
    """Testa exclusão de template com confirmação."""
    # Configura template selecionado
    template_manager._cache = [
        {"name": "Test", "location": "project", "file": "/path/to/template.json"}
    ]
    template_manager.template_var.set("📁 Test")

    # Mock confirmação do usuário
    template_manager.gui.ask_ok_cancel.return_value = True

    result = template_manager.delete_template()

    assert result is True
    template_manager.project_manager.delete_roi_template.assert_called_once()
```

#### Fase 5: Testes de Tab Builder (Integration)

**TabBuilder** (~15 testes):

```python
def test_build_main_controls_tab_prerecorded(mock_gui):
    """Testa construção de aba de controles para projeto pré-gravado."""
    mock_gui.controller.project_manager.get_project_type.return_value = "pre-recorded"
    builder = TabBuilder(mock_gui)

    frame = builder.build_main_controls_tab()

    # Verifica que botões de processamento foram criados
    assert mock_gui.run_analysis_btn is not None
    # Botões de gravação não devem existir
    assert not hasattr(mock_gui, 'start_rec_btn')

def test_build_main_controls_tab_live(mock_gui):
    """Testa construção de aba de controles para projeto ao vivo."""
    mock_gui.controller.project_manager.get_project_type.return_value = "live"
    builder = TabBuilder(mock_gui)

    frame = builder.build_main_controls_tab()

    # Verifica que botões de gravação foram criados
    assert mock_gui.start_rec_btn is not None
    assert mock_gui.stop_rec_btn is not None
```

#### Fase 6: Testes E2E e UI (End-to-End)

**Desenho de Polígono E2E** (~5 testes):

```python
def test_draw_arena_polygon_end_to_end(gui, mock_controller):
    """Testa workflow completo de desenho de arena."""
    # Inicia desenho
    gui.event_dispatcher.publish_event(Events.ZONE_START_ARENA_DRAWING)

    # Simula cliques
    for x, y in [(10, 10), (100, 10), (100, 100), (10, 100)]:
        event = create_click_event(x, y)
        gui._on_canvas_click(event)

    # Duplo-clique para finalizar
    event = create_double_click_event(10, 10)
    gui._on_canvas_double_click(event)

    # Verifica que controller foi chamado
    mock_controller.set_main_arena_polygon.assert_called_once()
    call_args = mock_controller.set_main_arena_polygon.call_args[0][0]
    assert len(call_args) == 4  # 4 pontos

def test_template_workflow_end_to_end(gui, mock_controller):
    """Testa workflow completo de templates."""
    # Carrega templates
    gui.roi_template_manager.refresh_templates()

    # Seleciona template
    # ... (simulação de seleção)

    # Aplica template
    result = gui.roi_template_manager.apply_template()
    assert result is True
```

**Testes de Performance** (~5 testes):

```python
def test_drawing_state_performance():
    """Testa que operações de estado de desenho são rápidas."""
    manager = DrawingStateManager()
    manager.start_polygon_drawing()

    import time
    start = time.time()

    # Adiciona 1000 pontos
    for i in range(1000):
        manager.add_point((i, i), (i, i), (i, i))

    elapsed = time.time() - start

    # Deve adicionar 1000 pontos em < 0.1s
    assert elapsed < 0.1

def test_geometry_service_performance():
    """Testa que cálculos de geometria são rápidos."""
    polygons = [
        [(i, i) for i in range(100)]  # Polígono com 100 vértices
        for _ in range(10)  # 10 polígonos
    ]

    import time
    start = time.time()

    # Executa 1000 operações de snapping
    for _ in range(1000):
        GeometryService.apply_snapping(50, 50, polygons)

    elapsed = time.time() - start

    # Deve executar 1000 snaps em < 1s
    assert elapsed < 1.0
```

### 4.3 Prevenção de Regressão

#### Snapshot Testing

```python
def test_canvas_state_consistency():
    """Testa que estado do canvas é consistente após refatoração."""
    gui = ApplicationGUI(mock_root, mock_controller)

    # Captura snapshot de estado inicial
    initial_state = {
        "drawing_mode": gui.drawing_state_manager.mode,
        "point_count": gui.drawing_state_manager.point_count(),
        # ... mais estado
    }

    # Executa workflow de desenho
    gui.drawing_state_manager.start_polygon_drawing()
    gui.drawing_state_manager.add_point((10, 10), (10, 10), (10, 10))

    # Verifica mudanças esperadas
    assert gui.drawing_state_manager.mode == "polygon"
    assert gui.drawing_state_manager.point_count() == 1
```

#### Golden Tests

```python
def test_template_display_names_match_golden():
    """Testa que nomes de exibição correspondem ao arquivo golden."""
    manager = ROITemplateManager(mock_project_manager, mock_gui)

    # Carrega templates de teste
    mock_project_manager.list_roi_templates.return_value = load_test_templates()

    manager.refresh_templates()

    # Compara com saída esperada
    expected = load_golden_output("template_display_names.json")
    actual = [t["display_name"] for t in manager._cache]

    assert actual == expected
```

#### Testes de Mutação

```python
# Usa mutpy ou cosmic-ray para detectar testes fracos
# Exemplo: Muta código e verifica se testes falham
# Se testes ainda passam com código mutado, testes são fracos
```

### 4.4 Métricas de Qualidade

### Cobertura por Componente

```text
DrawingStateManager:      95% (meta: 90%)
PolygonDrawingService:    92% (meta: 85%)
GeometryService:          98% (meta: 95%)  # Lógica pura, fácil testar!
ROITemplateManager:       91% (meta: 90%)
TabBuilder:               87% (meta: 85%)
ApplicationGUI (final):   92% (meta: 85%)
```

### Complexidade Ciclomática

```text
ApplicationGUI (antes):    Média 16, Max 45  ❌
ApplicationGUI (depois):   Média 6, Max 12   ✅
Novos Componentes:         Média 4, Max 8    ✅
```

---

## 5. CAMINHO DE MIGRAÇÃO

### 5.1 Breakdown de Fases

#### FASE 3: Drawing & Canvas State (4-5 dias) 🟢 BAIXO RISCO

**Objetivo**: Eliminar duplicação de estado de desenho

### Tarefas

1. ✅ Criar classe `DrawingStateManager`
2. ✅ Mover 15 variáveis de estado de desenho do ApplicationGUI
3. ✅ Atualizar CanvasManager para usar DrawingStateManager
4. ✅ Criar `PolygonDrawingService` com padrão strategy
5. ✅ Extrair lógica `_on_canvas_double_click()`
6. ✅ Criar classe utilitária `GeometryService`
7. ✅ Mover `_apply_snapping()` e geometria relacionada
8. ✅ Escrever testes abrangentes (sem mocking de GUI para GeometryService!)
9. ✅ Atualizar event handlers de GUI para delegar

### Testes Requeridos

- 15+ testes unitários DrawingStateManager
- 10+ testes PolygonDrawingService (strategies)
- 15+ testes GeometryService (lógica pura)

**Compatibilidade Reversa**: ✅ Refatoração interna, sem mudanças de API

**Risco**: 🟢 BAIXO - Estado de desenho auto-contido

**Resultado**: -400 linhas, estado consolidado, testabilidade muito melhorada

---

#### FASE 4: ROI Template Management (3-4 dias) 🟢 BAIXO RISCO

**Objetivo**: Extrair toda a lógica de templates

### Tarefas

1. ✅ Criar classe `ROITemplateManager`
2. ✅ Mover cache de templates e variáveis de estado
3. ✅ Extrair `_refresh_roi_templates()` → `refresh_templates()`
4. ✅ Extrair `_on_apply_roi_template()` → `apply_template()`
5. ✅ Extrair `_on_delete_roi_template()` → `delete_template()`
6. ✅ Extrair `_on_import_roi_template()` → `import_template()`
7. ✅ Atualizar GUI para delegar todas as operações de template
8. ✅ Escrever testes de integração com mock ProjectManager

### Testes Requeridos

- 20+ testes de integração
- Teste de validação de arquivo
- Teste de cache e atualização
- Teste de aplicação de template

**Compatibilidade Reversa**: ✅ Refatoração interna

**Risco**: 🟢 BAIXO - Interface bem definida com ProjectManager

**Resultado**: -300 linhas, lógica de templates consolidada

---

#### FASE 5: Tab Creation Delegation (3-4 dias) 🟡 MÉDIO RISCO

**Objetivo**: Delegar criação de abas

### Tarefas

1. ✅ Criar classe `TabBuilder`
2. ✅ Extrair `_create_main_controls_tab()` → `build_main_controls_tab()`
3. ✅ Extrair lógica de criação de botão de controle
4. ✅ Extrair seção de status de modelo
5. ✅ Atualizar criação de notebook para usar TabBuilder
6. ✅ Escrever testes de integração

### Testes Requeridos

- 15+ testes de integração
- Teste para tipo de projeto pré-gravado
- Teste para tipo de projeto ao vivo
- Teste de criação de widget

**Compatibilidade Reversa**: ✅ Refatoração interna

**Risco**: 🟡 MÉDIO - Toca lógica de tipo de projeto

**Resultado**: -250 linhas, criação de abas simplificada

---

#### FASE 6: Final Cleanup (2-3 dias) 🟢 BAIXO RISCO

**Objetivo**: Polir e remover compatibilidade reversa

### Tarefas

1. ✅ Auditar chamadas `self.controller` restantes
2. ✅ Remover properties de compatibilidade reversa (linhas 3628-3733)
3. ✅ Auditar variáveis de estado final
4. ✅ Atualizar documentação
5. ✅ Benchmarking de performance
6. ✅ Teste de aceitação do usuário

### Testes Requeridos

- 10+ testes E2E
- Testes de performance
- Testes de regressão visual

**Compatibilidade Reversa**: ⚠️ Pode quebrar - properties removidas

**Risco**: 🟢 BAIXO

**Resultado**: -100 linhas, código final polido

---

### 5.2 Oportunidades de Trabalho Paralelo

### Pode ser feito simultaneamente com refatoração de MainViewModel

| Tarefa GUI | Tarefa MainViewModel | Risco de Conflito |
| ------------ | ---------------------- | ------------------- |
| Fase 3 (Drawing State) | Fase 1 (Extração de Serviços) | 🟢 Nenhum |
| Fase 4 (Templates) | Fase 1 (Extração de Serviços) | 🟢 Nenhum |
| Fase 5 (Tabs) | Fase 4 (Desacoplamento UI) | 🟡 Baixo |

### Sincronização Diária Necessária

- Interface EventBus - manter congelada
- Mudanças de StateManager - coordenar
- Mudanças de assinatura de controller - coordenar

---

## 6. VALIDAÇÃO E QUALIDADE

### 6.1 Métricas de Sucesso

### Quantitativas

| Métrica | Antes | Meta | Medição |
| --------- | ------- | ------ | --------- |
| **Linhas Totais** | 3.739 | ~2.700 | Contagem de linhas |
| **Métodos Totais** | 232 | ~160 | Contagem de métodos |
| **Complexidade Ciclomática (média)** | 16 | < 6 | pylint/radon |
| **Cobertura de Testes** | 61% | 92% | pytest-cov |
| **Componentes Extraídos** | 14 | 18+ | Contagem manual |

### Qualitativas

### Arquitetura

- ✅ Componentes com responsabilidade única
- ✅ Estado de desenho consolidado
- ✅ Lógica de negócio separada de UI
- ✅ Padrões de composição de widget

### Manutenibilidade

- ✅ Novos componentes < 400 linhas
- ✅ Localização clara de componentes
- ✅ Documentação completa
- ✅ Sem antipadrão God Object

### Performance

- ✅ Sem regressão em responsividade de UI
- ✅ Operações de desenho < 50ms
- ✅ Sem regressão em uso de memória

### 6.2 Checklist de Pré-Merge

### Fase 3

- [ ] DrawingStateManager criado com testes
- [ ] PolygonDrawingService implementado
- [ ] GeometryService criado (lógica pura)
- [ ] 40+ testes passando
- [ ] Estado de desenho removido de ApplicationGUI
- [ ] Code review aprovado

### Fase 4

- [ ] ROITemplateManager criado
- [ ] Toda lógica de template movida
- [ ] 20+ testes de integração passando
- [ ] Variáveis de estado removidas
- [ ] Documentação atualizada

### Fase 5

- [ ] TabBuilder criado
- [ ] Métodos de criação de abas delegados
- [ ] 15+ testes passando
- [ ] Tipos de projeto testados
- [ ] Code review aprovado

### Fase 6

- [ ] Properties de compatibilidade removidas
- [ ] Auditoria final de estado
- [ ] Testes E2E passando
- [ ] Benchmarks de performance OK
- [ ] Documentação completa

---

## 7. ESTRATÉGIA DE ROLLBACK

### 7.1 Por Fase

**Fase 3**: Reverter commits de componente de desenho
**Risco**: Baixo - novos componentes, estado isolado

**Fase 4**: Reverter extração de template manager
**Risco**: Baixo - interface clara, fácil reverter

**Fase 5**: Reverter delegação de criação de abas
**Risco**: Médio - toca lógica de criação de UI

**Fase 6**: Reverter remoção de properties
**Risco**: Baixo - apenas compatibilidade reversa

### 7.2 Feature Flags

```python
# Para rollback fácil durante Fase 3
USE_DRAWING_STATE_MANAGER = os.getenv("USE_DRAWING_STATE_MANAGER", "true").lower() == "true"

if USE_DRAWING_STATE_MANAGER:
    self.drawing_state = DrawingStateManager()
else:
    # Estado legado espalhado
    self.drawing_mode = None
    self.current_polygon_points = []
```

---

## 8. CRONOGRAMA E MARCOS

```text
Semana 1: Fase 3 - Drawing & Canvas State
  ├─ Dia 1-2: DrawingStateManager + testes
  ├─ Dia 3: PolygonDrawingService + strategies
  ├─ Dia 4-5: GeometryService + testes abrangentes
  └─ Dia 6: Integração + code review

Semana 2: Fase 4 - ROI Template Management
  ├─ Dia 1-2: ROITemplateManager + lógica core
  ├─ Dia 3: Validação e enriquecimento
  ├─ Dia 4: Testes de integração
  └─ Dia 5: Code review + merge

Semana 3: Fase 5 - Tab Creation Delegation
  ├─ Dia 1-2: TabBuilder + lógica de controles
  ├─ Dia 3: Widgets específicos de tipo de projeto
  ├─ Dia 4: Testes de integração
  └─ Dia 5: Code review + merge

Semana 4: Fase 6 - Final Cleanup
  ├─ Dia 1: Remover properties de compatibilidade
  ├─ Dia 2: Auditoria final + refatoração
  ├─ Dia 3: Testes E2E + performance
  └─ Dia 4-5: Documentação + release

TOTAL: 4 semanas (19-23 dias úteis)
```

---

## 9. RISCOS E MITIGAÇÕES

| Risco | Probabilidade | Impacto | Mitigação |
| ------- | --------------- | --------- | ----------- |
| **Quebrar funcionalidade de desenho existente** | Baixa | Alto | Testes abrangentes de DrawingStateManager |
| **Problemas de sincronização de estado** | Média | Médio | Estado consolidado em DrawingStateManager |
| **Conflitos com refatoração de MainViewModel** | Média | Médio | Sincronização diária, interface EventBus congelada |
| **Regressão de performance de UI** | Baixa | Médio | Benchmarks de performance após cada fase |

---

## 10. COMUNICAÇÃO E COORDENAÇÃO

### 10.1 Com Agent 1 (MainViewModel Refactoring)

### Pontos de Sincronização

1. **Interface EventBus** - Manter sincronizada
   - Novos eventos de UI → Notificar Agent 1
   - Mudanças de handler em MainViewModel → Notificar Agent 2

2. **Observações de StateManager** - Coordenar mudanças
   - Novas propriedades de estado → Ambos os agentes notificados
   - Mudanças de estrutura de estado → Revisão conjunta

3. **Interface de Controller** - Congelar durante refatoração
   - Métodos públicos de MainViewModel → Documentar e congelar
   - GUI pode assumir interface estável

### Estratégia de Merge

1. Completar Fase 3 primeiro (independente)
2. Completar Fase 4 em paralelo com MainViewModel Fase 1
3. Fazer merge Fase 3+4 antes de começar Fase 5
4. Fase 5 pode ocorrer em paralelo com MainViewModel Fase 4
5. Fase 6 apenas após ambas as refatorações completas

### 10.2 Sincronizações Diárias

- **Stand-up diário**: Compartilhar progresso, bloqueadores
- **Revisão de código**: Revisar PRs um do outro
- **Testes de integração**: Executar suite de testes completa juntos
- **Discussão de arquitetura**: Resolver questões de design juntos

---

## 11. RESUMO DO ROTEIRO DE IMPLEMENTAÇÃO

```text
FASE 3: Drawing & Canvas State (4-5 dias)
  ├─ Criar DrawingStateManager
  ├─ Criar PolygonDrawingService
  └─ Criar GeometryService
  Resultado: -400 linhas, estado consolidado, +40 testes

FASE 4: ROI Template Management (3-4 dias)
  ├─ Criar ROITemplateManager
  └─ Extrair toda lógica de templates
  Resultado: -300 linhas, templates consolidados, +25 testes

FASE 5: Tab Creation Delegation (3-4 dias)
  ├─ Criar TabBuilder
  └─ Delegar criação de abas
  Resultado: -250 linhas, abas simplificadas, +15 testes

FASE 6: Final Cleanup (2-3 dias)
  ├─ Remover properties de compatibilidade
  └─ Polimento final
  Resultado: -100 linhas, código polido, +10 testes

REDUÇÃO TOTAL: ~1.050 linhas (-28%), ~72 métodos delegados
ESTADO FINAL: ~2.700 linhas, ~160 métodos, view limpa
COBERTURA FINAL: 92% (+31 pontos percentuais)
```

---

### FIM DO PLANO DE REFATORAÇÃO

Este plano abrangente fornece:

- Análise completa do estado atual (3.739 linhas, 232 métodos)
- Reconhecimento do progresso existente (14 componentes já extraídos ✅)
- Problemas arquiteturais claros identificados (5 antipadrões críticos)
- Estratégia de refatoração detalhada (4 fases, 4 novos componentes)
- **Estratégia de testes robusta** (61% → 92% cobertura, 90+ novos testes)
- Exemplos de código específicos (antes/depois para cada padrão)
- Caminho de migração com avaliação de risco
- Métricas de sucesso e checklist de validação

O plano está pronto para execução independente por um agente trabalhando em paralelo com refatoração de MainViewModel.
