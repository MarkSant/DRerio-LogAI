# ruff: noqa: N816
from typing import Any

VideoCapture: Any
VideoWriter: Any
VideoWriter_fourcc: Any

# I/O and window helpers
imshow: Any
waitKey: Any
destroyAllWindows: Any
imread: Any
imwrite: Any
imdecode: Any

# Image processing
cvtColor: Any
resize: Any
flip: Any
addWeighted: Any
copyMakeBorder: Any
polylines: Any
rectangle: Any
circle: Any
putText: Any
getTextSize: Any
pointPolygonTest: Any
findContours: Any
contourArea: Any
boundingRect: Any
warpPerspective: Any
threshold: Any
GaussianBlur: Any
adaptiveThreshold: Any
morphologyEx: Any
convexHull: Any
arcLength: Any
approxPolyDP: Any
fillPoly: Any
getPerspectiveTransform: Any
minAreaRect: Any
boxPoints: Any
perspectiveTransform: Any

# Constants
FONT_HERSHEY_SIMPLEX: int
LINE_AA: int
COLOR_BGR2RGB: int
COLOR_BGR2GRAY: int
IMREAD_COLOR: int
THRESH_BINARY: int
THRESH_BINARY_INV: int
ADAPTIVE_THRESH_GAUSSIAN_C: int
INTER_NEAREST: int
INTER_LINEAR: int
BORDER_CONSTANT: int
RETR_EXTERNAL: int
CHAIN_APPROX_SIMPLE: int
MORPH_CLOSE: int
MORPH_OPEN: int

# Video capture properties/backends
CAP_PROP_FRAME_WIDTH: int
CAP_PROP_FRAME_HEIGHT: int
CAP_PROP_FPS: int
CAP_PROP_POS_MSEC: int
CAP_PROP_POS_FRAMES: int
CAP_PROP_FRAME_COUNT: int
CAP_ANY: int
CAP_DSHOW: int
CAP_MSMF: int
CAP_FFMPEG: int

# Misc
LANCZOS: int
setLogLevel: Any
error: Any
