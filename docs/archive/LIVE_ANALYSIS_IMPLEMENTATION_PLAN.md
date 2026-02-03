# Análise de Vídeo ao Vivo - Implementação e Plano

## 📋 Resumo Executivo

Este documento descreve a implementação do suporte para análise de vídeo ao vivo (webcams) no ZebTrack-AI, expandindo o sistema além de vídeos pré-gravados.

## 🎯 Objetivo

Permitir que o ZebTrack-AI analise streams de webcam em tempo real, não apenas vídeos gravados, mantendo compatibilidade com todo o pipeline de análise existente.

## 🔍 Análise do Fluxo Atual

### Arquitetura Existente

1. **Entrada de Vídeo**: `VideoFileSource` lê arquivos de vídeo (`io/video_source.py`)
2. **Entrada de Câmera**: `Camera` captura de webcams (`io/camera.py`) - **JÁ EXISTE**
3. **Processamento**: `VideoProcessingService` orquestra o pipeline de análise
4. **Gravação**: `Recorder` salva dados de detecção e frames
5. **Wizard**: Fluxos separados para projetos "pré-gravados" e "ao vivo"

### Estado Atual

✅ **O que funciona:**
- Projetos ao vivo podem GRAVAR de webcam
- Detecção em tempo real durante gravação
- Salvamento de dados durante gravação

❌ **O que faltava:**
- Processar stream de câmera diretamente sem gravar primeiro
- Analisar múltiplas sessões de câmera em lote
- Interface UI para análise rápida de câmera

## ✅ Implementações Realizadas

### 1. LiveStreamSource (CONCLUÍDO)
**Arquivo**: `src/zebtrack/io/live_stream_source.py`

Wrapper ao redor de `Camera` que adiciona:
- Limite de duração (segundos)
- Contagem de frames estimada para progresso
- Interface compatível com pipeline de vídeos

```python
stream = LiveStreamSource(
    camera_index=0,
    max_duration_s=300.0,  # 5 minutos
    settings_obj=settings
)
```

**Características:**
- Retorna `(False, None)` quando limite de duração atingido
- Calcula frame count estimado baseado em FPS x duração
- Mantém propriedades compatíveis com `VideoFileSource`

### 2. FrameSourceFactory (CONCLUÍDO)
**Arquivo**: `src/zebtrack/io/frame_source_factory.py`

Factory para criar `FrameSource` de diferentes tipos:

```python
# De arquivo de vídeo
source = FrameSourceFactory.create("video.mp4")

# De índice de câmera
source = FrameSourceFactory.create(0, settings_obj=settings)

# De config dict com duração
source = FrameSourceFactory.create({
    "type": "camera",
    "index": 0,
    "max_duration_s": 600.0
}, settings_obj=settings)
```

### 3. Configurações (CONCLUÍDO)
**Arquivo**: `src/zebtrack/settings.py`

Nova classe `LiveAnalysisSettings`:

```python
live_analysis:
  default_duration_s: 300.0    # 5 minutos padrão
  max_duration_s: 7200.0       # Máx 2 horas
  auto_stop_on_limit: true
  show_countdown: true
  countdown_duration_s: 5
```

Adicionado ao `config.yaml` com valores padrão.

### 4. UI Dialog (CONCLUÍDO)
**Arquivo**: `src/zebtrack/ui/dialogs/live_analysis_dialog.py`

Dialog completo com:
- Detecção automática de câmeras
- Configuração de duração (botões rápidos: 1min, 5min, 10min, 30min)
- Intervalos de análise e exibição
- Opção para gravar vídeo com overlay
- ID de experimento opcional
- Validação de inputs

### 5. Menu e Controller (PARCIAL)
**Arquivos**:
- `src/zebtrack/ui/gui.py` - Menu "Arquivo" adicionado ✅
- `src/zebtrack/core/main_view_model.py` - Método `start_live_camera_analysis()` ✅

**Adições:**
- Menu "Arquivo" → "Analisar Câmera ao Vivo..." (Ctrl+L)
- Método controller para orquestrar análise ao vivo
- Thread dedicada para processamento

