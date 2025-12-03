# Tratamento de Erros - ZebTrack-AI

Este documento descreve as estratégias e mecanismos de tratamento de erros implementados no ZebTrack-AI, garantindo robustez, rastreabilidade e recuperação adequada em caso de falhas.

## Visão Geral

O sistema de tratamento de erros do ZebTrack-AI é estruturado em três níveis:

1. **Erros Fatais**: Falhas críticas que impedem a continuação do processamento
2. **Erros Recuperáveis**: Falhas isoladas que permitem continuar o processamento de outros vídeos
3. **Erros de Validação**: Problemas de configuração ou dados detectados antes do processamento

## Arquitetura de Callbacks

### ProcessingCallbacks

O sistema utiliza callbacks especializados para comunicar erros do worker thread para a UI thread de forma thread-safe:

```python
@dataclass
class ProcessingCallbacks:
    on_error: Callable[[Exception, str], None] | None = None
    """
    Callback para erros recuperáveis.
    Args:
        error: A exceção que ocorreu
        context: Contexto legível sobre o que estava sendo executado
    """

    on_fatal_error: Callable[[Exception, str, dict], None] | None = None
    """
    Callback para erros fatais que impedem continuação.
    Args:
        error: A exceção
        context: Contexto legível
        recovery_info: Dict com informações para potencial recuperação:
            - can_retry: bool - Se o erro é potencialmente recuperável
            - affected_videos: list - Vídeos afetados pelo erro
            - state_snapshot: dict - Estado do processamento no momento do erro
    """
```

**Localização**: `src/zebtrack/core/processing_worker.py:28-90`

### Estrutura recovery_info

Quando um erro fatal ocorre, o callback `on_fatal_error` recebe um dicionário `recovery_info`:

```python
recovery_info = {
    "can_retry": False,  # Indica se retry automático é viável
    "affected_videos": [
        "/path/to/video1.mp4",
        "/path/to/video2.mp4"
    ],
    "state_snapshot": {
        "total_videos": 10,
        "analysis_interval_frames": 10,
        "display_interval_frames": 10,
        "single_video_mode": False,
        "output_base_dir": "/path/to/output"
    }
}
```

Este snapshot permite:
- Exibir informações detalhadas ao usuário
- Registrar estado completo para debugging
- Implementar lógica de recuperação parcial em versões futuras

**Localização**: `src/zebtrack/core/processing_worker.py:302-315`

## Estratégias de Recuperação

### Retry Strategy (ProcessingContext)

O worker suporta duas estratégias para lidar com erros em processamento em lote:

```python
@dataclass
class ProcessingContext:
    retry_strategy: str = "continue"  # "continue" | "stop"
```

#### 1. Strategy: "continue" (Padrão)

- **Comportamento**: Continua processando vídeos subsequentes após erro
- **Uso**: Processamento em lote onde alguns vídeos podem estar corrompidos
- **Rastreamento**: Erros são registrados em `context.failed_videos`
- **Logging**: `worker.processing.video_error` (nível ERROR)

```python
# Exemplo de registro de falha
self.context.failed_videos.append({
    "index": 2,
    "path": "/path/to/video.mp4",
    "error": "Invalid video codec",
    "experiment_id": "subject_003_day_02"
})
```

**Localização**: `src/zebtrack/core/processing_worker.py:272-297`

#### 2. Strategy: "stop"

- **Comportamento**: Interrompe todo o lote ao primeiro erro
- **Uso**: Validação de integridade ou processamento crítico
- **Logging**: `worker.processing.stop_on_error`

**Localização**: `src/zebtrack/core/processing_worker.py:294-296`

### Fluxo de Erro em Lote

```
[Vídeo 1] ✅ Sucesso
    ↓
[Vídeo 2] ❌ Erro → on_error() chamado
    ↓
retry_strategy == "continue"?
    ├─ Sim → Registra em failed_videos, continua para Vídeo 3
    └─ Não → Interrompe processamento
```

## Exceções Customizadas

### IntegrityError

