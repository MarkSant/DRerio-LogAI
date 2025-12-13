# Plano de Implementação: Suporte Multi-Aquário (2 Aquários por Vídeo)

**Status:** Aprovado para Implementação
**Criado em:** 2025-12-13
**Branch:** `feature/multi-aquarium-support`
**Complexidade:** Alta (Arquitetura cross-cutting)
**Cobertura de Testes Mínima:** 80%

---

## Resumo Executivo

Implementar suporte para vídeos contendo **2 aquários separados**, cada um com 1 animal, permitindo:
- Cada aquário pertencer a grupos diferentes (ex: Controle vs Tratamento)
- ROIs independentes por aquário
- Auto-detecção por contorno de 2 regiões retangulares
- Extração de metadados via regex customizável
- Saída organizada em pastas separadas por sujeito (Grupo/Dia/Sujeito)
- Visualização unificada mostrando ambos aquários simultaneamente

> **NOTA:** Não há necessidade de retrocompatibilidade pois o programa ainda está em fase de testes.

---

## Fase 0: Setup Inicial (Branch e Ambiente)

### 0.1 Criar Feature Branch
```bash
git checkout -b feature/multi-aquarium-support
```

### 0.2 Tag de Referência (Opcional)
```bash
git tag pre-multi-aquarium-v3.0
```

---

## Fase 1: Modelos de Dados Core (Foundation)

### 1.1 Novos Data Classes
**Arquivo:** `src/zebtrack/core/detector.py`

```python
@dataclass
class AquariumData:
    """Dados de zona para um único aquário com metadados."""
    id: int  # 0 ou 1 para vídeos com 2 aquários
    polygon: list[list[int]]  # Polígono da arena
    roi_polygons: list[list[list[int]]]  # ROIs dentro deste aquário
    roi_names: list[str]
    roi_colors: list[tuple[int, int, int]]
    group: str = ""  # Grupo (ex: "Controle", "Tratamento")
    subject_id: str = ""  # Identificador do sujeito
    day: int = 0  # Dia do experimento

@dataclass
class MultiAquariumZoneData:
    """Dados de zona para vídeos com múltiplos aquários."""
    aquariums: list[AquariumData] = field(default_factory=list)
    video_width: int = 0
    video_height: int = 0

    def get_aquarium(self, aquarium_id: int) -> AquariumData | None:
        """Retorna dados do aquário pelo ID."""
        for aq in self.aquariums:
            if aq.id == aquarium_id:
                return aq
        return None

    def to_zone_data(self, aquarium_id: int = 0) -> ZoneData:
        """Converte um aquário específico para ZoneData."""
        aq = self.get_aquarium(aquarium_id)
        if aq:
            return ZoneData(
                polygon=aq.polygon,
                roi_polygons=aq.roi_polygons,
                roi_names=aq.roi_names,
                roi_colors=aq.roi_colors
            )
        return ZoneData()
```

### 1.2 Modelo Pydantic para Configuração de Aquário
**Arquivo:** `src/zebtrack/ui/wizard/models.py`

```python
class AquariumConfig(BaseModel):
    """Configuração para um aquário em modo multi-aquário."""
    aquarium_id: int = Field(ge=0, le=1)
    group: str = Field(min_length=1)
    subject_id: str = ""
    day: int = Field(default=1, ge=1)

class MultiAquariumData(BaseModel):
    """Dados de configuração para vídeos com 2 aquários."""
    enabled: bool = False
    aquarium_configs: list[AquariumConfig] = Field(default_factory=list, max_length=2)
    regex_pattern: str = ""  # Padrão regex para extração de metadados
    regex_group_field: str = "group"  # Nome do grupo de captura para grupo
    regex_subject_field: str = "subject"  # Nome do grupo de captura para sujeito
    regex_day_field: str = "day"  # Nome do grupo de captura para dia

    @field_validator("aquarium_configs")
    @classmethod
    def validate_configs(cls, v):
        """Valida que há exatamente 2 configurações quando habilitado."""
        if len(v) > 2:
            raise ValueError("Máximo de 2 aquários permitidos")
        return v

# Estender CalibrationData existente
class CalibrationData(BaseModel):
    # ... campos existentes ...
    multi_aquarium: MultiAquariumData = Field(default_factory=MultiAquariumData)
```

### 1.3 Testes Unitários Fase 1 (Cobertura: 80%+)
**Arquivo:** `tests/core/test_multi_aquarium_models.py`

```python
class TestAquariumData:
    def test_creation_with_defaults(self):
        """Testa criação com valores padrão."""

    def test_creation_with_all_fields(self):
        """Testa criação com todos os campos."""

    def test_polygon_validation(self):
        """Testa validação de polígonos."""

class TestMultiAquariumZoneData:
    def test_get_aquarium_existing(self):
        """Testa busca de aquário existente."""

    def test_get_aquarium_not_found(self):
        """Testa busca de aquário inexistente."""

    def test_to_zone_data_conversion(self):
        """Testa conversão para ZoneData."""

class TestAquariumConfigPydantic:
    def test_valid_config(self):
        """Testa configuração válida."""

    def test_invalid_aquarium_id(self):
        """Testa ID de aquário inválido."""

    def test_regex_pattern_extraction(self):
        """Testa extração via regex."""
```

### Arquivos Modificados Fase 1:
- `src/zebtrack/core/detector.py` (adicionar classes)
- `src/zebtrack/ui/wizard/models.py` (estender CalibrationData)
- `tests/core/test_multi_aquarium_models.py` (criar)

---

## Fase 2: Extensão do ZoneManager

### 2.1 Armazenamento Multi-Aquário
**Arquivo:** `src/zebtrack/core/zone_manager.py`

Substituir estrutura de armazenamento para suportar multi-aquário:

```python
class ZoneManager:
    def __init__(self, ...):
        # Substituir zones_by_video para suportar multi-aquário
        self.zones_by_video: dict[str, MultiAquariumZoneData] = {}

    def save_multi_aquarium_zone_data(
        self,
        video_path: str,
        data: MultiAquariumZoneData
    ) -> bool:
        """Salva dados de zona multi-aquário para um vídeo."""

    def get_zone_data_for_video(
        self,
        video_path: str
    ) -> MultiAquariumZoneData | None:
        """Retorna dados de zona para um vídeo."""

    def get_aquarium_count(self, video_path: str) -> int:
        """Retorna número de aquários configurados para um vídeo."""

    def zone_data_to_dict(self, data: MultiAquariumZoneData) -> dict:
        """Serializa MultiAquariumZoneData para dict."""

    def zone_data_from_dict(self, d: dict) -> MultiAquariumZoneData:
        """Deserializa dict para MultiAquariumZoneData."""
```

### 2.2 Serialização JSON (project_config.json)
Nova estrutura no arquivo de projeto:
```json
{
  "zones_by_video": {
    "/path/to/video.mp4": {
      "aquariums": [
        {
          "id": 0,
          "polygon": [[x1,y1], [x2,y2], ...],
          "roi_polygons": [...],
          "roi_names": ["ROI_Centro", "ROI_Borda"],
          "roi_colors": [[255,0,0], [0,255,0]],
          "group": "Controle",
          "subject_id": "S01",
          "day": 1
        },
        {
          "id": 1,
          "polygon": [...],
          "roi_polygons": [...],
          "roi_names": ["ROI_Centro", "ROI_Borda"],
          "roi_colors": [[255,0,0], [0,255,0]],
          "group": "Tratamento",
          "subject_id": "S02",
          "day": 1
        }
      ],
      "video_width": 1280,
      "video_height": 720
    }
  }
}
```

### 2.3 Testes Unitários Fase 2 (Cobertura: 80%+)
**Arquivo:** `tests/core/test_zone_manager_multi_aquarium.py`

