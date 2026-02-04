# Análise de Paralelos: Projetos Live vs Análise de Câmera ao Vivo

## 📋 Resumo Executivo

Este documento analisa os **paralelos e diferenças** entre:

- **Projetos Live existentes** (gravação de câmera com projeto estruturado)
- **Análise de Câmera ao Vivo** (nova funcionalidade para análise rápida sem projeto)

## 🔍 Componentes Existentes de Projetos Live

### 1. RecordingService

**Arquivo**: `src/zebtrack/core/recording_service.py`

**Responsabilidades**:

- Orquestrar sessões de gravação
- Coordenar Recorder, StateManager, ProjectManager
- Gerenciar Arduino durante ciclo de gravação
- Agendar gravações com countdown opcional

**Métodos-chave**:

```python
def schedule_recording(context, project_data, trigger_source)
def start_session(context, project_data, trigger_source)
```

**⚠️ Análise**: Minha implementação **NÃO usou** RecordingService. Deveria ter considerado reutilizá-lo.

---

### 2. Loops de Processamento Live (GUI)

**Arquivo**: `src/zebtrack/ui/gui.py`

#### `_live_frame_capture_loop()` (linha 8226)

```python
def _live_frame_capture_loop(self):
    """Loop to capture frames from a LIVE source (camera)."""
    while not self.controller.program_exit_event.is_set():
        ret, frame = self.controller.active_frame_source.get_frame()
        if not ret:
            continue

        # Queue para processamento
        self.controller.frame_queue.put((live_frame_count, frame.copy()))

        # Queue para gravação de vídeo
        if self.controller.is_capturing_for_video:
            self.controller.video_queue.put(frame.copy())
```

**Características**:

- Loop contínuo com queues thread-safe
- Separação entre frames para processamento e gravação
- Controle via `program_exit_event`

#### `_live_processing_loop()` (linha 8254)

```python
def _live_processing_loop(self):
    """Loop to process frames from a LIVE source."""
    while not self.controller.program_exit_event.is_set():
        frame_number, frame = self.controller.frame_queue.get(timeout=1)

        if self.controller.is_processing:
            # Warping de perspectiva se calibração disponível
            calib_data = self.controller.project_manager.project_data.get("calibration")
            if h_matrix and target_dims:
                frame = cv2.warpPerspective(frame, h_matrix, tuple(target_dims))

            # Detecção
            detections, command = self.controller.detector.detect(frame, "live")

            # Arduino
            if command is not None:
                self.controller.arduino.send_command(command)

            # Gravação
            if self.controller.is_recording and detections:
                self.controller.recorder.write_detection_data(...)
```

**⚠️ Análise**: Esses loops **já existem** para projetos Live. Minha implementação criou uma abordagem paralela sem integrá-los.

---

### 3. run_live_calibration()

**Arquivo**: `src/zebtrack/core/main_view_model.py` (linha 2321)

**Fluxo**:

1. Verifica se câmera está disponível
2. Cria vídeo temporário
3. Grava 5 segundos da câmera
4. Executa detecção de aquário no clip
5. Retorna polígono detectado para UI

**Código relevante**:

```python
def run_live_calibration(self, temp_aquarium_method: str | None = None):
    # Grava clip temporário
    temp_video_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    writer = cv2.VideoWriter(temp_video_path, fourcc, fps, (w, h))

    start_time = time.time()
    while time.time() - start_time < 5:  # 5 segundos
        ret, frame = self.view.camera.get_frame()
        if not ret:
            break
        writer.write(frame)
    writer.release()

    # Detecta aquário
    detector = AquariumDetector(model_path=model_path, mode=aquarium_method)
    polygons = detector.detect_aquariums(temp_video_path)
```

**✅ Similaridade**: Este método faz exatamente o que `LiveStreamSource` deveria fazer: capturar por tempo limitado!

---

### 4. Camera Class

**Arquivo**: `src/zebtrack/io/camera.py`

**Recursos**:

- Thread-safe frame buffer
- Reconexão automática
- Monitoramento de lag
- Configuração via settings injetadas

**✅ Reutilização**: Minha `LiveStreamSource` **corretamente reutiliza** Camera.

---

