# ZebTrack-AI: Relatório Completo de Parâmetros de Detecção e Rastreamento

> **Gerado em**: Dezembro 2025  
> **Última Atualização**: Dezembro 2025  
> **Versão**: 4.0+  
> **Autor**: GitHub Copilot (Claude Opus 4.5)

Este documento apresenta uma análise completa de todos os parâmetros que afetam a detecção, rastreamento e estabilidade de IDs de animais no ZebTrack-AI.

---

## 📋 Índice

1. [Resumo Executivo](#1-resumo-executivo)
2. [Parâmetros YOLO (Detecção)](#2-parâmetros-yolo-detecção)
3. [Parâmetros ByteTrack (Rastreamento)](#3-parâmetros-bytetrack-rastreamento)
4. [Parâmetros Kalman Filter (Predição de Movimento)](#4-parâmetros-kalman-filter-predição-de-movimento)
5. [Parâmetros de Processamento de Vídeo](#5-parâmetros-de-processamento-de-vídeo)
6. [Hybrid Matching (Matching Híbrido)](#6-hybrid-matching-matching-híbrido)
7. [Fluxo de Dados e Dependências](#7-fluxo-de-dados-e-dependências)
8. [Configuração via config.yaml](#8-configuração-via-configyaml)
9. [Exposição na UI](#9-exposição-na-ui)
10. [Problemas Conhecidos e Correções Aplicadas](#10-problemas-conhecidos-e-correções-aplicadas)
11. [Recomendações de Configuração](#11-recomendações-de-configuração)

---

## 1. Resumo Executivo

### Pipeline de Rastreamento

```
Frame de Vídeo
     │
     ▼
┌─────────────────────────────────────────────────────────────────────┐
│ YOLO Model (Detecção)                                               │
│  • confidence_threshold: 0.05                                       │
│  • nms_threshold: 0.50                                              │
└─────────────────────────────────────────────────────────────────────┘
     │
     ▼ Lista de detecções (x1, y1, x2, y2, conf, class_id)
     │
┌─────────────────────────────────────────────────────────────────────┐
│ ByteTrack Tracker (Associação)                                      │
│  • track_threshold: 0.25                                            │
│  • match_threshold: 0.90 ⚠️ CORRIGIDO                               │
│  • max_center_distance: 300.0px                                     │
│  • track_buffer: 90 frames                                          │
│  • iou_threshold: 0.05 (para hybrid matching)                       │
└─────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Kalman Filter (Predição)                                            │
│  • dt = analysis_interval_frames (da UI) ⚠️ CORRIGIDO               │
│  • std_weight_position = (1/20) * sqrt(dt)                          │
│  • std_weight_velocity = (1/160) * sqrt(dt) * 2                     │
└─────────────────────────────────────────────────────────────────────┘
     │
     ▼ Lista de tracks (x1, y1, x2, y2, conf, track_id, class_id)
```

### Valores Otimizados Atuais (config.yaml)

| Parâmetro | Valor | Descrição |
|-----------|-------|-----------|
| `track_threshold` | 0.25 | Confiança mínima para manter track |
| `match_threshold` | 0.90 | Threshold de associação (mais alto = mais permissivo) |
| `max_center_distance` | 300.0 | Pixels máx para fallback de centro |
| `track_buffer` | 90 | Frames para manter tracks perdidos |
| `iou_threshold` | 0.05 | IoU mínimo antes de usar fallback de centro |

---

## 2. Parâmetros YOLO (Detecção)

### 2.1 confidence_threshold

| Atributo | Valor |
|----------|-------|
| **Localização** | `config.yaml` → `yolo_model.confidence_threshold` |
| **Arquivo Pydantic** | `settings.py` → `YoloModelSettings.confidence_threshold` |
| **Valor Default** | `0.05` |
| **Range Válido** | `(0.0, 1.0)` exclusivo |
| **Exposto na UI** | ❌ Não |

**Descrição**: Confiança mínima para uma detecção ser considerada válida. Valores baixos (0.05) detectam mais objetos mas podem gerar falsos positivos.

**Uso no Código**:
```python
# src/zebtrack/plugins/ultralytics_detector.py:44
self.conf_threshold = settings_obj.yolo_model.confidence_threshold
```

---

### 2.2 nms_threshold

| Atributo | Valor |
|----------|-------|
| **Localização** | `config.yaml` → `yolo_model.nms_threshold` |
| **Arquivo Pydantic** | `settings.py` → `YoloModelSettings.nms_threshold` |
| **Valor Default** | `0.50` |
| **Range Válido** | `(0.0, 1.0)` exclusivo |
| **Exposto na UI** | ❌ Não |

**Descrição**: Non-Maximum Suppression threshold. Filtra bboxes sobrepostos. Valores maiores permitem mais sobreposição.

**Uso no Código**:
```python
# src/zebtrack/plugins/ultralytics_detector.py:45
self.nms_threshold = settings_obj.yolo_model.nms_threshold
```

---

## 3. Parâmetros ByteTrack (Rastreamento)

### 3.1 track_threshold

| Atributo | Valor |
|----------|-------|
| **Localização** | `config.yaml` → `bytetrack.track_threshold` |
| **Arquivo Pydantic** | `settings.py` → `ByteTrackSettings.track_threshold` |
| **Valor Default** | `0.25` |
| **Range Válido** | `(0.0, 1.0)` exclusivo |
| **Exposto na UI** | ❌ Não |

**Descrição**: Confiança mínima para manter uma detecção associada a um track existente. Usado pelo ByteTrack na etapa de matching.

**Uso no Código**:
```python
# src/zebtrack/tracker/byte_tracker.py:196
self.det_thresh = args.track_thresh + 0.1

# src/zebtrack/tracker/byte_tracker.py:233
remain_inds = scores > self.args.track_thresh
```

**Fluxo**:
- Detecções com `score > track_threshold` são consideradas de alta confiança (first pass)
- Detecções com `0.1 < score < track_threshold` são usadas no second pass

---

### 3.2 match_threshold ⚠️ CORRIGIDO

| Atributo | Valor |
|----------|-------|
| **Localização** | `config.yaml` → `bytetrack.match_threshold` |
| **Arquivo Pydantic** | `settings.py` → `ByteTrackSettings.match_threshold` |
| **Valor Default** | `0.80` ⚠️ (era 0.15 antes da correção) |
| **Range Válido** | `(0.0, 1.0)` exclusivo |
| **Exposto na UI** | ❌ Não |

**Descrição**: Threshold para associar detecções não-matcheadas a tracks existentes na segunda passagem do ByteTrack.

> ⚠️ **IMPORTANTE**: Valores MAIORES são MAIS PERMISSIVOS (permitem maior distância/menor IoU).
> Para processamento esparso (a cada N frames), use valores altos (0.7-0.9).

**Problema Identificado e Corrigido**:
```python
# ANTES (hardcoded incorretamente):
# src/zebtrack/plugins/ultralytics_detector.py:50
self.match_threshold = 0.15  # ❌ Ignorava config.yaml!

# DEPOIS (correção aplicada):
self.match_threshold = getattr(settings_obj.bytetrack, "match_threshold", 0.80)  # ✅
```

**Uso no Código**:
```python
# src/zebtrack/tracker/byte_tracker.py (linhas 250, 280, 320)
matches, u_track, u_detection = matching.linear_assignment(
    dists, thresh=self.args.match_thresh
)
```

---

### 3.3 max_center_distance

| Atributo | Valor |
|----------|-------|
| **Localização** | `config.yaml` → `bytetrack.max_center_distance` |
| **Arquivo Pydantic** | `settings.py` → `ByteTrackSettings.max_center_distance` |
| **Valor Default** | `200.0` pixels |
| **Range Válido** | `> 0` |
| **Exposto na UI** | ❌ Não |

**Descrição**: Distância máxima centro-a-centro (em pixels) para matching por fallback de distância quando IoU falha. Essencial para objetos pequenos e rápidos como zebrafish.

**Cálculo de Referência**:
- Zebrafish típico: ~30x30 pixels
- 200px permite matching de movimentos de ~6-7 comprimentos corporais
- Com `processing_interval=10` a 30fps, isso permite ~20cm/s de velocidade real

**Uso no Código**:
```python
# src/zebtrack/tracker/byte_tracker.py:202
self.max_center_distance = max_center_distance

# src/zebtrack/tracker/matching.py:235
def center_distance(atracks, btracks, max_distance: float = 200.0):
    cost_matrix = distances / max_distance
    cost_matrix[distances > max_distance] = 1e6
```

---

### 3.4 track_buffer ⚠️ ATUALIZADO

| Atributo | Valor |
|----------|-------|
| **Localização** | `config.yaml` → `bytetrack.track_buffer` |
| **Arquivo Pydantic** | `settings.py` → `ByteTrackSettings.track_buffer` |
| **Valor Default** | `90` frames |
| **Range Válido** | `10-1000` |
| **Exposto na UI** | ❌ Não |

**Descrição**: Número de frames que um track "perdido" é mantido antes de ser removido. Escalado automaticamente pelo `processing_interval`.

**Cálculo no Código**:

```python
# src/zebtrack/tracker/byte_tracker.py:197-198
self.buffer_size = int(frame_rate / 30.0 * args.track_buffer * processing_interval)
self.max_time_lost = self.buffer_size
```

**Exemplo**:

- `frame_rate=30`, `track_buffer=90`, `processing_interval=10`
- `buffer_size = (30/30) * 90 * 10 = 900` frames reais (~30 segundos)

---

### 3.5 iou_threshold ⚠️ NOVO

| Atributo | Valor |
|----------|-------|
| **Localização** | `config.yaml` → `bytetrack.iou_threshold` |
| **Arquivo Pydantic** | `settings.py` → `ByteTrackSettings.iou_threshold` |
| **Valor Default** | `0.05` |
| **Range Válido** | `(0.0, 1.0)` exclusivo |
| **Exposto na UI** | ❌ Não |

**Descrição**: Threshold de IoU abaixo do qual o matching híbrido usa distância de centro em vez de IoU. Essencial para objetos pequenos como zebrafish onde overlap é mínimo.

**Por que é importante**:

- Zebrafish de ~30x30 pixels movendo-se entre frames têm overlap mínimo
- IoU de 0.05 significa apenas 5% de sobreposição
- Valores baixos (0.03-0.10) funcionam melhor para objetos pequenos e rápidos

**Uso no Código**:

```python
# src/zebtrack/tracker/byte_tracker.py
self.iou_threshold = iou_threshold

# Usado em hybrid_iou_center_distance():
iou_cost = matching.iou_distance(tracks, detections)
center_cost = matching.center_distance(tracks, detections, self.max_center_distance)

# Se IoU < threshold, usa centro:
use_center = (1 - iou_cost) < self.iou_threshold
cost_matrix = np.where(use_center, center_cost, iou_cost)
```

---

## 4. Parâmetros Kalman Filter (Predição de Movimento)

### 4.1 dt (Time Delta) ⚠️ CORRIGIDO

| Atributo | Valor |
|----------|-------|
| **Localização** | Calculado automaticamente |
| **Fonte** | `analysis_interval_frames` (da UI) → sincronizado para `processing_interval` |
| **Valor Típico** | `5-10` (configurável na UI) |
| **Exposto na UI** | ✅ Sim (indiretamente via "Intervalo de Análise") |

**Descrição**: Intervalo de tempo entre frames processados. Usado para modelar a matriz de movimento do Kalman Filter.

**Correção Aplicada**: Agora o valor da UI é sincronizado para o detector via `_initialize_detector()` no worker.

**Uso no Código**:

```python
# src/zebtrack/tracker/byte_tracker.py:200
self.kalman_filter = KalmanFilter(dt=float(processing_interval))

# src/zebtrack/tracker/kalman_filter.py:51-52
self._motion_mat = np.eye(2 * ndim, 2 * ndim)
for i in range(ndim):
    self._motion_mat[i, ndim + i] = dt  # x_new = x + v * dt
```

---

### 4.2 std_weight_position

| Atributo | Valor |
|----------|-------|
| **Fórmula** | `(1/20) * sqrt(dt)` |
| **Com dt=10** | `0.05 * 3.16 ≈ 0.158` |
| **Base ByteTrack** | `1/20 = 0.05` |

**Descrição**: Peso da incerteza posicional. Escalado por `sqrt(dt)` para compensar maiores mudanças posicionais com frames esparsos.

**Uso no Código**:
```python
# src/zebtrack/tracker/kalman_filter.py:68
dt_factor = np.sqrt(dt)
self._std_weight_position = (1.0 / 20) * dt_factor
```

---

### 4.3 std_weight_velocity

| Atributo | Valor |
|----------|-------|
| **Fórmula** | `(1/160) * sqrt(dt) * 2` |
| **Com dt=10** | `0.00625 * 3.16 * 2 ≈ 0.0395` |
| **Base ByteTrack** | `1/160 = 0.00625` |

**Descrição**: Peso da incerteza de velocidade. Fator extra de 2 para movimentos erráticos de zebrafish.

**Uso no Código**:
```python
# src/zebtrack/tracker/kalman_filter.py:69
self._std_weight_velocity = (1.0 / 160) * dt_factor * 2  # Extra factor for erratic motion
```

---

## 5. Parâmetros de Processamento de Vídeo

### 5.1 processing_interval

| Atributo | Valor |
|----------|-------|
| **Localização** | `config.yaml` → `video_processing.processing_interval` |
| **Arquivo Pydantic** | `settings.py` → `VideoProcessingSettings.processing_interval` |
| **Valor Default** | `10` |
| **Range Válido** | `[1, 1000]` |
| **Exposto na UI** | ✅ Sim (via wizard/config editor) |

**Descrição**: Processa 1 frame a cada N frames. Afeta diretamente:
- `KalmanFilter.dt`
- `BYTETracker.buffer_size`
- Velocidade de processamento

**Efeito no Pipeline**:
```
processing_interval = 10
     │
     ├──► Kalman dt = 10 (prediz movimento para 10 frames à frente)
     ├──► buffer_size = 60 * 10 = 600 (tracks perdidos mantidos por mais tempo)
     └──► fps efetivo = 30/10 = 3 detecções/segundo
```

---

### 5.2 processing_offset

| Atributo | Valor |
|----------|-------|
| **Localização** | `config.yaml` → `video_processing.processing_offset` |
| **Valor Default** | `1` |
| **Range Válido** | `>= 0` |
| **Exposto na UI** | ✅ Sim |

**Descrição**: Frame inicial do ciclo de processamento.
- `offset=1, interval=10` → processa frames 1, 11, 21, 31...
- `offset=0, interval=10` → processa frames 0, 10, 20, 30...

---

### 5.3 fps

| Atributo | Valor |
|----------|-------|
| **Localização** | `config.yaml` → `video_processing.fps` |
| **Valor Default** | `30` |
| **Range Válido** | `(1, 120]` |
| **Exposto na UI** | ❌ Não |

**Descrição**: FPS do vídeo de saída anotado. Também usado para cálculos de velocidade em cm/s.

---

## 6. Hybrid Matching (Matching Híbrido)

### 6.1 Algoritmo

O ByteTrack foi aprimorado com matching híbrido para cenários de processamento esparso:

```python
# src/zebtrack/tracker/matching.py:262-285
def hybrid_iou_center_distance(atracks, btracks, iou_thresh=0.1, max_center_dist=200.0):
    """
    1. Calcula IoU entre tracks e detecções
    2. Calcula distância de centro entre tracks e detecções
    3. Para cada par:
       - Se IoU > iou_thresh: usa custo IoU
       - Senão: usa custo de distância de centro
    """
    iou_cost = iou_distance(atracks, btracks)
    center_cost = center_distance(atracks, btracks, max_center_dist)
    
    has_iou = iou_cost < (1 - iou_thresh)  # IoU > 0.1
    cost_matrix = np.where(has_iou, iou_cost, center_cost)
    
    return cost_matrix
```

### 6.2 Parâmetros

| Parâmetro | Valor | Descrição |
|-----------|-------|-----------|
| `iou_thresh` | `0.1` | Mínimo IoU para considerar overlap válido |
| `max_center_dist` | `200.0` | Distância máxima para fallback |
| `use_hybrid_matching` | `True` | Ativa/desativa matching híbrido |

---

## 7. Fluxo de Dados e Dependências

### 7.1 Injeção de Dependências

```
__main__.py (Composition Root)
     │
     ├──► load_settings() → Settings
     │         │
     │         ├──► yolo_model.confidence_threshold
     │         ├──► yolo_model.nms_threshold
     │         ├──► bytetrack.track_threshold
     │         ├──► bytetrack.match_threshold
     │         ├──► bytetrack.max_center_distance
     │         └──► video_processing.processing_interval
     │
     ├──► DetectorService(settings_obj=settings)
     │         │
     │         └──► initialize_detector()
     │                   │
     │                   └──► UltralyticsDetectorPlugin(settings_obj=settings)
     │                              │
     │                              └──► self.match_threshold = settings.bytetrack.match_threshold
     │
     └──► MainViewModel(settings_obj=settings, ...)
```

### 7.2 Cascata de Parâmetros

```
config.yaml
     │
     ▼
Settings (Pydantic Models)
     │
     ▼
DetectorService/DetectorPlugin
     │
     ├──► Detector.__init__()
     │         │
     │         └──► BYTETracker(args)
     │                   │
     │                   ├──► args.track_thresh
     │                   ├──► args.match_thresh
     │                   └──► KalmanFilter(dt=processing_interval)
     │
     └──► Detector.detect()
               │
               └──► tracker.update(detections)
```

---

## 8. Configuração via config.yaml

### 8.1 Seção YOLO Model

```yaml
yolo_model:
  path: 'best_seg.pt'
  confidence_threshold: 0.05    # [0.0-1.0] Mais baixo = mais detecções
  nms_threshold: 0.5            # [0.0-1.0] Mais alto = mais overlap permitido
```

### 8.2 Seção ByteTrack

```yaml
bytetrack:
  track_threshold: 0.25         # [0.0-1.0] Confiança mínima para first pass
  match_threshold: 0.80         # [0.0-1.0] ⚠️ MAIOR = MAIS PERMISSIVO
  max_center_distance: 200.0    # pixels, para fallback de distância
```

### 8.3 Seção Video Processing

```yaml
video_processing:
  fps: 30
  processing_interval: 10       # Processa 1 a cada N frames
  processing_offset: 1          # Frame inicial
  single_animal_per_aquarium: false
```

---

## 9. Exposição na UI

### 9.1 Parâmetros Acessíveis pela UI

| Parâmetro | Localização na UI | Método de Acesso |
|-----------|-------------------|------------------|
| `processing_interval` | Wizard Step 4 / Config Editor | ComboBox/Entry |
| `processing_offset` | Config Editor | Entry |
| `single_animal_per_aquarium` | Wizard Step 2 | Checkbox |
| `roi_inclusion_rule` | Config Editor | ComboBox |

### 9.2 Parâmetros Não Expostos (config.yaml only)

| Parâmetro | Razão |
|-----------|-------|
| `confidence_threshold` | Técnico demais para usuário final |
| `nms_threshold` | Técnico demais para usuário final |
| `track_threshold` | Requer conhecimento de ByteTrack |
| `match_threshold` | Requer conhecimento de ByteTrack |
| `max_center_distance` | Dependente de resolução/objeto |

---

## 10. Problemas Conhecidos e Correções Aplicadas

### 10.1 match_threshold Hardcoded (CORRIGIDO ✅)

**Problema**: Plugins (`ultralytics_detector.py`, `openvino_detector.py`) usavam `match_threshold=0.15` hardcoded, ignorando o valor de `config.yaml` (0.80).

**Impacto**: IDs de animais saltavam frequentemente porque o threshold era muito restritivo.

**Correção Aplicada**:

```python
# ANTES:
self.match_threshold = 0.15

# DEPOIS:
self.match_threshold = getattr(settings_obj.bytetrack, "match_threshold", 0.80)
```

**Arquivos Modificados**:

- `src/zebtrack/plugins/ultralytics_detector.py` (linhas 46-48)
- `src/zebtrack/plugins/openvino_detector.py` (linhas similar)
- `src/zebtrack/settings.py` (default alterado de 0.15 → 0.80)
- `src/zebtrack/core/detector_service.py` (DEFAULT_MATCH_THRESHOLD = 0.80)

---

### 10.2 analysis_tab_frame Não Definido (CORRIGIDO ✅)

**Problema**: `self.gui.analysis_tab_frame` nunca era definido em `widget_factory.py`, causando falha na troca automática de aba.

**Correção Aplicada**:

```python
# src/zebtrack/ui/widget_factory.py:428
self.gui.analysis_tab_frame = self.gui.analysis_display_widget
```

---

### 10.3 BBox Sobre Aba de Zonas (CORRIGIDO ✅)

**Problema**: `renderer.update_overlay()` desenhava bboxes no canvas da aba de zonas durante análise.

**Correção Aplicada**:

```python
# src/zebtrack/ui/components/canvas/renderer.py:222-224
def update_overlay(self, detections, is_single_subject=False):
    if getattr(self.gui, 'analysis_active', False):
        return  # Skip drawing on zone canvas during analysis
```

---

### 10.4 processing_interval Não Propagado para ByteTracker (CORRIGIDO ✅)

**Problema**: O valor de `analysis_interval_frames` definido pelo usuário na UI não era usado pelo Kalman Filter do ByteTracker.

**Causa Raiz**:

1. `ProcessingContext` era criado com `analysis_interval_frames=10` **hardcoded** em `processing_coordinator.py`
2. O `detector` usava `settings.video_processing.processing_interval` do arquivo config, não o valor da UI
3. O Kalman Filter recebia `dt=1` (default) em vez do valor configurado pelo usuário

**Impacto**: Predições de movimento imprecisas → associações incorretas → IDs saltando

**Correções Aplicadas**:

**Arquivo 1: `processing_coordinator.py`** - Usar valores da UI ao criar contexto:

```python
# ANTES (linhas 375-376):
analysis_interval_frames=10,  # Will be updated by worker
display_interval_frames=10,  # Will be updated by worker

# DEPOIS:
# Calculate processing intervals from config or project settings
analysis_interval, display_interval = self._determine_processing_intervals(
    single_video_config
)
# ... e usar analysis_interval, display_interval
```

**Arquivo 2: `processing_worker.py`** - Sincronizar settings no worker:

```python
# ADICIONADO em _initialize_detector():
# CRITICAL: Sync processing_interval from analysis_interval_frames
if hasattr(settings, "video_processing"):
    runtime_interval = self.config.analysis_interval_frames
    config_interval = getattr(settings.video_processing, "processing_interval", 1)
    if runtime_interval != config_interval:
        log.info(
            "worker.detector.sync_processing_interval",
            config_interval=config_interval,
            runtime_interval=runtime_interval,
        )
        settings.video_processing.processing_interval = runtime_interval
```

**Fluxo Corrigido**:

```
UI (analysis_interval_frames=5)
     │
     ▼ compose_single_video_runtime_config()
     │
ProcessingContext(analysis_interval_frames=5)  ← ANTES era sempre 10!
     │
     ▼
WorkerConfig(analysis_interval_frames=5)
     │
     ▼ _initialize_detector() agora sincroniza
     │
settings.video_processing.processing_interval = 5
     │
     ▼
ByteTracker(processing_interval=5)
     │
     ▼
KalmanFilter(dt=5.0)  ← Predições corretas!
```

---

### 10.5 track_buffer e iou_threshold Não Configuráveis (CORRIGIDO ✅)

**Problema**: `track_buffer` e `iou_threshold` eram hardcoded no código.

**Correção Aplicada**:

- Adicionados a `ByteTrackSettings` em `settings.py`
- Adicionados métodos `_get_track_buffer()` e `_get_iou_threshold()` em `detector.py`
- `byte_tracker.py` agora aceita `iou_threshold` como parâmetro

```python
# src/zebtrack/settings.py - ByteTrackSettings
track_buffer: int = Field(
    90,
    ge=10,
    le=1000,
    description="Frames to keep lost tracks before removal (scaled by processing_interval)",
)
iou_threshold: float = Field(
    0.05,
    gt=0.0,
    lt=1.0,
    description="IoU threshold below which center-distance matching is used instead",
)
```

---

## 11. Recomendações de Configuração

### 11.1 Para Zebrafish em Laboratório (Recomendado)

```yaml
bytetrack:
  track_threshold: 0.25
  match_threshold: 0.90       # Alto para estabilidade máxima
  max_center_distance: 300.0  # ~10 body lengths para zebrafish 30px
  track_buffer: 90            # Mantém tracks por ~3s (30fps, interval=10)
  iou_threshold: 0.05         # Baixo - usa centro para objetos pequenos

video_processing:
  processing_interval: 10     # Balance velocidade/precisão
  fps: 30

yolo_model:
  confidence_threshold: 0.05  # Baixo para não perder detecções
  nms_threshold: 0.5
```

### 11.2 Para Objetos Lentos (ex: larvas)

```yaml
bytetrack:
  track_threshold: 0.3
  match_threshold: 0.80       # Pode ser mais restritivo
  max_center_distance: 150.0  # Movimento menor esperado
  track_buffer: 60
  iou_threshold: 0.10         # Maior IoU para objetos maiores

video_processing:
  processing_interval: 5      # Mais frames para movimentos lentos
```

### 11.3 Para Alta Velocidade/Oclusões Frequentes

```yaml
bytetrack:
  track_threshold: 0.20       # Mais permissivo no first pass
  match_threshold: 0.95       # Muito permissivo para re-associação
  max_center_distance: 400.0  # Maior range de matching
  track_buffer: 120           # Mantém tracks por mais tempo
  iou_threshold: 0.03         # Quase sempre usa centro

video_processing:
  processing_interval: 5      # Menos intervalo = menos movimento entre frames
```

### 11.4 Tabela de Referência Rápida

| Cenário | match_threshold | max_center_distance | track_buffer | iou_threshold |
|---------|-----------------|---------------------|--------------|---------------|
| Zebrafish padrão | 0.90 | 300 | 90 | 0.05 |
| Larvas lentas | 0.80 | 150 | 60 | 0.10 |
| Alta velocidade | 0.95 | 400 | 120 | 0.03 |
| Oclusões frequentes | 0.95 | 350 | 150 | 0.05 |
| Múltiplos animais próximos | 0.85 | 200 | 90 | 0.10 |

### 11.5 Diagnóstico de Problemas Comuns

| Sintoma | Causa Provável | Solução |
|---------|----------------|---------|
| IDs saltando frequentemente | `match_threshold` baixo | Aumentar para 0.85-0.95 |
| IDs não se reconectam após oclusão | `track_buffer` baixo | Aumentar para 90-120 |
| Animais rápidos perdem tracking | `max_center_distance` baixo | Aumentar para 300-400 |
| Falsos matches entre animais | `match_threshold` alto demais | Reduzir para 0.80-0.85 |
| Predição de movimento errada | `processing_interval` não sincronizado | Verificar se UI valor é propagado |

---

## Apêndice A: Arquivos Relevantes

| Arquivo | Propósito |
|---------|-----------|
| `config.yaml` | Configuração principal |
| `src/zebtrack/settings.py` | Modelos Pydantic de validação |
| `src/zebtrack/tracker/byte_tracker.py` | Tracker ByteTrack |
| `src/zebtrack/tracker/kalman_filter.py` | Filtro de Kalman |
| `src/zebtrack/tracker/matching.py` | Funções de matching (IoU, centro, híbrido) |
| `src/zebtrack/plugins/ultralytics_detector.py` | Plugin YOLO |
| `src/zebtrack/plugins/openvino_detector.py` | Plugin OpenVINO |
| `src/zebtrack/core/detector_service.py` | Serviço de detecção |
| `src/zebtrack/core/detector.py` | Classe Detector principal |

---

## Apêndice B: Diagrama de Classes Simplificado

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Settings                                   │
│  ├── YoloModelSettings                                              │
│  │     ├── confidence_threshold: float                              │
│  │     └── nms_threshold: float                                     │
│  ├── ByteTrackSettings                                              │
│  │     ├── track_threshold: float                                   │
│  │     ├── match_threshold: float                                   │
│  │     └── max_center_distance: float                               │
│  └── VideoProcessingSettings                                        │
│        ├── fps: int                                                 │
│        ├── processing_interval: int                                 │
│        └── processing_offset: int                                   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      DetectorService                                 │
│  ├── settings: Settings                                             │
│  └── detector: Detector                                             │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Detector                                    │
│  ├── plugin: DetectorPlugin (Ultralytics/OpenVINO)                  │
│  └── tracker: BYTETracker                                           │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        BYTETracker                                   │
│  ├── args.track_thresh                                              │
│  ├── args.match_thresh                                              │
│  ├── max_center_distance                                            │
│  ├── buffer_size (scaled by processing_interval)                    │
│  └── kalman_filter: KalmanFilter(dt=processing_interval)            │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       KalmanFilter                                   │
│  ├── dt: float (time delta)                                         │
│  ├── _motion_mat: np.ndarray (8x8)                                  │
│  ├── _std_weight_position: float (scaled by sqrt(dt))               │
│  └── _std_weight_velocity: float (scaled by sqrt(dt))               │
└─────────────────────────────────────────────────────────────────────┘
```

---

*Documento gerado automaticamente. Para atualizações, consulte o código-fonte.*
