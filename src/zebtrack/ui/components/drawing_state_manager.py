class DrawingStateManager:
    """Manages polygon drawing state and undo/redo stacks."""

    def __init__(self):
        # Drawing mode state
        self.mode: str | None = None  # "polygon", "circle", None
        self.drawing_type: str | None = None  # "arena", "roi"

        # Polygon points (3 coordinate systems)
        self.canvas_points: list[tuple[float, float]] = []
        self.video_points: list[tuple[float, float]] = []
        self.current_points: list[tuple[float, float]] = []

        # Undo/Redo stacks
        self._history: list[tuple] = []
        self._redo_stack: list[tuple] = []

        # Vertex editing state
        self.dragging_vertex_index: int | None = None
        self.vertex_hover_index: int | None = None
        self.vertex_hover_tolerance: int = 10

        # Circle drawing state
        self.circle_center: tuple[float, float] | None = None

    def start_polygon_drawing(self):
        """Initialize polygon drawing mode."""
        self.mode = "polygon"
        self.clear_points()
        self._history.clear()
        self._redo_stack.clear()

    def add_point(self, canvas_pt, video_pt, current_pt):
        """Add point to the polygon."""
        # Save to undo stack before adding
        self._history.append(
            (list(self.canvas_points), list(self.video_points), list(self.current_points))
        )
        self._redo_stack.clear()

        self.canvas_points.append(canvas_pt)
        self.video_points.append(video_pt)
        self.current_points.append(current_pt)

    def undo(self) -> bool:
        """Undo last point. Returns True if successful."""
        if not self._history:
            return False

        # Save current state for redo
        self._redo_stack.append(
            (self.canvas_points.copy(), self.video_points.copy(), self.current_points.copy())
        )

        # Restore previous state
        self.canvas_points, self.video_points, self.current_points = self._history.pop()
        return True

    def redo(self) -> bool:
        """Redo last undone point. Returns True if successful."""
        if not self._redo_stack:
            return False

        # Save current state to history
        self._history.append(
            (self.canvas_points.copy(), self.video_points.copy(), self.current_points.copy())
        )

        # Restore redo state
        self.canvas_points, self.video_points, self.current_points = self._redo_stack.pop()
        return True

    def clear_points(self):
        """Clear all points."""
        self.canvas_points.clear()
        self.video_points.clear()
        self.current_points.clear()

    def has_points(self) -> bool:
        """Check whether any points have been drawn."""
        return len(self.current_points) > 0

    def point_count(self) -> int:
        """Return the number of drawn points."""
        return len(self.current_points)