## 🆚 Comparação: Live Projects vs Live Analysis

| Aspecto | Projetos Live Existentes | Análise de Câmera ao Vivo (Nova) |
| --------- | ------------------------- | ----------------------------------- |
| **Propósito** | Gravação estruturada em projetos | Análise rápida sem projeto |
| **Duração** | Controlada por usuário (start/stop) | Limite de tempo pré-definido |
| **Estrutura** | Requer projeto com metadata | Independente de projeto |
| **Loops** | `_live_frame_capture_loop()` + `_live_processing_loop()` | Thread única em background |
| **Queues** | Queues separadas para processamento e gravação | Processamento direto |
| **Arduino** | Integrado via RecordingService | Não suportado (poderia ser) |
| **Calibração** | `run_live_calibration()` integrada | Usa zonas do projeto (se houver) |
| **Output** | Estrutura de pastas do projeto | Pasta `live_analysis_sessions/` |
| **UI** | Integrada no fluxo principal | Dialog separado |

---

## ❌ Problemas Identificados na Minha Implementação

### 1. Não Reutilizei Loops Existentes

**Problema**: Criei `_process_live_stream()` como thread separada ao invés de usar `_live_processing_loop()`.

**Consequência**: Código duplicado, possível divergência de comportamento.

**Correção necessária**: Integrar com loops existentes ou adaptar para usar mesma estrutura de queues.

---

### 2. Não Usei RecordingService

**Problema**: Chamei `recorder.start_recording()` diretamente.

**Consequência**:

- Perde funcionalidades de RecordingService (countdown, timed recording, Arduino)
- Não atualiza StateManager corretamente
- Não segue padrão arquitetural

**Correção necessária**:

```python
# Ao invés de:
recorder.start_recording(...)

# Deveria usar:
self.recording_service.start_session(
    context={...},
    project_data={...},
    trigger_source="live_analysis"
)
```

---

### 3. Método run_live_calibration Já Existe

**Problema**: Não aproveitei que já existe método para capturar clip temporário.

**Oportunidade perdida**: `run_live_calibration()` já faz:

- Captura por tempo limitado ✅
- Salva em arquivo temporário ✅
- Limpa recursos automaticamente ✅

**Minha LiveStreamSource reimplementa isso!**

---

### 4. Não Considerei Integração com Arduino

**Problema**: RecordingService já orquestra Arduino durante gravação.

**Funcionalidade perdida**:

- Sincronização com eventos externos
- Comandos baseados em zonas
- Modo trigger externo

---

### 5. Divergência nos Padrões de Threading

**Problema**: Projetos Live usam queues + event-based loops. Minha implementação usa thread direta.

**Consequência**: Dificuldade de integração futura, código menos testável.

---

## ✅ Acertos da Minha Implementação

### 1. LiveStreamSource é Útil

**Por quê**: Encapsula lógica de duração limitada de forma reutilizável.

**Usos possíveis**:

- `run_live_calibration()` poderia usar ao invés de loop manual
- Qualquer cenário que precise "gravar X segundos da câmera"

---

### 2. FrameSourceFactory Unifica Interfaces

**Por quê**: Permite tratar vídeos e câmeras de forma intercambiável.

**Valor**: Simplifica código que precisa processar ambos os tipos.

---

### 3. LiveAnalysisDialog é Independente

**Por quê**: Não depende de projeto existente, permite uso ad-hoc.

**Valor**: Útil para testes rápidos, demos, troubleshooting.

---

### 4. Settings Bem Estruturadas

**Por quê**: `LiveAnalysisSettings` seguem padrão Pydantic existente.

**Valor**: Consistência com resto do código.

---

## 🔧 Refatoração Recomendada

### Opção 1: Integrar com Fluxo Existente (RECOMENDADO)

```python
def start_live_camera_analysis(self):
    """Inicia análise usando infraestrutura existente de Live Projects."""

    # 1. Configura contexto para RecordingService
    context = {
        "folder_name": experiment_id,
        "output_folder": str(output_dir),
        "camera_width": camera.actual_width,
        "camera_height": camera.actual_height,
    }

    project_data = {
        "use_timed_recording": True,
        "recording_duration_s": duration_s,
        "use_countdown": False,
    }

    # 2. Usa RecordingService (já integrado com loops)
    self.recording_service.start_session(
        context=context,
        project_data=project_data,
        trigger_source="live_analysis"
    )

    # 3. Agenda auto-stop após duração
    def auto_stop():
        self.stop_recording()
        self._run_analysis_if_needed(output_dir, experiment_id)

    self.root.after(int(duration_s * 1000), auto_stop)
```

