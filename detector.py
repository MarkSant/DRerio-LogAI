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

    def _is_inside_square(self, x1, y1, x2, y2, square):
        (sx1, sy1), (sx2, sy2) = square
        # Check for any overlap between the bounding box and the square
        return not (x2 < sx1 or x1 > sx2 or y2 < sy1 or y1 > sy2)

    def _is_inside_polygon(self, x1, y1, x2, y2, polygon):
        # Check if either the top-left or bottom-right corner of the bbox is inside the polygon
        return cv2.pointPolygonTest(polygon, (x1, y1), False) >= 0 or \
               cv2.pointPolygonTest(polygon, (x2, y2), False) >= 0

    def process_frame(self, frame):
        """
        Processes a single frame for object detection and tracking.

        Args:
            frame: The input image frame from the camera.

        Returns:
            A tuple containing:
            - detections (list): A list of tuples, where each tuple contains
              (x1, y1, x2, y2, confidence).
            - command (int or None): The command to be sent to the Arduino, or None.
        """

        # Perform inference
        results = self.model(frame, verbose=False)
        predictions = results[0].boxes.data.cpu().numpy()

        bbox = []
        confs = []

        for det in predictions:
            x1, y1, x2, y2, confidence, _ = det
            if confidence > self.conf_threshold:
                bbox.append([int(x1), int(y1), int(x2), int(y2)])
                confs.append(float(confidence))

        # Apply Non-Max Suppression
        indices = cv2.dnn.NMSBoxes(bbox, confs, self.conf_threshold, self.nms_threshold)

        detections = []
        command_to_send = None

        if len(indices) > 0:
            best_detection_idx = indices[0] # Assuming the highest confidence detection is the primary one
            best_detection_idx = best_detection_idx if isinstance(best_detection_idx, np.int32) else best_detection_idx[0]

            box = bbox[best_detection_idx]
            x1, y1, x2, y2 = box[0], box[1], box[2], box[3]
            confidence = confs[best_detection_idx]

            detections.append((x1, y1, x2, y2, confidence))

            if self._is_inside_polygon(x1, y1, x2, y2, config.POLYGON):
                # Logic to determine if a command should be sent
                if self.flag == 0:
                    for index, square in enumerate(config.SQUARES):
                        if self._is_inside_square(x1, y1, x2, y2, square):
                            self.crossed_in = True
                            self.flag = 1
                            self.current_square = index + 1
                            command_to_send = config.ENTER_COMMANDS[index]
                            break
                elif self.flag == 1:
                    is_in_any_square = any(self._is_inside_square(x1, y1, x2, y2, sq) for sq in config.SQUARES)
                    if not is_in_any_square:
                        self.crossed_out = True
                        self.flag = 0
                        command_to_send = config.EXIT_COMMANDS[self.current_square - 1]
                        self.current_square = 0

        return detections, command_to_send

def draw_overlay(frame, detections):
    """
    Draws detection overlays on the frame.
    """
    # Draw squares
    for i, ((x1, y1), (x2, y2)) in enumerate(config.SQUARES):
        cv2.rectangle(frame, (x1, y1), (x2, y2), config.COLORS[i], 2)

    # Draw polygon
    cv2.polylines(frame, [config.POLYGON], isClosed=True, color=(0, 0, 0), thickness=1)

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
