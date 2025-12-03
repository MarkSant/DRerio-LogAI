# Guia do Event Bus (v4.0)

**Versão:** 4.0.0
**Componente:** `src/zebtrack/ui/event_bus_v2.py`

O `EventBusV2` é o coração da arquitetura desacoplada do ZebTrack-AI. Ele permite que componentes se comuniquem sem referências diretas uns aos outros.

## Como Funciona

O padrão é **Publicar/Assinar (Pub/Sub)**.
1.  Um componente (Publisher) emite um evento.
2.  O `EventBus` notifica todos os assinantes (Subscribers) daquele evento.
3.  O `UICoordinator` é o principal assinante, orquestrando as atualizações de UI.

## Lista de Eventos (UIEvents)

| Evento | Descrição | Payload (Dados) |
|--------|-----------|-----------------|
| `ZONES_UPDATED` | Zonas (arena/ROIs) foram alteradas (desenhadas, apagadas, editadas). | `{'zone_data': ZoneData \| None}` |
| `POLYGON_EDIT_REQUESTED` | Solicitação para editar vértices de um polígono existente. | `{'polygon': np.ndarray}` |
| `VIDEO_TREE_REFRESH_REQUESTED` | Solicitação para atualizar a árvore de seleção de vídeos. | `{'filter_text': str \| None}` |
| `PROJECT_VIEWS_REFRESH_REQUESTED` | Solicitação genérica para atualizar visualizações do projeto. | `{'reason': str, 'append_summary': bool}` |
| `READINESS_SNAPSHOT_UPDATED` | Atualização do status de prontidão dos vídeos (quais têm zonas, trajetórias). | `{'ready_with_trajectory': [...], ...}` |
| `VIDEO_LOADED` | Um novo vídeo foi carregado no canvas. | `{'video_path': str}` |
| `EXTERNAL_TRIGGER_NOTICE` | Aviso de aguardando trigger externo (Arduino). | `{'session_label': str, ...}` |

## Como Usar

### 1. Publicar um Evento (Publisher)

Use quando algo importante acontecer no seu componente.

```python
from zebtrack.ui.event_bus_v2 import Event, UIEvents

# Dentro de um método do seu componente (ex: DialogManager)
if self.event_bus_v2:
    self.event_bus_v2.publish(Event(
        type=UIEvents.ZONES_UPDATED,
        data={'zone_data': new_zone_data},
        source='MeuComponente'
    ))
```

### 2. Assinar um Evento (Subscriber)

Geralmente feito no `UICoordinator` ou componentes autônomos.

```python
# No método _setup_subscriptions do UICoordinator
self.event_bus.subscribe(UIEvents.ZONES_UPDATED, self._on_zones_updated)

def _on_zones_updated(self, data: dict):
    zone_data = data.get('zone_data')
    # Lógica de reação...
```

## Melhores Práticas

1.  **Payloads Leves:** Evite passar objetos pesados (como arrays de imagem gigantes) se não for estritamente necessário. Passe referências ou IDs.
2.  **Sem Loops:** Cuidado para que o tratamento de um evento A não publique um evento B que, por sua vez, publica o evento A novamente.
3.  **Thread Safety:** O `EventBus` é síncrono por padrão. Se publicar de uma thread secundária, o handler rodará nessa thread. O `UICoordinator` usa `root.after(0, ...)` para garantir que atualizações de GUI ocorram na main thread.

## Migração de Código Legado

Se encontrar uma chamada direta como:
```python
self.gui.update_zone_listbox(data)
```
Substitua por:
```python
self.event_bus.publish(Event(UIEvents.ZONES_UPDATED, {'zone_data': data}))
```