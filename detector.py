import cv2
import numpy as np
from ultralytics import YOLO
import config

class Detector:
    def __init__(self):
        """
        Initializes the object detector.
        """
        self.model = YOLO(config.YOLO_MODEL_PATH)
        self.conf_threshold = config.CONF_THRESHOLD
        self.nms_threshold = config.NMS_THRESHOLD

        # State variables for tracking object movement
        self.crossed_in = False
        self.crossed_out = False
        self.flag = 0
        self.current_square = 0

        # Placeholders for scaled coordinates
        self.scaled_polygon = config.POLYGON
        self.scaled_squares = config.SQUARES
        self.update_scaling(config.DESIRED_WIDTH, config.DESIRED_HEIGHT)

    def update_scaling(self, actual_width, actual_height):
        """
        Updates the polygon and square coordinates based on the actual video resolution.
        """
        base_width = config.DESIRED_WIDTH
        base_height = config.DESIRED_HEIGHT

        if actual_width == base_width and actual_height == base_height:
            self.scaled_polygon = config.POLYGON
            self.scaled_squares = config.SQUARES
            return

        scale_x = actual_width / base_width
        scale_y = actual_height / base_height

        # Scale polygon
        self.scaled_polygon = (config.POLYGON * [scale_x, scale_y]).astype(np.int32)

        # Scale squares
        self.scaled_squares = []
        for (p1, p2) in config.SQUARES:
            x1, y1 = p1
            x2, y2 = p2
            scaled_p1 = (int(x1 * scale_x), int(y1 * scale_y))
            scaled_p2 = (int(x2 * scale_x), int(y2 * scale_y))
            self.scaled_squares.append((scaled_p1, scaled_p2))

        print(f"Detector coordinates scaled for resolution {actual_width}x{actual_height}")

    def _is_inside_square(self, x1, y1, x2, y2, square):
        (sx1, sy1), (sx2, sy2) = square
        return not (x2 < sx1 or x1 > sx2 or y2 < sy1 or y1 > sy2)

    def _is_inside_polygon(self, x1, y1, x2, y2, polygon):
        return cv2.pointPolygonTest(polygon, (x1, y1), False) >= 0 or \
               cv2.pointPolygonTest(polygon, (x2, y2), False) >= 0

    def process_frame(self, frame, project_type):
        """
        Processes a single frame for object detection and tracking.
        Relies on the model's internal NMS.
        """
        results = self.model(frame, verbose=False, conf=self.conf_threshold, iou=self.nms_threshold)
        predictions = results[0].boxes.data.cpu().numpy()

        detections_in_polygon = []
        command_to_send = None
        found_object_for_state_change = False

        if len(predictions) > 0:
            for det in predictions:
                x1, y1, x2, y2, confidence, _ = det
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

                if self._is_inside_polygon(x1, y1, x2, y2, self.scaled_polygon):
                    detections_in_polygon.append((x1, y1, x2, y2, confidence))

                    if project_type == 'live' and not found_object_for_state_change:
                        if self.flag == 0:
                            for index, square in enumerate(self.scaled_squares):
                                if self._is_inside_square(x1, y1, x2, y2, square):
                                    self.crossed_in = True
                                    self.flag = 1
                                    self.current_square = index + 1
                                    command_to_send = config.ENTER_COMMANDS[index]
                                    found_object_for_state_change = True
                                    break
                        elif self.flag == 1:
                            is_in_any_square = any(self._is_inside_square(x1, y1, x2, y2, sq) for sq in self.scaled_squares)
                            if not is_in_any_square:
                                self.crossed_out = True
                                self.flag = 0
                                command_to_send = config.EXIT_COMMANDS[self.current_square - 1]
                                self.current_square = 0
                                found_object_for_state_change = True

        return detections_in_polygon, command_to_send

def draw_overlay(frame, detections, detector_instance):
    """
    Draws detection overlays on the frame using scaled coordinates from the detector instance.
    """
    # Draw scaled squares
    for i, ((x1, y1), (x2, y2)) in enumerate(detector_instance.scaled_squares):
        cv2.rectangle(frame, (x1, y1), (x2, y2), config.COLORS[i], 2)

    # Draw scaled polygon
    cv2.polylines(frame, [detector_instance.scaled_polygon], isClosed=True, color=(0, 0, 0), thickness=1)

    # Draw detections
    for (x1, y1, x2, y2, confidence) in detections:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 255), 2)
        cv2.putText(frame, f'{int(confidence * 100)}%', (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)

if __name__ == '__main__':
    # This test requires a camera and will display the output.
    from camera import Camera

    print("Running detector test...")
    cam = Camera()
    detector = Detector()

    while True:
        ret, frame = cam.get_frame()
        if not ret:
            print("Failed to get frame.")
            break

        detections, command = detector.process_frame(frame)

        if command is not None:
            print(f"Detector generated command: {command}")

        draw_overlay(frame, detections)

        cv2.imshow('Detector Test', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cam.release()
    cv2.destroyAllWindows()
    print("Detector test finished.")
