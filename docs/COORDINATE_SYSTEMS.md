# Sistema de Coordenadas e Transformações de Perspectiva

## Visão Geral

Este documento detalha como o ZebTrack-AI gerencia diferentes espaços de coordenadas, aplica transformações de perspectiva e converte entre pixels e centímetros. Entender este fluxo é essencial para contribuir com o código relacionado a detecção, rastreamento, análise ou visualização.

---

## Os Três Espaços de Coordenadas

O sistema opera em três espaços de coordenadas distintos:

### 1. Espaço Original do Vídeo
**Dimensões:** Resolução do vídeo capturado (ex: 1920x1080 pixels)

**Usado para:**
- Frames brutos da câmera/vídeo
- Arena desenhada pelo usuário na interface
- ROIs desenhadas pelo usuário
- Detecções brutas do modelo YOLO/OpenVINO

**Características:**
- Pode conter distorção de perspectiva
- Arena pode ser um polígono irregular
- Coordenadas absolutas em pixels

**Exemplo:**
```python
arena_polygon_original = [
    [150, 200],     # Canto superior esquerdo
    [1750, 180],    # Canto superior direito
    [1800, 920],    # Canto inferior direito
    [100, 950]      # Canto inferior esquerdo
]
```

---

### 2. Espaço Warped (Corrigido por Perspectiva)
**Dimensões:** Sempre 600×N pixels, onde N é calculado mantendo o aspect ratio real do aquário

**Usado para:**
- Armazenamento de trajetórias no Parquet
- Cálculos intermediários
- Normalização de coordenadas

**Características:**
- Arena se torna um retângulo perfeito `[(0,0), (600,0), (600,N), (0,N)]`
- Correção de perspectiva aplicada via homografia
- Escala uniforme facilita conversão para centímetros

**Cálculo das dimensões:**
```python
target_width_px = 600  # Fixo
aspect_ratio = aquarium_height_cm / aquarium_width_cm
target_height_px = int(600 * aspect_ratio)

# Exemplo: aquário 54×24cm
aspect_ratio = 24 / 54 = 0.444
target_height_px = 600 * 0.444 = 266 pixels
```

---

### 3. Espaço em Centímetros (Real)
**Dimensões:** Dimensões físicas informadas pelo usuário (ex: 54×24 cm)

**Usado para:**
- Todas as métricas comportamentais
- Análise de ROIs
- Geração de relatórios e gráficos

**Características:**
- Unidades do mundo real
- Eixo Y invertido (origem no canto inferior esquerdo)
- Arena sempre é um retângulo `[(0,0), (width_cm,0), (width_cm,height_cm), (0,height_cm)]`

---

## Pipeline de Transformações

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. ESPAÇO ORIGINAL (1920×1080 px)                               │
│    - Frames capturados                                           │
│    - Arena: polígono irregular                                   │
│    - ROIs: polígonos quaisquer                                   │
│    - Detecções YOLO: bounding boxes                             │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ↓ cv2.perspectiveTransform(homography_matrix)
                         ↓ [calibration.py:transform_bbox()]
                         │
┌────────────────────────┴────────────────────────────────────────┐
│ 2. ESPAÇO WARPED (600×266 px)                                   │
│    - Arena: retângulo perfeito [(0,0), (600,0), (600,266), (0,266)] │
│    - ROIs: transformadas                                         │
│    - Trajetórias: salvas no Parquet neste espaço               │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ↓ Divisão por pixel_per_cm_ratio
                         ↓ x_cm = x_warped_px / (600 / 54)
                         ↓ y_cm = (266 - y_warped_px) / (266 / 24)
                         │
┌────────────────────────┴────────────────────────────────────────┐
│ 3. ESPAÇO EM CENTÍMETROS (54×24 cm)                             │
│    - Arena: [(0,0), (54,0), (54,24), (0,24)]                   │
│    - ROIs: em coordenadas reais                                  │
│    - Métricas: distâncias, velocidades em cm/s                  │
│    - Gráficos: eixos mostram dimensões reais                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Fase 1: Captura e Configuração

### Captura do Vídeo
**Arquivo:** `controller.py:1511-1512`

```python
cap = cv2.VideoCapture(video_path)
frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))   # Ex: 1920
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) # Ex: 1080
```

### Desenho da Arena
**Interface:** `gui.py`

O usuário desenha um polígono sobre o primeiro frame do vídeo delimitando a área do aquário.

```python
# Exemplo de coordenadas capturadas
arena_polygon_px = [[150, 200], [1750, 180], [1800, 920], [100, 950]]
```