```python
class TestZoneManagerMultiAquarium:
    def test_save_multi_aquarium_zone_data(self):
        """Testa salvamento de dados multi-aquário."""

    def test_get_zone_data_for_video(self):
        """Testa recuperação de dados."""

    def test_get_aquarium_count(self):
        """Testa contagem de aquários."""

    def test_serialization_roundtrip(self):
        """Testa serialização e deserialização."""

    def test_save_to_project_file(self):
        """Testa persistência em project_config.json."""

    def test_load_from_project_file(self):
        """Testa carregamento de project_config.json."""
```

### Arquivos Modificados Fase 2:
- `src/zebtrack/core/zone_manager.py`
- `tests/core/test_zone_manager_multi_aquarium.py` (criar)

---

## Fase 3: Auto-Detecção de 2 Aquários

### 3.1 Novo Método em AquariumDetector
**Arquivo:** `src/zebtrack/core/aquarium_detector.py`

```python
def detect_multiple_aquariums(
    self,
    video_path: Path | str,
    expected_count: int = 2,
    stabilization_frames: int = 10
) -> list[np.ndarray]:
    """
    Detecta múltiplos aquários usando análise de contornos.

    Algoritmo:
    1. Ler frames de estabilização e calcular frame médio
    2. Converter para escala de cinza
    3. Aplicar threshold adaptativo
    4. Detecção de bordas (Canny)
    5. Encontrar contornos + aproximar para polígonos (approxPolyDP)
    6. Filtrar por área (cada aquário deve ocupar ~15-45% do frame)
    7. Filtrar por forma (aspect ratio próximo de retângulo)
    8. Validar que não há sobreposição significativa
    9. Ordenar por posição X (aquário esquerdo = índice 0)

    Args:
        video_path: Caminho para o arquivo de vídeo
        expected_count: Número esperado de aquários (fixo em 2)
        stabilization_frames: Frames para calcular média

    Returns:
        Lista de 2 polígonos numpy array (shape: Nx2) ou lista vazia se falhar

    Raises:
        ValueError: Se expected_count != 2
    """
    if expected_count != 2:
        raise ValueError("Apenas 2 aquários são suportados")

    # ... implementação do algoritmo ...
```

### 3.2 Algoritmo de Detecção por Contornos

```python
def _detect_aquariums_by_contours(
    self,
    frame: np.ndarray,
    expected_count: int = 2
) -> list[np.ndarray]:
    """
    Implementação do algoritmo de detecção por contornos.
    """
    # 1. Pré-processamento
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # 2. Threshold adaptativo
    thresh = cv2.adaptiveThreshold(
        blurred, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 2
    )

    # 3. Operações morfológicas para limpar ruído
    kernel = np.ones((5, 5), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    # 4. Encontrar contornos
    contours, _ = cv2.findContours(
        thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    # 5. Filtrar e ordenar candidatos
    frame_area = frame.shape[0] * frame.shape[1]
    candidates = []

    for contour in contours:
        area = cv2.contourArea(contour)
        area_ratio = area / frame_area

        # Cada aquário deve ocupar 15-45% do frame
        if 0.15 <= area_ratio <= 0.45:
            # Aproximar para polígono
            epsilon = 0.02 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)

            # Verificar se é aproximadamente retangular (4-6 vértices)
            if 4 <= len(approx) <= 8:
                x, y, w, h = cv2.boundingRect(approx)
                aspect_ratio = w / h if h > 0 else 0

                # Aspect ratio razoável para aquário
                if 0.5 <= aspect_ratio <= 3.0:
                    candidates.append({
                        'contour': approx,
                        'area': area,
                        'bbox': (x, y, w, h),
                        'center_x': x + w // 2
                    })

    # 6. Selecionar os 2 melhores candidatos
    if len(candidates) < expected_count:
        log.warning(
            "aquarium_detector.insufficient_candidates",
            found=len(candidates),
            expected=expected_count
        )
        return []

    # Ordenar por área (maiores primeiro) e pegar top 2
    candidates.sort(key=lambda c: c['area'], reverse=True)
    selected = candidates[:expected_count]

    # 7. Validar não sobreposição
    if self._check_overlap(selected[0]['bbox'], selected[1]['bbox']):
        log.warning("aquarium_detector.overlapping_detections")
        return []

    # 8. Ordenar por posição X (esquerda primeiro)
    selected.sort(key=lambda c: c['center_x'])

    return [c['contour'].reshape(-1, 2) for c in selected]

def _check_overlap(self, bbox1: tuple, bbox2: tuple, threshold: float = 0.1) -> bool:
    """Verifica se dois bboxes se sobrepõem significativamente."""
    x1, y1, w1, h1 = bbox1
    x2, y2, w2, h2 = bbox2

    # Calcular interseção
    x_left = max(x1, x2)
    y_top = max(y1, y2)
    x_right = min(x1 + w1, x2 + w2)
    y_bottom = min(y1 + h1, y2 + h2)

    if x_right < x_left or y_bottom < y_top:
        return False

    intersection = (x_right - x_left) * (y_bottom - y_top)
    min_area = min(w1 * h1, w2 * h2)

    return intersection / min_area > threshold
```

### 3.3 Fallback para Detecção Manual
Se auto-detecção falhar:
- Emitir evento `ZONE_AUTO_DETECT_FAILED`
- Mostrar mensagem: "Não foi possível detectar 2 aquários automaticamente. Por favor, desenhe manualmente."
- Habilitar modo de desenho manual

### 3.4 Testes Unitários Fase 3 (Cobertura: 80%+)
**Arquivo:** `tests/core/test_aquarium_detector_multi.py`

```python
class TestMultiAquariumDetection:
    @pytest.fixture
    def sample_dual_aquarium_frame(self):
        """Cria frame sintético com 2 aquários."""
        # Frame 1280x720 com 2 retângulos
        frame = np.ones((720, 1280, 3), dtype=np.uint8) * 200
        # Aquário esquerdo
        cv2.rectangle(frame, (50, 50), (550, 670), (0, 0, 0), -1)
        # Aquário direito
        cv2.rectangle(frame, (700, 50), (1200, 670), (0, 0, 0), -1)
        return frame

    def test_detect_two_aquariums_success(self, sample_dual_aquarium_frame):
        """Testa detecção bem-sucedida de 2 aquários."""

    def test_detect_aquariums_ordered_by_x(self, sample_dual_aquarium_frame):
        """Testa que aquários são ordenados por posição X."""

    def test_detect_rejects_overlapping(self):
        """Testa rejeição de aquários sobrepostos."""

    def test_detect_rejects_wrong_count(self):
        """Testa erro quando expected_count != 2."""

    def test_detect_fails_single_aquarium(self):
        """Testa falha quando só há 1 aquário."""

    def test_detect_with_stabilization(self, tmp_path):
        """Testa detecção com múltiplos frames de estabilização."""
```

### Arquivos Modificados Fase 3:
- `src/zebtrack/core/aquarium_detector.py`
- `tests/core/test_aquarium_detector_multi.py` (criar)

---

## Fase 4: UI - Diálogos de Configuração

### 4.1 Diálogo de Confirmação de Quantidade
**Arquivo:** `src/zebtrack/ui/dialogs/multi_aquarium_confirm_dialog.py`

```python
class MultiAquariumConfirmDialog(tk.Toplevel):
    """
    Diálogo exibido quando usuário clica em "Detectar Aquário (Auto)".

    Pergunta: "Quantos aquários existem neste vídeo?"
    Opções:
    - "1 aquário (padrão)"
    - "2 aquários"

    Se 2: Inicia auto-detecção de múltiplos aquários
    Se 1: Continua com detecção padrão
    """

    def __init__(
        self,
        parent: tk.Widget,
        on_confirm: Callable[[int], None],
        on_cancel: Callable[[], None] | None = None
    ):
        super().__init__(parent)
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self._build_ui()

    def _build_ui(self):
        """Constrói a interface do diálogo."""
        self.title("Configuração de Aquários")
        self.geometry("400x200")
        self.resizable(False, False)

        # Frame principal
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Pergunta
        ttk.Label(
            main_frame,
            text="Quantos aquários existem neste vídeo?",
            font=("Segoe UI", 12, "bold")
        ).pack(pady=(0, 15))

        # Opções
        self.aquarium_count = tk.IntVar(value=1)

        ttk.Radiobutton(
            main_frame,
            text="1 aquário (padrão)",
            variable=self.aquarium_count,
            value=1
        ).pack(anchor=tk.W, pady=5)

        ttk.Radiobutton(
            main_frame,
            text="2 aquários (lado a lado)",
            variable=self.aquarium_count,
            value=2
        ).pack(anchor=tk.W, pady=5)

        # Botões
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(20, 0))

        ttk.Button(
            btn_frame,
            text="Cancelar",
            command=self._on_cancel
        ).pack(side=tk.RIGHT, padx=5)

        ttk.Button(
            btn_frame,
            text="Confirmar",
            command=self._on_confirm,
            style="Accent.TButton"
        ).pack(side=tk.RIGHT, padx=5)
```