**Propósito**: Indicar falhas de integridade de arquivos (checksum, corrupção)

**Localização**: `src/zebtrack/utils.py:24-27`

```python
class IntegrityError(Exception):
    """Custom exception for file integrity errors."""
    pass
```

**Uso**:
```python
from zebtrack.utils import IntegrityError

def validate_video_file(path: Path):
    if not is_valid_codec(path):
        raise IntegrityError(f"Invalid codec in {path}")
```

### SerialError (Arduino)

**Propósito**: Erros de comunicação serial com Arduino

**Localização**: `src/zebtrack/io/arduino_manager.py:15`

```python
class SerialError(Exception):
    """Serial communication error"""
    pass
```

**Tratamento**: O sistema continua operando mesmo se Arduino falhar (degradação graciosa)

## Logging Estruturado de Erros

### Convenção de Domínio

O ZebTrack-AI usa `structlog` com a convenção `domínio.ação.resultado`:

```python
import structlog
log = structlog.get_logger()

# Erro recuperável em vídeo individual
log.error(
    "worker.processing.video_error",
    experiment_id="subject_001_day_01",
    error=str(exc),
    exc_info=True
)

# Erro fatal no worker
log.error(
    "worker.processing.fatal_error",
    error=str(exc),
    exc_info=True
)

# Erro de integridade em arquivo
log.error(
    "file.integrity.validation_failed",
    filepath=str(path),
    expected_sha256=expected,
    actual_sha256=actual
)

# Erro de Arduino (não-fatal)
log.warning(
    "arduino.serial.connection_lost",
    port=port,
    error=str(exc)
)
```

### Níveis de Severidade

| Nível | Uso | Exemplo |
|-------|-----|---------|
| `ERROR` | Erros que causam falha de operação | Vídeo corrompido, detector falhou |
| `WARNING` | Problemas que não impedem continuação | Arduino desconectado, cache miss |
| `INFO` | Eventos normais mas significativos | Worker iniciado, vídeo concluído |
| `DEBUG` | Detalhes para debugging | Garbage collection, frame skipping |

**Configuração**: `src/zebtrack/__main__.py:15-50`

## Fluxo de Erros em Runtime

### 1. Erro Fatal (Interrompe Tudo)

```
[ProcessingWorker.run()]
    ↓
Exception capturada no bloco try externo (linha 301)
    ↓
Constrói recovery_info com snapshot de estado
    ↓
Chama callbacks.on_fatal_error(exc, context, recovery_info)
    ↓
MainViewModel recebe callback via root.after()
    ↓
UI exibe messagebox com detalhes e opções
    ↓
Logging: "worker.processing.fatal_error"
```

**Localização**: `src/zebtrack/core/processing_worker.py:301-317`

### 2. Erro Recuperável (Continua)

```
[Loop de processamento de vídeos]
    ↓
Exception em process_single_video_func (linha 272)
    ↓
Chama callbacks.on_error(exc, context)
    ↓
Registra em context.failed_videos
    ↓
Verifica retry_strategy:
    ├─ "continue" → Próximo vídeo
    └─ "stop" → Break do loop
    ↓
Logging: "worker.processing.video_error"
```

**Localização**: `src/zebtrack/core/processing_worker.py:272-298`

### 3. Erro de Validação (Pré-processamento)

```
[MainViewModel.validate_project_config()]
    ↓
Detecta configuração inválida
    ↓
Lança ValueError ou ConfigError
    ↓
Capturado em bind do EventBus
    ↓
UI exibe erro antes de iniciar worker
    ↓
Logging: "config.validation.failed"
```

## Thread Safety

### Regras Críticas

1. **Callbacks são chamados do worker thread**:
   ```python
   # ❌ ERRADO - atualiza UI diretamente
   def on_error(exc, context):
       self.status_label.configure(text=f"Erro: {context}")

   # ✅ CORRETO - agenda no main thread
   def on_error(exc, context):
       self.root.after(0, self._update_error_ui, exc, context)
   ```