**Vantagens**:

- Reutiliza código testado
- Mantém consistência arquitetural
- Suporta Arduino automaticamente
- Usa loops thread-safe existentes

---

### Opção 2: Manter Separado mas Adaptar

```python
def start_live_camera_analysis(self):
    """Análise independente mas usando componentes existentes."""

    # Usa LiveStreamSource mas integra com queues
    frame_source = FrameSourceFactory.create(...)

    # Conecta com loops existentes
    self.view.controller.active_frame_source = frame_source
    self.view.controller.is_processing = True
    self.view.controller.is_recording = True

    # Deixa loops existentes processarem
    # (já estão rodando em background)
```

**Vantagens**:

- Código mais simples
- Mantém separação de conceitos
- Ainda aproveita loops testados

---

## 📊 Código Reutilizável vs Código Novo

### Deveria Ter Reutilizado

1. ✅ **Camera** - REUTILIZADO corretamente
2. ❌ **RecordingService** - NÃO usado
3. ❌ **_live_processing_loop()** - NÃO usado
4. ❌ **_live_frame_capture_loop()** - NÃO usado
5. ❌ **run_live_calibration()** lógica - NÃO reutilizada

### Criado Corretamente

1. ✅ **LiveStreamSource** - Útil, mas parcialmente redundante
2. ✅ **FrameSourceFactory** - Boa abstração
3. ✅ **LiveAnalysisDialog** - Interface nova necessária
4. ✅ **LiveAnalysisSettings** - Configuração apropriada

---

## 🧪 Testes

### Testes Criados

1. ✅ `test_live_stream_source.py` - Cobertura completa de LiveStreamSource
2. ✅ `test_frame_source_factory.py` - Cobertura completa de FrameSourceFactory

### Testes Que Deveriam Existir

1. ❌ `test_live_analysis_dialog.py` - Testar UI dialog
2. ❌ `test_live_analysis_integration.py` - Teste end-to-end com camera mockada
3. ❌ Integração com RecordingService

### Testes Existentes Relacionados

- `tests/io/test_camera.py` - Camera já testada ✅
- `tests/core/test_recording_service.py` - RecordingService já testado ✅
- `tests/ui/wizard/test_wizard_live_e2e.py` - Wizard Live já testado ✅

---

## 🎯 Conclusões e Recomendações

### O Que Funcionou

1. ✅ Abstração de FrameSource é boa
2. ✅ LiveStreamSource tem utilidade
3. ✅ Dialog independente permite uso rápido
4. ✅ Testes unitários cobrem novas classes

### O Que Precisa Melhorar

1. ❌ **CRÍTICO**: Integrar com RecordingService
2. ❌ **IMPORTANTE**: Reutilizar loops existentes ou justificar divergência
3. ❌ **MÉDIO**: Adicionar testes de integração
4. ❌ **BAIXO**: Considerar suporte a Arduino

### Ação Recomendada Imediata

**REFATORAR** `start_live_camera_analysis()` para usar:

1. RecordingService.start_session() ao invés de chamar Recorder diretamente
2. Loops de processamento existentes (_live_processing_loop) ao invés de thread própria
3. StateManager para tracking de estado
4. Mesmo padrão de eventos que projetos Live

### Estimativa de Esforço

- **Refatoração completa**: 3-4 horas
- **Testes de integração**: 2 horas
- **Documentação**: 1 hora
- **Total**: ~6-7 horas

---

## 📚 Referências de Código

### Arquivos-Chave para Integração

1. `src/zebtrack/core/recording_service.py` - Serviço a ser usado
2. `src/zebtrack/ui/gui.py:8226` - Loops de processamento
3. `src/zebtrack/core/main_view_model.py:2321` - run_live_calibration()
4. `src/zebtrack/core/main_view_model.py:2421` - start_recording()
5. `src/zebtrack/core/main_view_model.py:2709` - stop_recording()

