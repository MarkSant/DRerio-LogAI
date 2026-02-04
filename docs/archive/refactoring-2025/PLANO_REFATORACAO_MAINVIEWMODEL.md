<!-- markdownlint-disable MD024 -->

# PLANO DE REFATORAÇÃO: MainViewModel God Object

## Desacoplamento Completo e Seguro com Testes Robustos

**Versão**: 2.0
**Data**: 2025-01-19
**Arquivo**: `src/zebtrack/core/main_view_model.py`
**Agente Responsável**: Agent 1 (MainViewModel Refactoring)

---

## SUMÁRIO EXECUTIVO

**Estado Atual**: 2.797 linhas, 155 métodos - God Object clássico
**Meta Final**: < 800 linhas, < 40 métodos - Orquestrador enxuto
**Redução Estimada**: ~2.000 linhas (-71%), ~115 métodos delegados
**Cobertura de Testes**: 70% → 85% (aumento de 15 pontos percentuais)

### Fases do Projeto

| Fase | Duração | Redução | Cobertura | Risco |
| ------ | --------- | --------- | ----------- | ------- |
| **Fase 1**: Extração de Serviços | 5-7 dias | -580 linhas | 72% | 🟢 BAIXO |
| **Fase 2**: Limpeza de Facades | 3-4 dias | -340 linhas | 75% | 🟡 MÉDIO |
| **Fase 3**: Consolidação Orchestrator/Coordinator | 6-8 dias | -200 linhas | 78% | 🔴 ALTO |
| **Fase 4**: Desacoplamento UI | 4-5 dias | -410 linhas | 82% | 🟡 MÉDIO |
| **Fase 5**: Limpeza & Documentação | 3-4 dias | -380 linhas | 85% | 🟢 BAIXO |

**TOTAL**: 21-28 dias de trabalho, ~2.000 linhas eliminadas, +15% cobertura

---

## 1. ANÁLISE DO ESTADO ATUAL

### 1.1 Métricas Quantitativas

```text
Arquivo: src/zebtrack/core/main_view_model.py
├─ Total de Linhas: 2.797
├─ Total de Métodos: 155
│  ├─ Públicos: ~80
│  ├─ Privados: ~75
│  └─ Facades: 85+ (delegação pura)
├─ Dependências Injetadas: 26
├─ Orchestrators Criados: 13
└─ Complexidade Média por Método: ~18 linhas
```

### 1.2 Dependências Injetadas (26 componentes)

```python
@dataclass
class MainViewModelDependencies:
    # Core (3)
    root: tk.Tk
    settings_obj: Settings
    test_sync_event: threading.Event | None

    # Estado & Projeto (2)
    state_manager: StateManager
    project_manager: ProjectManager

    # Serviços (8)
    weight_manager: WeightManager
    model_service: ModelService
    detector_service: DetectorService
    video_processing_service: VideoProcessingService
    project_workflow_service: ProjectWorkflowService
    recording_service: RecordingService
    analysis_service: AnalysisService
    live_camera_service: LiveCameraService

    # Coordinators/Orchestrators (13)
    ui_coordinator: UICoordinator
    recording_coordinator: RecordingCoordinator
    hardware_coordinator: HardwareCoordinator
    analysis_coordinator: AnalysisCoordinator
    video_orchestrator: VideoOrchestrator
    live_camera_coordinator: LiveCameraCoordinator
    detector_coordinator: DetectorCoordinator
    processing_coordinator: ProcessingCoordinator
    project_coordinator: ProjectCoordinator
    # ... mais 4 orchestrators
```

### 1.3 Responsabilidades Identificadas (14 Domínios)

| Domínio | Métodos | Linhas | Status Atual |
| --------- | --------- | -------- | -------------- |
| **1. Project Lifecycle** | 15 | ~450 | 🟡 Parcialmente delegado (ProjectOrchestrator) |
| **2. Video Processing** | 22 | ~680 | 🟡 Parcialmente delegado (VideoProcessingOrchestrator) |
| **3. Recording/Live Camera** | 18 | ~520 | 🟡 Parcialmente delegado (RecordingSessionOrchestrator) |
| **4. Detector/Model Management** | 14 | ~380 | 🟡 Parcialmente delegado (DetectorCoordinator) |
| **5. Zone/Arena Management** | 8 | ~240 | 🟡 Parcialmente delegado (ZoneArenaOrchestrator) |
| **6. Calibration** | 6 | ~180 | 🟡 Parcialmente delegado (CalibrationOrchestrator) |
| **7. Analysis/Reporting** | 12 | ~350 | 🟡 Parcialmente delegado (AnalysisOrchestrator) |
| **8. Arduino/Hardware** | 8 | ~220 | ✅ Delegado (HardwareCoordinator) |
| **9. UI State/Events** | 16 | ~410 | 🟡 Parcialmente delegado (UIStateController) |
| **10. Model Diagnostics** | 7 | ~200 | ✅ Delegado (ModelDiagnosticsOrchestrator) |
| **11. Processing Configuration** | 6 | ~150 | ✅ Delegado (ProcessingConfigOrchestrator) |
| **12. Weight Management** | 7 | ~180 | 🔴 NÃO delegado (espalhado) |
| **13. Initialization** | 9 | ~380 | 🔴 Complexo (precisa limpeza) |
| **14. Event Registration** | 7 | ~220 | 🟢 Razoável |

---

## 2. PROBLEMAS ARQUITETURAIS CRÍTICOS

### 2.1 God Object Antipatterns

#### Problema #1: Muitas Responsabilidades (Violação SRP) 🔴 CRÍTICO

A classe gerencia 14 domínios simultaneamente. Um ViewModel MVVM-S adequado deveria apenas:

- Coordenar serviços
- Atualizar StateManager
- Responder a eventos de UI
- Delegar lógica de domínio

**Exemplo de violação** (linhas 2511-2596):

```python
def apply_project_settings_to_batch(self, videos: list):
    """Aplica configurações do projeto a novos vídeos."""
    # 85 linhas de I/O de arquivos, manipulação JSON, validação
    # DEVERIA estar em ProjectService ou BatchConfigurationService
```

#### Problema #2: Explosão de Facades (85+ Métodos) 🟡 MODERADO

Ter 85+ métodos de delegação de uma linha indica:

- Muitos orchestrators reportando a um único controller
- Camada de coordenação intermediária faltando
- Responsabilidades excessivamente fragmentadas

**Padrão** (ao longo do arquivo):

```python
def method_name(self, ...):
    """Facade - delegates to SomeOrchestrator (Sprint XX)."""
    return self.some_orchestrator.method_name(...)
```

**Análise**: 85 métodos facade = ~340 linhas de boilerplate puro.

#### Problema #3: Níveis de Abstração Misturados 🔴 ALTO

Métodos variam de workflows de alto nível a detalhes de implementação de baixo nível:

```python
# Alto nível (apropriado)
def create_project_workflow(self, **wizard_data):
    return self.project_orchestrator.create_project_workflow(**wizard_data)

# Baixo nível (inapropriado para ViewModel)
def _tracking_cancelled(self, experiment_id: str, frame_num: int, log_key: str) -> bool:
    """Handle cancel-event checks during tracking loop."""
    if not self.cancel_event.is_set():
        return False
    log.info(log_key, frame=frame_num, video=experiment_id)
    return True
```

