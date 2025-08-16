"""
Este módulo contém a classe Detector, responsável por usar o modelo YOLO
para detectar objetos em quadros de vídeo e a lógica associada para rastrear
a entrada e saída de áreas de interesse.
"""

import glob
import logging
import os
import time

import cv2
import numpy as np
import openvino as ov
import torch
from ultralytics import YOLO
from ultralytics.utils.ops import non_max_suppression, scale_boxes

from zebtrack.settings import settings


class Detector:
    """
    Encapsula o modelo de detecção (YOLO ou OpenVINO) e a lógica de detecção.

    Esta classe carrega o modelo de detecção de objetos, gerencia as coordenadas
    das áreas de interesse (escalando-as para a resolução do vídeo) e processa
    quadros individuais para encontrar objetos. Para projetos 'live', também
    implementa uma máquina de estados simples para gerar comandos para o Arduino
    baseado na movimentação do objeto detectado entre as áreas.
    """

    def __init__(self, project_manager=None, model_path: str = None):
        """
        Inicializa o detector de objetos.

        - Carrega o modelo YOLO ou OpenVINO com base na configuração do projeto.
        - Define os limiares de confiança e Non-Maximum Suppression (NMS).
        - Inicializa variáveis de estado para rastrear a movimentação do objeto.
        - Define as coordenadas das áreas de interesse com base na resolução padrão.

        Args:
            project_manager: O gerenciador de projetos para configurações.
            model_path (str, optional): Caminho para o modelo a ser carregado,
                                        substituindo o padrão dos settings.
        """
        self.model = None
        self.is_openvino = False
        self.compiled_model = None
        self.input_layer = None
        self.output_layer = None
        self.infer_request = None

        use_openvino = False
        openvino_path = ""
        if project_manager and project_manager.project_data:
            use_openvino = project_manager.project_data.get("use_openvino", False)
            openvino_path = project_manager.project_data.get("openvino_model_path", "")

        try:
            if use_openvino and openvino_path:
                self._load_openvino_model(openvino_path)
                self.is_openvino = True
            else:
                # Usa o model_path fornecido ou o caminho dos settings
                path_to_load = model_path or settings.yolo_model.path
                logging.info(f"Loading YOLO model from: {path_to_load}")
                self.model = YOLO(path_to_load)
        except Exception as e:
            logging.critical(f"Failed to load detection model: {e}")
            # As variáveis de modelo permanecem None, desativando o detector

        self.conf_threshold = settings.yolo_model.confidence_threshold
        self.nms_threshold = settings.yolo_model.nms_threshold

        # Variáveis de estado para rastrear a movimentação do objeto
        # (usado em projetos 'live').
        self.crossed_in = False
        self.crossed_out = False
        self.flag = 0  # 0: procurando entrada, 1: procurando saída
        self.current_square = 0  # Qual quadrado o objeto entrou

        # As coordenadas são definidas em `config.py` para uma resolução base
        # e escaladas para a resolução real do vídeo pela `update_scaling`.
        self.base_polygon = np.array(
            settings.detection_zones.polygon, dtype=np.int32
        )
        self.base_squares = settings.detection_zones.squares
        self.scaled_polygon = self.base_polygon
        self.scaled_squares = self.base_squares
        self.update_scaling(
            settings.camera.desired_width, settings.camera.desired_height
        )

    def update_scaling(self, actual_width, actual_height):
        """
        Atualiza as coordenadas do polígono e dos quadrados com base na
        resolução real do vídeo.

        Isso permite que as áreas de interesse sejam definidas uma vez em `config.py`
        e funcionem com vídeos de diferentes tamanhos.

        Args:
            actual_width (int): A largura real da fonte de vídeo.
            actual_height (int): A altura real da fonte de vídeo.
        """
        base_width = settings.camera.desired_width
        base_height = settings.camera.desired_height

        # Se a resolução já for a base, não há necessidade de escalar.
        if actual_width == base_width and actual_height == base_height:
            self.scaled_polygon = self.base_polygon
            self.scaled_squares = self.base_squares
            return

        scale_x = actual_width / base_width
        scale_y = actual_height / base_height

        # Escala o polígono
        self.scaled_polygon = (self.base_polygon * [scale_x, scale_y]).astype(
            np.int32
        )

        # Escala os quadrados
        self.scaled_squares = []
        for p1, p2 in self.base_squares:
            x1, y1 = p1
            x2, y2 = p2
            scaled_p1 = (int(x1 * scale_x), int(y1 * scale_y))
            scaled_p2 = (int(x2 * scale_x), int(y2 * scale_y))
            self.scaled_squares.append((scaled_p1, scaled_p2))

        logging.info(
            f"Detector coordinates scaled for resolution "
            f"{actual_width}x{actual_height}"
        )

    def _is_inside_square(self, x1, y1, x2, y2, square):
        """Verifica se uma caixa delimitadora se sobrepõe a um quadrado de área."""
        (sx1, sy1), (sx2, sy2) = square
        return not (x2 < sx1 or x1 > sx2 or y2 < sy1 or y1 > sy2)

    def _is_inside_polygon(self, x1, y1, x2, y2, polygon):
        """Verifica se um canto da caixa delimitadora está dentro do polígono."""
        return (
            cv2.pointPolygonTest(polygon, (x1, y1), False) >= 0
            or cv2.pointPolygonTest(polygon, (x2, y2), False) >= 0
        )

    def _load_openvino_model(self, model_dir_path):
        """
        Loads the OpenVINO model from the specified directory.
        It finds the .xml file within the directory to load the model.
        """
        xml_files = glob.glob(os.path.join(model_dir_path, "*.xml"))
        if not xml_files:
            raise FileNotFoundError(
                f"Could not find a .xml model file in directory: {model_dir_path}"
            )

        model_xml_path = xml_files[0]
        logging.info(f"Found OpenVINO model file: {model_xml_path}")

        core = ov.Core()
        model = core.read_model(model_xml_path)
        self.compiled_model = core.compile_model(model=model, device_name="AUTO")
        self.input_layer = self.compiled_model.input(0)
        self.output_layer = self.compiled_model.output(0)
        self.infer_request = self.compiled_model.create_infer_request()

    def _preprocess_openvino(self, frame):
        """
        Prepares a frame for OpenVINO inference using letterboxing, which is
        the standard for YOLO models.
        """
        # Get input size of the model
        n, c, h, w = self.input_layer.shape

        # Apply letterboxing. `auto=False` ensures the frame is padded
        # to the exact `new_shape` (e.g., 640x640), required for static shapes.
        letterboxed_frame, _, _ = letterbox(frame, new_shape=(w, h), auto=False)

        # Convert from BGR to RGB
        rgb_frame = cv2.cvtColor(letterboxed_frame, cv2.COLOR_BGR2RGB)

        # Transpose from HWC to CHW and normalize to [0,1]
        input_tensor = rgb_frame.transpose(2, 0, 1) / 255.0

        # Add batch dimension to create NHWC
        input_tensor = np.expand_dims(input_tensor, axis=0).astype(np.float32)

        return input_tensor

    def _postprocess_openvino(self, result, original_frame_shape):
        """
        Postprocesses the OpenVINO model's output using the official
        ultralytics utility functions for robust and accurate results.
        """
        # Get the raw output tensor from the model
        output_tensor = result[self.output_layer]

        # Use the official ultralytics non_max_suppression utility.
        # This handles all the complex parsing of class scores and confidences.
        # The output shape of the model is (1, 84, 8400) for COCO.
        # We pass it directly to the utility.
        preds = non_max_suppression(
            prediction=torch.from_numpy(output_tensor),
            conf_thres=self.conf_threshold,
            iou_thres=self.nms_threshold,
            agnostic=True,  # Class-agnostic NMS
        )

        # The result of NMS is a list with one element per image in the batch.
        # We only have one image, so we take the first element.
        detections = preds[0]

        if detections is None or len(detections) == 0:
            return []

        # Rescale the bounding boxes from the model's input size (e.g., 640x640)
        # back to the original frame's size.
        model_input_shape = (
            self.input_layer.shape[2],
            self.input_layer.shape[3],
        )  # (h, w)
        detections[:, :4] = scale_boxes(
            model_input_shape, detections[:, :4], original_frame_shape
        ).round()

        # Convert the results to the format expected by the rest of the application:
        # A list of tuples: (x1, y1, x2, y2, confidence)
        final_detections = []
        for *xyxy, conf, cls in detections:
            # We ignore 'cls' for now as the application is class-agnostic
            final_detections.append(
                (int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3]), float(conf))
            )

        return final_detections

    def process_frame(self, frame, project_type):
        """
        Processa um único quadro para detecção de objetos e rastreamento de estado.
        """
        # Se o modelo não foi carregado com sucesso, não faz nada.
        if self.model is None and self.compiled_model is None:
            return [], None

        start_time = time.perf_counter()

        if self.is_openvino:
            # --- OpenVINO Inference Path ---
            input_tensor = self._preprocess_openvino(frame)
            # The `infer` method is the recommended sync approach in the latest API
            self.infer_request.infer({self.input_layer.any_name: input_tensor})
            results = self.infer_request.results
            predictions = self._postprocess_openvino(results, frame.shape)
            # The output is already in (x1, y1, x2, y2, confidence) format
        else:
            # --- Default Ultralytics Inference Path ---
            results = self.model(
                frame, verbose=False, conf=self.conf_threshold, iou=self.nms_threshold
            )
            # Convert to a common format: list of (x1, y1, x2, y2, confidence)
            predictions = []
            for det in results[0].boxes.data.cpu().numpy():
                x1, y1, x2, y2, confidence, _ = det
                predictions.append((int(x1), int(y1), int(x2), int(y2), confidence))

        # --- Common Logic for both paths ---
        detections_in_polygon = []
        command_to_send = None
        found_object_for_state_change = (
            False  # Garante que apenas um comando seja enviado por quadro
        )

        if len(predictions) > 0:
            for det in predictions:
                x1, y1, x2, y2, confidence = det
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

                if self._is_inside_polygon(x1, y1, x2, y2, self.scaled_polygon):
                    detections_in_polygon.append((x1, y1, x2, y2, confidence))

                    if project_type == "live" and not found_object_for_state_change:
                        if self.flag == 0:
                            for index, square in enumerate(self.scaled_squares):
                                if self._is_inside_square(x1, y1, x2, y2, square):
                                    self.crossed_in = True
                                    self.flag = 1
                                    self.current_square = index + 1
                                    command_to_send = (
                                        settings.detection_zones.enter_commands[index]
                                    )
                                    found_object_for_state_change = True
                                    break
                        elif self.flag == 1:
                            is_in_any_square = any(
                                self._is_inside_square(x1, y1, x2, y2, sq)
                                for sq in self.scaled_squares
                            )
                            if not is_in_any_square:
                                self.crossed_out = True
                                self.flag = 0
                                command_to_send = settings.detection_zones.exit_commands[
                                    self.current_square - 1
                                ]
                                self.current_square = 0
                                found_object_for_state_change = True

        end_time = time.perf_counter()
        logging.debug(f"Frame processing time: {(end_time - start_time) * 1000:.2f} ms")

        return detections_in_polygon, command_to_send