### 4.2 Diálogo de Atribuição de Aquários
**Arquivo:** `src/zebtrack/ui/dialogs/aquarium_assignment_dialog.py`

```python
class AquariumAssignmentDialog(tk.Toplevel):
    """
    Diálogo para atribuir grupo, sujeito e dia a cada aquário.

    Exibido quando:
    - Auto-detecção encontra 2 aquários
    - Usuário desenha o 2º aquário manualmente

    Layout:
    ┌──────────────────────────────────────────────┐
    │  Configuração dos Aquários                   │
    ├──────────────────────────────────────────────┤
    │  ┌─ Aquário 1 (Esquerda) ─────────────────┐  │
    │  │ Grupo:    [Combobox: Controle     ▼]  │  │
    │  │ Sujeito:  [Entry: S01              ]  │  │
    │  │ Dia:      [Spinbox: 1        ▲▼   ]  │  │
    │  └───────────────────────────────────────┘  │
    │                                              │
    │  ┌─ Aquário 2 (Direita) ──────────────────┐  │
    │  │ Grupo:    [Combobox: Tratamento   ▼]  │  │
    │  │ Sujeito:  [Entry: S02              ]  │  │
    │  │ Dia:      [Spinbox: 1        ▲▼   ]  │  │
    │  └───────────────────────────────────────┘  │
    │                                              │
    │  ☑ Aplicar para todos os vídeos do batch    │
    │                                              │
    │           [Cancelar]  [Confirmar]           │
    └──────────────────────────────────────────────┘
    """

    def __init__(
        self,
        parent: tk.Widget,
        available_groups: list[str],
        video_path: str,
        on_confirm: Callable[[list[AquariumConfig]], None],
        on_cancel: Callable[[], None] | None = None
    ):
        super().__init__(parent)
        self.available_groups = available_groups
        self.video_path = video_path
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self._build_ui()

    def get_configs(self) -> list[AquariumConfig]:
        """Retorna as configurações de ambos os aquários."""
        return [
            AquariumConfig(
                aquarium_id=0,
                group=self.group_var_0.get(),
                subject_id=self.subject_var_0.get(),
                day=self.day_var_0.get()
            ),
            AquariumConfig(
                aquarium_id=1,
                group=self.group_var_1.get(),
                subject_id=self.subject_var_1.get(),
                day=self.day_var_1.get()
            )
        ]
```

### 4.3 Integração com ZoneControlsWidget
**Arquivo:** `src/zebtrack/ui/components/zone_controls.py`

Adicionar:
```python
# Novo frame para seleção de aquário (visível apenas em modo multi-aquário)
self.aquarium_selector_frame = ttk.LabelFrame(
    self.controls_frame,
    text="Aquário Ativo"
)

self.active_aquarium_var = tk.IntVar(value=0)

ttk.Radiobutton(
    self.aquarium_selector_frame,
    text="Aquário 1 (Esquerda)",
    variable=self.active_aquarium_var,
    value=0,
    command=self._on_aquarium_selected
).pack(anchor=tk.W, padx=5, pady=2)

ttk.Radiobutton(
    self.aquarium_selector_frame,
    text="Aquário 2 (Direita)",
    variable=self.active_aquarium_var,
    value=1,
    command=self._on_aquarium_selected
).pack(anchor=tk.W, padx=5, pady=2)

def _on_aquarium_selected(self):
    """Callback quando usuário seleciona um aquário."""
    aquarium_id = self.active_aquarium_var.get()
    self.event_bus.publish(
        Events.ZONE_AQUARIUM_SELECTED,
        {"aquarium_id": aquarium_id}
    )
```

### 4.4 Testes GUI Fase 4 (Cobertura: 80%+)
**Arquivo:** `tests/ui/test_aquarium_dialogs.py`

```python
@pytest.mark.gui
class TestMultiAquariumConfirmDialog:
    def test_dialog_creation(self, tkinter_root):
        """Testa criação do diálogo."""

    def test_single_aquarium_selection(self, tkinter_root):
        """Testa seleção de 1 aquário."""

    def test_dual_aquarium_selection(self, tkinter_root):
        """Testa seleção de 2 aquários."""

    def test_callback_on_confirm(self, tkinter_root):
        """Testa callback de confirmação."""

@pytest.mark.gui
class TestAquariumAssignmentDialog:
    def test_dialog_with_available_groups(self, tkinter_root):
        """Testa diálogo com grupos disponíveis."""

    def test_get_configs_returns_valid_data(self, tkinter_root):
        """Testa retorno de configurações válidas."""

    def test_validation_empty_subject(self, tkinter_root):
        """Testa validação de sujeito vazio."""
```

### Arquivos Criados/Modificados Fase 4:
- `src/zebtrack/ui/dialogs/multi_aquarium_confirm_dialog.py` (criar)
- `src/zebtrack/ui/dialogs/aquarium_assignment_dialog.py` (criar)
- `src/zebtrack/ui/components/zone_controls.py` (modificar)
- `src/zebtrack/ui/dialogs/__init__.py` (adicionar exports)
- `tests/ui/test_aquarium_dialogs.py` (criar)

---

## Fase 5: Sistema de Eventos

### 5.1 Novos Eventos (EventBus v1)
**Arquivo:** `src/zebtrack/ui/events.py`

```python
class Events:
    # ... eventos existentes ...

    # Multi-Aquário Events
    ZONE_MULTI_AUTO_DETECT = "zone:multi_auto_detect"
    ZONE_MULTI_AUTO_DETECT_SUCCESS = "zone:multi_auto_detect_success"
    ZONE_MULTI_AUTO_DETECT_FAILED = "zone:multi_auto_detect_failed"
    ZONE_AQUARIUM_SELECTED = "zone:aquarium_selected"
    ZONE_AQUARIUM_CONFIG_UPDATED = "zone:aquarium_config_updated"
    ZONE_SECOND_AQUARIUM_DRAWN = "zone:second_aquarium_drawn"
```

### 5.2 Payloads de Eventos

| Evento | Payload | Handler |
|--------|---------|---------|
| `ZONE_MULTI_AUTO_DETECT` | `{video_path: str, stabilization_frames: int}` | `ProcessingCoordinator` |
| `ZONE_MULTI_AUTO_DETECT_SUCCESS` | `{video_path: str, polygons: list[list]}` | `ZoneControls`, `CanvasManager` |
| `ZONE_MULTI_AUTO_DETECT_FAILED` | `{video_path: str, reason: str}` | `ZoneControls` |
| `ZONE_AQUARIUM_SELECTED` | `{aquarium_id: int}` | `EventDispatcher`, `CanvasManager` |
| `ZONE_AQUARIUM_CONFIG_UPDATED` | `{aquarium_id: int, config: AquariumConfig}` | `ProjectLifecycleCoordinator` |
| `ZONE_SECOND_AQUARIUM_DRAWN` | `{video_path: str, polygon: list}` | Opens `AquariumAssignmentDialog` |

### 5.3 Handlers nos Coordinators
**Arquivo:** `src/zebtrack/coordinators/processing_coordinator.py`

