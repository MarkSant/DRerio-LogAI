# ZebTrack-AI: Sistema de Tracking Unificado - Referência Técnica Completa

> **Versão**: 5.0 (Pós-Auditoria)
> **Data**: Dezembro 2025
> **Status**: Validado e Otimizado
> **Contexto**: Unificação dos documentos `TRACKING_SYSTEM_REFERENCE.md` e `TRACKING_PARAMETERS_REFERENCE.md`.

Este documento serve como a fonte única de verdade para a arquitetura, parâmetros e funcionamento do sistema de rastreamento do ZebTrack-AI. Ele incorpora as correções críticas realizadas no algoritmo ByteTrack para suportar rastreamento robusto de animais pequenos em frames esparsos.

---

## 📋 Índice

1. [Visão Geral da Arquitetura](#1-visão-geral-da-arquitetura)
2. [Pipeline de Processamento](#2-pipeline-de-processamento)
3. [Parâmetros Detalhados](#3-parâmetros-detalhados)
    *   [3.1 Detecção (YOLO)](#31-detecção-yolo)
    *   [3.2 Rastreamento (ByteTrack)](#32-rastreamento-bytetrack)
    *   [3.3 Predição (Kalman Filter)](#33-predição-kalman-filter)
4. [Mecanismos Avançados](#4-mecanismos-avançados)
    *   [4.1 Correção do Threshold de Associação (Critical Fix)](#41-correção-do-threshold-de-associação-critical-fix)
    *   [4.2 Matching Híbrido (IoU + Distância)](#42-matching-híbrido-iou--distância)
    *   [4.3 Processamento Esparso e Escalonamento Temporal](#43-processamento-esparso-e-escalonamento-temporal)
5. [Guia de Configuração e Tuning](#5-guia-de-configuração-e-tuning)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Visão Geral da Arquitetura

O sistema de tracking do ZebTrack-AI é projetado para rastrear zebrafish (adultos e larvas) em vídeos, suportando **processamento esparso** (analisando 1 frame a cada N) para alta performance, sem sacrificar a estabilidade da identidade dos animais.

### Componentes Chave

*   **DetectorService**: Orquestrador principal.
*   **DetectorPlugin**: Abstração para modelos de IA (Ultralytics YOLO / OpenVINO).
*   **BYTETracker**: Algoritmo de rastreamento multi-objeto (MOT) modificado.
*   **KalmanFilter**: Estimador de estado para prever movimento.
*   **ProcessingWorker**: Processo isolado que executa o pipeline.

---

## 2. Pipeline de Processamento

```mermaid
graph TD
    A[Frame de Vídeo] --> B{Processar Frame?}
    B -- Sim (1 a cada N) --> C[YOLO Detector]
    B -- Não --> Z[Ignorar]

    C --> D[Lista de Detecções]
    D --> E[ByteTrack: 1ª Associação]
    E -- High Score Dets --> F{Match com Tracks?}
    F -- Sim --> G[Atualizar Kalman]
    F -- Não --> H[ByteTrack: 2ª Associação]

    H -- Low Score Dets --> I{Match com Perdidos?}
    I -- Sim (Hybrid Match) --> G
    I -- Não --> J[Criar Novo Track / Marcar Perdido]

    G --> K[Gravar Dados (Parquet)]
    K --> L[Renderizar Overlay]
```

---

## 3. Parâmetros Detalhados

### 3.1 Detecção (YOLO)

Responsável por encontrar os animais em cada frame processado.

| Parâmetro | Default | Localização (`config.yaml`) | Descrição |
|-----------|---------|-----------------------------|-----------|
| `confidence_threshold` | `0.05` | `yolo_model.confidence_threshold` | Confiança mínima para aceitar uma detecção. Valor baixo evita perder animais difíceis. |
| `nms_threshold` | `0.50` | `yolo_model.nms_threshold` | Non-Maximum Suppression. Controla a sobreposição permitida entre bboxes. |

### 3.2 Rastreamento (ByteTrack)

Responsável por manter a identidade dos animais ao longo do tempo.

| Parâmetro | Default | Localização (`config.yaml`) | Descrição |
|-----------|---------|-----------------------------|-----------|
| `track_threshold` | `0.25` | `bytetrack.track_threshold` | Confiança mínima para considerar uma detecção como "alta confiança" (1ª passagem). |
| `match_threshold` | `0.95` | `bytetrack.match_threshold` | **CRÍTICO.** Custo máximo aceitável para associação. Valores altos (0.95) são mais permissivos. |
| `max_center_distance` | `400.0` | `bytetrack.max_center_distance` | Distância máxima (pixels) para matching quando IoU falha. Essencial para movimentos rápidos. |
| `track_buffer` | `150` | `bytetrack.track_buffer` | Frames para manter memória de um track perdido. Escalado automaticamente pelo intervalo de processamento. |
| `iou_threshold` | `0.05` | `bytetrack.iou_threshold` | Se IoU < 0.05, o sistema usa distância de centro. Permite rastrear objetos sem sobreposição. |

### 3.3 Predição (Kalman Filter)

Modelo matemático que prevê onde o animal estará no próximo frame.

*   **`dt` (Delta Time):** Definido dinamicamente pelo `processing_interval`. Se processar a cada 10 frames, `dt=10`.
*   **Incerteza de Posição:** Escala com `sqrt(dt)`.
*   **Incerteza de Velocidade:** Escala com `sqrt(dt) * 2` (fator extra para movimentos erráticos de peixes).

---

## 4. Mecanismos Avançados

### 4.1 Correção do Threshold de Associação (Critical Fix)

**Problema Anterior:** O ByteTrack original tinha um valor hardcoded de `0.5` na segunda etapa de associação. Isso significava que mesmo configurando `match_threshold: 0.95`, o sistema rejeitava associações difíceis (com custo > 0.5) na etapa de recuperação.

**Solução Aplicada (Dez 2025):** O código foi alterado para usar `self.args.match_thresh` em ambas as etapas de associação.

```python
# src/zebtrack/tracker/byte_tracker.py
# Antes:
# matches, u_track, _ = matching.linear_assignment(dists, thresh=0.5)

# Depois:
matches, u_track, _ = matching.linear_assignment(dists, thresh=self.args.match_thresh)
```

Isso garante que a permissividade configurada pelo usuário seja respeitada em todo o pipeline.

### 4.2 Matching Híbrido (IoU + Distância)

Para animais pequenos que se movem rápido, a sobreposição de caixas (IoU) entre frames consecutivos é frequentemente zero. O ZebTrack implementa um matching híbrido:

1.  Calcula IoU.
2.  Se `IoU > iou_threshold` (0.05), usa o custo de IoU (1 - IoU).
3.  Se `IoU <= iou_threshold`, usa o custo de **Distância de Centro Normalizada** (distância / `max_center_distance`).

Isso permite que o tracker "salte" espaços vazios onde o IoU falharia.

### 4.3 Processamento Esparso e Escalonamento Temporal

Ao processar 1 frame a cada N (ex: N=10):
1.  **Kalman Filter:** Recebe `dt=10`. Prevê um deslocamento 10x maior.
2.  **Track Buffer:** Se configurado para 150 frames, e N=10, o buffer interno é ajustado para manter a memória pelo tempo equivalente em segundos reais.
    *   Fórmula: `buffer_size = (fps / 30) * track_buffer * processing_interval`

---

## 5. Guia de Configuração e Tuning

### Cenário A: Zebrafish Adulto (Padrão)
Animais rápidos, tamanho médio (~30-50px).

```yaml
video_processing:
  processing_interval: 10
bytetrack:
  match_threshold: 0.95       # Máxima permissividade
  max_center_distance: 400.0  # Aceita grandes saltos
  track_buffer: 150           # Memória longa
  iou_threshold: 0.05         # Prefere distância de centro
```

### Cenário B: Larvas (Lentas e Pequenas)
Movimento quase imperceptível, tamanho muito pequeno (~10px).

```yaml
video_processing:
  processing_interval: 5      # Menor intervalo para capturar micro-movimentos
bytetrack:
  match_threshold: 0.80       # Mais restritivo para evitar trocas erradas
  max_center_distance: 100.0  # Movimento esperado é pequeno
  track_buffer: 60
  iou_threshold: 0.10
```

### Cenário C: Alta Densidade (Muitos Animais)
Risco de troca de identidade (ID Switch).

```yaml
bytetrack:
  match_threshold: 0.85       # Reduzir permissividade
  max_center_distance: 200.0  # Limitar área de busca
  single_animal_per_aquarium: false
```

---

## 6. Troubleshooting

| Sintoma | Causa Provável | Solução |
|---------|----------------|---------|
| **IDs trocando a cada poucos frames** | `match_threshold` baixo ou hardcoded (corrigido na v5.0) | Verificar se `match_threshold >= 0.90`. |
| **Animal perde ID ao parar** | Detecção falhando (confiança baixa) | Reduzir `confidence_threshold` (YOLO) ou aumentar `track_buffer`. |
| **Animal "salta" para outro peixe** | `max_center_distance` muito alto | Reduzir para 200-300px. |
| **Trajetória em zigue-zague** | Ruído de detecção | Aumentar `trajectory_smoothing.window_length` no config. |

---

## 7. Referência de Código

*   **Tracker:** `src/zebtrack/tracker/byte_tracker.py`
*   **Settings:** `src/zebtrack/settings.py`
*   **Detector:** `src/zebtrack/core/detector.py`
*   **Worker:** `src/zebtrack/core/processing_worker.py`
