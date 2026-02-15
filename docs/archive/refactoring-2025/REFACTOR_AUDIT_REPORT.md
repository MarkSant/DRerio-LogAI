# Relatório de Auditoria de Refatoração (Pente-Fino) - ZebTrack-AI

**Data:** 26/11/2025
**Status:** ✅ Correções Críticas Aplicadas

Este relatório documenta as correções aplicadas para resolver regressões introduzidas pela decomposição da "God Class" `ApplicationGUI` e pela implementação da Arquitetura Orientada a Eventos.

## 1. Correções de Regressão (GUI Shim Layer)

Para evitar `AttributeError` e `MethodNotFound` em componentes que ainda dependem da estrutura antiga da `ApplicationGUI`, foi implementada uma camada de compatibilidade ("Shim Layer").

### Métodos "Delegate" Adicionados
Os seguintes métodos foram reimplementados na `ApplicationGUI` para delegar chamadas aos novos Managers:

*   `_refresh_zone_indicators()` -> Delega para `CanvasManager.redraw_zones_from_project_data()`
*   `_enable_roi_button_if_arena_exists()` -> Delega para `CanvasManager.update_roi_button_state()`
*   `_maybe_offer_zone_reuse(video_path)` -> Delega para `DialogManager.offer_zone_reuse(video_path)`
*   `_on_handle_press`, `_on_handle_drag`, `_on_handle_release` -> Delegam para `CanvasEventHandler` (necessário para edição de polígonos).
*   `publish_video_hierarchy_snapshot` -> Delega para `EventBusV2`.

### Atributos Legados Inicializados
Os seguintes atributos, anteriormente definidos dinamicamente ou no `__init__` antigo, foram restaurados explicitamente para evitar falhas em componentes como `CanvasManager` e `WidgetFactory`:

*   `self.edited_polygon_points` (Estado de edição de polígono)
*   `self.interactive_polygon_item`
*   `self.polygon_handles`
*   `self.current_editing_zone`
*   `self._dragged_handle_index`, `self._drag_offset`, `self._drag_start_mouse`
*   `self._original_image`, `self._raw_bg_image` (Cache de imagem)
*   `self._roi_templates_cache`
*   `self.roi_choice_var`
*   `self.video_path`

## 2. Correção de Fluxo "Single Video"

**Problema Identificado:**
O fluxo de análise de vídeo único (`start_single_video_processing`) falhava ao tentar salvar dados de zona, pois invocava `self.save_project()` (via `persist=True`) mesmo quando nenhum projeto estava carregado (`project_path` é `None`).

**Correção:**
Alterada a chamada em `src/zebtrack/coordinators/processing_coordinator.py` para:
```python
self.project_manager.save_zone_data(
    zone_data,
    video_path,
    persist=bool(self.project_manager.project_path)  # Só persiste se houver projeto
)
```

## 3. Recuperação do Overlay de Detecção

**Problema Identificado:**
O evento `Events.UI_UPDATE_DETECTION_OVERLAY`, emitido pelo `ProcessingWorker`, não estava sendo escutado por ninguém na camada de UI, resultando na ausência de feedback visual (bounding boxes) durante a análise.

**Correção:**
Adicionada subscrição explícita em `src/zebtrack/ui/components/event_dispatcher.py`:
```python
self.event_bus.subscribe(Events.UI_UPDATE_DETECTION_OVERLAY,
    lambda d: self.gui.update_detection_overlay(
        detections=d.get("detections"), report=d.get("report")
    ))
```

## 4. Próximos Passos (Dívida Técnica)

Embora o sistema esteja estabilizado, as seguintes refatorações são recomendadas para remover a dependência da "Shim Layer":

1.  **Estado do Canvas:** Mover `edited_polygon_points` e afins para dentro de `CanvasManager` e atualizar todas as referências.
2.  **Bindings de Eventos:** Atualizar `canvas/renderer.py` para vincular eventos do Tkinter diretamente aos métodos do `CanvasEventHandler`, removendo a necessidade de delegates na GUI.
3.  **Injeção de Dependência:** Continuar substituindo acessos `self.gui.algum_manager` por injeção direta de managers onde possível.

---
**Auditoria concluída com sucesso.** O código agora deve executar os fluxos principais sem erros de atributo ou método ausente.