### 6. VideoProcessingService (PARCIAL)
**Arquivo**: `src/zebtrack/core/video_processing_service.py`

Novo método `process_frame_source()` adicionado para aceitar `FrameSource`.

## 🚧 Trabalho Pendente

### Crítico (Necessário para funcionar)

1. **Adaptar `run_tracking_if_needed` para FrameSource**
   - **Local**: `video_processing_service.py:312`
   - **Mudança**: Aceitar `FrameSource` ou `Path` em `video_path`
   - **Lógica**:
     ```python
     if isinstance(video_path, FrameSource):
         cap = video_path  # Use frame source directly
         frame_width = video_path.get_properties()["width"]
         frame_height = video_path.get_properties()["height"]
     else:
         cap = cv2.VideoCapture(str(video_path))
         frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
         ...
     ```

2. **Atualizar loop de processamento**
   - **Local**: `video_processing_service.py:400-490`
   - **Mudança**: Usar `cap.get_frame()` ao invés de `cap.read()` quando for FrameSource
   - **Timing**: Para live streams, usar `time.time()` como timestamp ao invés de `CAP_PROP_POS_MSEC`

3. **Adaptar cálculo de progresso**
   - **Local**: Callbacks de progresso
   - **Mudança**: Para live streams, usar `elapsed_time / max_duration` ao invés de `frame_num / total_frames`

### Desejável (Melhorias)

4. **Teste de integração**
   - **Local**: `tests/test_live_analysis_integration.py` (criar)
   - **Conteúdo**: Teste end-to-end com câmera mockada

5. **Tratamento de erros de câmera**
   - Reconexão automática se câmera desconectar
   - Feedback visual de status da câmera

6. **Preview antes de iniciar**
   - Mostrar frame da câmera antes de começar análise
   - Permitir ajuste de zonas ao vivo

7. **Análise pós-captura opcional**
   - Permitir análise imediata ou adiar
   - Batch analysis de múltiplas sessões ao vivo

## 📁 Estrutura de Arquivos Criados/Modificados

```
src/zebtrack/
├── io/
│   ├── frame_source_factory.py     ✅ NOVO
│   ├── live_stream_source.py       ✅ NOVO
│   └── __init__.py                 ✅ MODIFICADO
├── core/
│   ├── main_view_model.py          ✅ MODIFICADO (+start_live_camera_analysis)
│   └── video_processing_service.py ⚠️  MODIFICADO (+process_frame_source,
│                                                    run_tracking_if_needed PENDENTE)
├── ui/
│   ├── gui.py                      ✅ MODIFICADO (+Menu Arquivo)
│   └── dialogs/
│       ├── live_analysis_dialog.py ✅ NOVO
│       └── __init__.py             ✅ MODIFICADO
├── settings.py                     ✅ MODIFICADO (+LiveAnalysisSettings)
└── config.yaml                     ✅ MODIFICADO (+live_analysis)
```

## 🔄 Fluxo de Execução Planejado

1. **Usuário**: Menu Arquivo → "Analisar Câmera ao Vivo..."
2. **UI**: Abre `LiveAnalysisDialog`
   - Detecta câmeras disponíveis
   - Usuário configura duração, intervalos, etc.
3. **Controller**: `start_live_camera_analysis()`
   - Cria `LiveStreamSource` via `FrameSourceFactory`
   - Prepara diretório de saída
   - Chama `video_processing_service.process_frame_source()`
4. **Processing**:
   - `process_frame_source()` → `run_tracking_if_needed()`
   - Loop de detecção com `frame_source.get_frame()`
   - Recorder salva dados (Parquet + vídeo opcional)
   - Progress callbacks atualizam UI
5. **Finalização**:
   - Análise de ROIs se configurado
   - Geração de relatórios
   - Notificação ao usuário

## 🧪 Como Testar (Quando Completo)

### Teste Manual