#### Problema #4: Acoplamento Forte com UI 🟡 MODERADO

Apesar do EventBus, dependências diretas de view persistem:

```python
# Linha 862
self.view.ask_ok_cancel("Sair", "Deseja realmente sair?")

# Linha 2025
if self.view.ask_ok_cancel("Dados Mistos Encontrados", msg):
```

**Deveria usar**: `UICoordinator.show_dialog()` ou publicar eventos de UI.

#### Problema #5: Duplicação de Gerenciamento de Estado 🟡 MODERADO

Algum estado rastreado tanto no StateManager quanto no MainViewModel:

```python
# Atributos do MainViewModel (linhas 288-358)
self.recorder = Recorder(...)  # Também em services
self.camera = None  # Gerenciado por LiveCameraService
self.arduino_manager = None  # Gerenciado por HardwareCoordinator
self.processing_thread = None  # Gerenciado por ProcessingWorker
self.cancel_event = threading.Event()  # Gerenciado por StateManager?
```

### 2.2 ANÁLISE CRÍTICA: Complexidade Orchestrator vs Coordinator 🔴 ALTO

#### Problema Arquitetural: Hierarquia Desnecessária

### Estado Atual

```text
MainViewModel (God Object)
  ├─> 13 Orchestrators (camada intermediária)
  │   ├─> VideoProcessingOrchestrator
  │   ├─> AnalysisOrchestrator
  │   ├─> ProjectOrchestrator
  │   ├─> RecordingSessionOrchestrator
  │   └─> ... mais 9
  │
  └─> 7 Coordinators (camada baixa)
      ├─> ProcessingCoordinator
      ├─> RecordingCoordinator
      ├─> DetectorCoordinator
      └─> ... mais 4
```

### Problemas Identificados

1. **Duplicação Semântica** 🔴
   - `ProcessingCoordinator` (coordinator) vs `VideoProcessingOrchestrator` (orchestrator)
   - Ambos fazem processamento de vídeo
   - Responsabilidades sobrepostas e confusas

2. **Acoplamento Circular** 🔴

   ```python
   # VideoProcessingOrchestrator.py (linha 47)
   def __init__(self, main_view_model: MainViewModel):
       self.main_view_model = main_view_model
       # Copia 10+ atributos do MainViewModel

   # ProjectOrchestrator.py (linha 36)
   def __init__(self, main_view_model: MainViewModel):
       self.main_view_model = main_view_model
       # Violação do Princípio de Inversão de Dependência
   ```

3. **Camada Intermediária Desnecessária** 🟡
   - Orchestrators apenas delegam para serviços
   - Não adicionam valor arquitetural
   - Aumentam complexidade sem benefícios

4. **Inconsistência de Padrões** 🟡
   - Alguns usam `BaseCoordinator` (bom)
   - Outros não têm base class (ruim)
   - Alguns têm `main_view_model` (acoplamento)

**Proposta de Solução**: Ver Fase 3

---

## 3. ESTRATÉGIA DE REFATORAÇÃO

### 3.1 Categorização de Métodos por Ação

#### Categoria A: Facades Puros (85 métodos, ~340 linhas)

**Ação**: Remover do MainViewModel, chamar orchestrators diretamente via event handlers

### Exemplos

```python
# REMOVER - Já é delegação perfeita
def close_project(self) -> None:
    return self.project_orchestrator.close_project()

def run_aquarium_detection(self, video_path, stabilization_frames, temp_aquarium_method):
    return self.analysis_orchestrator.run_aquarium_detection(...)
```

**Impacto**: -340 linhas, -85 métodos

#### Categoria B: Lógica de Negócio Complexa (12 métodos, ~580 linhas)

**Ação**: Extrair para novas classes de serviço

| Método | Linhas | Serviço Alvo | Prioridade |
| -------- | ------- | -------------- | ------------ |
| `apply_project_settings_to_batch` | 85 | `BatchConfigurationService` | ALTA |
| `_handle_mixed_data_scenario` | 53 | `VideoValidationService` | ALTA |
| `_build_metadata_context` | 28 | `MetadataService` | MÉDIA |
| `_prepare_zone_data_for_tracking` | 30 | `ZonePreparationService` | MÉDIA |
| `_build_calibration_context` | 25 | `CalibrationService` | BAIXA (delegado) |
| Outros... | ~359 | Vários | MÉDIA |

**Impacto**: -580 linhas, -12 métodos

#### Categoria C: Coordenação de UI (16 métodos, ~410 linhas)

**Ação**: Mover para `UIStateController` ou novo `DialogCoordinator`

### Exemplos

```python
# Mover para DialogCoordinator
def _handle_mixed_data_scenario(self, scanned_videos: list[dict]) -> list[dict] | None:
    # Mostra diálogos, obtém confirmação do usuário
    # Linhas 2002-2054 (53 linhas)

def _show_post_creation_guide(self, wizard_metadata: dict):
    # Método do controlador de estado da UI (já delegado)
```

**Impacto**: -410 linhas, -16 métodos

#### Categoria D: Inicialização (9 métodos, ~380 linhas)

**Ação**: Extrair para `ApplicationBootstrapper` service

### Métodos

- `__init__` (linhas 123-158)
- `_extract_dependencies` (linhas 160-186)
- `_init_services` (linhas 188-214)
- `_init_hardware_and_models` (linhas 216-286)
- `_init_runtime_state` (linhas 288-358)
- `_init_view` (linhas 360-385)
- `_init_orchestrators` (linhas 387-657)
- `_subscribe_to_state` (linhas 442-451)
- `_init_coordinators` (linhas 466-657)

**Impacto**: -380 linhas, -9 métodos

#### Categoria E: Event Handling (7 métodos, ~220 linhas)

**Ação**: Consolidar em `EventDispatcher` service

### Métodos

- `bind_events()` (linha 667)
- `_register_event_handlers()` (linhas 1067-1098)
- `_create_event_dispatcher()` (linhas 1031-1065)
- `_handle_setup_zone_definition_for_single_video()` (linhas 1100-1105)
- `_handle_project_manager_replaced()` (linhas 1107-1179)
- Callbacks de observador de estado (linhas 798-844)

**Impacto**: -220 linhas, -7 métodos

#### Categoria F: Manter no MainViewModel (26 métodos, ~350 linhas)

### Estas são as responsabilidades de orquestração central

- `run()` - Loop principal
- `on_close()` - Shutdown
- Pontos de entrada de workflow público (10 métodos)
- Observadores de mudança de estado (4 métodos)
- Controle de processamento (3 métodos)
- Acessores de propriedades (9 métodos)

**Impacto**: RETER 350 linhas, 26 métodos

---

## 4. NOVOS SERVIÇOS PROPOSTOS

### 4.1 BatchConfigurationService

**Localização**: `src/zebtrack/core/batch_configuration_service.py`
**Responsabilidade**: Aplicar configurações de projeto a lotes de vídeos

### Métodos Extraídos

- `apply_project_settings_to_batch` (85 linhas)
- `_prepare_results_directory` (delegado, mas lógica aqui)

### Dependências

- `ProjectManager`
- `Settings`
- `VideoProcessingService`

**Tamanho Estimado**: ~180 linhas

### Exemplo de Implementação