**Importante:** Estas coordenadas estão em pixels do **vídeo original**.

### Informação das Dimensões Reais
**Interface:** Dialog na GUI

```python
aquarium_width_cm = 54   # Largura FÍSICA do aquário
aquarium_height_cm = 24  # Altura FÍSICA do aquário
```

**Importante:** Estas são medidas do **aquário real**, não da imagem!

---

## Fase 2: Calibração

### Classe Calibration
**Arquivo:** `calibration.py`

A classe `Calibration` é responsável por:
1. Calcular a matriz de homografia
2. Definir as dimensões do espaço warped
3. Calcular as razões pixel/cm
4. Fornecer métodos de transformação de coordenadas

### Processo Interno

#### 1. Encontrar Cantos da Arena
```python
# _find_corners() usa cv2.minAreaRect
corners = cv2.boxPoints(cv2.minAreaRect(arena_polygon_px))
# Retorna 4 pontos que formam o retângulo de área mínima
```

#### 2. Calcular Dimensões Warped
```python
target_width_px = 600  # Constante fixa
aspect_ratio = aquarium_height_cm / aquarium_width_cm
target_height_px = int(target_width_px * aspect_ratio)
target_dims_px = (target_width_px, target_height_px)
```

**Exemplo:**
- Aquário: 54cm × 24cm
- Aspect ratio: 24/54 = 0.444
- Dimensões warped: 600px × 266px

#### 3. Calcular Matriz de Homografia
```python
# Pontos de origem (arena no vídeo original)
source_points = ordered_corners  # 4 cantos encontrados

# Pontos de destino (retângulo perfeito warped)
destination_points = np.array([
    [0, 0],
    [target_width_px - 1, 0],
    [target_width_px - 1, target_height_px - 1],
    [0, target_height_px - 1]
], dtype="float32")

# Calcula transformação de perspectiva
homography_matrix = cv2.getPerspectiveTransform(
    source_points,
    destination_points
)
```

Esta matriz permite transformar qualquer ponto do espaço original → warped.

#### 4. Calcular Razões Pixel/CM
```python
px_per_cm_x = target_width_px / aquarium_width_cm   # 600 / 54 = 11.11
px_per_cm_y = target_height_px / aquarium_height_cm # 266 / 24 = 11.08
pixel_per_cm_ratio = (px_per_cm_x, px_per_cm_y)
```

**Importante:** Estas razões convertem pixels **warped** → centímetros.

### Métodos de Transformação

#### transform_point()
```python
def transform_point(self, x: float, y: float) -> tuple[float, float]:
    """Transforma um ponto: original → warped"""
    point = np.array([[[x, y]]], dtype=np.float32)
    warped = cv2.perspectiveTransform(point, self.homography_matrix)
    return (float(warped[0][0][0]), float(warped[0][0][1]))
```

#### transform_bbox()
```python
def transform_bbox(self, x1, y1, x2, y2) -> tuple:
    """Transforma bounding box: original → warped"""
    # Transforma os 4 cantos
    corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    warped_corners = self.transform_points(corners)

    # Encontra nova bbox que engloba os cantos transformados
    xs = [p[0] for p in warped_corners]
    ys = [p[1] for p in warped_corners]
    return (min(xs), min(ys), max(xs), max(ys))
```

---

## Fase 3: Detecção e Gravação

### Loop de Processamento
**Arquivo:** `controller.py:1568-1582`

```python
while not self.cancel_event.is_set():
    ret, frame = cap.read()  # Frame ORIGINAL (1920×1080)

    # Detecção no frame original
    detections, _ = self.detector.process_frame(frame)
    # detections = [(x1, y1, x2, y2, confidence, track_id), ...]
    # Coordenadas em pixels ORIGINAIS

    # Grava com transformação
    recorder.write_detection_data(timestamp, frame_num, detections)
```

### Transformação e Gravação
**Arquivo:** `recorder.py:119-156`

