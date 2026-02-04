<!-- markdownlint-disable MD024 -->

# 🎯 Plano de Ação: Correção e Unificação dos Fluxos de Câmera ao Vivo

**Data:** 2025-01-11 (Atualizado)
**Versão:** 1.1
**Status:** Pendente Implementação
**Prioridade:** 🔴 CRÍTICA

## Changelog v1.1

- ✅ Adicionado **Bug #6 (CRÍTICO)**: Acoplamento LiveCameraService → RecordingService
- ✅ Adicionada **Fase 2.6**: Desacoplamento completo com código detalhado
- ✅ Explicação de como o acoplamento causa os sintomas reportados
- ✅ Atualização nos checklists de validação e implementação

---

## 📋 Índice

1. [Contexto e Motivação](#-contexto-e-motivação)
2. [Problemas Identificados](#-problemas-identificados)
3. [Objetivos](#-objetivos)
4. [Arquitetura Alvo](#%EF%B8%8F-arquitetura-alvo)
5. [Plano de Implementação](#plano-de-implementação)
6. [Validação e Testes](#-validação-e-testes)
7. [Rollback Plan](#-rollback-plan)
8. [Referências](#-referências)

---

## Contexto e Motivação

### Situação Atual

O ZebTrack-AI possui **DOIS sistemas paralelos** para gerenciar câmeras ao vivo, causando bugs graves:

1. **Sistema NOVO** (v2.0): `LiveCameraService` - bem arquitetado, MVVM-S compliant
2. **Sistema LEGADO** (pré-v2.0): Threads em `gui.py` - código monolítico, problemático

### Dois Contextos de Uso

## Contexto 1: Análise de Vídeo Único com Câmera

- Menu: "Analisar Vídeo Único" → RadioButton "Câmera ao Vivo"
- Status: ✅ Usa sistema NOVO (LiveCameraService)
- Problema: ❌ Ignora intervalos de análise/exibição configurados

## Contexto 2: Projetos Live (Gravação de Sessões)

- Menu: "Novo Projeto" → Wizard → Tipo "Live"
- Status: ❌ Usa sistema LEGADO (threads em gui.py)
- Problema: ❌ Ignora `camera_index` selecionado no wizard (sempre abre câmera 0)

---

## 🐛 Problemas Identificados

### Bug 1: 🔴 CRÍTICO - Projetos Live ignoram `camera_index` do wizard

**Localização:** `src/zebtrack/ui/gui.py:2822-2840`

### Código problemático

```python
if project_type == "live":
    # ❌ USA settings global (camera.index = 0 default)
    self.controller.camera = Camera(settings_obj=self.controller.settings)

    # ❌ IGNORA project_data["camera_index"] salvo pelo wizard!
```

### Impacto

- Usuário seleciona câmera 1 no wizard
- Sistema abre câmera 0
- Dados gravados da câmera errada

---

### Bug 2: 🔴 CRÍTICO - Intervalos de análise/exibição ignorados

**Localização:** `src/zebtrack/ui/components/event_dispatcher.py:520-524`

### Código problemático

```python
if source_type == "camera":
    camera_index = dialog.result.get("camera_index", 0)
    # ❌ Passa apenas camera_index, perde intervalos!
    self.gui.controller.start_live_camera_analysis(camera_index=camera_index)
```

### Impacto

- Usuário configura `analysis_interval=10`, `display_interval=10`
- Sistema usa `interval=1` (padrão hardcoded)
- Desempenho degradado, processa todos os frames

---

### Bug 3: 🟡 MÉDIO - LiveStreamSource ignora `camera_index`

**Localização:** `src/zebtrack/io/live_stream_source.py:60-61`

### Código problemático

```python
def __init__(self, camera_index: int = 0, ...):
    self.camera_index = camera_index  # ← Armazena mas não usa
    self.camera = Camera(settings_obj=settings_obj)  # ← USA settings.camera.index!
```

### Impacto

- Atualmente não usado (LiveCameraService usa Camera diretamente)
- Bug latente para uso futuro

---

### Bug 4: 🟡 MÉDIO - FrameSourceFactory ignora `camera_index`

**Localização:** `src/zebtrack/io/frame_source_factory.py:104`

### Código problemático

```python
return Camera(settings_obj=settings_obj)  # ❌ Não modifica camera.index
```

### Impacto

- Similar ao Bug 3
- Bug latente

---

### Problema 5: 🔴 CRÍTICO - Código legado coexiste e causa conflitos

**Localização:** `src/zebtrack/ui/gui.py:2856-2916`

### Threads legados

- `_live_frame_capture_loop()` (linha 2897)
- `_live_processing_loop()` (linha 2923)

### Impacto

- Duplicação de threads (4 threads ao invés de 2)
- Duplicação de frame buffers (2x memória)
- Competição por hardware (múltiplos `cv2.VideoCapture`)
- Race conditions
- Código difícil de manter

---

### Bug 6: 🔴 CRÍTICO - Acoplamento indevido entre LiveCameraService e RecordingService

**Localização:** `src/zebtrack/core/live_camera_service.py:178-213`

### Código problemático

```python
def start_session(self, ...):
    # ... setup camera, detector, preview window ...

    # Linha 178-188: Constrói contexto para RecordingService
    context = {
        "day": 1,
        "group": "live_analysis",
        "cobaia": experiment_id,
        "folder_name": folder_name,
        "output_folder": str(output_dir),
        "camera_width": self.camera.actual_width if self.camera else 640,
        "camera_height": self.camera.actual_height if self.camera else 480,
        "arduino_enabled": False,
    }

    project_data = {
        "use_timed_recording": True,
        "recording_duration_s": duration_s,
        "use_countdown": False,
        "use_arduino": False,
    }

    # Linha 209: ❌ CHAMA RecordingService (ACOPLAMENTO CRÍTICO)
    self.recording_service.start_session(
        context=context,
        project_data=project_data,
        trigger_source="live_analysis",
    )
```

#### Por que isso é problemático

`RecordingService` foi projetado para **contexto de PROJETO** e assume:

1. Existe um projeto carregado (`ProjectManager`)
2. Pode acessar `project_manager.get_zone_data()` (linha ~150 em recording_service.py)
3. Atualiza estado global via `StateManager.update_recording_state()`
4. Chama callbacks de UI (`_update_button_state()`) que modificam controles do projeto
5. Pode interagir com Arduino via projeto

### Impacto CRÍTICO - Como causa os sintomas reportados

1. **Múltiplas câmeras ativando (LEDs acendem):**
   - RecordingService pode chamar `setup_detector()` que recarrega zonas
   - Detector pode instanciar Camera temporária para validação
   - Resultado: 2-3 objetos Camera simultâneos = múltiplos LEDs

2. **Câmera errada abre:**
   - RecordingService acessa `self.controller.settings` (global)
   - Ignora o `camera_index` passado ao LiveCameraService
   - Usa `settings.camera.index` (padrão = 0)

3. **Preview não mostra imagens / delays:**
   - RecordingService compete pelos mesmos frame queues
   - Atualiza StateManager causando race conditions
   - UI recebe sinais conflitantes sobre estado de gravação

4. **Side effects indesejados:**
   - Atualiza botões de projeto (Start/Stop Recording) mesmo sem projeto aberto
   - Pode disparar callbacks de Arduino
   - Polui logs com eventos de "recording_started" quando é só análise

### Impacto

- ❌ LiveCameraService (análise standalone) **DEPENDE** de RecordingService (orientado a projetos)
- ❌ Acoplamento tight = código frágil, difícil de manter
- ❌ Viola princípio de responsabilidade única (SRP)
- ❌ Análise standalone não deveria modificar estado global
- ❌ Causa os bugs principais: múltiplas câmeras, câmera errada, preview quebrado

### Solução necessária (Fase 2.6)

- Desacoplar: LiveCameraService deve ter gravação própria e leve
- RecordingService continua servindo projetos
- Separação clara de responsabilidades

### UPDATE 2025-11-11:**✅**CORRIGIDO - TypeError em LiveCameraService.start_session()

- **Problema:** Após refatoração parcial do Bug 6, a chamada ao `Recorder.start_recording()`
  estava usando parâmetros incorretos, causando `TypeError: Recorder.start_recording() got
  an unexpected keyword argument 'folder_name'`
- **Causa:** Parâmetros incorretos foram passados: `folder_name`, `video_filename`,
  `parquet_filename`, `width`, `height`, `fps` ao invés de `output_folder`, `frame_width`,
  `frame_height`, `zones`, `is_video_file`, `base_name`
- **Correção:** Ajustada a chamada em `live_camera_service.py` (linhas 193-218) para usar
  a assinatura correta de `Recorder.start_recording()`
- **Teste:** Adicionado teste de regressão `test_recorder_called_with_correct_parameters()`
  em `test_live_camera_service_threading.py` para prevenir futuros erros
- **Status:** 24/24 testes passando ✅

---

## 🎯 Objetivos

### Primários

1. ✅ **Unificar fluxos**: Ambos contextos usam `LiveCameraService`
2. ✅ **Respeitar configurações**: `camera_index`, intervalos sempre respeitados
3. ✅ **Deprecar legado**: Remover threads de `gui.py`
4. ✅ **Melhorar desempenho**: -50% threads, -50% memória

### Secundários

1. ✅ **Código limpo**: -200 linhas de código legado
2. ✅ **Manutenibilidade**: Um caminho de código = menos bugs
3. ✅ **Escalabilidade**: Fácil adicionar multi-câmera no futuro
4. ✅ **Alinhamento arquitetural**: Seguir MVVM-S rigorosamente

---

## 🏗️ Arquitetura Alvo

### Diagrama de Fluxo Unificado

```text
┌─────────────────────────────────────────────────────────────┐
│                    ENTRY POINTS (GUI)                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Menu: "Analisar Vídeo Único"          Menu: "Novo Projeto" │
│         (Contexto 1)                         (Contexto 2)   │
│            ↓                                      ↓          │
│  SingleVideoConfigDialog                   Wizard 5 passos  │
│    - camera_index = 1                       - camera_index  │
│    - analysis_interval = 10                 - intervals     │
│    - display_interval = 10                  - project_data  │
│            ↓                                      ↓          │
└────────────┼──────────────────────────────────────┼─────────┘
             │                                      │
             └──────────────┬───────────────────────┘
                            ↓
             ┌──────────────────────────────┐
             │   MainViewModel (Controller) │
             │ start_live_camera_analysis   │
             │     _from_config(config)     │
             └──────────────┬───────────────┘
                            ↓
             ┌──────────────────────────────┐
             │      LiveCameraService       │
             │   (Sistema Unificado v2.0)   │
             ├──────────────────────────────┤
             │ start_session(               │
             │   camera_index,              │
             │   duration_s,                │
             │   experiment_id,             │
             │   analysis_interval,         │
             │   display_interval,          │
             │   record_video               │
             │ )                            │
             └──────────────┬───────────────┘
                            ↓
        ┌───────────────────┴───────────────────┐
        │                                       │
        ↓                                       ↓
┌───────────────┐                    ┌──────────────────┐
│ _setup_camera │                    │ RecordingService │
│ (camera_index)│                    │  (coordenação)   │
└───────┬───────┘                    └────────┬─────────┘
        ↓                                     ↓
┌───────────────┐                    ┌──────────────────┐
│    Camera     │                    │     Recorder     │
│ (cv2.Video    │                    │  (Parquet/MP4)   │
│  Capture)     │                    └──────────────────┘
└───────┬───────┘
        ↓
┌───────────────────────────────────────┐
│  _capture_loop() + _processing_loop() │
│         (daemon threads)              │
└───────────────┬───────────────────────┘
                ↓
        ┌───────────────┐
        │ LivePreview   │
        │    Window     │
        └───────────────┘
```

### Características da Arquitetura

- ✅ **Um único serviço**: `LiveCameraService` para ambos contextos
- ✅ **Configuração completa**: Todos parâmetros passados explicitamente
- ✅ **Separação de responsabilidades**: Service layer isolado da GUI
- ✅ **Thread safety**: Daemon threads com cleanup automático
- ✅ **Dependency Injection**: Settings modificados via `model_copy(deep=True)`

---

## Plano de Implementação

### Fase 1: Correções Críticas e Urgentes

#### 1.1. Fix Bug 2 - Passar intervalos completos no Contexto 1

**Arquivo:** `src/zebtrack/ui/components/event_dispatcher.py`

**Localização:** Linhas 509-538

### Mudança

```python
def handle_analyze_single_video_clicked(self) -> None:
    """Handle the UI part of the single video workflow."""
    from zebtrack.ui.dialogs import SingleVideoConfigDialog
    from zebtrack.ui.events import Events

    dialog = SingleVideoConfigDialog(self.gui.root, settings_obj=self.gui.controller.settings)
    if not dialog.result:
        return  # User cancelled

    source_type = dialog.result.get("source_type", "video")

    if source_type == "camera":
        # ANTES:
        # camera_index = dialog.result.get("camera_index", 0)
        # self.gui.controller.start_live_camera_analysis(camera_index=camera_index)
        # return

        # DEPOIS:
        # Passar configuração completa, não apenas camera_index
        config = dialog.result
        self.gui.controller.start_live_camera_analysis_from_config(config)
        return

    # Video file analysis: require video_path
    video_path = dialog.result.get("video_path")
    if not video_path:
        return

    # Pass both config and video path to the controller via event
    self.publish_event(
        Events.VIDEO_ANALYZE_SINGLE,
        {
            "video_path": video_path,
            "config": dialog.result,
        },
    )
```

---

#### 1.2. Criar método `start_live_camera_analysis_from_config()`

**Arquivo:** `src/zebtrack/core/main_view_model.py`

**Localização:** Adicionar após linha 2702

### Código

```python
def start_live_camera_analysis_from_config(self, config: dict):
    """
    Start live camera analysis with full configuration from SingleVideoConfigDialog.

    This method extracts all parameters from the config dictionary and delegates
    to LiveCameraService, ensuring intervals and other settings are respected.

    Args:
        config: Configuration dictionary from SingleVideoConfigDialog containing:
            - camera_index: int - Camera device index
            - analysis_interval_frames: int - Analyze every N frames
            - display_interval_frames: int - Display every N frames
            - (other dialog parameters)
    """
    log.info("controller.live_analysis.start_from_config", config_keys=list(config.keys()))

    # Extract configuration with defaults
    camera_index = config["camera_index"]

    # Duration: use setting or default
    if hasattr(self.settings, "live_analysis"):
        duration_s = self.settings.live_analysis.default_duration_s
    else:
        duration_s = 300.0  # 5 minutes default

    # Experiment ID
    experiment_id = config.get("experiment_id") or f"camera_{camera_index}"

    # ✅ CRITICAL: Extract intervals from config (not hardcoded defaults!)
    analysis_interval_frames = config.get("analysis_interval_frames", 1)
    display_interval_frames = config.get("display_interval_frames", 1)

    # Video recording (optional)
    record_video = config.get("record_video", True)

    log.info(
        "controller.live_analysis.extracted_config",
        camera_index=camera_index,
        duration_s=duration_s,
        analysis_interval=analysis_interval_frames,
        display_interval=display_interval_frames,
        record_video=record_video,
    )

    # Delegate to LiveCameraService with complete configuration
    success = self.live_camera_service.start_session(
        camera_index=camera_index,
        duration_s=duration_s,
        experiment_id=experiment_id,
        analysis_interval_frames=analysis_interval_frames,
        display_interval_frames=display_interval_frames,
        record_video=record_video,
    )

    # UI feedback
    if success and self.ui_event_bus:
        self.ui_event_bus.publish_event(
            Events.UI_SET_STATUS,
            {
                "message": (
                    f"Analisando câmera {camera_index} "
                    f"(análise: {analysis_interval_frames}f, "
                    f"exibição: {display_interval_frames}f)"
                )
            },
        )
    elif not success and self.ui_event_bus:
        self.ui_event_bus.publish_event(
            Events.UI_SHOW_ERROR,
            {
                "title": "Erro na Análise",
                "message": f"Falha ao iniciar análise de câmera {camera_index}.",
            },
        )
```

---

#### 1.3. Fix Bug 1 - Projetos Live usam `camera_index` correto

**Arquivo:** `src/zebtrack/ui/gui.py`

**Localização:** Linhas 2822-2840

### Mudança

```python
if project_type == "live":
    try:
        # ANTES:
        # self.controller.camera = Camera(settings_obj=self.controller.settings)

        # DEPOIS:
        # ✅ Use camera_index from project_data (saved by wizard)
        pm = self.controller.project_manager
        camera_index = pm.project_data.get("camera_index", 0)

        log.info(
            "gui.project_loading.live_camera_setup",
            camera_index=camera_index,
            project_name=pm.get_project_name(),
        )

        # Create temporary settings with correct camera index
        temp_settings = self.controller.settings.model_copy(deep=True)
        temp_settings.camera.index = camera_index

        # Initialize camera with modified settings
        self.controller.camera = Camera(settings_obj=temp_settings)

        self.controller.active_frame_source = self.controller.camera
        self.controller.detector.update_scaling(
            self.controller.camera.actual_width,
            self.controller.camera.actual_height,
        )
    except OSError as e:
        self.show_error("Erro na Câmera", str(e))
        self._create_welcome_frame()
        return
```

---

### Fase 2: Migração Arquitetural - Deprecar Código Legado

#### 2.1. Marcar threads legados como DEPRECATED

**Arquivo:** `src/zebtrack/ui/gui.py`

**Localização:** Linhas 2856-2867

### Mudança

```python
if project_type == "live":
    # ⚠️ DEPRECATED: Legacy thread system for Live projects
    # TODO: Migrate to LiveCameraService in Phase 2.2
    # This code will be removed in v3.0

    log.warning(
        "gui.project_loading.legacy_threads_active",
        message=(
            "Using deprecated thread system for Live projects. "
            "Migrate to LiveCameraService for better performance and reliability."
        ),
    )

    self.controller.capture_thread = threading.Thread(
        target=self._live_frame_capture_loop, name="CaptureThread", daemon=True
    )
    self.controller.processing_thread = threading.Thread(
        target=self._live_processing_loop, name="ProcessingThread", daemon=True
    )
    self.controller.capture_thread.start()
    self.controller.processing_thread.start()

    # Auto-calibration for Live projects when no zones are defined
    self.root.after(1000, self._check_live_project_calibration)
```

### Adicionar docstrings de deprecation

```python
def _live_frame_capture_loop(self):
    """
    Loop to capture frames from a LIVE source (camera).

    .. deprecated:: 2.1
        This method is deprecated and will be removed in v3.0.
        Use LiveCameraService for live camera management instead.
    """
    # ... existing code ...

def _live_processing_loop(self):
    """
    Loop to process frames from a LIVE source.

    .. deprecated:: 2.1
        This method is deprecated and will be removed in v3.0.
        Use LiveCameraService for live camera processing instead.
    """
    # ... existing code ...
```

---

#### 2.2. Criar método de gravação de sessão via LiveCameraService

**Arquivo:** `src/zebtrack/core/main_view_model.py`

**Localização:** Adicionar novo método

### Código

```python
def start_live_project_session(
    self,
    day: int,
    group: str,
    subject: str,
    duration_s: float | None = None,
) -> bool:
    """
    Start a live recording session for a Live project.

    This method replaces the legacy thread-based system in gui.py,
    using LiveCameraService for unified camera management.

    Args:
        day: Day number (from project grid)
        group: Group identifier
        subject: Subject/animal identifier
        duration_s: Optional duration override (uses project default if None)

    Returns:
        True if session started successfully, False otherwise
    """
    pm = self.project_manager

    # Validate project type
    if pm.get_project_type() != "live":
        log.error("start_live_project_session.wrong_project_type")
        return False

    # Extract project configuration
    project_data = pm.project_data
    camera_index = project_data.get("camera_index", 0)

    # Duration: use parameter, project default, or fallback
    if duration_s is None:
        duration_s = project_data.get("recording_duration_s", 300.0)

    # Intervals
    analysis_interval_frames = project_data.get("analysis_interval_frames", 1)
    display_interval_frames = project_data.get("display_interval_frames", 1)

    # Experiment ID for this session
    experiment_id = f"day{day}_{group}_{subject}"

    log.info(
        "controller.live_project_session.start",
        project=pm.get_project_name(),
        experiment_id=experiment_id,
        camera_index=camera_index,
        duration_s=duration_s,
    )

    # Delegate to LiveCameraService (unified system)
    success = self.live_camera_service.start_session(
        camera_index=camera_index,
        duration_s=duration_s,
        experiment_id=experiment_id,
        analysis_interval_frames=analysis_interval_frames,
        display_interval_frames=display_interval_frames,
        record_video=True,  # Projects always record
    )

    return success
```

---

#### 2.3. Modificar LiveCameraService para suportar projetos

**Arquivo:** `src/zebtrack/core/live_camera_service.py`

**Localização:** Método `start_session()`, linhas 96-216

### Mudança no output_dir

```python
def start_session(
    self,
    camera_index: int,
    duration_s: float,
    experiment_id: str,
    analysis_interval_frames: int = 1,
    display_interval_frames: int = 1,
    record_video: bool = True,
    output_base_dir: str | None = None,  # ✅ NOVO: permite customizar output
) -> bool:
    """
    Start a live camera analysis session.

    Args:
        camera_index: Camera device index
        duration_s: Session duration in seconds
        experiment_id: Identifier for this session
        analysis_interval_frames: Analyze every N frames
        display_interval_frames: Display every N frames
        record_video: Whether to record video
        output_base_dir: Custom output directory (default: live_analysis_sessions/)

    Returns:
        True if session started successfully, False otherwise
    """
    # ... existing validation code ...

    # Create output directory
    from datetime import datetime

    # ✅ Allow custom output directory for projects
    if output_base_dir:
        output_base = Path(output_base_dir)
    else:
        output_base = Path("live_analysis_sessions")

    output_base.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{experiment_id}_{timestamp}"
    output_dir = output_base / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # ... rest of existing code ...
```

---

#### 2.4. Atualizar chamadas no grid de projetos

**Arquivo:** `src/zebtrack/ui/gui.py`

**Localização:** Método `_on_grid_cell_clicked()` e relacionados

### Mudança

```python
def _start_recording_session(self, day: int, group: str, subject: str):
    """
    Start a recording session (Live or timed).

    For Live projects, delegates to LiveCameraService (NEW).
    For pre-recorded projects, uses legacy RecordingService.
    """
    pm = self.controller.project_manager
    project_type = pm.get_project_type()

    if project_type == "live":
        # ✅ NEW: Use LiveCameraService for Live projects
        success = self.controller.start_live_project_session(
            day=day,
            group=group,
            subject=subject,
        )

        if not success:
            self.show_error(
                "Erro na Gravação",
                f"Falha ao iniciar sessão de gravação para {group}/{subject}."
            )
        return

    # Legacy path for pre-recorded projects
    # ... existing RecordingService code ...
```

---

#### 2.5. Remover threads legados (BREAKING CHANGE)

**Arquivo:** `src/zebtrack/ui/gui.py`

**Localização:** Linhas 2856-2867, 2897-2916, 2923-2975

**Ação:** COMENTAR (não remover ainda) com marcação de remoção

```python
# ========================================================================
# DEPRECATED CODE - SCHEDULED FOR REMOVAL IN v3.0
# ========================================================================
# This legacy thread system has been replaced by LiveCameraService
# Kept commented for reference during migration period
# Remove after all tests pass and user validation is complete
# ========================================================================

# if project_type == "live"
#     self.controller.capture_thread = threading.Thread(
#         target=self._live_frame_capture_loop, name="CaptureThread", daemon=True
#     )
#     self.controller.processing_thread = threading.Thread(
#         target=self._live_processing_loop, name="ProcessingThread", daemon=True
#     )
#     self.controller.capture_thread.start()
#     self.controller.processing_thread.start()
#     self.root.after(1000, self._check_live_project_calibration)

# def _live_frame_capture_loop(self)
#     """DEPRECATED - Use LiveCameraService instead."""
#     # ... existing code commented out ..

# def _live_processing_loop(self)
#     """DEPRECATED - Use LiveCameraService instead."""
#     # ... existing code commented out ..
```

---

#### 2.6. 🔥 CRÍTICO - Desacoplar LiveCameraService do RecordingService

## Contexto

Atualmente, `LiveCameraService.start_session()` chama `RecordingService.start_session()` na linha 209.
Isso cria acoplamento tight e causa múltiplos bugs (câmera errada, múltiplas câmeras, preview quebrado).

**Solução:** LiveCameraService deve gerenciar sua própria gravação de forma leve, sem depender de RecordingService.

---

**Arquivo:** `src/zebtrack/core/live_camera_service.py`

**Localização:** Método `start_session()`, linhas 178-216

### Mudança Completa

```python
def start_session(
    self,
    camera_index: int,
    duration_s: float,
    experiment_id: str,
    analysis_interval_frames: int = 1,
    display_interval_frames: int = 1,
    record_video: bool = True,
    output_base_dir: str | None = None,
) -> bool:
    """
    Start a live camera analysis session.

    Args:
        camera_index: Camera device index
        duration_s: Session duration in seconds
        experiment_id: Identifier for this session
        analysis_interval_frames: Analyze every N frames
        display_interval_frames: Display every N frames
        record_video: Whether to record video
        output_base_dir: Custom output directory (default: live_analysis_sessions/)

    Returns:
        True if session started successfully, False otherwise
    """
    log.info(
        "live_camera_service.start_session",
        camera_index=camera_index,
        duration_s=duration_s,
        experiment_id=experiment_id,
        analysis_interval=analysis_interval_frames,
        display_interval=display_interval_frames,
    )

    # Store configuration
    self.analysis_interval_frames = analysis_interval_frames
    self.display_interval_frames = display_interval_frames
    self.is_capturing_for_video = record_video

    # Setup camera
    if not self._setup_camera(camera_index):
        return False

    # Create output directory
    from datetime import datetime

    if output_base_dir:
        output_base = Path(output_base_dir)
    else:
        output_base = Path("live_analysis_sessions")

    output_base.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{experiment_id}_{timestamp}"
    output_dir = output_base / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # Setup detector if needed
    if not self.detector_service.detector:
        if not self.controller.setup_detector():
            log.error("live_camera_service.detector_setup_failed")
            return False

    # Apply zones to detector if available
    zone_data = self.project_manager.get_zone_data() if self.project_manager else None
    if zone_data and self.camera:
        # CRITICAL: Use actual camera dimensions for correct zone rescaling
        self.detector_service.configure_zones(
            zone_data=zone_data,
            width=self.camera.actual_width,
            height=self.camera.actual_height,
        )

    # Create preview window
    log.info("live_camera_service.about_to_create_preview_window", camera_index=camera_index)
    self._create_preview_window(camera_index, duration_s)
    log.info("live_camera_service.preview_window_creation_complete", camera_index=camera_index)

    # Start threads before recording
    if not self._start_threads():
        return False

    # Update state
    self.state_manager.update_processing_state(
        source="live_camera_service.start",
        is_processing=True,
    )

    # ========================================================================
    # ✅ NOVA IMPLEMENTAÇÃO: Gravação leve DENTRO de LiveCameraService
    # ========================================================================
    # Substituiu chamada a RecordingService (linha 209 REMOVIDA)
    # LiveCameraService agora é autossuficiente e não polui estado global

    # Initialize lightweight recorder for standalone analysis
    if record_video and self.controller.recorder:
        # Prepare recorder context (simplified, no project assumptions)
        video_filename = f"{experiment_id}_{timestamp}.mp4"
        parquet_filename = f"{experiment_id}_{timestamp}.parquet"

        # Start recorder directly (no RecordingService intermediary)
        try:
            recorder_started = self.controller.recorder.start_recording(
                folder_name=str(output_dir),
                video_filename=video_filename,
                parquet_filename=parquet_filename,
                width=self.camera.actual_width if self.camera else 640,
                height=self.camera.actual_height if self.camera else 480,
                fps=self.camera.actual_fps if self.camera else 30.0,
            )

            if not recorder_started:
                log.error("live_camera_service.recorder_start_failed")
                self.stop_session()
                return False

            log.info(
                "live_camera_service.recorder_started",
                output_dir=str(output_dir),
                video_file=video_filename,
            )

        except Exception as e:
            log.error(
                "live_camera_service.recorder_init_error",
                error=str(e),
                exc_info=True,
            )
            self.stop_session()
            return False

    # Setup session completion timer (replaces RecordingService timer)
    self._setup_session_timer(duration_s, output_dir)

    log.info("live_camera_service.session_started", output_dir=str(output_dir))
    return True
```

---

### Adicionar novo método auxiliar

```python
def _setup_session_timer(self, duration_s: float, output_dir: Path):
    """
    Setup timer to automatically stop session after duration.

    Replaces RecordingService's timed recording logic.

    Args:
        duration_s: Session duration in seconds
        output_dir: Output directory for results
    """
    def on_timer_expired():
        """Called when duration expires."""
        log.info(
            "live_camera_service.timer_expired",
            duration_s=duration_s,
        )
        self._on_session_complete(output_dir)

    # Schedule timer (in milliseconds)
    if self.root:
        self.timer_id = self.root.after(
            int(duration_s * 1000),
            on_timer_expired,
        )
        log.info(
            "live_camera_service.timer_scheduled",
            duration_s=duration_s,
        )
```

---

### Modificar `stop_session()` para limpar timer

```python
def stop_session(self):
    """Stop the current live camera analysis session."""
    log.info("live_camera_service.stop_session")

    # ✅ NOVO: Cancelar timer se existir
    if hasattr(self, "timer_id") and self.timer_id and self.root:
        try:
            self.root.after_cancel(self.timer_id)
            log.info("live_camera_service.timer_cancelled")
        except Exception as e:
            log.warning("live_camera_service.timer_cancel_error", error=str(e))

    # ✅ NOVO: Parar recorder diretamente (não via RecordingService)
    if self.controller.recorder:
        try:
            self.controller.recorder.stop_recording()
            log.info("live_camera_service.recorder_stopped")
        except Exception as e:
            log.warning("live_camera_service.recorder_stop_error", error=str(e))

    # Signal threads to exit
    self.exit_event.set()

    # Wait for threads to finish
    if self.capture_thread and self.capture_thread.is_alive():
        self.capture_thread.join(timeout=2.0)

    if self.processing_thread and self.processing_thread.is_alive():
        self.processing_thread.join(timeout=2.0)

    # Close preview window
    if self.preview_window:
        try:
            self.preview_window.destroy()
        except Exception as e:
            log.warning("live_camera_service.preview_close_error", error=str(e))
        self.preview_window = None

    # Release camera
    if self.camera:
        self.camera.release()
        self.camera = None

    # Update state
    self.state_manager.update_processing_state(
        source="live_camera_service.stop",
        is_processing=False,
    )

    # Clear queues
    self._clear_queues()

    log.info("live_camera_service.session_stopped")
```

---

### Adicionar campo de instância no `__init__()`

```python
def __init__(
    self,
    controller: MainViewModel,
    state_manager: StateManager,
    project_manager: ProjectManager,
    recording_service: RecordingService,  # Manter injetado mas não usar
    detector_service: DetectorService,
    root: Misc | None = None,
):
    """
    Initialize LiveCameraService.

    Args:
        controller: MainViewModel controller for accessing resources
        state_manager: StateManager for centralized state tracking
        project_manager: ProjectManager for project-specific data
        recording_service: RecordingService (kept for DI compatibility, not used)
        detector_service: DetectorService for detection operations
        root: Tkinter root for UI updates
    """
    self.controller = controller
    self.state_manager = state_manager
    self.project_manager = project_manager
    self.recording_service = recording_service  # Not used after refactor
    self.detector_service = detector_service
    self.root = root

    # Threading infrastructure
    self.frame_queue = queue.Queue(maxsize=30)
    self.video_queue = queue.Queue(maxsize=30)
    self.exit_event = threading.Event()
    self.capture_thread: threading.Thread | None = None
    self.processing_thread: threading.Thread | None = None

    # Active session state
    self.camera: Camera | None = None
    self.preview_window: LivePreviewWindow | None = None
    self.analysis_interval_frames = 1
    self.display_interval_frames = 1
    self.is_capturing_for_video = False
    self.timer_id: str | None = None  # ✅ NOVO: ID do timer de duração
```

---

### Resultado

- ✅ LiveCameraService **NÃO** chama RecordingService
- ✅ Gravação leve e autossuficiente
- ✅ Não polui estado global
- ✅ Não modifica UI de projetos
- ✅ Respeita camera_index corretamente
- ✅ Evita múltiplas instâncias de Camera
- ✅ Preview funciona sem race conditions

---

### Fase 3: Correções Preventivas (Bugs Latentes)

#### 3.1. Fix Bug 3 - LiveStreamSource respeita `camera_index`

**Arquivo:** `src/zebtrack/io/live_stream_source.py`

**Localização:** Linhas 36-75

### Mudança

```python
def __init__(
    self,
    camera_index: int = 0,
    max_duration_s: float = 300.0,
    settings_obj: "Settings | None" = None,
):
    """
    Initialize live stream source with duration limit.

    Args:
        camera_index: Camera device index (default 0)
        max_duration_s: Maximum capture duration in seconds (default 300 = 5 min)
        settings_obj: Settings instance (required for Camera initialization)
    """
    if settings_obj is None:
        raise RuntimeError(
            "LiveStreamSource: Settings not injected. "
            "Use: LiveStreamSource(settings_obj=load_settings())"
        )

    self.camera_index = camera_index
    self.max_duration_s = max_duration_s
    self.settings = settings_obj

    # ANTES:
    # self.camera = Camera(settings_obj=settings_obj)

    # DEPOIS:
    # ✅ Create modified settings with correct camera index
    temp_settings = settings_obj.model_copy(deep=True)
    temp_settings.camera.index = camera_index
    self.camera = Camera(settings_obj=temp_settings)

    # ... rest of existing code ...
```

---

#### 3.2. Fix Bug 4 - FrameSourceFactory respeita `camera_index`

**Arquivo:** `src/zebtrack/io/frame_source_factory.py`

**Localização:** Linhas 58-104

### Mudança

```python
@staticmethod
def create_from_camera(
    camera_index: int,
    max_duration_s: float | None = None,
    settings_obj: "Settings | None" = None,
) -> FrameSource:
    """
    Create a camera-based source with optional duration limit.

    Args:
        camera_index: Camera device index
        max_duration_s: Optional duration limit (None = unlimited)
        settings_obj: Settings instance

    Returns:
        LiveStreamSource if duration specified, Camera otherwise
    """
    if settings_obj is None:
        raise ValueError("settings_obj is required for camera sources")

    if max_duration_s is not None:
        # Time-limited stream
        log.info(
            "frame_source_factory.create_live_stream",
            camera_index=camera_index,
            max_duration_s=max_duration_s,
        )
        return LiveStreamSource(
            camera_index=camera_index,
            max_duration_s=max_duration_s,
            settings_obj=settings_obj,
        )
    else:
        # Unlimited camera stream
        log.info(
            "frame_source_factory.create_camera",
            camera_index=camera_index,
            duration="unlimited",
        )

        # ANTES:
        # return Camera(settings_obj=settings_obj)

        # DEPOIS:
        # ✅ Create modified settings with correct camera index
        temp_settings = settings_obj.model_copy(deep=True)
        temp_settings.camera.index = camera_index
        return Camera(settings_obj=temp_settings)
```

---

### Fase 4: Documentação e Deprecation Warnings

#### 4.1. Atualizar CHANGELOG.md

**Arquivo:** `CHANGELOG.md`

### Adicionar

```markdown
## [2.1.0] - 2025-01-XX

### 🔴 Breaking Changes
- **Live Projects**: Migrated to unified LiveCameraService architecture
  - Legacy thread system (`_live_frame_capture_loop`, `_live_processing_loop`) deprecated
  - Will be removed in v3.0

### ✨ Features
- Unified camera management for both analysis contexts
- Live projects now respect `camera_index` selected in wizard
- Intervals (analysis/display) properly respected in all workflows

### 🐛 Bug Fixes
- **CRITICAL**: Fixed Live projects always opening camera 0 (now uses wizard selection)
- **CRITICAL**: Fixed analysis intervals being ignored in single video workflow
- **CRITICAL**: Decoupled LiveCameraService from RecordingService (eliminated tight coupling)
  - Fixed multiple cameras activating simultaneously
  - Fixed wrong camera opening (respects camera_index correctly)
  - Fixed preview window delays and display issues
  - Eliminated unwanted side effects on global state
- Fixed LiveStreamSource ignoring camera_index parameter
- Fixed FrameSourceFactory ignoring camera_index parameter

### 🚀 Performance
- Reduced thread count by 50% (4 → 2 threads)
- Reduced frame buffer memory by 50%
- Eliminated lock contention overhead

### 📝 Deprecated
- `gui._live_frame_capture_loop()` - Use LiveCameraService
- `gui._live_processing_loop()` - Use LiveCameraService
- Scheduled for removal: v3.0

### 🏗️ Architecture
- Unified `LiveCameraService` for both contexts:
  - Context 1: Single video analysis with camera
  - Context 2: Live projects with multi-session recording
```

---

#### 4.2. Atualizar CLAUDE.md

**Arquivo:** `CLAUDE.md`

**Seção a atualizar:** "Recent Major Features"

```markdown
### Phase 7: Live Camera Unification (Jan 2025)
- **Unified Architecture**: Single `LiveCameraService` for all camera workflows
- **Bug Fixes**:
  - Live projects respect `camera_index` from wizard (not hardcoded 0)
  - Intervals (analysis/display) properly passed and respected
  - LiveStreamSource and FrameSourceFactory honor camera_index
- **Deprecation**: Legacy thread system in gui.py marked for removal (v3.0)
- **Performance**: 50% reduction in threads and memory usage
```

---

#### 4.3. Criar arquivo de documentação técnica

**Arquivo:** `docs/LIVE_CAMERA_UNIFICATION.md`

### Criar novo arquivo

```markdown
# Live Camera Unification - Technical Documentation

## Overview

ZebTrack-AI v2.1 unified all live camera workflows under a single service architecture,
eliminating code duplication and fixing critical bugs in camera selection and configuration.

## Architecture

### Before (v2.0)
- **Context 1** (Single video analysis): LiveCameraService ✅
- **Context 2** (Live projects): Legacy threads in gui.py ❌
- Result: Duplicated code, conflicting hardware access, bugs

### After (v2.1)
- **Both contexts**: LiveCameraService ✅
- Result: Unified, performant, maintainable

## Migration Guide

### For Users
No action required. Existing projects will continue to work with improved reliability.

### For Developers

#### Using LiveCameraService

```python
# Context 1: Single video analysis
config = single_video_dialog.result
controller.start_live_camera_analysis_from_config(config)

# Context 2: Live project session
controller.start_live_project_session(
    day=1,
    group="control",
    subject="fish01"
)
```text

#### Deprecated Code

The following methods are deprecated and will be removed in v3.0:

- `gui._live_frame_capture_loop()`
- `gui._live_processing_loop()`

Use `LiveCameraService` instead.

## Testing

All tests updated to use unified architecture. See:

- `tests/integration/test_live_camera_analysis_integration.py`
- `tests/core/test_live_camera_service.py`

```

---

## ✅ Validação e Testes

### Checklist de Validação Funcional

## Contexto 1: Análise de Vídeo Único

- [ ] **Teste 1.1**: Selecionar câmera 1, verificar que câmera 1 abre (não 0)
- [ ] **Teste 1.2**: Configurar `analysis_interval=15`, verificar logs mostram interval=15
- [ ] **Teste 1.3**: Configurar `display_interval=20`, verificar preview atualiza a cada 20 frames
- [ ] **Teste 1.4**: Apenas câmera selecionada acende LED (não outras câmeras) ✅**Fix Bug #6**
- [ ] **Teste 1.5**: Preview mostra imagens dentro de 2 segundos ✅**Fix Bug #6**
- [ ] **Teste 1.6**: Gravação salva em `live_analysis_sessions/` com Parquet correto
- [ ] **Teste 1.7**: Verificar logs NÃO mostram "recording_service.start_session" ✅**Fix Bug #6**
- [ ] **Teste 1.8**: Verificar que botões de projeto não mudam de estado ✅**Fix Bug #6**

## Contexto 2: Projetos Live

- [ ] **Teste 2.1**: Criar projeto, wizard seleciona câmera 1, salvar
- [ ] **Teste 2.2**: Abrir projeto, verificar câmera 1 abre (não 0)
- [ ] **Teste 2.3**: Iniciar gravação de sessão, verificar dados salvos em `projects/.../sessions/`
- [ ] **Teste 2.4**: Verificar que apenas 2 threads daemon estão ativas (não 4)
- [ ] **Teste 2.5**: Múltiplas sessões do mesmo projeto usam câmera correta
- [ ] **Teste 2.6**: Arduino commands funcionam se configurado

#### Regressão

- [ ] **Teste R.1**: Análise de vídeo de arquivo continua funcionando
- [ ] **Teste R.2**: Projetos pre-recorded continuam funcionando
- [ ] **Teste R.3**: Detecção de zonas automática funciona
- [ ] **Teste R.4**: ROI templates carregam corretamente
- [ ] **Teste R.5**: Todos os 2568 testes passam

---

### Testes Automatizados

#### Teste: Intervalos respeitados

**Arquivo:** `tests/integration/test_live_intervals_respected.py`

```python
"""
Integration test: Verify analysis/display intervals are respected.
"""
import pytest
from unittest.mock import MagicMock, patch
from zebtrack.core.main_view_model import MainViewModel

@pytest.mark.integration
def test_single_video_camera_respects_intervals():
    """Test that camera analysis from SingleVideoConfigDialog respects intervals."""
    # Mock config from dialog
    config = {
        "source_type": "camera",
        "camera_index": 0,
        "analysis_interval_frames": 15,
        "display_interval_frames": 20,
        "record_video": True,
    }

    # Mock controller
    with patch("zebtrack.core.main_view_model.LiveCameraService") as mock_service:
        controller = MainViewModel(...)  # Setup mocks

        # Call new method
        controller.start_live_camera_analysis_from_config(config)

        # Verify LiveCameraService.start_session called with correct intervals
        mock_service.return_value.start_session.assert_called_once()
        call_kwargs = mock_service.return_value.start_session.call_args.kwargs

        assert call_kwargs["analysis_interval_frames"] == 15
        assert call_kwargs["display_interval_frames"] == 20
        assert call_kwargs["camera_index"] == 0
```

#### Teste: Projeto Live usa camera_index correto

**Arquivo:** `tests/integration/test_live_project_camera_index.py`

```python
"""
Integration test: Verify Live projects use correct camera_index.
"""
import pytest
from unittest.mock import MagicMock, patch
from zebtrack.ui.gui import GUI

@pytest.mark.integration
@pytest.mark.gui
def test_live_project_opens_correct_camera(tkinter_root, tmp_path):
    """Test that opening Live project uses camera_index from project_data."""
    # Create mock project with camera_index=1
    project_data = {
        "project_type": "live",
        "camera_index": 1,
        "analysis_interval_frames": 10,
    }

    with patch("zebtrack.io.camera.Camera") as MockCamera:
        gui = GUI(...)  # Setup

        # Simulate loading project
        gui.controller.project_manager.project_data = project_data
        gui._finish_project_loading()

        # Verify Camera initialized with modified settings
        assert MockCamera.call_count == 1
        settings_arg = MockCamera.call_args.kwargs["settings_obj"]
        assert settings_arg.camera.index == 1  # ✅ Not 0!
```

---

### Performance Benchmarks

### Executar antes e depois

```bash
# Contar threads ativas
poetry run python -c "
from zebtrack.core.main_view_model import MainViewModel
import threading
controller = MainViewModel(...)
# Abrir projeto Live
print(f'Active threads: {threading.active_count()}')
"

# Medir uso de memória
poetry run python -m memory_profiler scripts/benchmark_live_camera.py

# Verificar latência de captura
poetry run pytest tests/performance/test_live_camera_latency.py -v
```

### Métricas esperadas

- Threads: 4 → 2 (-50%)
- Memória: ~60MB → ~30MB (-50%)
- Latência: 0-5ms → 0-2ms (mais consistente)

---

## 🔄 Rollback Plan

### Se bugs críticos forem encontrados

### Etapa 1: Reverter mudanças da Fase 2

```bash
git revert <commit-fase-2>
# Reativa threads legados, mantém fix de intervalos
```

### Etapa 2: Manter apenas Fase 1 (fixes críticos)

```bash
# Fase 1 é segura, apenas corrige bugs óbvios
# Pode ser mantida independentemente
```

### Etapa 3: Hotfix se necessário

```bash
# Se Fase 1 causar problemas, reverter apenas event_dispatcher.py
git checkout HEAD~1 -- src/zebtrack/ui/components/event_dispatcher.py
```

---

## 📚 Referências

### Arquivos Principais Modificados

| Arquivo | Linhas | Tipo de Mudança |
| --------- | -------- | ----------------- |
| `src/zebtrack/ui/components/event_dispatcher.py` | 509-538 | Modificação |
| `src/zebtrack/core/main_view_model.py` | +novo método | Adição |
| `src/zebtrack/ui/gui.py` | 2822-2840 | Modificação |
| `src/zebtrack/ui/gui.py` | 2856-2916 | Deprecation |
| `src/zebtrack/io/live_stream_source.py` | 60-61 | Correção |
| `src/zebtrack/io/frame_source_factory.py` | 104 | Correção |
| `src/zebtrack/core/live_camera_service.py` | 178-216 | **Refatoração crítica** - Desacoplamento |
| `src/zebtrack/core/live_camera_service.py` | +métodos novos | Adição (timer, recording) |
| `CHANGELOG.md` | - | Adição |
| `docs/LIVE_CAMERA_UNIFICATION.md` | - | Novo arquivo |

### Commits Sugeridos

```bash
# Fase 1
git commit -m "fix(camera): respect analysis/display intervals in single video workflow (Bug #2)"
git commit -m "fix(camera): live projects use camera_index from wizard (Bug #1)"

# Fase 2
git commit -m "refactor(camera): decouple LiveCameraService from RecordingService (Bug #6 - CRITICAL)

BREAKING: LiveCameraService no longer depends on RecordingService for standalone analysis.
This fixes multiple critical bugs:
- Multiple cameras activating simultaneously (LEDs)
- Wrong camera opening (respects camera_index now)
- Preview window delays and display issues
- Unwanted side effects on global state

LiveCameraService now manages its own lightweight recording and session timer."

git commit -m "refactor(camera): migrate live projects to LiveCameraService"
git commit -m "deprecate(gui): mark legacy thread system for removal in v3.0"

# Fase 3
git commit -m "fix(camera): LiveStreamSource honors camera_index parameter (Bug #3)"
git commit -m "fix(camera): FrameSourceFactory honors camera_index parameter (Bug #4)"

# Fase 4
git commit -m "docs: update CHANGELOG and technical documentation"
git commit -m "test: add integration tests for unified camera workflows"
```

### Estimativa de Tempo

| Fase | Tempo Estimado | Risco |
| ------ | ---------------- | ------- |
| Fase 1 | 2-3 horas | Baixo |
| Fase 2 | 4-6 horas | Médio |
| Fase 3 | 1-2 horas | Baixo |
| Fase 4 | 2-3 horas | Baixo |
| **Total**|**9-14 horas** | - |

---

## ✅ Checklist de Implementação

### Antes de Começar

- [ ] Criar branch: `fix/unify-live-camera-flows`
- [ ] Fazer backup do projeto atual
- [ ] Rodar todos os testes: `poetry run pytest -m "" -n0`
- [ ] Verificar que todos passam (baseline)

### Fase 1: Fixes Críticos

- [ ] Modificar `event_dispatcher.py` (passar config completo)
- [ ] Criar `start_live_camera_analysis_from_config()` em `main_view_model.py`
- [ ] Modificar `gui.py` linha 2840 (usar camera_index do project_data)
- [ ] Rodar testes de regressão
- [ ] Testar manualmente Contexto 1 e 2
- [ ] Commit: "fix(camera): critical bugs in camera selection and intervals"

### Fase 2: Migração Arquitetural

- [ ] **2.6 CRÍTICO**: Desacoplar LiveCameraService do RecordingService
  - [ ] Remover chamada a `recording_service.start_session()` (linha 209)
  - [ ] Implementar gravação leve diretamente no LiveCameraService
  - [ ] Adicionar método `_setup_session_timer()`
  - [ ] Modificar `stop_session()` para parar recorder diretamente
  - [ ] Adicionar campo `timer_id` no `__init__()`
  - [ ] Testar que apenas 1 câmera abre (LED único)
  - [ ] Testar que preview funciona imediatamente
  - [ ] Verificar logs não mostram eventos de RecordingService
- [ ] Marcar threads legados como DEPRECATED
- [ ] Criar `start_live_project_session()` em `main_view_model.py`
- [ ] Modificar `LiveCameraService` para aceitar `output_base_dir`
- [ ] Atualizar `_on_grid_cell_clicked()` em `gui.py`
- [ ] Comentar código legado (não remover)
- [ ] Rodar testes de regressão
- [ ] Testar manualmente projetos Live
- [ ] Commit: "refactor(camera): migrate to unified LiveCameraService"

### Fase 3: Fixes Preventivos

- [ ] Modificar `LiveStreamSource.__init__()`
- [ ] Modificar `FrameSourceFactory.create_from_camera()`
- [ ] Rodar testes unitários
- [ ] Commit: "fix(camera): preventive fixes for latent bugs"

### Fase 4: Documentação

- [ ] Atualizar `CHANGELOG.md`
- [ ] Atualizar `CLAUDE.md`
- [ ] Criar `docs/LIVE_CAMERA_UNIFICATION.md`
- [ ] Adicionar testes de integração
- [ ] Commit: "docs: document live camera unification"

### Finalização

- [ ] Rodar suite completa de testes: `poetry run pytest -m "" -n0`
- [ ] Rodar linter: `poetry run ruff check .`
- [ ] Validação manual completa (Checklist acima)
- [ ] Performance benchmarks
- [ ] Push da branch
- [ ] Criar Pull Request
- [ ] Code review
- [ ] Merge após aprovação

---

## 🎉 Resultado Esperado

Após implementação completa:

✅ **Funcionalidade**

- Contexto 1 e 2 usam sistema unificado
- Camera_index sempre respeitado
- Intervalos sempre respeitados
- Preview funciona consistentemente

✅ **Performance**

- 50% menos threads (4 → 2)
- 50% menos memória (buffers duplicados eliminados)
- Latência mais consistente
- Zero overhead de locks

✅ **Código**

- 200 linhas de código legado removido
- Um caminho de código = menos bugs
- Arquitetura MVVM-S consistente
- Fácil manter e estender

✅ **Documentação**

- Changelog atualizado
- Guia técnico completo
- Deprecation warnings claros
- Testes de integração

---

### FIM DO PLANO DE AÇÃO

*Este documento será atualizado conforme a implementação progride.*