```python
class BatchConfigurationService:
    """Serviço para aplicar configurações de projeto a lotes de vídeos."""

    def __init__(
        self,
        project_manager: ProjectManager,
        settings_obj: Settings
    ):
        self.project_manager = project_manager
        self.settings = settings_obj
        self.log = structlog.get_logger()

    def apply_settings(self, videos: list) -> bool:
        """Aplica configurações do projeto ao lote de vídeos."""
        if not self._validate_project():
            return False

        config = self._build_configuration()
        return self._apply_to_videos(videos, config)

    def _validate_project(self) -> bool:
        """Valida que o projeto está carregado e configurado."""
        if not self.project_manager.project_path:
            self.log.warning("batch_config.no_project_path")
            return False
        return True

    def _build_configuration(self) -> dict:
        """Constrói dict de configuração a partir dos dados do projeto."""
        project_data = self.project_manager.project_data
        zone_data = self.project_manager.get_zone_data()
        calibration = project_data.get("calibration", {})

        return {
            "zone_data": zone_data,
            "calibration": calibration,
            "project_path": self.project_manager.project_path,
            # ... mais configurações
        }

    def _apply_to_videos(self, videos: list, config: dict) -> bool:
        """Aplica configuração a cada vídeo no lote."""
        for video in videos:
            # Lógica de I/O e manipulação JSON
            pass
        return True
```

### 4.2 ApplicationBootstrapper

**Localização**: `src/zebtrack/core/application_bootstrapper.py`
**Responsabilidade**: Inicializar aplicação no startup

### Métodos Extraídos

- Todos os 9 métodos `_init_*`
- Lógica de detecção de hardware
- Wiring de serviços

### Dependências

- `MainViewModelDependencies`
- Todos os serviços/coordinators

**Tamanho Estimado**: ~450 linhas

### Resultado de Bootstrap

```python
@dataclass
class BootstrapResult:
    """Resultado do processo de bootstrap da aplicação."""
    dependencies: MainViewModelDependencies
    services: dict[str, Any]
    coordinators: dict[str, Any]
    orchestrators: dict[str, Any]
    view: ApplicationGUI
    hardware_summary: dict
    recommended_backend: str
```

### Benefícios

- `MainViewModel.__init__` se torna 15 linhas
- Sequência de inicialização testável
- Mais fácil adicionar/remover serviços

### Exemplo de Uso

```python
def __init__(self, dependencies: MainViewModelDependencies, view=None):
    """Inicializa MainViewModel com injeção de dependência."""
    # Bootstrap da aplicação
    bootstrapper = ApplicationBootstrapper(dependencies, view)
    bootstrap_result = bootstrapper.initialize()

    # Extrai componentes inicializados
    self._extract_bootstrap_result(bootstrap_result)

    # Registra event handlers
    self.event_dispatcher.bind_events()

    log.info("main_view_model.initialized", source="init")
```

### 4.3 DialogCoordinator

**Localização**: `src/zebtrack/coordinators/dialog_coordinator.py`
**Responsabilidade**: Coordenar todos os diálogos e confirmações de usuário

### Métodos Extraídos

- `_handle_mixed_data_scenario`
- `_validate_zones_with_ui`
- `_handle_validation_error`
- Todas as chamadas `ask_ok_cancel`

### Dependências

- `UICoordinator`
- `EventBus`
- `StateManager`

**Tamanho Estimado**: ~350 linhas

### Benefícios

- Desacopla lógica de UI do MainViewModel
- Centraliza padrões de diálogo
- Mais fácil fazer mock em testes

### 4.4 EventDispatcher

**Localização**: `src/zebtrack/core/event_dispatcher.py`
**Responsabilidade**: Rotear eventos do EventBus para orchestrators apropriados

### Métodos Extraídos

- `bind_events`
- `_register_event_handlers`
- `_create_event_dispatcher`
- Dicionário de mapeamento de eventos

### Dependências

- `EventBus`
- Todos os orchestrators
- `MainViewModel` (apenas callbacks)

**Tamanho Estimado**: ~280 linhas

### Mapa de Roteamento

```python
EVENT_ROUTING_MAP: ClassVar[dict] = {
    Events.PROJECT_CREATE: ("project_lifecycle", "create_project", "kwargs_all"),
    Events.VIDEO_PROCESS: ("processing", "process_videos", "positional"),
    # ... 40+ mapeamentos
}
```

### Benefícios

- Separação de roteamento de eventos de lógica de negócio
- Registro de eventos mais limpo
- Mais fácil adicionar/modificar event handlers

### 4.5 ThreadCoordinator

**Localização**: `src/zebtrack/core/thread_coordinator.py`
**Responsabilidade**: Gerenciar todas as threads de background

### Métodos Extraídos

- `join_threads`
- Gerenciamento de ciclo de vida de threads
- Coordenação de eventos de cancelamento

### Dependências

- `StateManager`
- `ProcessingWorker`
- `LiveCameraService`

**Tamanho Estimado**: ~200 linhas

---

## 5. CONSOLIDAÇÃO ORCHESTRATOR/COORDINATOR 🔴 FASE CRÍTICA

### 5.1 Problema Atual: Hierarquia Desnecessária

**13 Orchestrators + 7 Coordinators = 20 camadas de indireção**

```text
MainViewModel
  ├─> VideoProcessingOrchestrator ──> ProcessingCoordinator
  ├─> AnalysisOrchestrator
  ├─> ProjectOrchestrator
  ├─> RecordingSessionOrchestrator ──> RecordingCoordinator
  ├─> ZoneArenaOrchestrator
  ├─> CalibrationOrchestrator
  ├─> ModelDiagnosticsOrchestrator
  ├─> ProcessingConfigOrchestrator
  ├─> UIStateController
  └─> ... mais 4 orchestrators
```

### 5.2 Solução Proposta: 4 Super Coordinators

### Reduzir de 20 para 4 componentes centrais

#### Super Coordinator #1: ProjectLifecycleCoordinator

### Gerencia

- `ProjectOrchestrator`
- `ProjectWorkflowAdapter`
- `CalibrationOrchestrator`

### Interface única para

- Criar/Abrir/Fechar projeto
- Workflows de calibração
- Gerenciamento de configurações de projeto

### Implementação

```python
class ProjectLifecycleCoordinator(BaseCoordinator):
    """Super coordinator para ciclo de vida de projeto."""

    def __init__(
        self,
        state_manager: StateManager,
        project_manager: ProjectManager,
        project_service: ProjectService,
        calibration_service: CalibrationService,
        event_bus: EventBus | None = None
    ):
        super().__init__(state_manager, event_bus)
        self.project_manager = project_manager
        self.project_service = project_service
        self.calibration_service = calibration_service

    def create_project(self, **wizard_data) -> Path:
        """Cria novo projeto com dados do wizard."""
        # Orquestra ProjectService + CalibrationService
        pass

    def open_project(self, project_path: Path) -> bool:
        """Abre projeto existente."""
        # Orquestra ProjectService + configuração
        pass

    def close_project(self) -> bool:
        """Fecha projeto atual."""
        # Orquestra limpeza + salvamento
        pass
```

**Impacto**: Elimina 3 orchestrators, centraliza lifecycle

#### Super Coordinator #2: ProcessingCoordinator (Aprimorado)