### Testes Existentes para Referência

1. `tests/core/test_recording_service.py` - Como testar RecordingService
2. `tests/ui/wizard/test_wizard_live_e2e.py` - Fluxo completo Live
3. `tests/io/test_camera.py` - Como mockar Camera

---

## 💬 Perguntas para Decisão de Arquitetura

1. **LiveAnalysisDialog deve criar projeto temporário ou permanecer independente?**
   - Independente = mais simples, menos recursos
   - Com projeto = reutiliza toda infraestrutura

2. **Suporte a Arduino é necessário em análise rápida?**
   - Se sim: usar RecordingService obrigatoriamente
   - Se não: pode manter simplificado

3. **LiveStreamSource deve substituir lógica em run_live_calibration()?**
   - Oportunidade de consolidar código
   - Requer refatoração cuidadosa

4. **Análise de câmera deve aparecer na árvore de projeto?**
   - Se sim: precisa integração com ProjectManager
   - Se não: manter como "análise avulsa"

---

---

## ✅ REFATORAÇÃO COMPLETADA (Nov 1, 2025)

### Mudanças Implementadas

#### 1. `start_live_camera_analysis()` Refatorado

**Antes** (Abordagem Isolada):

```python
# Criava LiveStreamSource
frame_source = FrameSourceFactory.create(...)

# Thread própria para processamento
def _process_live_stream():
    self.video_processing_service.process_frame_source(...)
threading.Thread(target=_process_live_stream).start()
```

**Depois** (Integrado com RecordingService):

```python
# Usa camera diretamente
self.active_frame_source = self.view.camera
self.is_processing = True

# Contexto para RecordingService (mimics live project)
context = {
    "day": 1,
    "group": "live_analysis",
    "cobaia": experiment_id,
    "folder_name": folder_name,
    "output_folder": str(output_dir),
    "camera_width": camera_width,
    "camera_height": camera_height,
    "arduino_enabled": False,
}

project_data = {
    "use_timed_recording": True,
    "recording_duration_s": duration_s,
    "use_countdown": False,
    "use_arduino": False,
}

# Usa RecordingService para orquestração
self.recording_service.start_session(
    context=context,
    project_data=project_data,
    trigger_source="live_analysis",
)

# Loops existentes (_live_frame_capture_loop, _live_processing_loop)
# processam automaticamente via self.active_frame_source
```

**Benefícios Obtidos**:

1. ✅ Reutiliza `RecordingService` para coordenação
2. ✅ Usa loops existentes `_live_frame_capture_loop()` e `_live_processing_loop()`
3. ✅ Auto-stop via `use_timed_recording` (já testado em projetos Live)
4. ✅ Consistência arquitetural com resto do código
5. ✅ StateManager atualizado automaticamente
6. ✅ Logs estruturados via RecordingService

---

#### 2. Testes de Integração Criados

**Arquivo**: `tests/integration/test_live_camera_analysis_integration.py`

**Cobertura** (8 testes, todos passando ✅):

1. `test_live_camera_analysis_uses_recording_service` - Verifica uso de RecordingService
2. `test_live_camera_analysis_sets_active_frame_source` - Verifica `active_frame_source = camera`
3. `test_live_camera_analysis_enables_timed_recording` - Verifica timed recording habilitado
4. `test_live_camera_analysis_creates_output_directory` - Verifica estrutura de output
5. `test_live_camera_analysis_dialog_cancelled` - Verifica cancelamento
6. `test_live_camera_analysis_camera_unavailable` - Verifica erro de câmera
7. `test_live_camera_analysis_detector_setup_fails` - Verifica erro de detector
8. `test_live_camera_analysis_no_arduino` - Verifica Arduino desabilitado

**Resultados**:

```text
========================= 8 passed, 4 warnings in 9.78s ===================
```

---

### Arquitetura Final: Live Analysis vs Live Projects

