# Service Layer Patterns - ZebTrack-AI

Guia de padrões de delegação para futuras refatorações após FASE 3.

## 📋 Visão Geral

A refatoração FASE 3 estabeleceu um padrão claro de **Service Layer** para separar lógica de processamento de vídeo da coordenação de UI. Este documento descreve os padrões para manter e estender esta arquitetura.

---

## 🎯 Responsabilidades

### **MainViewModel** (Coordenador)
- ✅ Gerenciar estado da aplicação via `StateManager`
- ✅ Coordenar UI via `UICoordinator` e `EventBus`
- ✅ Preparar contexto e injetar dependências
- ✅ Aplicar configurações temporárias (ex: `_temporary_single_animal_mode`)
- ✅ Pós-processar resultados (ex: `refresh_project_views`)
- ❌ NÃO processar vídeos diretamente
- ❌ NÃO ler/gravar arquivos de análise
- ❌ NÃO calcular métricas comportamentais

### **VideoProcessingService** (Worker)
- ✅ Processar vídeos frame-by-frame
- ✅ Executar análise de trajetórias
- ✅ Gerar relatórios (Parquet, Excel, DOCX)
- ✅ Calcular métricas comportamentais
- ✅ Gerenciar pipeline de tracking → analysis → reports
- ❌ NÃO atualizar UI diretamente
- ❌ NÃO modificar `StateManager`
- ❌ NÃO chamar `UICoordinator` ou `EventBus`

---

## 🔄 Padrão de Delegação

### Estrutura Básica

```python
def metodo_coordenador(self, parametros):
    """Coordena a operação delegando ao service.

    MainViewModel: Prepara contexto → Delega → Pós-processa
    """
    # 1. PREPARAÇÃO: Injetar estado atual
    self.service.detector = self.detector
    self.service.recorder = self.recorder
    self.service.cancel_event = self.cancel_event

    # 2. CONTEXTO TEMPORÁRIO (se necessário)
    with self._temporary_single_animal_mode(config):
        # 3. DELEGAÇÃO: Chamar service
        result = self.service.processar_operacao(parametros)

    # 4. PÓS-PROCESSAMENTO: Atualizar UI/views
    if result:
        self.refresh_project_views(reason="operacao_completa")

    return result
```

### Exemplo Real: `_run_tracking_if_needed`

```python
def _run_tracking_if_needed(
    self,
    video_path: Path | str,
    results_dir: str,
    experiment_id: str,
    progress_callback=None,
    calibration_data: dict | None = None,
    analysis_interval_frames: int = 10,
    display_interval_frames: int = 10,
) -> tuple[bool, list | None]:
    """Delegate to VideoProcessingService.run_tracking_if_needed.

    Phase 3: Refactored to delegate to service layer.
    Injects current detector state before delegating.
    """
    # PREPARAÇÃO: Injetar estado
    self.video_processing_service.detector = self.detector

    # DELEGAÇÃO: Processar vídeo
    return self.video_processing_service.run_tracking_if_needed(
        video_path=video_path,
        results_dir=results_dir,
        experiment_id=experiment_id,
        progress_callback=progress_callback,
        calibration_data=calibration_data,
        analysis_interval_frames=analysis_interval_frames,
        display_interval_frames=display_interval_frames,
    )
```

### Exemplo Real: `_process_single_video`

```python
def _process_single_video(
    self,
    *,
    index: int,
    total_videos: int,
    video_info: dict,
    single_video_config: dict | None,
    analysis_interval_frames: int,
    display_interval_frames: int,
    output_base_dir: str,
    experiment_id: str,
    metadata_context: dict | None,
    analysis_profile: dict | None,
) -> tuple[bool, str | None]:
    """Delegate to VideoProcessingService.process_single_video.

    Phase 3: Refactored to delegate to service layer.
    Injects current detector/recorder state before delegating.
    """
    # PREPARAÇÃO: Injetar múltiplas dependências
    self.video_processing_service.detector = self.detector
    self.video_processing_service.recorder = self.recorder
    self.video_processing_service.cancel_event = self.cancel_event

    # CONTEXTO TEMPORÁRIO: Aplicar modo single-animal se configurado
    with self._temporary_single_animal_mode(single_video_config):
        success, results_dir = self.video_processing_service.process_single_video(
            index=index,
            total_videos=total_videos,
            video_info=video_info,
            single_video_config=single_video_config,
            analysis_interval_frames=analysis_interval_frames,
            display_interval_frames=display_interval_frames,
            output_base_dir=output_base_dir,
            experiment_id=experiment_id,
            metadata_context=metadata_context,
            analysis_profile=analysis_profile,
        )

        # PÓS-PROCESSAMENTO: Atualizar views após sucesso
        if success:
            self.refresh_project_views(
                reason="processing_progress",
                append_summary=True,
            )

        return success, results_dir
```