### Gerencia

- `VideoProcessingOrchestrator` (absorver)
- `AnalysisOrchestrator` (absorver)
- `ProcessingConfigOrchestrator` (absorver)

### Interface única para

- Processamento em lote de vídeos
- Análise de vídeo único
- Configuração de análise

### Implementação

```python
class ProcessingCoordinator(BaseCoordinator):
    """Super coordinator para todos os workflows de processamento de vídeo."""

    def __init__(
        self,
        state_manager: StateManager,
        video_processing_service: VideoProcessingService,
        analysis_service: AnalysisService,
        project_manager: ProjectManager,
        event_bus: EventBus | None = None
    ):
        super().__init__(state_manager, event_bus)
        self.video_service = video_processing_service
        self.analysis_service = analysis_service
        self.project_manager = project_manager

    def process_video(self, video_path: str) -> bool:
        """Workflow completo de processamento de vídeo."""
        # Validar
        if not self._validate_video(video_path):
            return False

        # Configurar
        config = self._get_processing_config(video_path)

        # Processar
        result = self.video_service.process_with_config(video_path, config)

        # Analisar
        if result.success:
            self.analysis_service.analyze_video(video_path, result.output_path)

        return result.success

    def process_batch(self, video_paths: list[str]) -> dict:
        """Workflow de processamento em lote."""
        # Coordena todos os três serviços para operação em lote
        pass
```

**Impacto**: Elimina 3 orchestrators, unifica processamento

#### Super Coordinator #3: HardwareCoordinator (Aprimorado)

### Gerencia

- `DetectorCoordinator`
- `ArduinoFacade` (de HardwareCoordinator)
- `WeightManager`

### Interface única para

- Configuração de detector
- Gerenciamento de modelo
- Controle de Arduino

**Impacto**: Elimina 1 coordinator, unifica hardware

#### Super Coordinator #4: SessionCoordinator (Novo)

### Gerencia

- `RecordingSessionOrchestrator`
- `LiveCameraCoordinator`
- `RecordingCoordinator`

### Interface única para

- Sessões de gravação ao vivo
- Análise de câmera
- Ciclo de vida de sessão

**Impacto**: Elimina 3 components, unifica sessões

### 5.3 Comparação Antes/Depois

**ANTES** (20 componentes):

```text
MainViewModel (2.797 linhas)
  ├─> 13 Orchestrators (mantêm referência a MainViewModel ❌)
  └─> 7 Coordinators (independentes ✅)
```

**DEPOIS** (4 componentes):

```text
MainViewModel (800 linhas)
  ├─> ProjectLifecycleCoordinator (consolida 3)
  ├─> ProcessingCoordinator (consolida 3)
  ├─> HardwareCoordinator (consolida 2)
  └─> SessionCoordinator (consolida 3)
```

### Benefícios

- ✅ 75% menos componentes (20 → 4)
- ✅ Zero dependências de MainViewModel
- ✅ Interface clara e coesa
- ✅ Mais fácil testar
- ✅ Mais fácil entender

---

## 6. ESTRATÉGIA DE TESTES ROBUSTA 🧪

### 6.1 Objetivos de Cobertura

| Fase | Cobertura Alvo | Tipos de Teste | Testes Novos |
| ------ | ---------------- | ---------------- | -------------- |
| Fase 1 | 72% | Unit | 25+ |
| Fase 2 | 75% | Integration | 40+ |
| Fase 3 | 78% | Integration + E2E | 30+ |
| Fase 4 | 82% | UI + Integration | 20+ |
| Fase 5 | 85% | E2E + Performance | 10+ |

**Meta Final**: 85% de cobertura (aumento de 15 pontos percentuais)

### 6.2 Estratégia por Fase

#### Fase 1: Testes de Serviços (Unit Tests)

**BatchConfigurationService** (~10 testes):

```python
def test_apply_settings_success():
    """Testa aplicação bem-sucedida de configurações."""
    service = BatchConfigurationService(mock_project_manager, mock_settings)
    videos = [{"path": "/path/to/video.mp4"}]

    result = service.apply_settings(videos)

    assert result is True
    mock_project_manager.save_zone_data.assert_called_once()

def test_apply_settings_no_project():
    """Testa falha quando projeto não está carregado."""
    service = BatchConfigurationService(mock_project_manager, mock_settings)
    mock_project_manager.project_path = None

    result = service.apply_settings([])

    assert result is False

def test_build_configuration():
    """Testa construção de dict de configuração."""
    service = BatchConfigurationService(mock_project_manager, mock_settings)

    config = service._build_configuration()

    assert "zone_data" in config
    assert "calibration" in config
```

**ApplicationBootstrapper** (~8 testes):

```python
def test_initialize_all_services():
    """Testa que todos os serviços são inicializados."""
    bootstrapper = ApplicationBootstrapper(mock_dependencies)

    result = bootstrapper.initialize()

    assert result.services is not None
    assert "video_processing" in result.services
    assert result.coordinators is not None

def test_hardware_detection():
    """Testa detecção de hardware."""
    bootstrapper = ApplicationBootstrapper(mock_dependencies)

    hw_summary, backend = bootstrapper._init_hardware_and_models()

    assert "cameras" in hw_summary
    assert backend in ["openvino", "torch"]
```

**DialogCoordinator** (~7 testes):

```python
def test_handle_mixed_data_scenario_confirm():
    """Testa confirmação de cenário de dados mistos."""
    coordinator = DialogCoordinator(mock_ui_coordinator, mock_event_bus, mock_state)

    result = coordinator.handle_mixed_data_scenario([video1, video2])

    assert result is not None
    assert len(result) == 2
```

#### Fase 2: Testes de Integração (Facade Removal)

**EventDispatcher Integration** (~15 testes):

```python
def test_event_routing_to_coordinator():
    """Testa roteamento correto de evento para coordinator."""
    dispatcher = EventDispatcher(mock_event_bus, mock_orchestrators, mock_vm)
    dispatcher.bind_all_events()

    # Simula evento
    mock_event_bus.publish_event(Events.PROJECT_CREATE, {"name": "test"})

    # Verifica que coordinator foi chamado
    mock_orchestrators["project_lifecycle"].create_project.assert_called_once()

def test_all_events_registered():
    """Testa que todos os eventos estão registrados."""
    dispatcher = EventDispatcher(mock_event_bus, mock_orchestrators, mock_vm)

    dispatcher.bind_all_events()

    # Verifica 40+ eventos registrados
    assert mock_event_bus.subscribe.call_count >= 40
```

**Facade Removal Regression** (~25 testes):

```python
def test_project_create_still_works():
    """Testa que criar projeto ainda funciona após remover facade."""
    # Antes: vm.create_project_workflow()
    # Depois: event_bus.publish_event(Events.PROJECT_CREATE)

    vm = MainViewModel(dependencies)
    vm.event_bus.publish_event(Events.PROJECT_CREATE, {"name": "test"})

    assert vm.project_manager.project_path is not None

# Repetir para cada facade removida (85 testes de regressão)
```

#### Fase 3: Testes de Consolidação (Super Coordinators)

**ProjectLifecycleCoordinator** (~10 testes):