| Componente | Live Projects | Live Analysis (Refatorado) |
| ------------ | --------------- | ---------------------------- |
| **RecordingService** | ✅ Usado | ✅ **Usado** (refatorado) |
| **Loops de Processamento** | ✅ `_live_processing_loop()` | ✅ **Reutilizados** |
| **Frame Capture Loop** | ✅ `_live_frame_capture_loop()` | ✅ **Reutilizados** |
| **active_frame_source** | `self.view.camera` | `self.view.camera` (compatível) |
| **Timed Recording** | ✅ Via RecordingService | ✅ Via RecordingService |
| **Arduino** | ✅ Integrado | ❌ Desabilitado (contexto=False) |
| **StateManager** | ✅ Atualizado | ✅ Atualizado (via RecordingService) |
| **Estrutura de Projeto** | Requer projeto | Simula projeto (day=1, group="live_analysis") |

---

### LiveStreamSource: Status Atual

**Decisão Arquitetural**: LiveStreamSource foi **mantido mas não usado** no fluxo principal.

**Por quê?**

- Fluxo refatorado usa `self.view.camera` diretamente
- Loops existentes já esperam objeto `Camera`
- RecordingService já gerencia timed recording

**Utilidade Futura**:

1. Pode ser usado em `run_live_calibration()` para consolidar lógica de duração
2. Útil se futuras features precisarem de duração limitada + FrameSource interface
3. Serve como wrapper se precisar trocar Camera por outra implementação

**Recomendação**: Manter no código (já tem testes) mas documentar que é opcional.

---

### Código Consolidado vs Código Removível

#### Manter

1. ✅ `LiveStreamSource` - Útil, testado, pode ser usado futuramente
2. ✅ `FrameSourceFactory` - Abstração válida para vídeos vs câmeras
3. ✅ `LiveAnalysisDialog` - UI necessária
4. ✅ `LiveAnalysisSettings` - Configuração necessária
5. ✅ Testes de `test_live_stream_source.py` e `test_frame_source_factory.py`

#### Remover

1. ❌ `process_frame_source()` em VideoProcessingService - **NÃO usado no fluxo refatorado**
2. ❌ Thread separada `_process_live_stream()` - **Substituída por loops existentes**

---

### Lições Aprendidas

1. **SEMPRE investigar código existente ANTES de implementar**
   - RecordingService já existia e fazia 90% do necessário
   - Loops de processamento já estavam implementados e testados

2. **Reutilizar infraestrutura arquitetural > Criar código novo**
   - Código novo = mais testes, mais manutenção, mais bugs
   - Código existente = já testado, já integrado, já compreendido

3. **Abstrações são úteis mas não sempre necessárias**
   - LiveStreamSource é uma boa abstração...
   - ...mas o fluxo existente não precisava dela

4. **Testes de integração revelam decisões arquiteturais erradas**
   - Criar testes forçou análise de como componentes interagem
   - Mock de RecordingService revelou que deveria ser usado, não mockado

5. **Consistência arquitetural > Código "mais limpo" isolado**
   - Melhor seguir padrão existente (mesmo que imperfeito)
   - Do que criar abordagem "ideal" mas divergente

---

### Esforço Real vs Estimado

| Tarefa | Estimado | Real | Razão da Diferença |
| -------- | ---------- | ------ | -------------------- |
| Refatoração `start_live_camera_analysis()` | 3-4h | 2h | Código mais simples que esperado |
| Testes de integração | 2h | 1.5h | Reutilizou fixtures existentes |
| Documentação | 1h | 0.5h | Decisões ficaram claras rápido |
| **Total** | **6-7h** | **4h** | **Investigação prévia ajudou** |

---

### Próximos Passos (Opcional)

1. **Considerar**: Refatorar `run_live_calibration()` para usar `LiveStreamSource`
   - Consolidaria lógica de "gravar X segundos da câmera"
   - Atualmente reimplementa controle de duração

2. **Considerar**: Adicionar suporte opcional a Arduino em live analysis
   - Requer checkbox no `LiveAnalysisDialog`
   - Contexto já suporta (`arduino_enabled=False` → `True`)

3. **Manter**: `VideoProcessingService.process_frame_source()` para análise offline futura
   - Pode ser útil se precisar processar vídeos já gravados como "streams"
   - Não remover, apenas documentar uso

---

**Data**: Novembro 1, 2025
**Status**: ✅ Refatoração completa, 8 testes passando, integrado com RecordingService