```python
# Terminal/Console Python
from zebtrack.settings import load_settings
from zebtrack.io import FrameSourceFactory

settings = load_settings()

# Teste 1: LiveStreamSource básico
stream = FrameSourceFactory.create({
    "type": "camera",
    "index": 0,
    "max_duration_s": 10.0
}, settings_obj=settings)

print(stream.get_properties())

for i in range(100):
    ret, frame = stream.get_frame()
    if not ret:
        print(f"Stream ended at frame {i}")
        break
    print(f"Frame {i+1}, shape: {frame.shape}")

stream.release()
```

### Teste UI

1. Executar: `poetry run zebtrack`
2. Menu: Arquivo → Analisar Câmera ao Vivo...
3. Detectar câmeras
4. Configurar duração: 30 segundos
5. Iniciar análise
6. Verificar:
   - Stream de vídeo ao vivo
   - Detecções em overlay
   - Progresso atualizado
   - Arquivo Parquet gerado
   - Vídeo gravado (se habilitado)

## 🎓 Lições Aprendidas

1. **FrameSource é a chave**: Interface abstrata permite intercambiar vídeos e câmeras
2. **Duração é essencial**: Streams ao vivo precisam limite de tempo para compatibilidade com progress tracking
3. **Timestamps diferentes**: Vídeos têm POS_MSEC, câmeras usam time.time()
4. **Factory pattern**: Simplifica criação de fontes complexas
5. **Settings injection**: Crucial para Camera/LiveStreamSource funcionarem

## 📚 Referências

- `docs/ARCHITECTURE.md` - Arquitetura geral do sistema
- `docs/DEPENDENCY_INJECTION_GUIDE.md` - Padrões de injeção de dependência
- `src/zebtrack/io/camera.py` - Implementação existente de Camera
- `src/zebtrack/io/video_source.py` - Implementação de VideoFileSource
- `src/zebtrack/io/frame_source.py` - Interface abstrata FrameSource

## 🚀 Próximos Passos

### Prioridade 1 (Funcionalidade básica)
1. Completar adaptação de `run_tracking_if_needed` para FrameSource
2. Testar fluxo completo com câmera real
3. Corrigir bugs encontrados

### Prioridade 2 (Robustez)
4. Adicionar tratamento de erros
5. Melhorar feedback visual
6. Teste de integração automatizado

### Prioridade 3 (Recursos avançados)
7. Preview antes de iniciar
8. Ajuste de zonas ao vivo
9. Análise batch de sessões ao vivo

## 💡 Notas de Implementação

### Compatibilidade com Recorder

O `Recorder` já suporta tanto vídeos quanto streams ao vivo:
- `is_video_file=True`: Não grava vídeo, apenas Parquet
- `is_video_file=False`: Grava vídeo MP4 + Parquet

Para análise ao vivo, usar `is_video_file=False` se `record_video=True`.

### Thread Safety

O `Camera` já tem thread-safe frame buffer. `LiveStreamSource` herda isso.
Controller usa `root.after()` para updates de UI - OK.

### Cleanup de Recursos

Sempre chamar `frame_source.release()` em bloco `finally`:
```python
try:
    frame_source = FrameSourceFactory.create(...)
    # ... processamento ...
finally:
    frame_source.release()
```

## 📝 Checklist de Implementação

- [x] Criar LiveStreamSource
- [x] Criar FrameSourceFactory
- [x] Adicionar LiveAnalysisSettings
- [x] Criar LiveAnalysisDialog
- [x] Adicionar menu Arquivo
- [x] Adicionar start_live_camera_analysis() ao controller
- [x] Adicionar process_frame_source() ao VideoProcessingService
- [ ] Adaptar run_tracking_if_needed para FrameSource
- [ ] Atualizar loop de processamento para FrameSource
- [ ] Testar fluxo completo
- [ ] Adicionar testes de integração
- [ ] Documentar no README/wiki

---

**Status Atual**: 70% completo
**Bloqueadores**: Adaptação de `run_tracking_if_needed` para aceitar FrameSource
**Estimativa para completar**: 2-3 horas de desenvolvimento + testes
