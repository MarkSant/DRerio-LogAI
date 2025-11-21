# Guia de Migração: Refatoração do MainViewModel (Fases 1-5)

Este documento descreve as mudanças arquiteturais significativas realizadas durante a refatoração do `MainViewModel` e fornece um guia para desenvolvedores sobre como trabalhar com a nova arquitetura desacoplada.

## Resumo das Mudanças

O `MainViewModel` foi transformado de um "God Object" (~2800 linhas, acoplamento forte) em um orquestrador enxuto (~1700 linhas) que delega responsabilidades para serviços especializados e coordenadores.

### Principais Alterações Arquiteturais

1.  **Injeção de Dependência (DI)**:
    *   Todas as dependências são injetadas via construtor usando `MainViewModelDependencies`.
    *   O `MainViewModel` não cria mais seus próprios serviços ou a View.

2.  **Super Coordinators**:
    *   A lógica de orquestração foi consolidada em 4 coordenadores principais:
        *   `ProjectLifecycleCoordinator`: Gerencia projetos e calibração.
        *   `HardwareCoordinator`: Gerencia detectores, modelos e Arduino.
        *   `ProcessingCoordinator`: Gerencia processamento de vídeo e análise.
        *   `SessionCoordinator`: Gerencia gravação ao vivo e câmeras.
        *   `UICoordinator`: Gerencia atualizações de UI e eventos.
        *   `DialogCoordinator`: Gerencia diálogos síncronos.

3.  **Desacoplamento de UI (Event-Driven)**:
    *   **Remoção de `self.view`**: O `MainViewModel` não possui mais referência direta à `ApplicationGUI`.
    *   **EventBus**: A comunicação ViewModel -> View é feita exclusivamente via eventos (`src/zebtrack/ui/events.py`).
    *   **UICoordinator**: Responsável por ouvir eventos e atualizar a View.

## Como Realizar Tarefas Comuns

### 1. Atualizar a Interface Gráfica

**ANTIGO (Legado):**
```python
# No MainViewModel
self.view.update_status("Processando...")
self.view.show_error("Erro", "Falha X")
```

**NOVO (Recomendado):**
```python
# No MainViewModel ou Services
self.ui_event_bus.publish_event(Events.UI_SET_STATUS, {"message": "Processando..."})
self.ui_event_bus.publish_event(Events.UI_SHOW_ERROR, {"title": "Erro", "message": "Falha X"})
```

### 2. Solicitar Confirmação ou Input do Usuário (Síncrono)

Para casos onde o fluxo precisa parar e esperar o usuário (ex: Salvar Arquivo, Confirmar Sair), use o `DialogCoordinator`.

**ANTIGO:**
```python
if self.view.ask_ok_cancel("Título", "Mensagem"):
    ...
filename = self.view.ask_save_filename(...)
```

**NOVO:**
```python
# Injetar dialog_coordinator
if self.dialog_coordinator.ask_yes_no("Título", "Mensagem"):
    ...
filename = self.dialog_coordinator.ask_save_filename(...)
```

### 3. Adicionar Nova Lógica de Negócio

Não adicione métodos ao `MainViewModel`. Em vez disso:
1.  Identifique o domínio (Projeto, Hardware, Processamento, Sessão).
2.  Adicione o método ao **Service** apropriado (ex: `ProjectService`).
3.  Se envolver coordenação de múltiplos serviços e UI, adicione ao **Coordinator** correspondente (ex: `ProjectLifecycleCoordinator`).

### 4. Acessar a View (Apenas em Casos Extremos/Legados)

Se absolutamente necessário para componentes legados que ainda não foram migrados:
A referência da View está mantida no `UICoordinator`.

```python
view = self.ui_coordinator.view
```
*Evite usar isso em código novo.*

## Mapeamento de Componentes Legados

| Orchestrator Antigo | Novo Local |
|---------------------|------------|
| `VideoProcessingOrchestrator` | `ProcessingCoordinator` |
| `AnalysisOrchestrator` | `ProcessingCoordinator` |
| `ProjectOrchestrator` | `ProjectLifecycleCoordinator` |
| `CalibrationOrchestrator` | `ProjectLifecycleCoordinator` |
| `DetectorCoordinator` | `HardwareCoordinator` |
| `RecordingSessionOrchestrator` | `SessionCoordinator` |
| `LiveCameraCoordinator` | `SessionCoordinator` |

## Próximos Passos

*   Continuar a migração de serviços menores para não dependerem de `view` injetada.
*   Refatorar `ApplicationGUI` para não depender de `controller` (fluxo bidirecional via eventos).