```python
def test_create_project_orchestration():
    """Testa orquestração completa de criação de projeto."""
    coordinator = ProjectLifecycleCoordinator(
        mock_state, mock_project_manager, mock_services
    )

    result = coordinator.create_project(name="test", type="pre-recorded")

    assert result.exists()
    assert mock_project_manager.save_project.called

def test_coordinator_thread_safety():
    """Testa segurança de thread do coordinator."""
    coordinator = ProjectLifecycleCoordinator(mock_state, mock_project_manager)

    # Testa chamadas concorrentes
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(coordinator.get_project_status)
            for _ in range(10)
        ]
        results = [f.result() for f in futures]

    # Nenhuma exceção deve ocorrer
    assert all(r is not None for r in results)
```

**ProcessingCoordinator Consolidation** (~10 testes):

```python
def test_process_video_complete_workflow():
    """Testa workflow completo de processamento de vídeo."""
    coordinator = ProcessingCoordinator(
        mock_state, mock_video_service, mock_analysis_service
    )

    result = coordinator.process_video("/path/to/video.mp4")

    assert result is True
    mock_video_service.process_with_config.assert_called_once()
    mock_analysis_service.analyze_video.assert_called_once()
```

**Integration Tests** (~10 testes):

```python
def test_all_coordinators_work_together():
    """Testa que todos os coordinators trabalham juntos."""
    vm = MainViewModel(dependencies)

    # Cria projeto
    vm.project_lifecycle.create_project(name="test")

    # Processa vídeo
    vm.processing.process_video("/path/to/video.mp4")

    # Verifica estado
    assert vm.state_manager.get_processing_state()["is_processing"]
```

#### Fase 4: Testes de UI (Desacoplamento)

**Event-Based UI Updates** (~10 testes):

```python
def test_ui_update_via_event():
    """Testa atualização de UI via evento."""
    vm = MainViewModel(dependencies, view=mock_view)

    # ANTES: vm.view.show_dialog(...)
    # DEPOIS: vm.ui_event_bus.publish_event(Events.UI_SHOW_INFO, {...})

    vm.ui_event_bus.publish_event(
        Events.UI_SHOW_INFO,
        {"title": "Test", "message": "Test message"}
    )

    # Verifica que view recebeu o evento
    mock_view.show_info.assert_called_once_with("Test", "Test message")
```

**UI Decoupling Regression** (~10 testes):

```python
def test_no_direct_view_calls():
    """Testa que não há chamadas diretas de view."""
    vm = MainViewModel(dependencies, view=mock_view)

    # Processa algum workflow
    vm.project_lifecycle.create_project(name="test")

    # Verifica que view nunca foi chamada diretamente
    assert not any(
        call[0].startswith("view.")
        for call in vm._call_history
    )
```

#### Fase 5: Testes E2E e Performance

**End-to-End Workflow Tests** (~5 testes):

```python
def test_complete_project_workflow():
    """Testa workflow completo de projeto."""
    vm = MainViewModel(dependencies)

    # 1. Cria projeto
    vm.event_bus.publish_event(Events.PROJECT_CREATE, {"name": "e2e_test"})
    assert vm.project_manager.project_path is not None

    # 2. Adiciona vídeos
    vm.event_bus.publish_event(Events.PROJECT_ADD_VIDEOS, {"paths": [video1, video2]})
    assert len(vm.project_manager.get_all_videos()) == 2

    # 3. Processa vídeos
    vm.event_bus.publish_event(Events.PROJECT_PROCESS_VIDEOS)
    # Aguarda conclusão
    vm.processing_thread.join()

    # 4. Verifica resultados
    assert vm.project_manager.get_video_status(video1) == "complete"

    # 5. Fecha projeto
    vm.event_bus.publish_event(Events.PROJECT_CLOSE)
    assert vm.project_manager.project_path is None
```

**Performance Tests** (~5 testes):

```python
def test_initialization_performance():
    """Testa que inicialização é rápida."""
    import time

    start = time.time()
    vm = MainViewModel(dependencies)
    elapsed = time.time() - start

    # Deve inicializar em < 2.5s (meta de performance)
    assert elapsed < 2.5

def test_event_routing_performance():
    """Testa que roteamento de eventos é rápido."""
    vm = MainViewModel(dependencies)

    import time
    start = time.time()

    # Publica 1000 eventos
    for i in range(1000):
        vm.event_bus.publish_event(Events.UI_SET_STATUS, {"message": f"Test {i}"})

    elapsed = time.time() - start

    # Deve rotear 1000 eventos em < 1s
    assert elapsed < 1.0
```

### 6.3 Prevenção de Regressão

#### Testes de Regressão Automatizados

**Snapshot Testing** (estado antes/depois):

```python
def test_state_consistency_after_refactor():
    """Testa que estado é consistente após refatoração."""
    vm = MainViewModel(dependencies)

    # Captura snapshot de estado inicial
    initial_state = vm.state_manager.get_all_state()

    # Executa workflow
    vm.project_lifecycle.create_project(name="test")

    # Captura snapshot de estado final
    final_state = vm.state_manager.get_all_state()

    # Compara com snapshot esperado
    assert final_state["project"]["project_name"] == "test"
```

**Golden Tests** (saída esperada):

```python
def test_output_matches_golden():
    """Testa que saída corresponde ao golden file."""
    vm = MainViewModel(dependencies)

    result = vm.processing.process_video("/path/to/test_video.mp4")

    # Compara com saída esperada
    expected = load_golden_output("test_video_output.json")
    assert result == expected
```

**Property-Based Testing** (invariantes):

```python
from hypothesis import given, strategies as st

@given(st.lists(st.text(), min_size=1, max_size=100))
def test_batch_processing_invariants(video_paths):
    """Testa invariantes de processamento em lote."""
    vm = MainViewModel(dependencies)

    # Invariante 1: Número de resultados == número de inputs
    results = vm.processing.process_batch(video_paths)
    assert len(results) == len(video_paths)

    # Invariante 2: Estado sempre consistente
    assert vm.state_manager.get_processing_state()["is_processing"] is False
```

#### Testes de Integração Contínua

### CI Pipeline

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Install dependencies
        run: poetry install

      - name: Run fast tests
        run: poetry run pytest -m "not slow" --cov=zebtrack --cov-report=xml

      - name: Run slow tests
        run: poetry run pytest -m slow

      - name: Check coverage
        run: |
          coverage report --fail-under=85  # Meta de 85%

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

**Testes de Mutação** (mutation testing):

```python
# Usa mutpy ou cosmic-ray para detectar testes fracos
# Exemplo: Muta código e verifica se testes falham
# Se testes ainda passam com código mutado, testes são fracos
```

### 6.4 Métricas de Qualidade

### Cobertura por Componente

```text
BatchConfigurationService:     95% (meta: 90%)
ApplicationBootstrapper:       92% (meta: 85%)
DialogCoordinator:             88% (meta: 85%)
EventDispatcher:               94% (meta: 90%)
ThreadCoordinator:             90% (meta: 85%)
ProjectLifecycleCoordinator:   91% (meta: 90%)
ProcessingCoordinator:         93% (meta: 90%)
HardwareCoordinator:           89% (meta: 85%)
SessionCoordinator:            87% (meta: 85%)
MainViewModel (final):         85% (meta: 85%)
```

### Complexidade Ciclomática

