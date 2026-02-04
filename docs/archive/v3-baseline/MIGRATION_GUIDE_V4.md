# Guia de Migração v4.0

Este guia consolida as instruções para desenvolvedores migrarem código legado para a nova arquitetura Event-Driven v4.0.

## Principais Mudanças

1. **GUI mais leve:** Métodos de lógica de negócios foram removidos de `ApplicationGUI`.
2. **Event Bus:** Comunicação via eventos em vez de chamadas diretas.
3. **Managers:** Funcionalidades agrupadas em `CanvasManager`, `DialogManager`, etc.

## Check-list de Migração

Ao adicionar ou modificar código:

- [ ] **Não adicione métodos à `GUI`**: Se precisar de nova lógica de UI, adicione ao `UICoordinator` ou a um Manager específico.
- [ ] **Use Eventos**: Em vez de chamar `gui.refresh_...()`, publique um evento correspondente.
- [ ] **Injeção de Dependência**: Se seu componente precisa acessar outro, receba-o no construtor ou use o `UICoordinator` como mediador via eventos.

## Mapeamento de Métodos (De -> Para)

| Código Antigo (v3) | Código Novo (v4) |
| -------------------- | ------------------ |
| `gui.update_zone_listbox(data)` | `event_bus.publish(Event(UIEvents.ZONES_UPDATED, ...))` |
| `gui.refresh_project_views()` | `event_bus.publish(Event(UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED, ...))` |
| `gui._refresh_video_selector_tree()` | `event_bus.publish(Event(UIEvents.VIDEO_TREE_REFRESH_REQUESTED, ...))` |
| `gui.apply_pending_readiness_snapshot(...)` | `event_bus.publish(Event(UIEvents.READINESS_SNAPSHOT_UPDATED, ...))` |

## Exemplo Prático: Adicionando um Botão

**Antes (v3):**

```python
# gui.py
def _on_click(self):
    self.process_data()
    self.update_ui()
```

**Depois (v4):**

```python
# component.py
def _on_click(self):
    # Processa dados localmente ou via Controller
    self.event_bus.publish(Event(UIEvents.DATA_PROCESSED, result))

# ui_coordinator.py
def _on_data_processed(self, event):
    self.canvas_manager.show_result(event.data)
```