```python
def _setup_event_handlers(self):
    # ... handlers existentes ...
    self.event_bus.subscribe(
        Events.ZONE_MULTI_AUTO_DETECT,
        self._handle_multi_auto_detect
    )

async def _handle_multi_auto_detect(self, payload: dict):
    """Handler para auto-detecção de múltiplos aquários."""
    video_path = payload.get("video_path")
    stabilization_frames = payload.get("stabilization_frames", 10)

    try:
        polygons = self.aquarium_detector.detect_multiple_aquariums(
            video_path=video_path,
            expected_count=2,
            stabilization_frames=stabilization_frames
        )

        if len(polygons) == 2:
            self.event_bus.publish(
                Events.ZONE_MULTI_AUTO_DETECT_SUCCESS,
                {
                    "video_path": video_path,
                    "polygons": [p.tolist() for p in polygons]
                }
            )
        else:
            self.event_bus.publish(
                Events.ZONE_MULTI_AUTO_DETECT_FAILED,
                {
                    "video_path": video_path,
                    "reason": f"Encontrados {len(polygons)} aquários, esperados 2"
                }
            )
    except Exception as e:
        log.error("multi_auto_detect.failed", error=str(e))
        self.event_bus.publish(
            Events.ZONE_MULTI_AUTO_DETECT_FAILED,
            {"video_path": video_path, "reason": str(e)}
        )
```

**Arquivo:** `src/zebtrack/coordinators/project_lifecycle_coordinator.py`

```python
def _setup_event_handlers(self):
    # ... handlers existentes ...
    self.event_bus.subscribe(
        Events.ZONE_AQUARIUM_CONFIG_UPDATED,
        self._handle_aquarium_config_updated
    )

def _handle_aquarium_config_updated(self, payload: dict):
    """Handler para atualização de configuração de aquário."""
    aquarium_id = payload.get("aquarium_id")
    config = payload.get("config")
    video_path = payload.get("video_path")

    # Atualizar no ZoneManager
    zone_data = self.zone_manager.get_zone_data_for_video(video_path)
    if zone_data:
        aquarium = zone_data.get_aquarium(aquarium_id)
        if aquarium:
            aquarium.group = config.group
            aquarium.subject_id = config.subject_id
            aquarium.day = config.day
            self.zone_manager.save_multi_aquarium_zone_data(video_path, zone_data)
```

### 5.4 Atualizar SYSTEM_INTEGRATION_MAP.md
Adicionar seção "Multi-Aquarium Events" com todos os novos eventos documentados.

### Arquivos Modificados Fase 5:
- `src/zebtrack/ui/events.py`
- `src/zebtrack/ui/components/event_dispatcher.py`
- `src/zebtrack/coordinators/processing_coordinator.py`
- `src/zebtrack/coordinators/project_lifecycle_coordinator.py`
- `docs/architecture/SYSTEM_INTEGRATION_MAP.md`

---

## Fase 6: Detector com Particionamento

### 6.1 Detecção Particionada por Aquário
**Arquivo:** `src/zebtrack/core/detector.py`

```python
class Detector:
    def __init__(self, ...):
        # ... código existente ...

        # Multi-aquário: ByteTrackers separados por aquário
        self._multi_aquarium_mode: bool = False
        self._aquariums: list[AquariumData] = []
        self._byte_trackers: dict[int, BYTETracker] = {}
        self._scaled_aquarium_polygons: dict[int, np.ndarray] = {}

    def set_multi_aquarium_zones(
        self,
        aquariums: list[AquariumData],
        actual_width: int,
        actual_height: int
    ):
        """Configura zonas para múltiplos aquários."""
        self._multi_aquarium_mode = True
        self._aquariums = aquariums

        # Criar ByteTracker separado para cada aquário
        for aq in aquariums:
            self._byte_trackers[aq.id] = BYTETracker(
                track_thresh=self._track_threshold,
                match_thresh=self._match_threshold,
                track_buffer=self._track_buffer
            )

            # Escalar polígono
            scale_x = actual_width / self.base_width
            scale_y = actual_height / self.base_height
            polygon_np = np.array(aq.polygon, dtype=np.float32)
            self._scaled_aquarium_polygons[aq.id] = (
                polygon_np * [scale_x, scale_y]
            ).astype(np.int32)

    def detect_partitioned(
        self,
        frame: np.ndarray
    ) -> dict[int, list[tuple]]:
        """
        Executa detecção e particiona resultados por aquário.

        Returns:
            {aquarium_id: [(x1,y1,x2,y2,conf,track_id,class_id), ...]}
        """
        if not self._multi_aquarium_mode:
            raise RuntimeError("Detector não está em modo multi-aquário")

        # Executar detecção no frame completo
        raw_detections = self.plugin.detect(frame)

        # Particionar por aquário
        partitioned = {aq.id: [] for aq in self._aquariums}

        for det in raw_detections:
            x1, y1, x2, y2, conf, class_id = det[:6]
            centroid = ((x1 + x2) / 2, (y1 + y2) / 2)

            # Verificar em qual aquário está
            for aq in self._aquariums:
                polygon = self._scaled_aquarium_polygons[aq.id]
                if self._point_in_polygon(centroid, polygon):
                    partitioned[aq.id].append(det)
                    break

        # Aplicar tracking separadamente por aquário
        results = {}
        for aq_id, detections in partitioned.items():
            if detections:
                tracker = self._byte_trackers[aq_id]
                tracked = self._apply_tracking(detections, tracker)

                # Offset track_id para evitar colisões
                # Format: aquarium_id * 1000 + local_track_id
                results[aq_id] = [
                    (d[0], d[1], d[2], d[3], d[4],
                     aq_id * 1000 + d[5] if d[5] is not None else None,
                     d[6])
                    for d in tracked
                ]
            else:
                results[aq_id] = []

        return results

    def _point_in_polygon(
        self,
        point: tuple[float, float],
        polygon: np.ndarray
    ) -> bool:
        """Verifica se ponto está dentro do polígono."""
        return cv2.pointPolygonTest(polygon, point, False) >= 0
```

### 6.2 Reset de Trackers por Aquário
```python
def reset_multi_aquarium_tracking(self, aquarium_id: int | None = None):
    """Reseta estado de tracking para um ou todos os aquários."""
    if aquarium_id is not None:
        if aquarium_id in self._byte_trackers:
            self._byte_trackers[aquarium_id] = BYTETracker(...)
    else:
        for aq_id in self._byte_trackers:
            self._byte_trackers[aq_id] = BYTETracker(...)
```

### 6.3 Testes Unitários Fase 6 (Cobertura: 80%+)
**Arquivo:** `tests/core/test_detector_partitioned.py`

```python
class TestDetectorPartitioned:
    @pytest.fixture
    def dual_aquarium_setup(self):
        """Setup com 2 aquários."""
        return [
            AquariumData(
                id=0,
                polygon=[[0, 0], [500, 0], [500, 720], [0, 720]],
                group="Controle"
            ),
            AquariumData(
                id=1,
                polygon=[[600, 0], [1280, 0], [1280, 720], [600, 720]],
                group="Tratamento"
            )
        ]

    def test_set_multi_aquarium_zones(self, detector, dual_aquarium_setup):
        """Testa configuração de zonas multi-aquário."""

    def test_detect_partitioned_correct_assignment(self, detector, dual_aquarium_setup):
        """Testa que detecções são atribuídas ao aquário correto."""

    def test_track_ids_unique_across_aquariums(self, detector, dual_aquarium_setup):
        """Testa que track_ids são únicos entre aquários."""

    def test_track_id_offset_format(self, detector, dual_aquarium_setup):
        """Testa formato de offset (aq_id * 1000 + local_id)."""

    def test_detection_on_boundary_assigned_correctly(self, detector, dual_aquarium_setup):
        """Testa detecção na borda entre aquários."""

    def test_reset_tracking_single_aquarium(self, detector, dual_aquarium_setup):
        """Testa reset de tracking para um aquário."""

    def test_reset_tracking_all_aquariums(self, detector, dual_aquarium_setup):
        """Testa reset de tracking para todos os aquários."""
```