---

## 🛠️ Adicionando Nova Funcionalidade

### Checklist para Novas Features

#### **1. Determinar Camada Apropriada**

- **Service Layer** se:
  - ✅ Processa dados de vídeo/trajetória
  - ✅ Executa cálculos intensivos
  - ✅ Lê/grava arquivos de análise
  - ✅ Pode ser testado sem UI

- **ViewModel** se:
  - ✅ Coordena múltiplos services
  - ✅ Gerencia estado da aplicação
  - ✅ Atualiza UI/views
  - ✅ Requer context managers temporários

#### **2. Implementar no Service**

```python
# video_processing_service.py
def nova_funcionalidade(self, parametros):
    """Executa nova operação de processamento.

    Args:
        parametros: Dados necessários

    Returns:
        Resultado da operação

    Note:
        NÃO atualiza UI diretamente. Use progress_callback para feedback.
    """
    # Validar entrada
    if not self._validar_entrada(parametros):
        log.error("service.nova_funcionalidade.validacao_falhou")
        return None

    # Processar
    try:
        resultado = self._executar_processamento(parametros)
        log.info("service.nova_funcionalidade.sucesso")
        return resultado
    except Exception as e:
        log.error("service.nova_funcionalidade.erro", error=str(e))
        return None
```

#### **3. Adicionar Delegador no ViewModel**

```python
# main_view_model.py
def nova_funcionalidade(self, parametros):
    """Coordena nova funcionalidade delegando ao service.

    Phase X: Implementado seguindo padrão FASE 3.
    """
    # Preparar: Injetar estado
    self.video_processing_service.detector = self.detector

    # Delegar
    resultado = self.video_processing_service.nova_funcionalidade(parametros)

    # Pós-processar: Atualizar UI
    if resultado:
        self.ui_coordinator.set_status(self.view, "Operação concluída")
        self.refresh_project_views(reason="nova_funcionalidade")

    return resultado
```

#### **4. Testar Ambas as Camadas**

```python
# tests/test_video_processing_service.py
def test_nova_funcionalidade_service():
    """Testa service isoladamente (sem UI)."""
    service = VideoProcessingService(...)
    resultado = service.nova_funcionalidade(parametros_teste)
    assert resultado == resultado_esperado

# tests/test_main_view_model.py
def test_nova_funcionalidade_delegacao():
    """Testa delegação e pós-processamento."""
    vm = MainViewModel(...)
    resultado = vm.nova_funcionalidade(parametros_teste)

    # Verificar delegação
    assert vm.video_processing_service.nova_funcionalidade.called

    # Verificar pós-processamento
    assert vm.refresh_project_views.called
```

---

## 🚫 Anti-Patterns (O que NÃO fazer)

### ❌ Service atualizando UI

```python
# ERRADO: Service não deve chamar UI
def processar_video(self):
    resultado = self._processar()
    self.ui_coordinator.set_status(...)  # ❌ NUNCA!
    return resultado
```

```python
# CORRETO: ViewModel coordena UI
def processar_video_vm(self):
    resultado = self.service.processar_video()
    if resultado:
        self.ui_coordinator.set_status(...)  # ✅ ViewModel coordena
    return resultado
```

### ❌ ViewModel processando dados

```python
# ERRADO: ViewModel não deve processar diretamente
def calcular_metricas(self):
    df = pd.read_parquet(...)  # ❌ ViewModel não lê arquivos
    metricas = df.describe()   # ❌ ViewModel não calcula
    return metricas
```

```python
# CORRETO: Service processa, ViewModel delega
def calcular_metricas_vm(self):
    return self.service.calcular_metricas()  # ✅ Delegação simples
```