def letterbox(
    img: np.ndarray,
    new_shape: tuple = (640, 640),
    color: tuple = (114, 114, 114),
    auto: bool = True,
    scaleFill: bool = False,
    scaleup: bool = True,
    stride: int = 32,
):
    """
    Resize and pad image while meeting stride-multiple constraints.
    This is the standard letterboxing function from the ultralytics library.
    """
    shape = img.shape[:2]  # current shape [height, width]
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)

    # Scale ratio (new / old)
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    if not scaleup:  # only scale down, do not scale up (for better test mAP)
        r = min(r, 1.0)

    # Compute padding
    ratio = r, r  # width, height ratios
    new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]  # wh padding
    if auto:  # minimum rectangle
        dw, dh = np.mod(dw, stride), np.mod(dh, stride)  # wh padding
    elif scaleFill:  # stretch
        dw, dh = 0.0, 0.0
        new_unpad = (new_shape[1], new_shape[0])
        ratio = new_shape[1] / shape[1], new_shape[0] / shape[0]  # width, height ratios

    dw /= 2  # divide padding into 2 sides
    dh /= 2

    if shape[::-1] != new_unpad:  # resize
        img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.copyMakeBorder(
        img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color
    )  # add border
    return img, ratio, (dw, dh)


def draw_overlay(frame, detections, detector_instance):
    """
    Desenha sobreposições de detecção no quadro.

    Isso inclui as áreas de interesse, o polígono de processamento e as
    caixas delimitadoras para cada objeto detectado.

    Args:
        frame: O quadro de vídeo no qual desenhar.
        detections (list): A lista de detecções a serem desenhadas.
        detector_instance (Detector): A instância do detector que contém as
                                      coordenadas escaladas das áreas.
    """
    # Desenha os quadrados de área de interesse
    for i, ((x1, y1), (x2, y2)) in enumerate(detector_instance.scaled_squares):
        cv2.rectangle(frame, (x1, y1), (x2, y2), settings.detection_zones.colors[i], 2)

    # Desenha o polígono da área de processamento
    cv2.polylines(
        frame,
        [detector_instance.scaled_polygon],
        isClosed=True,
        color=(0, 0, 0),
        thickness=1,
    )

    # Desenha as caixas delimitadoras das detecções
    for x1, y1, x2, y2, confidence in detections:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 255), 2)
        cv2.putText(
            frame,
            f"{int(confidence * 100)}%",
            (x1, y1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 0, 255),
            2,
        )


if __name__ == "__main__":
    # This test requires a camera and will display the output.
    from zebtrack.io.camera import Camera

    print("Running detector test...")
    cam = Camera()
    detector = Detector()

    while True:
        ret, frame = cam.get_frame()
        if not ret:
            print("Failed to get frame.")
            break

        detections, command = detector.process_frame(frame, "live")

        if command is not None:
            print(f"Detector generated command: {command}")

        draw_overlay(frame, detections, detector)

        cv2.imshow("Detector Test", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cam.release()
    cv2.destroyAllWindows()
    print("Detector test finished.")
