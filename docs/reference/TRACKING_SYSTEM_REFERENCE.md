# ZebTrack-AI: Sistema de Tracking - Referência Técnica

> **Versão**: 2.1
> **Última atualização**: Dezembro 2025
> **Público-alvo**: Desenvolvedores, agentes AI, usuários avançados

Este documento detalha o fluxo completo do sistema de tracking, desde a configuração pelo usuário até a geração do relatório final.

---

## 📋 Índice

1. [Visão Geral do Fluxo](#1-visão-geral-do-fluxo)
2. [Configuração pelo Usuário](#2-configuração-pelo-usuário)
3. [Parâmetros do ByteTracker](#3-parâmetros-do-bytetracker)
4. [Filtro de Kalman](#4-filtro-de-kalman)
5. [Processamento de Vídeo](#5-processamento-de-vídeo)
6. [Gravação e Relatório](#6-gravação-e-relatório)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Visão Geral do Fluxo

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CONFIGURAÇÃO DO USUÁRIO                              │
│  UI ou config.yaml → processing_interval, single_animal_per_aquarium        │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PROCESSAMENTO DE VÍDEO                               │
│  ProcessingWorker → processa 1 a cada N frames                               │
│  detector.detect() → YOLO + ByteTracker                                      │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BYTETRACKER                                        │
│  Kalman Filter (dt=interval) → Predição de movimento                         │
│  Hybrid Matching → IoU + Centro-distância                                    │
│  Atribuição de track_id consistente                                          │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           RECORDER                                           │
│  Grava: timestamp, frame, track_id, bbox, confidence, x_cm, y_cm            │
│  Arquivo Parquet para análise posterior                                      │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ANÁLISE E RELATÓRIO                                     │
│  AnalysisService → Distância, velocidade, tempo em zonas                     │
│  Relatório Excel com métricas por track_id                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Configuração pelo Usuário

### 2.1 Parâmetros Disponíveis na Interface Gráfica

| Parâmetro | Localização UI | Descrição |
|-----------|----------------|-----------|
| `processing_interval` | ✅ Painel principal | Processar 1 a cada N frames |
| `single_animal_per_aquarium` | ✅ Configurações de vídeo | Modo animal único (desativa fuse_score) |

### 2.2 Parâmetros Apenas em config.yaml

| Parâmetro | Seção | Padrão | Descrição |
|-----------|-------|--------|-----------|
| `track_threshold` | `bytetrack` | 0.25 | Confiança mínima para manter detecção |
| `match_threshold` | `bytetrack` | 0.95 | Limiar máximo de custo para associação |
| `track_buffer` | `bytetrack` | 150 | Frames para manter track perdida |
| `max_center_distance` | `bytetrack` | 400.0 | Distância máxima centro-a-centro (px) |
| `iou_threshold` | `bytetrack` | 0.05 | IoU mínimo para preferir matching por IoU |

### 2.3 Exemplo de config.yaml

```yaml
video_processing:
  fps: 30
  processing_interval: 10      # Processa 1 a cada 10 frames
  single_animal_per_aquarium: true  # Modo animal único

bytetrack:
  track_threshold: 0.25        # Mínimo de confiança
  match_threshold: 0.95        # Muito permissivo (aceita custos até 0.95)
  track_buffer: 150            # Mantém tracks por ~5s @ 30fps
  max_center_distance: 400.0   # Aceita movimentos de até 400px
  iou_threshold: 0.05          # Prefere centro-distância para objetos pequenos
```

---

## 3. Parâmetros do ByteTracker

### 3.1 `track_threshold` (Limiar de Detecção)

**Arquivo**: `src/zebtrack/settings.py` → `ByteTrackSettings.track_threshold`
**Valor padrão**: 0.25
**Faixa válida**: 0 < valor < 1

#### O que faz:
Filtra detecções com confiança abaixo deste limiar **antes** de tentar associar a tracks existentes.

#### Impacto:
| Valor | Efeito |
|-------|--------|
| **Baixo (0.1-0.2)** | Aceita mais detecções, pode incluir falsos positivos |
| **Médio (0.25-0.4)** | Balanço entre sensibilidade e precisão |
| **Alto (0.5+)** | Apenas detecções muito confiantes, pode perder animais |

#### Uso interno:
```python
# byte_tracker.py linha 195
self.det_thresh = args.track_thresh + 0.1  # Limiar para NOVAS tracks
```

---

### 3.2 `match_threshold` (Limiar de Associação)

**Arquivo**: `src/zebtrack/settings.py` → `ByteTrackSettings.match_threshold`
**Valor padrão**: 0.95
**Faixa válida**: 0 < valor ≤ 1

#### O que faz:
Define o **custo máximo aceitável** para associar uma detecção a uma track existente.

#### Escala de custo:
- 0.0 = Match perfeito (100% overlap ou distância zero)
- 1.0 = Pior match possível (sem overlap)

#### Impacto:
| Valor | Efeito |
|-------|--------|
| **Baixo (0.3-0.5)** | Exige matches muito bons, IDs trocam frequentemente |
| **Médio (0.6-0.8)** | Balanço entre estabilidade e precisão |
| **Alto (0.9-0.95)** | Muito permissivo, IDs mais estáveis mas pode associar errado |

#### Recomendação para zebrafish:
Use **0.95** para máxima estabilidade de IDs. O algoritmo híbrido (IoU + centro) já garante associações corretas.

---

### 3.3 `track_buffer` (Buffer de Tracks Perdidas)

**Arquivo**: `src/zebtrack/settings.py` → `ByteTrackSettings.track_buffer`
**Valor padrão**: 150
**Faixa válida**: 10 ≤ valor ≤ 1000

#### O que faz:
Número de **chamadas de update()** que uma track "perdida" é mantida antes de ser removida permanentemente.

#### ⚠️ IMPORTANTE: Escalamento por processing_interval

```python
# byte_tracker.py linhas 197-199
self.buffer_size = int(frame_rate / 30.0 * args.track_buffer * processing_interval)
self.max_time_lost = self.buffer_size
```

**Exemplo**:
- `track_buffer = 150`, `processing_interval = 10`, `fps = 30`
- `buffer_size = 30/30 × 150 × 10 = 1500`
- Tempo real: 1500 / (30/10) = 500 segundos de memória

#### Impacto:
| Valor | Efeito |
|-------|--------|
| **Baixo (10-30)** | Tracks perdidas rapidamente, novos IDs frequentes |
| **Médio (60-150)** | ~2-5 segundos de memória |
| **Alto (300+)** | Longa memória, pode re-associar após oclusões longas |

#### Uso interno:
```python
# byte_tracker.py linhas 374-377
for track in self.lost_stracks:
    if self.frame_id - track.end_frame > self.max_time_lost:
        track.mark_removed()  # Remove permanentemente
```

---

### 3.4 `max_center_distance` (Distância Máxima de Centro)

**Arquivo**: `src/zebtrack/settings.py` → `ByteTrackSettings.max_center_distance`
**Valor padrão**: 400.0 pixels
**Faixa válida**: > 0

#### O que faz:
Quando o matching por IoU falha (objetos não se sobrepõem entre frames), o ByteTracker usa **distância entre centros** como fallback. Este parâmetro define o máximo aceitável.

#### Cálculo sugerido:
```
max_center_distance = velocidade_máxima × processing_interval × margem_segurança
```

**Exemplo para zebrafish**:
- Tamanho do peixe: ~30px
- Velocidade máxima: ~15 px/frame
- processing_interval: 10
- Distância esperada: 15 × 10 = 150px
- Com margem 2x: 300px
- Valor recomendado: **400px** (para movimentos erráticos)

#### Impacto:
| Valor | Efeito |
|-------|--------|
| **Baixo (50-100)** | Apenas movimentos pequenos aceitos, IDs trocam com movimento |
| **Médio (200-300)** | Adequado para animais que se movem moderadamente |
| **Alto (400+)** | Aceita grandes movimentos, mais estável |

---

### 3.5 `iou_threshold` (Limiar de IoU Mínimo)

**Arquivo**: `src/zebtrack/settings.py` → `ByteTrackSettings.iou_threshold`
**Valor padrão**: 0.05
**Faixa válida**: 0 ≤ valor < 1

#### O que faz:
Define quando **preferir IoU** sobre **distância de centro** no matching híbrido.

#### Lógica:
```python
# matching.py - hybrid_iou_center_distance()
if iou >= iou_thresh:
    cost = 1.0 - iou  # Usa custo baseado em IoU
else:
    cost = normalized_center_distance  # Usa custo baseado em distância
```

#### Impacto:
| Valor | Efeito |
|-------|--------|
| **Zero (0.0)** | Sempre usa centro-distância, ignora overlap |
| **Baixo (0.05-0.1)** | Usa IoU apenas quando há algum overlap |
| **Alto (0.3+)** | Exige overlap significativo para usar IoU |

#### Recomendação:
Para objetos **pequenos e rápidos** (zebrafish), use **0.05**. Isso permite matching por distância quando não há overlap entre frames.

---

### 3.6 `single_animal_mode` (Modo Animal Único)

**Arquivo**: `src/zebtrack/settings.py` → `VideoProcessingSettings.single_animal_per_aquarium`
**Valor padrão**: false
**Disponível na UI**: ✅ Sim

#### O que faz:
Quando ativado, **desabilita a função `fuse_score`** no ByteTracker.

#### Por que isso importa:
A função `fuse_score` multiplica o custo de matching pela confiança da detecção:

```python
# matching.py
def fuse_score(cost_matrix, detections):
    for d, det in enumerate(detections):
        cost_matrix[:, d] *= (1 - det.score)  # Penaliza baixa confiança
```

**Problema**: Se confiança = 0.3, um custo de 0.25 vira 0.25 × 0.7 = 0.525!

#### Impacto:
| Modo | Efeito |
|------|--------|
| **false** | fuse_score ativo, útil para múltiplos animais similares |
| **true** | fuse_score desativado, IDs mais estáveis com 1 animal |

---

## 4. Filtro de Kalman

### 4.1 Visão Geral

O Kalman Filter prediz onde o animal **estará** no próximo frame processado, baseado em:
- Posição atual (x, y)
- Velocidade estimada (vx, vy)
- Tempo entre observações (dt = processing_interval)

### 4.2 Parâmetro `dt` (Delta Time)

**Arquivo**: `src/zebtrack/tracker/kalman_filter.py`
**Configurado por**: `processing_interval`

#### Matriz de Movimento:
```
┌                          ┐
│ 1  0  0  0  dt  0  0  0  │
│ 0  1  0  0  0  dt  0  0  │   x_new = x + vx × dt
│ 0  0  1  0  0  0  dt  0  │   y_new = y + vy × dt
│ 0  0  0  1  0  0  0  dt  │
│ 0  0  0  0  1  0  0  0   │
│ 0  0  0  0  0  1  0  0   │
│ 0  0  0  0  0  0  1  0   │
│ 0  0  0  0  0  0  0  1   │
└                          ┘
```

### 4.3 Escalamento de Incerteza

```python
# kalman_filter.py linhas 68-72
dt_factor = np.sqrt(dt)
self._std_weight_position = (1.0 / 20) * dt_factor   # Escala com √dt
self._std_weight_velocity = (1.0 / 160) * dt_factor * 2  # Extra para movimento errático
```

**Por que √dt?**
A variância de posição escala linearmente com tempo, então o desvio padrão escala com √tempo.

---

## 5. Processamento de Vídeo

### 5.1 Fluxo de Frames

```python
# processing_worker.py (simplificado)
for frame_num in range(total_frames):
    should_process = (frame_num % processing_interval == 0)

    if should_process:
        # 1. Lê frame do vídeo
        frame = video.read(frame_num)

        # 2. Detecta objetos (YOLO)
        detections = detector.detect(frame)

        # 3. ByteTracker atribui IDs
        # (internamente: Kalman predict → matching → update)

        # 4. Grava dados
        timestamp = frame_num / fps
        recorder.write_detection_data(timestamp, frame_num, detections)
```

### 5.2 Cálculo de Timestamp

```python
timestamp = frame_number / fps

# Exemplo:
# Frame 100 @ 30fps = 3.333 segundos
# Frame 300 @ 30fps = 10.0 segundos
```

**Importante**: O timestamp representa o tempo **real** no vídeo, não o número de processamentos.

---

## 6. Gravação e Relatório

### 6.1 Estrutura do Parquet

```
timestamp │ frame │ track_id │ x1  │ y1  │ x2  │ y2  │ conf │ x_cm │ y_cm
──────────┼───────┼──────────┼─────┼─────┼─────┼─────┼──────┼──────┼──────
0.000     │ 0     │ 1        │ 610 │ 420 │ 680 │ 450 │ 0.85 │ 10.2 │ 7.0
0.333     │ 10    │ 1        │ 615 │ 425 │ 685 │ 455 │ 0.78 │ 10.4 │ 7.1
0.667     │ 20    │ 1        │ 620 │ 430 │ 690 │ 460 │ 0.82 │ 10.5 │ 7.2
```

**Nota**: Apenas frames processados aparecem (0, 10, 20...). Frame 5 não existe no arquivo.

### 6.2 Métricas Calculadas

| Métrica | Fórmula |
|---------|---------|
| **Distância Total** | Σ √[(x₂-x₁)² + (y₂-y₁)²] para pontos consecutivos |
| **Velocidade Média** | distância_total / (timestamp_final - timestamp_inicial) |
| **Tempo em Zona** | frames_na_zona × (1/fps × processing_interval) |

---

## 7. Troubleshooting

### 7.1 IDs Trocando Frequentemente

**Sintoma**: Animal muda de ID a cada poucos frames.

**Causas e Soluções**:

| Causa | Solução |
|-------|---------|
| `match_threshold` muito baixo | Aumentar para 0.9-0.95 |
| `max_center_distance` muito baixo | Aumentar para 300-400px |
| `fuse_score` penalizando | Ativar `single_animal_per_aquarium: true` |
| `processing_interval` alto sem ajuste de dt | Verificar se Kalman recebe dt correto |

### 7.2 Tracks Perdidas Rapidamente

**Sintoma**: Animal some e reaparece com novo ID após breve oclusão.

**Solução**: Aumentar `track_buffer`:
```yaml
bytetrack:
  track_buffer: 300  # ~10 segundos @ 30fps
```

### 7.3 Associações Incorretas

**Sintoma**: Dois animais trocam IDs entre si.

**Soluções**:
- Diminuir `max_center_distance` (força matches mais precisos)
- Diminuir `match_threshold` (exige melhor qualidade de match)
- Verificar se `single_animal_mode` está correto para o cenário

### 7.4 Verificar Parâmetros em Uso

Execute com log detalhado:
```powershell
poetry run python -m zebtrack --log-level zebtrack.core.detector=DEBUG
```

Procure por:
```
detector.bytetrack.initializing track_thresh=0.25 match_thresh=0.95 track_buffer=150 ...
```

---

## 📚 Referências de Código

| Componente | Arquivo |
|------------|---------|
| ByteTracker | `src/zebtrack/tracker/byte_tracker.py` |
| Kalman Filter | `src/zebtrack/tracker/kalman_filter.py` |
| Matching | `src/zebtrack/tracker/matching.py` |
| Detector | `src/zebtrack/core/detector.py` |
| Processing Worker | `src/zebtrack/core/processing_worker.py` |
| Recorder | `src/zebtrack/io/recorder.py` |
| Settings | `src/zebtrack/settings.py` |

---

## 📝 Changelog

- **v2.1** (Dez 2025): Adicionado `single_animal_mode` para desativar `fuse_score`
- **v2.0** (Dez 2025): Matching híbrido (IoU + centro-distância), escalamento de buffer por interval
- **v1.0** (Nov 2025): Implementação inicial com ByteTrack
