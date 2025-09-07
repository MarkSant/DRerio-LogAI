import glob
import os
from typing import List, Tuple

import cv2
import numpy as np
import openvino as ov
import torch
from ultralytics.utils.ops import non_max_suppression, scale_boxes
from zebtrack.plugins.base import DetectorPlugin
from zebtrack.settings import settings


class OpenVINOPlugin(DetectorPlugin):
    """A detector plugin that uses an OpenVINO-optimized model."""

    def __init__(self, model_path: str):
        """
        Initializes the plugin and loads the OpenVINO model.

        Args:
            model_path (str): Path to the directory containing the .xml and .bin files.
        """
        self.conf_threshold = settings.yolo_model.confidence_threshold
        self.nms_threshold = settings.yolo_model.nms_threshold

        xml_files = glob.glob(os.path.join(model_path, "*.xml"))
        if not xml_files:
            raise FileNotFoundError(
                f"Could not find a .xml model file in directory: {model_path}"
            )

        model_xml_path = xml_files[0]
        core = ov.Core()
        model = core.read_model(model_xml_path)
        self.compiled_model = core.compile_model(model=model, device_name="AUTO")
        self.input_layer = self.compiled_model.input(0)
        self.output_layer = self.compiled_model.output(0)
        self.infer_request = self.compiled_model.create_infer_request()

    def detect(self, frame: np.ndarray) -> List[Tuple[int, int, int, int, float]]:
        """Performs inference using the OpenVINO model."""
        input_tensor = self._preprocess(frame)
        self.infer_request.infer({self.input_layer.any_name: input_tensor})
        results = self.infer_request.results
        predictions = self._postprocess(results, frame.shape)
        return predictions

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        """Prepares a frame for OpenVINO inference using letterboxing."""
        n, c, h, w = self.input_layer.shape
        letterboxed_frame, _, _ = _letterbox(frame, new_shape=(w, h), auto=False)
        rgb_frame = cv2.cvtColor(letterboxed_frame, cv2.COLOR_BGR2RGB)
        input_tensor = rgb_frame.transpose(2, 0, 1) / 255.0
        input_tensor = np.expand_dims(input_tensor, axis=0).astype(np.float32)
        return input_tensor

    def _postprocess(self, result: dict, original_frame_shape: tuple) -> list:
        """Postprocesses the OpenVINO model's output."""
        output_tensor = result[self.output_layer]
        preds = non_max_suppression(
            prediction=torch.from_numpy(output_tensor),
            conf_thres=self.conf_threshold,
            iou_thres=self.nms_threshold,
            agnostic=True,
        )
        detections = preds[0]
        if detections is None or len(detections) == 0:
            return []

        detections[:, :4] = scale_boxes(
            self.model_input_shape, detections[:, :4], original_frame_shape
        ).round()

        final_detections = []
        for *xyxy, conf, cls in detections:
            final_detections.append(
                (int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3]), float(conf))
            )
        return final_detections

    @staticmethod
    def get_name() -> str:
        return "OpenVINO"

    @property
    def model_input_shape(self) -> Tuple[int, int]:
        return self.input_layer.shape[2], self.input_layer.shape[3]  # (h, w)


def _letterbox(
    img: np.ndarray,
    new_shape: tuple = (640, 640),
    color: tuple = (114, 114, 114),
    auto: bool = True,
    scaleFill: bool = False,
    scaleup: bool = True,
    stride: int = 32,
):
    """
    Standard letterboxing function from ultralytics.
    Resizes and pads image while meeting stride-multiple constraints.
    """
    shape = img.shape[:2]
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)

    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    if not scaleup:
        r = min(r, 1.0)

    ratio = r, r
    new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]
    if auto:
        dw, dh = np.mod(dw, stride), np.mod(dh, stride)
    elif scaleFill:
        dw, dh = 0.0, 0.0
        new_unpad = (new_shape[1], new_shape[0])
        ratio = new_shape[1] / shape[1], new_shape[0] / shape[0]

    dw /= 2
    dh /= 2

    if shape[::-1] != new_unpad:
        img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.copyMakeBorder(
        img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color
    )
    return img, ratio, (dw, dh)