### Arquivos Modificados Fase 6:
- `src/zebtrack/core/detector.py`
- `tests/core/test_detector_partitioned.py` (criar)

---

## Fase 7: Recorder Multi-Aquário

### 7.1 Extensão do Schema Parquet
**Arquivo:** `src/zebtrack/io/recorder.py`

```python
class Recorder:
    def __init__(self, ...):
        # ... código existente ...
        self._multi_aquarium_mode: bool = False
        self._aquarium_recorders: dict[int, "Recorder"] = {}

    def start_recording_multi_aquarium(
        self,
        output_folder: str,
        width: int,
        height: int,
        zones_by_aquarium: dict[int, ZoneData],
        fps: float = 30.0,
        write_video: bool = True
    ) -> bool:
        """
        Inicia gravação para múltiplos aquários.

        Cria estrutura:
        output_folder/
        ├── aquarium_0/
        │   └── 3_CoordMovimento_*.parquet
        └── aquarium_1/
            └── 3_CoordMovimento_*.parquet
        """
        self._multi_aquarium_mode = True

        for aq_id, zone_data in zones_by_aquarium.items():
            aq_folder = Path(output_folder) / f"aquarium_{aq_id}"
            aq_folder.mkdir(parents=True, exist_ok=True)

            # Criar recorder separado para cada aquário
            aq_recorder = Recorder(settings_obj=self.settings)
            success = aq_recorder.start_recording(
                output_folder=str(aq_folder),
                width=width,
                height=height,
                zones=zone_data,
                fps=fps,
                write_video=write_video
            )

            if success:
                self._aquarium_recorders[aq_id] = aq_recorder
            else:
                log.error("recorder.multi_aquarium.failed", aquarium_id=aq_id)
                return False

        return True

    def write_partitioned_detection_data(
        self,
        timestamp: float,
        frame_number: int,
        partitioned_detections: dict[int, list[tuple]]
    ):
        """Escreve dados de detecção particionados por aquário."""
        if not self._multi_aquarium_mode:
            raise RuntimeError("Recorder não está em modo multi-aquário")

        for aq_id, detections in partitioned_detections.items():
            if aq_id in self._aquarium_recorders:
                recorder = self._aquarium_recorders[aq_id]
                recorder.write_detection_data(timestamp, frame_number, detections)

    def stop_recording_multi_aquarium(self):
        """Para gravação de todos os aquários."""
        for aq_id, recorder in self._aquarium_recorders.items():
            try:
                recorder.stop_recording()
            except Exception as e:
                log.error(
                    "recorder.multi_aquarium.stop_failed",
                    aquarium_id=aq_id,
                    error=str(e)
                )

        self._aquarium_recorders.clear()
        self._multi_aquarium_mode = False
```

### 7.2 Adição da Coluna aquarium_id
Para cada arquivo Parquet individual, adicionar coluna `aquarium_id`:

```python
def _determine_parquet_columns(self, aquarium_id: int | None = None) -> list[str]:
    columns = [
        "timestamp",
        "frame",
        "track_id",
        "x1", "y1", "x2", "y2",
        "confidence",
        "x_center_px", "y_center_px"
    ]

    if aquarium_id is not None:
        columns.insert(3, "aquarium_id")

    if self._calibration is not None:
        columns.extend(["x_cm", "y_cm"])

    return columns
```

### 7.3 Testes Unitários Fase 7 (Cobertura: 80%+)
**Arquivo:** `tests/io/test_recorder_multi_aquarium.py`

```python
class TestRecorderMultiAquarium:
    def test_start_recording_creates_folders(self, tmp_path):
        """Testa criação de pastas por aquário."""

    def test_write_partitioned_data(self, tmp_path):
        """Testa escrita de dados particionados."""

    def test_parquet_schema_includes_aquarium_id(self, tmp_path):
        """Testa que schema inclui aquarium_id."""

    def test_stop_recording_closes_all(self, tmp_path):
        """Testa que stop fecha todos os recorders."""

    def test_video_output_per_aquarium(self, tmp_path):
        """Testa geração de vídeo por aquário."""
```

### Arquivos Modificados Fase 7:
- `src/zebtrack/io/recorder.py`
- `tests/io/test_recorder_multi_aquarium.py` (criar)

---

## Fase 8: ProjectManager - Resolução de Diretórios

### 8.1 Método para Resolução Multi-Aquário
**Arquivo:** `src/zebtrack/core/project_manager.py`

```python
def resolve_multi_aquarium_results_directories(
    self,
    experiment_id: str,
    aquarium_configs: list[AquariumConfig]
) -> dict[int, Path]:
    """
    Resolve diretórios de resultados para múltiplos aquários.

    Estrutura: {project_root}/Grupo_{group}/Dia_{day}/Sujeito_{subject_id}/

    Args:
        experiment_id: ID do experimento/vídeo
        aquarium_configs: Lista de configurações de aquários

    Returns:
        {aquarium_id: Path} mapeando cada aquário para seu diretório
    """
    result = {}

    for config in aquarium_configs:
        # Construir caminho hierárquico
        group_component = self._format_group_component({"group": config.group})
        day_component = self._format_day_component({"day": config.day})
        subject_component = self._format_subject_component(
            {"subject_id": config.subject_id}
        )

        results_dir = (
            self._project_root /
            group_component /
            day_component /
            subject_component
        )

        results_dir.mkdir(parents=True, exist_ok=True)
        result[config.aquarium_id] = results_dir

    return result

def register_multi_aquarium_outputs(
    self,
    experiment_id: str,
    outputs_by_aquarium: dict[int, dict]
):
    """
    Registra outputs de múltiplos aquários no projeto.

    Args:
        experiment_id: ID do experimento/vídeo
        outputs_by_aquarium: {aquarium_id: {parquet_files: {...}, results_dir: str}}
    """
    video_entry = self.find_video_entry(experiment_id)
    if video_entry:
        video_entry["multi_aquarium_outputs"] = outputs_by_aquarium
        self.save_project()
```

### 8.2 Testes Unitários Fase 8 (Cobertura: 80%+)
**Arquivo:** `tests/core/test_project_manager_multi_aquarium.py`

```python
class TestProjectManagerMultiAquarium:
    def test_resolve_directories_creates_structure(self, project_manager):
        """Testa criação de estrutura de diretórios."""

    def test_different_groups_different_paths(self, project_manager):
        """Testa que grupos diferentes geram caminhos diferentes."""

    def test_register_outputs(self, project_manager):
        """Testa registro de outputs."""

    def test_path_sanitization(self, project_manager):
        """Testa sanitização de nomes de pasta."""
```

### Arquivos Modificados Fase 8:
- `src/zebtrack/core/project_manager.py`
- `tests/core/test_project_manager_multi_aquarium.py` (criar)

---

## Fase 9: Wizard - Configuração Multi-Aquário

### 9.1 Extensão do Calibration Step
**Arquivo:** `src/zebtrack/ui/wizard/calibration_step.py`

Adicionar seção colapsável "Modo Multi-Aquário":