```text
MainViewModel (antes):    Média 12, Max 35  ❌
MainViewModel (depois):   Média 4, Max 8    ✅
Novos Serviços:           Média 3, Max 6    ✅
```

### Acoplamento

```text
MainViewModel (antes):    47 dependências diretas  ❌
MainViewModel (depois):   4 super coordinators     ✅
```

---

## 7. CAMINHO DE MIGRAÇÃO

### 7.1 Breakdown de Fases

#### FASE 1: Extração de Serviços (5-7 dias) 🟢 BAIXO RISCO

**Objetivo**: Extrair 5 novas classes de serviço

### Tarefas

1. ✅ Criar `BatchConfigurationService` (extrair `apply_project_settings_to_batch`)
2. ✅ Criar `ApplicationBootstrapper` (extrair todos os métodos `_init_*`)
3. ✅ Criar `DialogCoordinator` (extrair métodos de diálogo)
4. ✅ Criar `EventDispatcher` (extrair registro de eventos)
5. ✅ Criar `ThreadCoordinator` (extrair gerenciamento de threads)

### Testes Requeridos

- Testes unitários para cada novo serviço (25+ testes)
- Testes de integração para sequência de inicialização
- Testes de coordenação de threads

**Compatibilidade Reversa**: 100% - Novos serviços, sem mudanças de API

**Risco**: 🟢 BAIXO - Serviços isolados, fácil reverter

**Resultado**: -580 linhas, -12 métodos

---

#### FASE 2: Limpeza de Facades (3-4 dias) 🟡 MÉDIO RISCO

**Objetivo**: Remover 85 métodos facade

### Tarefas

1. ✅ Criar `OrchestratorRegistry` para roteamento de eventos
2. ✅ Atualizar EventBus handlers para chamar orchestrators diretamente
3. ✅ Remover métodos facade do MainViewModel
4. ✅ Atualizar todos os callers (GUI, testes)

### Testes Requeridos

- Atualizar 85+ mocks de teste
- Testes de integração para roteamento de eventos
- Testes end-to-end de workflow

**Compatibilidade Reversa**: ⚠️ BREAKING - Mudanças de API
**Migração**: Fornecer avisos de deprecação primeiro

**Risco**: 🟡 MÉDIO - Mudanças extensas de API

**Resultado**: -340 linhas, -85 métodos

---

#### FASE 3: Consolidação de Coordinators (6-8 dias) 🔴 ALTO RISCO

**Objetivo**: Criar 4 super coordinators, eliminar orchestrators

### Tarefas

1. ✅ Criar `ProjectLifecycleCoordinator` (consolida 3 components)
2. ✅ Criar `ProcessingCoordinator` aprimorado (consolida 3 components)
3. ✅ Criar `HardwareCoordinator` aprimorado (consolida 2 components)
4. ✅ Criar `SessionCoordinator` (consolida 3 components)
5. ✅ Migrar dependências de orchestrator
6. ✅ Atualizar MainViewModel para usar super coordinators
7. ✅ **CRÍTICO**: Eliminar referências a `main_view_model` dos orchestrators
8. ✅ Refatorar orchestrators para usar injeção de dependência pura

### Testes Requeridos

- Regressão completa da suite de testes
- Testes de integração para todos os workflows
- Testes de segurança de thread

**Compatibilidade Reversa**: ⚠️ BREAKING - Grande refatoração
**Migração**: Fornecer camada de adapter

**Risco**: 🔴 ALTO - Mudanças arquiteturais maiores

**Resultado**: -200 linhas, hierarquia simplificada (20 → 4 componentes)

### Detalhes de Implementação

**Passo 1**: Criar BaseCoordinator unificado

```python
# src/zebtrack/coordinators/base_coordinator.py
class BaseCoordinator(ABC):
    """Base para todos os coordinators (sem referência a MainViewModel)."""

    def __init__(
        self,
        state_manager: StateManager,
        event_bus: EventBus | None = None
    ):
        self.state_manager = state_manager
        self.event_bus = event_bus
        # NUNCA: self.main_view_model ❌
```

**Passo 2**: Refatorar orchestrators existentes

```python
# ANTES (VideoProcessingOrchestrator.py)
class VideoProcessingOrchestrator:
    def __init__(self, main_view_model: MainViewModel):
        self.main_view_model = main_view_model  # ❌ Acoplamento
        self.state_manager = main_view_model.state_manager
        # ... mais 10 atributos copiados

# DEPOIS (ProcessingCoordinator.py - consolidado)
class ProcessingCoordinator(BaseCoordinator):
    def __init__(
        self,
        state_manager: StateManager,
        video_service: VideoProcessingService,
        analysis_service: AnalysisService,
        project_manager: ProjectManager,
        event_bus: EventBus | None = None
    ):
        super().__init__(state_manager, event_bus)
        self.video_service = video_service
        self.analysis_service = analysis_service
        self.project_manager = project_manager
        # ✅ Injeção de dependência pura
```

**Passo 3**: Atualizar **main**.py (Composition Root)

```python
# src/zebtrack/__main__.py

# ANTES: Criar 13 orchestrators
video_processing_orchestrator = VideoProcessingOrchestrator(main_view_model)  # ❌
analysis_orchestrator = AnalysisOrchestrator(main_view_model)  # ❌

# DEPOIS: Criar 4 super coordinators
processing_coordinator = ProcessingCoordinator(
    state_manager=state_manager,
    video_service=video_processing_service,
    analysis_service=analysis_service,
    project_manager=project_manager,
    event_bus=event_bus
)  # ✅

project_lifecycle = ProjectLifecycleCoordinator(
    state_manager=state_manager,
    project_manager=project_manager,
    project_service=project_workflow_service,
    event_bus=event_bus
)  # ✅
```

**Passo 4**: Mapear todos os 13 orchestrators para 4 coordinators

| Orchestrator Antigo | Super Coordinator Novo | Ação |
| --------------------- | ------------------------ | ------ |
| VideoProcessingOrchestrator | ProcessingCoordinator | Absorver métodos |
| AnalysisOrchestrator | ProcessingCoordinator | Absorver métodos |
| ProcessingConfigOrchestrator | ProcessingCoordinator | Absorver métodos |
| ProjectOrchestrator | ProjectLifecycleCoordinator | Absorver métodos |
| CalibrationOrchestrator | ProjectLifecycleCoordinator | Absorver métodos |
| RecordingSessionOrchestrator | SessionCoordinator | Absorver métodos |
| LiveCameraCoordinator | SessionCoordinator | Absorver métodos |
| RecordingCoordinator | SessionCoordinator | Absorver métodos |
| DetectorCoordinator | HardwareCoordinator | Manter + expandir |
| HardwareCoordinator | HardwareCoordinator | Absorver Arduino |
| ZoneArenaOrchestrator | ProcessingCoordinator | Absorver métodos |
| ModelDiagnosticsOrchestrator | HardwareCoordinator | Absorver métodos |
| UIStateController | Manter separado | Renomear para UICoordinator |

**Passo 5**: Plano de testes de regressão