```python
def write_detection_data(self, timestamp, frame_number, detections):
    for x1, y1, x2, y2, confidence, track_id in detections:
        # 🔥 TRANSFORMAÇÃO APLICADA AQUI
        if self.calibration:
            x1_w, y1_w, x2_w, y2_w = self.calibration.transform_bbox(
                x1, y1, x2, y2  # Original (1920×1080)
            )
            # Agora em warped (600×266)

        # Calcula centro em coordenadas warped
        x_center = (x1_w + x2_w) / 2
        y_center = (y1_w + y2_w) / 2

        # Converte warped → centímetros
        x_cm = x_center / self.pixel_per_cm_ratio[0]
        y_cm = y_center / self.pixel_per_cm_ratio[1]

        # Salva no Parquet
        data_point = {
            "x1": x1_w,              # Pixels warped
            "y1": y1_w,              # Pixels warped
            "x2": x2_w,              # Pixels warped
            "y2": y2_w,              # Pixels warped
            "x_center_px": x_center, # Pixels warped
            "y_center_px": y_center, # Pixels warped
            "x_cm": x_cm,            # Centímetros
            "y_cm": y_cm,            # Centímetros
        }
        self.detection_data.append(data_point)
```

### Exemplo Numérico Completo

```
ENTRADA (espaço original 1920×1080):
  Detecção: bbox = (500, 300, 550, 350)

PASSO 1: Transformação de perspectiva
  homography_matrix aplicada aos 4 cantos
  Resultado: bbox_warped ≈ (125, 80, 145, 95)

PASSO 2: Cálculo do centro (espaço warped)
  x_center = (125 + 145) / 2 = 135 px
  y_center = (80 + 95) / 2 = 87.5 px

PASSO 3: Conversão para centímetros
  x_cm = 135 / 11.11 = 12.15 cm ✅
  y_cm = 87.5 / 11.08 = 7.90 cm ✅

GRAVADO NO PARQUET:
  x_center_px = 135    (warped)
  y_center_px = 87.5   (warped)
  x_cm = 12.15
  y_cm = 7.90
```

---

## Fase 4: Análise

### BehavioralAnalyzer
**Arquivo:** `behavior.py:67-81, 140-142`

O `BehavioralAnalyzer` recebe dados já transformados:

```python
# Preprocessamento
df["x_cm"] = df["x_center_px"] / self._pixelcm_x
df["y_cm"] = (video_height_px - df["y_center_px"]) / self._pixelcm_y
```

**Parâmetros:**
- `video_height_px` = 266 (altura warped)
- `x_center_px`, `y_center_px` = coordenadas warped (já transformadas)
- `pixelcm_x` = 11.11, `pixelcm_y` = 11.08

**Inversão do eixo Y:** A subtração `(video_height_px - y)` inverte o eixo Y para que a origem fique no canto **inferior** esquerdo (convenção cartesiana).

### Arena em Centímetros
**Arquivo:** `controller.py:1950-1955`

```python
# Arena no espaço warped é um retângulo perfeito
arena_polygon_warped = [
    [0, 0],
    [video_width_px, 0],
    [video_width_px, video_height_px],
    [0, video_height_px]
]
# Ex: [(0,0), (600,0), (600,266), (0,266)]
```

Convertido para CM no `BehavioralAnalyzer`:

```python
arena_coords_cm = [
    (x / pixelcm_x, (video_height_px - y) / pixelcm_y)
    for x, y in arena_polygon_warped
]
# Resultado: [(0,0), (54,0), (54,24), (0,24)]
# ✅ Dimensões reais do aquário!
```

### ROIs em Centímetros
**Arquivo:** `controller.py:1958-1972`

```python
rois = []
for i, roi_polygon_original in enumerate(zone_data.roi_polygons):
    # PASSO 1: Transformar de original → warped
    warped_roi_points = cal.transform_points(roi_polygon_original)

    # PASSO 2: Converter warped → cm
    roi_points_cm = [
        (x / pixelcm_x, (video_height_px - y) / pixelcm_y)
        for x, y in warped_roi_points
    ]

    rois.append(ROI(
        name=zone_data.roi_names[i],
        geometry=Polygon(roi_points_cm)
    ))
```

---

## Fase 5: Geração de Relatórios

### Gráficos
**Arquivo:** `reporter.py`

Todos os gráficos trabalham diretamente em centímetros:

```python
# Arena
arena_poly_cm = b_analyzer.arena_polygon_cm
min_x, min_y, max_x, max_y = arena_poly_cm.bounds
# Resultado: (0, 0, 54, 24) ✅

# Trajetória
x = traj_data["x_cm_smoothed"]  # Valores 0-54 cm
y = traj_data["y_cm_smoothed"]  # Valores 0-24 cm

# ROIs
for roi_name, roi in r_analyzer.rois.items():
    ax.add_patch(Polygon(roi.geometry.exterior.coords))

# Configuração dos eixos
ax.set_xlabel("Position (cm)")
ax.set_ylabel("Position (cm)")
ax.set_xlim(0, 54)  # Largura real
ax.set_ylim(0, 24)  # Altura real
ax.set_aspect("equal", adjustable="box")
```

