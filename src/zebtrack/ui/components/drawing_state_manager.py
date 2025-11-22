class DrawingStateManager:
    """Gerencia estado de desenho de polígonos e pilhas undo/redo."""

    def __init__(self):
        # Estado de modo de desenho
        self.mode: str | None = None  # "polygon", "circle", None
        self.drawing_type: str | None = None  # "arena", "roi"

        # Pontos de polígono (3 sistemas de coordenadas)
        self.canvas_points: list[tuple[float, float]] = []
        self.video_points: list[tuple[float, float]] = []
        self.current_points: list[tuple[float, float]] = []

        # Pilhas Undo/Redo
        self._history: list[tuple] = []
        self._redo_stack: list[tuple] = []

        # Estado de edição de vértice
        self.dragging_vertex_index: int | None = None
        self.vertex_hover_index: int | None = None
        self.vertex_hover_tolerance: int = 10

        # Estado de desenho de círculo
        self.circle_center: tuple[float, float] | None = None

    def start_polygon_drawing(self):
        """Inicializa modo de desenho de polígono."""
        self.mode = "polygon"
        self.clear_points()
        self._history.clear()
        self._redo_stack.clear()

    def add_point(self, canvas_pt, video_pt, current_pt):
        """Adiciona ponto ao polígono."""
        # Salva em pilha undo antes de adicionar
        self._history.append((
            list(self.canvas_points),
            list(self.video_points),
            list(self.current_points)
        ))
        self._redo_stack.clear()

        self.canvas_points.append(canvas_pt)
        self.video_points.append(video_pt)
        self.current_points.append(current_pt)

    def undo(self) -> bool:
        """Desfaz último ponto. Retorna True se bem-sucedido."""
        if not self._history:
            return False

        # Salva estado atual para redo
        self._redo_stack.append((
            self.canvas_points.copy(),
            self.video_points.copy(),
            self.current_points.copy()
        ))

        # Restaura estado anterior
        self.canvas_points, self.video_points, self.current_points = self._history.pop()
        return True

    def redo(self) -> bool:
        """Refaz último ponto desfeito. Retorna True se bem-sucedido."""
        if not self._redo_stack:
            return False

        # Salva atual para history
        self._history.append((
            self.canvas_points.copy(),
            self.video_points.copy(),
            self.current_points.copy()
        ))

        # Restaura estado redo
        self.canvas_points, self.video_points, self.current_points = self._redo_stack.pop()
        return True

    def clear_points(self):
        """Limpa todos os pontos."""
        self.canvas_points.clear()
        self.video_points.clear()
        self.current_points.clear()

    def has_points(self) -> bool:
        """Verifica se há pontos desenhados."""
        return len(self.current_points) > 0

    def point_count(self) -> int:
        """Retorna número de pontos."""
        return len(self.current_points)