2. **StateManager é thread-safe**: Pode ser atualizado de qualquer thread
   ```python
   # OK de qualquer thread
   state_manager.set("processing.status", "error")
   ```

3. **Logging é thread-safe**: `structlog` é configurado para multi-threading
   ```python
   # OK de qualquer thread
   log.error("worker.error", thread=threading.current_thread().name)
   ```

**Referência**: `src/zebtrack/core/main_view_model.py` (handlers de callbacks)

## Práticas Recomendadas

### Para Desenvolvedores

1. **Sempre use callbacks apropriados**:
   - `on_error`: Para falhas isoladas e recuperáveis
   - `on_fatal_error`: Para falhas que impedem continuação

2. **Inclua contexto rico em exceções**:
   ```python
   raise IntegrityError(
       f"SHA256 mismatch for {path.name}: "
       f"expected {expected}, got {actual}"
   )
   ```

3. **Registre estado antes de propagar**:
   ```python
   try:
       process_video(path)
   except Exception as exc:
       log.error(
           "processing.video.failed",
           video=str(path),
           frame_count=frame_count,
           error=str(exc),
           exc_info=True
       )
       raise  # Re-raise para worker capturar
   ```

4. **Use `exc_info=True` para stack traces**:
   ```python
   log.error("fatal.error", exc_info=True)  # Inclui traceback completo
   ```

### Para Usuários (UI)

- **Erros Recuperáveis**: Exibidos na barra de status, permitem continuar
- **Erros Fatais**: Diálogo modal com detalhes e botão "Ver Log"
- **Validação**: Feedback inline antes de iniciar processamento

## Sumário de Callbacks Esperados

| Callback | Thread | Quando Chamado | Ação Típica da UI |
|----------|--------|----------------|-------------------|
| `on_error` | Worker | Erro em vídeo individual | Atualizar status_label, continuar |
| `on_fatal_error` | Worker | Erro que impede continuação | Exibir messagebox, parar processamento |
| `on_completed` | Worker | Sempre ao final | Exibir resumo com failed_list |

## Debugging de Erros

### Logs

- **Console**: Saída imediata durante desenvolvimento
- **Arquivo**: `analysis.log` (rotação a cada 5 MB, 5 backups)
- **Formato**: JSON estruturado com timestamp e contexto

```json
{
  "event": "worker.processing.video_error",
  "level": "error",
  "timestamp": "14:35:22",
  "experiment_id": "subject_001_day_01",
  "error": "Invalid frame dimensions",
  "thread": "ProcessingWorker"
}
```

### Rastreamento de Falhas em Lote

Ao final do processamento, o callback `on_completed` recebe um `summary`:

```python
summary = {
    "total_videos": 10,
    "successful": 7,
    "failed": 2,
    "skipped": 1,
    "failed_list": [
        {
            "index": 3,
            "path": "/path/to/video3.mp4",
            "error": "Codec not supported",
            "experiment_id": "subject_003_day_01"
        },
        {
            "index": 7,
            "path": "/path/to/video7.mp4",
            "error": "File corrupted",
            "experiment_id": "subject_007_day_01"
        }
    ]
}
```

Este resumo permite gerar relatórios de falhas e reprocessar apenas vídeos problemáticos.

## Arquivos Relacionados

- `src/zebtrack/core/processing_worker.py` - Implementação principal de callbacks e retry
- `src/zebtrack/core/main_view_model.py` - Handlers de callbacks no controller
- `src/zebtrack/utils.py` - Exceções customizadas (`IntegrityError`)
- `src/zebtrack/io/arduino_manager.py` - Exceção `SerialError`
- `src/zebtrack/__main__.py` - Configuração de logging
- `tests/test_processing_worker.py` - Testes de cenários de erro

## Próximos Passos

- [ ] Implementar retry automático para erros de I/O transitórios
- [ ] Adicionar telemetria de erros para análise de padrões
- [ ] Criar UI para reprocessar apenas vídeos de `failed_list`
- [ ] Suportar `can_retry: True` em recovery_info para erros parcialmente recuperáveis