```python
def _build_multi_aquarium_section(self):
    """Constrói seção de configuração multi-aquário."""

    # Frame principal colapsável
    self.multi_aq_frame = ttk.LabelFrame(
        self.content_frame,
        text="Configuração Multi-Aquário",
        padding=10
    )

    # Toggle de ativação
    self.multi_aq_enabled = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        self.multi_aq_frame,
        text="Este projeto contém vídeos com 2 aquários",
        variable=self.multi_aq_enabled,
        command=self._on_multi_aq_toggled
    ).pack(anchor=tk.W)

    # Frame de configuração (visível apenas quando habilitado)
    self.multi_aq_config_frame = ttk.Frame(self.multi_aq_frame)

    # Aquário 1
    aq1_frame = ttk.LabelFrame(self.multi_aq_config_frame, text="Aquário 1 (Esquerda)")
    ttk.Label(aq1_frame, text="Grupo:").grid(row=0, column=0, sticky=tk.W, pady=2)
    self.aq1_group = ttk.Combobox(aq1_frame, values=self._get_available_groups())
    self.aq1_group.grid(row=0, column=1, sticky=tk.EW, pady=2)
    ttk.Label(aq1_frame, text="Sujeito:").grid(row=1, column=0, sticky=tk.W, pady=2)
    self.aq1_subject = ttk.Entry(aq1_frame)
    self.aq1_subject.grid(row=1, column=1, sticky=tk.EW, pady=2)
    aq1_frame.pack(fill=tk.X, pady=5)

    # Aquário 2
    aq2_frame = ttk.LabelFrame(self.multi_aq_config_frame, text="Aquário 2 (Direita)")
    ttk.Label(aq2_frame, text="Grupo:").grid(row=0, column=0, sticky=tk.W, pady=2)
    self.aq2_group = ttk.Combobox(aq2_frame, values=self._get_available_groups())
    self.aq2_group.grid(row=0, column=1, sticky=tk.EW, pady=2)
    ttk.Label(aq2_frame, text="Sujeito:").grid(row=1, column=0, sticky=tk.W, pady=2)
    self.aq2_subject = ttk.Entry(aq2_frame)
    self.aq2_subject.grid(row=1, column=1, sticky=tk.EW, pady=2)
    aq2_frame.pack(fill=tk.X, pady=5)

    # Regex Builder
    self._build_regex_section()

def _build_regex_section(self):
    """Constrói seção de configuração de regex."""
    regex_frame = ttk.LabelFrame(
        self.multi_aq_config_frame,
        text="Extração Automática de Metadados (Regex)"
    )

    # Campo de padrão
    ttk.Label(regex_frame, text="Padrão:").grid(row=0, column=0, sticky=tk.W)
    self.regex_pattern = ttk.Entry(regex_frame, width=50)
    self.regex_pattern.grid(row=0, column=1, sticky=tk.EW, padx=5)
    self.regex_pattern.bind("<KeyRelease>", self._update_regex_preview)

    # Preview
    ttk.Label(regex_frame, text="Preview:").grid(row=1, column=0, sticky=tk.NW)
    self.regex_preview = ttk.Label(
        regex_frame,
        text="(Digite um padrão para ver o resultado)",
        foreground="gray"
    )
    self.regex_preview.grid(row=1, column=1, sticky=tk.W, padx=5)

    # Exemplo de arquivo
    ttk.Label(regex_frame, text="Arquivo de teste:").grid(row=2, column=0, sticky=tk.W)
    self.regex_test_file = ttk.Entry(regex_frame, width=50)
    self.regex_test_file.grid(row=2, column=1, sticky=tk.EW, padx=5)
    self.regex_test_file.bind("<KeyRelease>", self._update_regex_preview)

    # Exemplo de padrão
    example_text = "Exemplo: (?P<group>\\w+)_D(?P<day>\\d+)_S(?P<subj1>\\d+)_S(?P<subj2>\\d+)"
    ttk.Label(regex_frame, text=example_text, foreground="gray").grid(
        row=3, column=0, columnspan=2, sticky=tk.W, pady=(10, 0)
    )

    regex_frame.pack(fill=tk.X, pady=10)

def _update_regex_preview(self, event=None):
    """Atualiza preview do regex em tempo real."""
    pattern = self.regex_pattern.get()
    test_file = self.regex_test_file.get() or "Ctrl_D01_S01_S02.mp4"

    if not pattern:
        self.regex_preview.config(text="(Digite um padrão)", foreground="gray")
        return

    try:
        import re
        match = re.match(pattern, test_file)
        if match:
            groups = match.groupdict()
            preview_parts = [f"{k}: {v}" for k, v in groups.items()]
            self.regex_preview.config(
                text=" | ".join(preview_parts),
                foreground="green"
            )
        else:
            self.regex_preview.config(text="Sem correspondência", foreground="red")
    except re.error as e:
        self.regex_preview.config(text=f"Erro: {e}", foreground="red")
```

### 9.2 Validação no WizardService
**Arquivo:** `src/zebtrack/core/wizard_service.py`

```python
def validate_multi_aquarium_config(
    self,
    config: MultiAquariumData,
    sample_filenames: list[str] | None = None
) -> tuple[bool, list[str]]:
    """
    Valida configuração multi-aquário.

    Checks:
    1. Se habilitado, deve ter 2 aquários configurados
    2. Grupos não podem ser iguais (opcional - warning)
    3. Se regex fornecido, deve ser válido
    4. Se regex fornecido, deve extrair campos esperados
    """
    errors = []

    if not config.enabled:
        return True, []

    # Check 1: Quantidade de aquários
    if len(config.aquarium_configs) != 2:
        errors.append("Exatamente 2 aquários devem ser configurados")

    # Check 2: Validar regex se fornecido
    if config.regex_pattern:
        try:
            import re
            compiled = re.compile(config.regex_pattern)
            groups = compiled.groupindex.keys()

            # Verificar se extrai os campos necessários
            expected = {config.regex_group_field, config.regex_subject_field}
            if not expected.issubset(groups):
                missing = expected - set(groups)
                errors.append(f"Regex não captura: {missing}")

            # Testar em arquivos de amostra
            if sample_filenames:
                for filename in sample_filenames[:3]:
                    match = compiled.match(filename)
                    if not match:
                        errors.append(f"Regex não corresponde a: {filename}")
                        break

        except re.error as e:
            errors.append(f"Padrão regex inválido: {e}")

    return len(errors) == 0, errors
```

### 9.3 Testes Fase 9 (Cobertura: 80%+)
**Arquivo:** `tests/ui/wizard/test_multi_aquarium_wizard.py`

```python
@pytest.mark.gui
class TestMultiAquariumWizardStep:
    def test_toggle_enables_config_section(self, tkinter_root):
        """Testa que toggle habilita seção de configuração."""

    def test_regex_preview_updates(self, tkinter_root):
        """Testa atualização em tempo real do preview."""

    def test_regex_error_handling(self, tkinter_root):
        """Testa tratamento de erros de regex."""

    def test_get_data_returns_valid_config(self, tkinter_root):
        """Testa retorno de configuração válida."""

class TestWizardServiceMultiAquariumValidation:
    def test_validate_disabled_config(self, wizard_service):
        """Testa validação de config desabilitada."""

    def test_validate_missing_aquariums(self, wizard_service):
        """Testa validação sem aquários."""

    def test_validate_invalid_regex(self, wizard_service):
        """Testa validação de regex inválido."""

    def test_validate_regex_missing_groups(self, wizard_service):
        """Testa validação de regex sem grupos necessários."""

    def test_validate_success(self, wizard_service):
        """Testa validação bem-sucedida."""
```

### Arquivos Modificados Fase 9:
- `src/zebtrack/ui/wizard/calibration_step.py`
- `src/zebtrack/core/wizard_service.py`
- `tests/ui/wizard/test_multi_aquarium_wizard.py` (criar)

---

## Fase 10: Analysis Service Multi-Aquário

### 10.1 Análise Separada por Aquário
**Arquivo:** `src/zebtrack/analysis/analysis_service.py`

