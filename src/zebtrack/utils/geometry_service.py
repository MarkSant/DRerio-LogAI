import numpy as np
import cv2
from zebtrack.utils import polygon_centroid, snap_point_to_axes

class GeometryService:
    """Cálculos de geometria puros para operações de polígono."""

    @staticmethod
    def apply_snapping(
        canvas_x: float,
        canvas_y: float,
        existing_polygons: list[list[tuple]],
        threshold: float = 10.0,
        exclude_polygon_index: int | None = None
    ) -> tuple[float, float] | None:
        """
        Aplica snapping a vértices, arestas ou eixos de alinhamento.

        Integra:
        - Snapping para vértices (distância euclidiana)
        - Snapping para arestas (projeção ortogonal)
        - Snapping para eixos (horizontal/vertical) de vértices e centroides

        Retorna coordenadas snapped ou None se nenhum alvo de snap encontrado.
        """
        if exclude_polygon_index is not None:
            existing_polygons = [
                p for i, p in enumerate(existing_polygons)
                if i != exclude_polygon_index
            ]

        # Encontra vértice ou aresta mais próxima
        closest_point = None
        min_distance = threshold

        # Coleta âncoras e centros para axis snapping
        anchors = []
        axis_centers = []

        for polygon in existing_polygons:
            # Add vertices to anchors
            for vertex in polygon:
                anchors.append(vertex)

            # Calculate centroid for axis snapping
            centroid = polygon_centroid(polygon)
            if centroid:
                axis_centers.append(centroid)

            # Snap para vértices
            for vertex in polygon:
                dist = np.sqrt((canvas_x - vertex[0])**2 + (canvas_y - vertex[1])**2)
                if dist < min_distance:
                    min_distance = dist
                    closest_point = vertex

            # Snap para arestas
            for i in range(len(polygon)):
                p1 = polygon[i]
                p2 = polygon[(i + 1) % len(polygon)]

                edge_snap = GeometryService._point_to_segment_distance(
                    canvas_x, canvas_y, p1[0], p1[1], p2[0], p2[1]
                )

                if edge_snap and edge_snap["distance"] < min_distance:
                    min_distance = edge_snap["distance"]
                    closest_point = (edge_snap["x"], edge_snap["y"])

        # Axis snapping logic
        axis_snap = snap_point_to_axes(
            (canvas_x, canvas_y),
            anchors=anchors,
            centers=axis_centers,
            threshold=float(threshold),
        )

        if axis_snap is not None:
            axis_dist = np.sqrt((canvas_x - axis_snap[0])**2 + (canvas_y - axis_snap[1])**2)
            if axis_dist < min_distance:
                closest_point = axis_snap
                min_distance = axis_dist

        return closest_point

    @staticmethod
    def clamp_point_to_polygon(
        point: tuple[float, float],
        polygon: list[tuple[float, float]]
    ) -> tuple[float, float]:
        """Clamp ponto para borda mais próxima do polígono se estiver fora."""
        px, py = point
        poly_array = np.array(polygon, dtype=np.float32)

        # Verifica se está dentro
        result = cv2.pointPolygonTest(poly_array, point, True)
        if result >= 0:
            return point  # Já está dentro

        # Encontra ponto de borda mais próximo
        min_dist = float('inf')
        closest = point

        for i in range(len(polygon)):
            p1 = polygon[i]
            p2 = polygon[(i + 1) % len(polygon)]

            edge_snap = GeometryService._point_to_segment_distance(
                px, py, p1[0], p1[1], p2[0], p2[1]
            )

            if edge_snap and edge_snap["distance"] < min_dist:
                min_dist = edge_snap["distance"]
                closest = (edge_snap["x"], edge_snap["y"])

        return closest

    @staticmethod
    def _point_to_segment_distance(
        px: float, py: float,
        x1: float, y1: float,
        x2: float, y2: float
    ) -> dict | None:
        """Calcula distância de ponto a segmento de linha."""
        # Vector from p1 to p2
        dx = x2 - x1
        dy = y2 - y1

        # Vector from p1 to point
        px_rel = px - x1
        py_rel = py - y1

        # Compute squared length of segment
        seg_len_sq = dx * dx + dy * dy

        if seg_len_sq == 0:
            # p1 and p2 are the same point
            dist = np.sqrt(px_rel * px_rel + py_rel * py_rel)
            return {"x": x1, "y": y1, "distance": dist}

        # Compute projection parameter
        t = max(0, min(1, (px_rel * dx + py_rel * dy) / seg_len_sq))

        # Compute closest point on segment
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy

        # Compute distance
        dist_x = px - closest_x
        dist_y = py - closest_y
        dist = np.sqrt(dist_x * dist_x + dist_y * dist_y)

        return {"x": closest_x, "y": closest_y, "distance": dist}