### Exemplo de Saída
- **Eixo X:** 0 a 54 cm (largura do aquário)
- **Eixo Y:** 0 a 24 cm (altura do aquário)
- **Arena:** Retângulo perfeito cobrindo toda a área
- **ROIs:** Desenhadas nas posições corretas em escala real
- **Trajetória:** Valores em centímetros correspondendo a movimentos reais

---

## Validação do Sistema

### Teste de Dimensões

**Entrada:**
```python
video_resolution = (1920, 1080)  # pixels
aquarium_real_size = (54, 24)    # cm
```

**Saída esperada:**
```python
# Espaço warped
warped_dimensions = (600, 266)  # pixels

# Razões de conversão
pixel_per_cm = (11.11, 11.08)   # px/cm

# Arena em CM
arena_bounds = (0, 0, 54, 24)   # ✅ Dimensões reais!

# Gráficos
x_axis_range = (0, 54)          # cm
y_axis_range = (0, 24)          # cm
```

### Teste de Transformação

**Ponto no centro da arena (espaço original):**
```python
center_original = (960, 540)  # Centro do frame 1920×1080
```

**Após transformação:**
```python
center_warped = cal.transform_point(960, 540)
# ≈ (300, 133) - Centro do warped 600×266

center_cm = (300/11.11, (266-133)/11.08)
# ≈ (27, 12) - Centro do aquário 54×24 cm ✅
```

---

## Pontos-Chave para Desenvolvedores

### ✅ Sempre Lembre

1. **Transformação ocorre ANTES de salvar no Parquet**
   - Localização: `recorder.py:126-129`
   - Método: `calibration.transform_bbox()`

2. **Arena no warped é SEMPRE um retângulo perfeito**
   - Coordenadas: `[(0,0), (width,0), (width,height), (0,height)]`
   - Não importa como foi desenhada no vídeo original

3. **ROIs são transformadas: original → warped → cm**
   - Transformação: `calibration.transform_points()`
   - Conversão: divisão por `pixel_per_cm_ratio`

4. **pixel_per_cm_ratio se refere ao espaço WARPED**
   - Sempre 600×N pixels → dimensões reais em cm
   - Nunca use com coordenadas do vídeo original!

5. **Relatórios exibem dimensões REAIS do aquário**
   - Eixos em centímetros
   - Escala 1:1 entre coordenadas e mundo real

### ❌ Evite

1. **Não** dividir coordenadas originais por `pixel_per_cm_ratio`
   ```python
   # ❌ ERRADO
   x_cm = x_original / pixel_per_cm_ratio[0]

   # ✅ CORRETO
   x_warped = cal.transform_point(x_original, y_original)[0]
   x_cm = x_warped / pixel_per_cm_ratio[0]
   ```

2. **Não** assumir que arena é retângulo no espaço original
   ```python
   # ❌ ERRADO - arena pode ser polígono irregular
   arena_original = [(0,0), (width,0), (width,height), (0,height)]

   # ✅ CORRETO - arena é definida pelo usuário
   arena_original = user_drawn_polygon
   ```

3. **Não** usar dimensões do vídeo original para cálculos de CM
   ```python
   # ❌ ERRADO
   y_cm = (1080 - y_original) / pixel_per_cm_y

   # ✅ CORRETO
   y_warped = cal.transform_point(x_original, y_original)[1]
   y_cm = (266 - y_warped) / pixel_per_cm_y
   ```

---

## Arquivos Principais

### Calibração
- `src/zebtrack/core/calibration.py`: Classe `Calibration` com métodos de transformação

### Gravação
- `src/zebtrack/io/recorder.py`: Método `write_detection_data()` aplica transformação

### Análise
- `src/zebtrack/analysis/behavior.py`: `BehavioralAnalyzer` converte para CM
- `src/zebtrack/analysis/roi.py`: `ROIAnalyzer` trabalha em espaço CM

### Controle
- `src/zebtrack/core/controller.py`: Orquestra todo o pipeline

### Relatórios
- `src/zebtrack/analysis/reporter.py`: Gera gráficos e relatórios em CM

---

## Referências Adicionais

- [ARCHITECTURE.md](./ARCHITECTURE.md): Visão geral da arquitetura do sistema
- [CLAUDE.md](../CLAUDE.md): Guia para contribuir com o projeto
- [OpenCV Perspective Transformation](https://docs.opencv.org/4.x/da/d54/group__imgproc__transform.html#gaf73673a7e8e18ec6963e3774e6a94b87)