### ❌ Injeção de dependências esquecida

```python
# ERRADO: Service usa detector None
def processar_video(self):
    return self.service.processar()  # ❌ Faltou injetar self.detector
```

```python
# CORRETO: Sempre injetar estado antes de delegar
def processar_video(self):
    self.service.detector = self.detector  # ✅ Injeção explícita
    return self.service.processar()
```

---

## 📊 Injeção de Dependências

### Dependências Comuns para Injetar

```python
# Sempre injetar antes de chamar service:
self.video_processing_service.detector = self.detector
self.video_processing_service.recorder = self.recorder
self.video_processing_service.cancel_event = self.cancel_event
self.video_processing_service.state_manager = self.state_manager
```

### Por que Injeção Manual?

- ✅ **Transparência**: Explícito onde estado é usado
- ✅ **Testabilidade**: Services podem ser testados com mocks
- ✅ **Flexibilidade**: Estado pode mudar durante contextos temporários
- ❌ Não usar DI automático (ex: `injector`) - adiciona complexidade desnecessária

---

## 🧪 Testes Integração

### Verificar Estrutura de Delegação

```python
# tests/test_overlay_integration.py (exemplo FASE 3)
def test_detector_draw_overlay_called_in_service(self):
    """Verifica que implementação está no service."""
    service_file = Path("src/zebtrack/core/video_processing_service.py")
    content = service_file.read_text(encoding="utf-8")
    assert "self.detector.draw_overlay(frame, detections)" in content

def test_viewmodel_delegates_correctly(self):
    """Verifica que ViewModel delega para service."""
    vm_file = Path("src/zebtrack/core/main_view_model.py")
    content = vm_file.read_text(encoding="utf-8")
    assert "self.video_processing_service.run_tracking_if_needed(" in content
```

---

## 📝 Logging Estruturado

### Padrão de Log Keys

```python
# Service layer: domain.action.result
log.info("service.tracking.start", video=experiment_id)
log.info("service.tracking.success", frames=count)
log.error("service.tracking.failed", error=str(e))

# ViewModel: controller.action.result
log.info("controller.processing.delegating", service="VideoProcessingService")
log.info("controller.processing.complete", videos=total)
```

---

## 🔧 Manutenção

### Quando Refatorar para Service

Refatore lógica para service se:
- ✅ Método tem >100 linhas de processamento
- ✅ Lê/grava arquivos diretamente
- ✅ Executa loops intensivos (ex: frames)
- ✅ Pode ser reutilizado em múltiplos contextos
- ✅ Bloqueia thread por >1 segundo

### Como Refatorar (FASE 3 Pattern)

1. **Copiar método** para service com sufixo (ex: `_ORIGINAL_MOVED_TO_SERVICE`)
2. **Implementar no service** adaptando para não ter dependências UI
3. **Criar delegador** no ViewModel injetando dependências
4. **Testar extensivamente** (mínimo 700+ testes passando)
5. **Validar em produção** (Passo 2)
6. **Remover método original** após validação completa (Passo 3)

---

## 📚 Referências

- **TRANSITION_NOTE.md**: Histórico completo da refatoração FASE 3
- **ARCHITECTURE.md**: Diagrama de camadas e responsabilidades
- **REFERENCE_GUIDE.md**: API completa de services e coordenadores
- **tests/test_overlay_integration.py**: Exemplos de testes estruturais

---

## ✅ Checklist de Implementação

Ao adicionar nova funcionalidade:

- [ ] Implementei no **Service** sem dependências UI
- [ ] Criei **delegador** no ViewModel injetando estado
- [ ] Adicionei **pós-processamento** (ex: `refresh_project_views`)
- [ ] Implementei **testes** para ambas as camadas
- [ ] Usei **logging estruturado** (`domain.action.result`)
- [ ] Documentei **docstrings** mencionando fase de refatoração
- [ ] Validei com **bateria completa de testes** (>700 passing)
- [ ] Atualizei **REFERENCE_GUIDE.md** se API pública mudou

---

**Atualizado**: Passo 4 - FASE 3 Complete
**Commit**: b531581 (Remoção de métodos temporários)
**Status**: ✅ Service Layer Pattern estabelecido e documentado