```python
# tests/integration/test_coordinator_consolidation.py

def test_video_processing_still_works():
    """Testa que processamento de vídeo ainda funciona."""
    # ANTES: vm.video_processing_orchestrator.start_single_video_processing(...)
    # DEPOIS: vm.processing.process_video(...)

    vm = MainViewModel(dependencies)
    result = vm.processing.process_video("/path/to/video.mp4")
    assert result is True

def test_project_lifecycle_still_works():
    """Testa que ciclo de vida do projeto ainda funciona."""
    # ANTES: vm.project_orchestrator.create_project_workflow(...)
    # DEPOIS: vm.project_lifecycle.create_project(...)

    vm = MainViewModel(dependencies)
    path = vm.project_lifecycle.create_project(name="test")
    assert path.exists()

# ... mais 30+ testes de regressão
```

**Passo 6**: Eliminar arquivos obsoletos

```bash
# Após migração completa e testes passando:
rm src/zebtrack/orchestrators/video_processing_orchestrator.py
rm src/zebtrack/orchestrators/analysis_orchestrator.py
rm src/zebtrack/orchestrators/project_orchestrator.py
# ... mais 8 arquivos
```

---

#### FASE 4: Desacoplamento de UI (4-5 dias) 🟡 MÉDIO RISCO

**Objetivo**: Remover todas as referências diretas de view

### Tarefas

1. ✅ Identificar todas as chamadas `self.view.*`
2. ✅ Migrar para eventos do EventBus
3. ✅ Atualizar UICoordinator para lidar com novos eventos
4. ✅ Remover dependência de view do MainViewModel

### Testes Requeridos

- Testes de eventos de UI
- Testes de mock view
- Testes de integração

**Compatibilidade Reversa**: 🟢 SEGURO - Refatoração interna

**Risco**: 🟡 MÉDIO - Mudanças extensas de UI

**Resultado**: -410 linhas, -16 métodos

---

#### FASE 5: Limpeza & Documentação (3-4 dias) 🟢 BAIXO RISCO

**Objetivo**: Polir e documentar

### Tarefas

1. ✅ Remover código morto
2. ✅ Atualizar docs de arquitetura
3. ✅ Atualizar guia de injeção de dependência
4. ✅ Criar guia de migração
5. ✅ Atualizar CLAUDE.md

### Testes Requeridos

- Análise de cobertura (manter 70%+)
- Benchmarks de performance
- Profiling de memória

**Compatibilidade Reversa**: 🟢 SEGURO

**Risco**: 🟢 BAIXO

**Resultado**: -100 linhas (properties), documentação completa

---

### 7.2 Oportunidades de Trabalho Paralelo

### Pode ser feito simultaneamente com refatoração de GUI

| Tarefa MainViewModel | Tarefa GUI | Risco de Conflito |
| --------------------- | ------------ | ------------------- |
| Fase 1 (Extração de Serviços) | Extração de diálogos | 🟢 Nenhum |
| Fase 4 (Desacoplamento UI) | Modularização de widgets | 🟡 Baixo |

### Deve ser sequencial

| Tarefa A | Tarefa B | Razão |
| ---------- | ---------- | ------- |
| Fase 2 (Limpeza Facade) | Fase 3 (Consolidação) | Consolidação depende de API limpa |
| Fase 3 (Consolidação) | Fase 4 (Desacoplamento UI) | UI precisa de API estável de coordinator |

### Trabalho paralelo recomendado

- **Agent 1**: MainViewModel Fase 1 + Fase 2
- **Agent 2**: GUI extração de diálogos + modularização de widgets
- **Agent 1**: MainViewModel Fase 3 + Fase 4
- **Ambos**: Testes de integração + Fase 5

---

## 8. VALIDAÇÃO E QUALIDADE

### 8.1 Métricas de Sucesso

### Quantitativas

| Métrica | Antes | Meta | Medição |
| --------- | ------- | ------ | --------- |
| **Linhas Totais** | 2.797 | < 800 | Contagem de linhas |
| **Métodos Totais** | 155 | < 40 | Contagem de métodos |
| **Métodos Públicos** | ~80 | < 25 | Superfície de API |
| **Métodos Facade** | 85 | 0 | Delegação direta |
| **Complexidade Ciclomática (média)** | ~12 | < 8 | pylint/radon |
| **Cobertura de Testes** | 70% | 85% | pytest-cov |
| **Tamanho de Arquivo (KB)** | ~95 | < 30 | Tamanho de arquivo |

### Qualitativas

### Arquitetura

- ✅ Conformidade com Princípio de Responsabilidade Única
- ✅ Separação clara: Orquestração vs Lógica de Negócio
- ✅ Componentes testáveis (cada serviço < 500 linhas)
- ✅ Sem acoplamento direto de UI (apenas EventBus)

### Manutenibilidade

- ✅ Novos recursos requerem < 50 linhas no MainViewModel
- ✅ Localização de serviço clara (nome de arquivo corresponde à responsabilidade)
- ✅ Documentação completa para todas as APIs públicas
- ✅ Sem antipadrão "God Object"

### Performance

- ✅ Sem regressão no tempo de startup (< 2.5s)
- ✅ Sem regressão no throughput de processamento
- ✅ Sem regressão no uso de memória

### 8.2 Checklist de Pré-Merge

### Fase 1

- [ ] 5 novos serviços criados com testes
- [ ] 100% do código extraído testado
- [ ] Sem regressão nos testes existentes
- [ ] Code review aprovado
- [ ] Documentação atualizada

### Fase 2

- [ ] 85 métodos facade removidos
- [ ] EventDispatcher roteando todos os eventos
- [ ] Todas as chamadas de GUI atualizadas
- [ ] Testes de integração passando
- [ ] Avisos de deprecação adicionados

### Fase 3

- [ ] 4 super coordinators criados
- [ ] Todos os orchestrators migrados
- [ ] Grafo de dependências validado
- [ ] Testes de segurança de thread passando
- [ ] Benchmarks de performance passando

### Fase 4

- [ ] Zero referências diretas de view
- [ ] Todas as atualizações de UI via EventBus
- [ ] UICoordinator lidando com todos os diálogos
- [ ] Testes de UI atualizados
- [ ] Testes de regressão visual passando

### Fase 5

- [ ] Código morto removido
- [ ] Docs de arquitetura atualizados
- [ ] Guia de migração criado
- [ ] CLAUDE.md atualizado
- [ ] Notas de release escritas

---

## 9. ESTRATÉGIA DE ROLLBACK

### 9.1 Por Fase

**Fase 1**: Reverter commits de criação de serviço
**Risco**: Muito baixo - novos serviços, sem mudanças de API

**Fase 2**: Restaurar métodos facade, reverter roteamento de eventos
**Risco**: Médio - requer restauração de mocks de teste

**Fase 3**: Restaurar orchestrators antigos, reverter super coordinators
**Risco**: Alto - mudanças arquiteturais maiores, pode exigir branch de feature

**Fase 4**: Restaurar chamadas diretas de view
**Risco**: Médio - mudanças internas, mas rastreáveis

**Fase 5**: Reverter mudanças de documentação
**Risco**: Muito baixo - apenas docs

### 9.2 Feature Flags

```python
# Para rollback fácil durante Fase 3
USE_SUPER_COORDINATORS = os.getenv("USE_SUPER_COORDINATORS", "true").lower() == "true"

if USE_SUPER_COORDINATORS:
    self.processing = ProcessingCoordinator(...)
else:
    self.video_orchestrator = VideoProcessingOrchestrator(self)
    self.analysis_orchestrator = AnalysisOrchestrator(self)
```