```python
def run_multi_aquarium_analysis(
    self,
    aquarium_data_map: dict[int, tuple[pd.DataFrame, AquariumData]],
    fps: float = 30.0,
    **kwargs
) -> dict[int, AnalysisResult]:
    """
    Executa análise completa para cada aquário.

    Args:
        aquarium_data_map: {aquarium_id: (trajectory_df, aquarium_data)}
        fps: Frames por segundo

    Returns:
        {aquarium_id: AnalysisResult}
    """
    results = {}

    for aq_id, (trajectory_df, aq_data) in aquarium_data_map.items():
        log.info(
            "analysis.multi_aquarium.starting",
            aquarium_id=aq_id,
            group=aq_data.group,
            subject=aq_data.subject_id
        )

        try:
            # Converter AquariumData para formato esperado
            zone_data = ZoneData(
                polygon=aq_data.polygon,
                roi_polygons=aq_data.roi_polygons,
                roi_names=aq_data.roi_names,
                roi_colors=aq_data.roi_colors
            )

            result = self.run_full_analysis(
                trajectory_df=trajectory_df,
                arena_polygon_px=aq_data.polygon,
                roi_polygons_px=aq_data.roi_polygons,
                roi_names=aq_data.roi_names,
                fps=fps,
                **kwargs
            )

            results[aq_id] = result

        except Exception as e:
            log.error(
                "analysis.multi_aquarium.failed",
                aquarium_id=aq_id,
                error=str(e)
            )
            results[aq_id] = None

    return results
```

### 10.2 Reporter Multi-Aquário
**Arquivo:** `src/zebtrack/analysis/reporter.py`

```python
def export_multi_aquarium_reports(
    self,
    results_by_aquarium: dict[int, AnalysisResult],
    output_dirs_by_aquarium: dict[int, Path],
    base_name: str,
    aquarium_configs: list[AquariumConfig]
) -> dict[int, dict]:
    """
    Exporta relatórios separados para cada aquário.

    Returns:
        {aquarium_id: {summary_path: str, report_path: str}}
    """
    output_paths = {}

    for aq_id, result in results_by_aquarium.items():
        if result is None:
            continue

        output_dir = output_dirs_by_aquarium.get(aq_id)
        if not output_dir:
            continue

        config = next(
            (c for c in aquarium_configs if c.aquarium_id == aq_id),
            None
        )

        # Adicionar metadata ao nome
        suffix = f"_aq{aq_id}_{config.group}_{config.subject_id}" if config else f"_aq{aq_id}"

        # Exportar summary
        summary_path = self.export_summary_data(
            result=result,
            output_folder=str(output_dir),
            base_name=f"{base_name}{suffix}"
        )

        # Exportar report
        report_path = self.export_individual_report(
            result=result,
            output_folder=str(output_dir),
            base_name=f"{base_name}{suffix}"
        )

        output_paths[aq_id] = {
            "summary_path": summary_path,
            "report_path": report_path
        }

    return output_paths
```

### 10.3 Testes Fase 10 (Cobertura: 80%+)
**Arquivo:** `tests/analysis/test_analysis_multi_aquarium.py`

```python
class TestMultiAquariumAnalysis:
    @pytest.fixture
    def dual_trajectory_data(self):
        """Fixture com trajetórias de 2 aquários."""
        # Gerar dados de trajetória sintéticos

    def test_run_multi_aquarium_analysis(self, analysis_service, dual_trajectory_data):
        """Testa análise de múltiplos aquários."""

    def test_results_per_aquarium(self, analysis_service, dual_trajectory_data):
        """Testa que resultados são gerados por aquário."""

    def test_handles_aquarium_failure(self, analysis_service):
        """Testa tratamento de falha em um aquário."""

class TestMultiAquariumReporter:
    def test_export_separate_reports(self, reporter, tmp_path):
        """Testa exportação de relatórios separados."""

    def test_output_paths_correct(self, reporter, tmp_path):
        """Testa que caminhos de saída estão corretos."""
```

### Arquivos Modificados Fase 10:
- `src/zebtrack/analysis/analysis_service.py`
- `src/zebtrack/analysis/reporter.py`
- `tests/analysis/test_analysis_multi_aquarium.py` (criar)

---

## Fase 11: Visualização Unificada

### 11.1 Overlay com 2 Aquários
**Arquivo:** `src/zebtrack/ui/components/canvas/canvas_manager.py`

```python
# Cores para cada aquário
AQUARIUM_COLORS = {
    0: {"border": "#0066CC", "fill": "#0066CC33", "text": "Aquário 1"},
    1: {"border": "#00CC66", "fill": "#00CC6633", "text": "Aquário 2"}
}

def draw_multi_aquarium_overlay(
    self,
    frame: np.ndarray,
    zone_data: MultiAquariumZoneData,
    detections_by_aquarium: dict[int, list[tuple]] | None = None
) -> np.ndarray:
    """
    Desenha overlay com múltiplos aquários.

    - Cada aquário tem borda com cor distinta
    - Label no canto superior indicando aquário e grupo
    - Detecções coloridas por aquário
    """
    overlay = frame.copy()

    for aq in zone_data.aquariums:
        colors = AQUARIUM_COLORS.get(aq.id, AQUARIUM_COLORS[0])

        # Desenhar polígono do aquário
        polygon = np.array(aq.polygon, dtype=np.int32)
        cv2.polylines(overlay, [polygon], True, self._hex_to_bgr(colors["border"]), 2)

        # Label do aquário
        label = f"{colors['text']} - {aq.group}"
        x, y = polygon[0]  # Canto superior esquerdo
        cv2.putText(
            overlay, label,
            (x + 5, y + 20),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6,
            self._hex_to_bgr(colors["border"]), 2
        )

        # Desenhar ROIs deste aquário
        for i, roi_polygon in enumerate(aq.roi_polygons):
            roi_np = np.array(roi_polygon, dtype=np.int32)
            cv2.polylines(overlay, [roi_np], True, aq.roi_colors[i], 1)

            if i < len(aq.roi_names):
                cx, cy = self._polygon_centroid(roi_np)
                cv2.putText(
                    overlay, aq.roi_names[i],
                    (cx - 20, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    aq.roi_colors[i], 1
                )

        # Desenhar detecções deste aquário
        if detections_by_aquarium and aq.id in detections_by_aquarium:
            for det in detections_by_aquarium[aq.id]:
                x1, y1, x2, y2, conf, track_id, _ = det
                color = self._hex_to_bgr(colors["border"])
                cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)

                if track_id is not None:
                    # Mostrar track_id local (sem offset)
                    local_id = track_id % 1000
                    cv2.putText(
                        overlay, f"ID:{local_id}",
                        (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        color, 1
                    )

    return overlay
```

### 11.2 Integração com gui.py
**Arquivo:** `src/zebtrack/ui/gui.py`

Modificar `_draw_detection_overlay()` para usar o novo método quando em modo multi-aquário.

### 11.3 Testes GUI Fase 11
- Teste visual de renderização com 2 aquários
- Teste de cores corretas por aquário
- Teste de labels corretos

### Arquivos Modificados Fase 11:
- `src/zebtrack/ui/components/canvas/canvas_manager.py`
- `src/zebtrack/ui/gui.py`

---

## Fase 12: Testes de Integração

### 12.1 Testes E2E Multi-Aquário
**Arquivo:** `tests/integration/test_multi_aquarium_e2e.py`

```python
@pytest.mark.integration
class TestMultiAquariumE2E:
    @pytest.fixture
    def dual_aquarium_video(self, tmp_path):
        """Cria vídeo sintético com 2 aquários."""
        # Gerar vídeo de teste com 2 regiões retangulares distintas

    def test_complete_workflow(self, dual_aquarium_video, tmp_path):
        """
        Testa fluxo completo:
        1. Criar projeto via wizard com multi-aquário
        2. Auto-detectar 2 aquários
        3. Configurar grupos/sujeitos
        4. Processar vídeo
        5. Verificar outputs por aquário
        6. Executar análise
        7. Verificar relatórios separados
        """

    def test_auto_detection(self, dual_aquarium_video):
        """Testa auto-detecção funciona end-to-end."""

    def test_output_folder_structure(self, dual_aquarium_video, tmp_path):
        """
        Verifica estrutura:
        project/
        ├── Grupo_Controle/
        │   └── Dia_01/
        │       └── Sujeito_01/
        │           └── *.parquet, *.xlsx, *.docx
        └── Grupo_Tratamento/
            └── Dia_01/
                └── Sujeito_02/
                    └── *.parquet, *.xlsx, *.docx
        """

    def test_parquet_data_integrity(self, dual_aquarium_video, tmp_path):
        """Verifica integridade dos dados nos parquets."""

    def test_analysis_results_per_aquarium(self, dual_aquarium_video, tmp_path):
        """Verifica que análise gera resultados separados."""
```

