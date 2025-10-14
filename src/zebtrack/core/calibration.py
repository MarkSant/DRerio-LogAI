import cv2
import numpy as np
import structlog

log = structlog.get_logger()


class Calibration:
    """
    Handles perspective correction and scale calibration based on a detected polygon.
    """

    def __init__(self, polygon, real_width_cm: float, real_height_cm: float):
        """
        Initializes the Calibration object.

        Args:
            polygon (np.ndarray): A single polygon (numpy array) from AquariumDetector.
            real_width_cm (float): The real-world width of the aquarium in cm.
            real_height_cm (float): The real-world height of the aquarium in cm.
        """
        self.polygon = polygon
        self.real_width_cm = real_width_cm
        self.real_height_cm = real_height_cm
        self.homography_matrix = None
        self.pixel_per_cm_ratio = (0.0, 0.0)  # (x_ratio, y_ratio)
        self.target_dims_px = (0, 0)  # (width, height)

        if self.polygon is not None:
            self._process_polygon()

    def _process_polygon(self):
        """
        Processes the detected polygon to calculate the homography matrix and scale.
        """
        # 1. Find the four corner points of the polygon.
        # Using cv2.minAreaRect is a robust way to find the corners of a
        # near-rectangular shape. A more complex RANSAC-based line fitting
        # could be implemented here in the future if needed.
        corners = self._find_corners(self.polygon)
        if corners is None or len(corners) != 4:
            log.error("calibration.process.corner_detection_failed")
            return

        # 2. Define the destination rectangle for the perspective transform.
        # We establish a target pixel width and calculate the height to maintain
        # the real-world aspect ratio. This creates our "ideal" top-down view.
        target_width_px = 600
        aspect_ratio = self.real_height_cm / self.real_width_cm
        target_height_px = int(target_width_px * aspect_ratio)
        self.target_dims_px = (target_width_px, target_height_px)

        destination_points = np.array(
            [
                [0, 0],
                [target_width_px - 1, 0],
                [target_width_px - 1, target_height_px - 1],
                [0, target_height_px - 1],
            ],
            dtype="float32",
        )

        # 3. Calculate the homography matrix.
        # The source points (corners) must be in a consistent order.
        ordered_corners = self._order_points(corners)
        self.homography_matrix = cv2.getPerspectiveTransform(ordered_corners, destination_points)

        # 4. Calculate the final pixel-to-cm ratio based on the warped dimensions.
        px_per_cm_x = target_width_px / self.real_width_cm
        px_per_cm_y = target_height_px / self.real_height_cm
        self.pixel_per_cm_ratio = (px_per_cm_x, px_per_cm_y)

        log.debug(
            "calibration.process.success",
            ratio=self.pixel_per_cm_ratio,
            target_dims=self.target_dims_px,
        )

    @staticmethod
    def _find_corners(polygon: np.ndarray) -> np.ndarray | None:
        """
        Finds the four corners of a polygon using its minimum area rectangle.
        """
        if polygon is None or len(polygon) < 3:
            return None
        # Ensure polygon is in the correct format (np.float32 or np.int32)
        polygon = np.array(polygon, dtype=np.float32)
        # `cv2.minAreaRect` finds the minimum-area bounding box of a point set.
        rect = cv2.minAreaRect(polygon)
        # `cv2.boxPoints` calculates the four vertices of the rotated rectangle.
        box = cv2.boxPoints(rect)
        return box.astype("float32")

    @staticmethod
    def _order_points(pts: np.ndarray) -> np.ndarray:
        """
        Orders the 4 corner points into a consistent order:
        top-left, top-right, bottom-right, bottom-left.
        This is crucial for cv2.getPerspectiveTransform.
        """
        rect = np.zeros((4, 2), dtype="float32")

        # The top-left point will have the smallest sum, whereas
        # the bottom-right point will have the largest sum.
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]

        # The top-right point will have the smallest difference,
        # whereas the bottom-left will have the largest difference.
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]

        return rect

    def warp_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Applies the calculated perspective warp to a given frame.
        """
        if self.homography_matrix is None:
            log.warning("calibration.warp.no_matrix", returning_original=True)
            return frame

        return cv2.warpPerspective(frame, self.homography_matrix, self.target_dims_px)

    def transform_points(self, points: list) -> list:
        """
        Transforms a list of points using the homography matrix.

        Args:
            points: List of [x, y] coordinates

        Returns:
            List of transformed [x, y] coordinates
        """
        if self.homography_matrix is None:
            log.warning("calibration.transform.no_matrix", returning_original=True)
            return points

        # Convert to numpy array and reshape for cv2.perspectiveTransform
        pts = np.array(points, dtype=np.float32).reshape(-1, 1, 2)
        transformed = cv2.perspectiveTransform(pts, self.homography_matrix)
        # Reshape back to list of [x, y]
        return transformed.reshape(-1, 2).tolist()

    def transform_bbox(self, x1: float, y1: float, x2: float, y2: float) -> tuple:
        """
        Transforms a bounding box from original video space to warped space.

        This method transforms all 4 corners of the bbox and finds the new
        axis-aligned bounding box that encompasses all transformed points.

        Args:
            x1: Left x coordinate
            y1: Top y coordinate
            x2: Right x coordinate
            y2: Bottom y coordinate

        Returns:
            Tuple of (x1_w, y1_w, x2_w, y2_w) in warped space
        """
        if self.homography_matrix is None:
            log.warning("calibration.transform.no_matrix", returning_original=True)
            return (x1, y1, x2, y2)

        # Transform all 4 corners of the bounding box
        corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        warped_corners = self.transform_points(corners)

        # Find new axis-aligned bbox that encompasses all transformed points
        xs = [p[0] for p in warped_corners]
        ys = [p[1] for p in warped_corners]

        return (min(xs), min(ys), max(xs), max(ys))