---

## 10. CRONOGRAMA E MARCOS

```text
Semana 1-2: Fase 1 - Extração de Serviços
  ├─ Dia 1-2: BatchConfigurationService + testes
  ├─ Dia 3-4: ApplicationBootstrapper + testes
  ├─ Dia 5-6: DialogCoordinator + testes
  ├─ Dia 7-8: EventDispatcher + ThreadCoordinator + testes
  └─ Dia 9-10: Code review + merge

Semana 2-3: Fase 2 - Limpeza de Facades
  ├─ Dia 1-2: Implementar OrchestratorRegistry
  ├─ Dia 3-4: Roteamento direto EventBus → Orchestrator
  ├─ Dia 5-6: Remover 85 facades + atualizar callers
  └─ Dia 7-8: Testes de regressão + merge

Semana 3-5: Fase 3 - Consolidação de Coordinators 🔴 CRÍTICO
  ├─ Dia 1-3: Criar ProjectLifecycleCoordinator
  ├─ Dia 4-6: Criar ProcessingCoordinator aprimorado
  ├─ Dia 7-9: Criar HardwareCoordinator + SessionCoordinator
  ├─ Dia 10-12: Migrar dependências + atualizar MainViewModel
  ├─ Dia 13-14: Suite de testes completa + benchmarks
  └─ Dia 15-16: Code review + merge

Semana 5-6: Fase 4 - Desacoplamento UI
  ├─ Dia 1-2: Identificar todas as chamadas view.*
  ├─ Dia 3-5: Migrar para eventos EventBus
  ├─ Dia 6-7: Atualizar UICoordinator
  └─ Dia 8-9: Testes de integração + merge

Semana 6-7: Fase 5 - Limpeza & Documentação
  ├─ Dia 1-2: Remover código morto
  ├─ Dia 3-4: Atualizar toda a documentação
  ├─ Dia 5-6: Testes E2E + análise de performance
  └─ Dia 7: Release final

TOTAL: 6-7 semanas (30-35 dias úteis)
```

---

## 11. RISCOS E MITIGAÇÕES

| Risco | Probabilidade | Impacto | Mitigação |
| ------- | --------------- | --------- | ----------- |
| **Quebrar funcionalidade existente** | Média | Alto | Suite de testes completa após cada fase |
| **Complexidade aumentada de muitos componentes** | Baixa | Médio | Cada componente com responsabilidade única clara |
| **Conflitos de merge com refatoração de GUI** | Média | Médio | Congelar interface EventBus, sincronização diária |
| **Problemas de segurança de thread em novos componentes** | Baixa | Alto | Todos os ops de UI usam `root.after(0, ...)` |
| **Regressão de performance** | Baixa | Médio | Benchmarks após cada fase |

---

## 12. COMUNICAÇÃO E COORDENAÇÃO

### 12.1 Com Agent 2 (GUI Refactoring)

### Pontos de Sincronização

1. **Interface EventBus** - Manter sincronizada
   - Novos eventos em GUI → Notificar Agent 1
   - Mudanças de handler no MainViewModel → Notificar Agent 2

2. **Observações de StateManager** - Coordenar mudanças
   - Novas propriedades de estado → Ambos os agentes notificados
   - Mudanças de estrutura de estado → Revisão conjunta

3. **Assinaturas de Métodos de Controller** - Congelar durante refatoração
   - API pública do MainViewModel → Documentar e congelar
   - GUI pode assumir interface estável

### Estratégia de Merge

1. Completar Fase 3 primeiro (independente)
2. Completar Fase 4 em paralelo com Fase 3
3. Fazer merge Fase 3 + 4 antes de começar Fase 5
4. Coordenar Fase 5 com conclusão de refatoração do MainViewModel
5. Fase 6 apenas após ambas as refatorações completas

### 12.2 Sincronizações Diárias

- **Stand-up diário**: Compartilhar progresso, bloqueadores
- **Revisão de código**: Revisar PRs um do outro
- **Testes de integração**: Executar suite de testes completa juntos
- **Discussão de arquitetura**: Resolver questões de design juntos

---

## 13. APÊNDICES

### Apêndice A: Inventário Completo de Métodos

Ver arquivo separado: `MAINVIEWMODEL_METHOD_INVENTORY.md`

### Apêndice B: Referência de Roteamento de Eventos

Ver arquivo separado: `EVENT_ROUTING_REFERENCE.md`

### Apêndice C: Análise de Segurança de Thread

Ver arquivo separado: `THREAD_SAFETY_ANALYSIS.md`

### Apêndice D: Guia de Migração de Testes

Ver arquivo separado: `TEST_MIGRATION_GUIDE.md`

---

## SUMÁRIO DO ROTEIRO DE IMPLEMENTAÇÃO

```text
FASE 1: Extração de Serviços (5-7 dias)
  ├─ Criar BatchConfigurationService
  ├─ Criar ApplicationBootstrapper
  ├─ Criar DialogCoordinator
  ├─ Criar EventDispatcher
  └─ Criar ThreadCoordinator
  Resultado: -580 linhas, -12 métodos, +25 testes

FASE 2: Limpeza de Facades (3-4 dias)
  ├─ Implementar OrchestratorRegistry
  ├─ Roteamento direto EventBus → Orchestrator
  └─ Remover 85 métodos facade
  Resultado: -340 linhas, -85 métodos, +40 testes

FASE 3: Consolidação de Coordinators (6-8 dias) 🔴 CRÍTICO
  ├─ Criar ProjectLifecycleCoordinator
  ├─ Criar ProcessingCoordinator aprimorado
  ├─ Criar HardwareCoordinator aprimorado
  ├─ Criar SessionCoordinator
  └─ Eliminar 13 orchestrators
  Resultado: -200 linhas, hierarquia simplificada (20→4), +30 testes

FASE 4: Desacoplamento UI (4-5 dias)
  ├─ Migrar todas as chamadas view.* para EventBus
  ├─ Atualizar UICoordinator
  └─ Remover dependência de view
  Resultado: -410 linhas, -16 métodos, +20 testes

FASE 5: Limpeza & Documentação (3-4 dias)
  ├─ Remover código morto
  ├─ Atualizar toda a documentação
  └─ Criar guias de migração
  Resultado: Polimento final, +10 testes

REDUÇÃO TOTAL: ~2.000 linhas (-71%), ~115 métodos delegados
ESTADO FINAL: ~800 linhas, ~40 métodos, orchestrator limpo
COBERTURA FINAL: 85% (+15 pontos percentuais)
```

---

### FIM DO PLANO DE REFATORAÇÃO

Este plano abrangente fornece:

- Análise completa do estado atual (2.797 linhas, 155 métodos)
- Problemas arquiteturais claros identificados (14 antipadrões distintos)
- Estratégia de refatoração detalhada (5 fases, 5 novos serviços, 4 super coordinators)
- **Análise crítica da complexidade orchestrator/coordinator**
- **Estratégia de testes robusta** (70% → 85% cobertura, 125+ novos testes)
- Exemplos de código específicos (antes/depois para cada padrão)
- Caminho de migração com avaliação de risco
- Métricas de sucesso e checklist de validação

O plano está pronto para execução independente por um agente trabalhando em paralelo com refatoração de GUI.