### 12.2 Arquivos Criados Fase 12:
- `tests/integration/test_multi_aquarium_e2e.py`

---

## Fase 13: Documentação

### 13.1 Atualizações Obrigatórias

| Documento | Atualizações |
|-----------|-------------|
| `CLAUDE.md` | Nova seção "Multi-Aquário Support", atualizar ZoneData |
| `docs/architecture/SYSTEM_INTEGRATION_MAP.md` | Novos eventos e payloads |
| `docs/architecture/ARCHITECTURE.md` | Diagrama com fluxo multi-aquário |
| `docs/guides/developer/DEVELOPER_GUIDE_WIZARD.md` | Seção do wizard multi-aquário |
| `docs/reference/COORDINATE_SYSTEMS.md` | Coordenadas por aquário |
| `docs/wiki/2_Full_Tutorial.md` | Tutorial para vídeos com 2 aquários |
| `README_TESTS.md` | Novos markers e testes |

### 13.2 ADR (Architecture Decision Record)
**Arquivo:** `docs/decisions/ADR-001-multi-aquarium-support.md`

```markdown
# ADR-001: Suporte Multi-Aquário

## Status
Aceito

## Contexto
Necessidade de analisar vídeos contendo 2 aquários separados, cada um com 1 animal,
permitindo grupos diferentes por aquário.

## Decisão
1. Suporte fixo para 2 aquários (não N genérico)
2. ByteTrackers separados por aquário para tracking independente
3. Track IDs com offset (aquarium_id * 1000 + local_id)
4. Arquivos de saída separados por sujeito na hierarquia Grupo/Dia/Sujeito
5. Auto-detecção por análise de contornos

## Consequências
- Simplificação do código por limitar a 2 aquários
- Melhor organização de outputs por sujeito
- Tracking independente evita interferência entre animais
```

---

## Fase 14: Atualização de Testes Existentes

### 14.1 Testes que Precisam de Adaptação

Verificar e ajustar:
- `tests/core/test_detector.py` - Adicionar testes para modo não-multi
- `tests/io/test_recorder.py` - Garantir funcionamento sem multi-aquário
- `tests/core/test_zone_manager.py` - Adaptar para novo formato
- `tests/analysis/test_analysis_service.py` - Manter funcionamento padrão

### 14.2 Fixtures Atualizadas
**Arquivo:** `tests/conftest.py`

```python
@pytest.fixture
def single_aquarium_zone_data():
    """ZoneData padrão para testes de 1 aquário."""
    return MultiAquariumZoneData(
        aquariums=[
            AquariumData(
                id=0,
                polygon=[[0, 0], [1280, 0], [1280, 720], [0, 720]],
                roi_polygons=[],
                roi_names=[],
                roi_colors=[],
                group="Default",
                subject_id="S01",
                day=1
            )
        ],
        video_width=1280,
        video_height=720
    )

@pytest.fixture
def multi_aquarium_zone_data():
    """MultiAquariumZoneData para testes de 2 aquários."""
    return MultiAquariumZoneData(
        aquariums=[
            AquariumData(
                id=0,
                polygon=[[0, 0], [600, 0], [600, 720], [0, 720]],
                roi_polygons=[],
                roi_names=[],
                roi_colors=[],
                group="Controle",
                subject_id="S01",
                day=1
            ),
            AquariumData(
                id=1,
                polygon=[[680, 0], [1280, 0], [1280, 720], [680, 720]],
                roi_polygons=[],
                roi_names=[],
                roi_colors=[],
                group="Tratamento",
                subject_id="S02",
                day=1
            )
        ],
        video_width=1280,
        video_height=720
    )
```

---

## Fase 15: Validação Final e Merge

### 15.1 Checklist de Validação
- [ ] Todos os testes passam: `poetry run pytest -m "" -n0`
- [ ] Ruff sem erros: `poetry run ruff check .`
- [ ] Cobertura >= 80%: `poetry run pytest --cov --cov-fail-under=80`
- [ ] Projeto novo com 2 aquários funciona completamente
- [ ] Auto-detecção de 2 aquários funciona
- [ ] Wizard configura multi-aquário corretamente
- [ ] Regex extrai metadados corretamente
- [ ] Outputs organizados em pastas corretas
- [ ] Relatórios gerados por sujeito
- [ ] Documentação atualizada
- [ ] Pre-commit passa: `poetry run pre-commit run --all-files`

### 15.2 Merge para Main
```bash
git checkout main
git merge feature/multi-aquarium-support
git tag v3.1.0-multi-aquarium
git push origin main --tags
```

---

## Arquivos Críticos (Resumo Completo)

### Criar (13 arquivos):
1. `src/zebtrack/ui/dialogs/aquarium_assignment_dialog.py`
2. `src/zebtrack/ui/dialogs/multi_aquarium_confirm_dialog.py`
3. `tests/core/test_multi_aquarium_models.py`
4. `tests/core/test_zone_manager_multi_aquarium.py`
5. `tests/core/test_aquarium_detector_multi.py`
6. `tests/core/test_detector_partitioned.py`
7. `tests/io/test_recorder_multi_aquarium.py`
8. `tests/core/test_project_manager_multi_aquarium.py`
9. `tests/ui/wizard/test_multi_aquarium_wizard.py`
10. `tests/ui/test_aquarium_dialogs.py`
11. `tests/analysis/test_analysis_multi_aquarium.py`
12. `tests/integration/test_multi_aquarium_e2e.py`
13. `docs/decisions/ADR-001-multi-aquarium-support.md`

### Modificar (20 arquivos):
1. `src/zebtrack/core/detector.py`
2. `src/zebtrack/ui/wizard/models.py`
3. `src/zebtrack/core/zone_manager.py`
4. `src/zebtrack/core/aquarium_detector.py`
5. `src/zebtrack/ui/components/zone_controls.py`
6. `src/zebtrack/ui/events.py`
7. `src/zebtrack/ui/components/event_dispatcher.py`
8. `src/zebtrack/coordinators/processing_coordinator.py`
9. `src/zebtrack/coordinators/project_lifecycle_coordinator.py`
10. `src/zebtrack/io/recorder.py`
11. `src/zebtrack/core/project_manager.py`
12. `src/zebtrack/ui/wizard/calibration_step.py`
13. `src/zebtrack/core/wizard_service.py`
14. `src/zebtrack/analysis/analysis_service.py`
15. `src/zebtrack/analysis/reporter.py`
16. `src/zebtrack/ui/components/canvas/canvas_manager.py`
17. `src/zebtrack/ui/gui.py`
18. `src/zebtrack/ui/dialogs/__init__.py`
19. `tests/conftest.py`
20. `CLAUDE.md`
21. `docs/architecture/SYSTEM_INTEGRATION_MAP.md`

---

## Riscos e Mitigações

| Risco | Impacto | Probabilidade | Mitigação |
|-------|---------|---------------|-----------|
| Colisão de track_id entre aquários | Médio | Médio | Offset de IDs por aquário (id * 1000) |
| Auto-detecção falha em vídeos complexos | Médio | Médio | Fallback para desenho manual |
| Performance degradada com 2 ByteTrackers | Baixo | Médio | Inicialização lazy, profiling |
| Complexidade do Wizard aumenta | Médio | Baixo | UI progressiva, seção colapsável |
| Regex incorreto quebra extração | Médio | Médio | Preview em tempo real, validação |

---

## Notas de Implementação

1. **Incremental**: Cada fase deve ser testável independentemente
2. **Documentação First**: Atualizar docs junto com código
3. **Testes**: Mínimo 80% de cobertura em código novo
4. **Performance**: Profiling antes de otimizações prematuras
5. **Branch Feature**: Todo código na branch `feature/multi-aquarium-support`
6. **Commits Atômicos**: Um commit por sub-tarefa dentro de cada fase
