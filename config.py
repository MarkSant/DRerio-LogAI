import numpy as np

# Camera settings
CAMERA_INDEX = 1
DESIRED_WIDTH = 1280
DESIRED_HEIGHT = 720

# Arduino settings
ARDUINO_PORT = 'COM13'
BAUD_RATE = 9600

# YOLO model settings
YOLO_MODEL_PATH = 'best12.pt'
CONF_THRESHOLD = 0.3
NMS_THRESHOLD = 0.3

# Detection zones
SQUARES = [
    ((150, 490), (360, 660)),  # Bottom-left
    ((385, 140), (550, 310)),  # Top-left
    ((630, 490), (765, 660)),  # Bottom-right
    ((850, 140), (1020, 310))  # Top-right
]

# Colors for the squares
COLORS = [
    (0, 0, 255),    # Red
    (255, 0, 0),    # Blue
    (0, 255, 0),    # Green
    (0, 0, 255)     # Red
]

# Arduino commands
ENTER_COMMANDS = [1, 3, 5, 7]
EXIT_COMMANDS = [2, 4, 6, 8]

# Polygon coordinates for detection area
POLYGON = np.array([
    [150, 310], [385, 310], [385, 140], [550, 140],
    [550, 310], [850, 310], [850, 140], [1020, 140],
    [1020, 490], [765, 490], [765, 660], [630, 660],
    [630, 490], [360, 490], [360, 660], [150, 660]
], np.int32)

# Video settings
FPS = 30

# Processing settings
PROCESSING_INTERVAL = 10  # Process every x frames
PROCESSING_OFFSET = 1     # Start on frame y
