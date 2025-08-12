"""
Este módulo contém a classe Detector, responsável por usar o modelo YOLO
para detectar objetos em quadros de vídeo e a lógica associada para rastrear
a entrada e saída de áreas de interesse.
"""
import cv2
import numpy as np
from ultralytics import YOLO
import openvino as ov
import config

class Detector:
    """
    Encapsula o modelo de detecção (YOLO ou OpenVINO) e a lógica de detecção.

    Esta classe carrega o modelo de detecção de objetos, gerencia as coordenadas
    das áreas de interesse (escalando-as para a resolução do vídeo) e processa
    quadros individuais para encontrar objetos. Para projetos 'live', também
    implementa uma máquina de estados simples para gerar comandos para o Arduino
    baseado na movimentação do objeto detectado entre as áreas.
    """
    def __init__(self, project_manager=None):
        """
        Inicializa o detector de objetos.

        - Carrega o modelo YOLO ou OpenVINO com base na configuração do projeto.
        - Define os limiares de confiança e Non-Maximum Suppression (NMS).
        - Inicializa variáveis de estado para rastrear a movimentação do objeto.
        - Define as coordenadas das áreas de interesse com base na resolução padrão.
        """
        self.model = None
        self.is_openvino = False
        self.compiled_model = None
        self.input_layer = None
        self.output_layer = None

        use_openvino = False
        openvino_path = ""
        if project_manager and project_manager.project_data:
            use_openvino = project_manager.project_data.get("use_openvino", False)
            openvino_path = project_manager.project_data.get("openvino_model_path", "")

        if use_openvino and openvino_path:
            self._load_openvino_model(openvino_path)
            self.is_openvino = True
        else:
            self.model = YOLO(config.YOLO_MODEL_PATH)

        self.conf_threshold = config.CONF_THRESHOLD
        self.nms_threshold = config.NMS_THRESHOLD

        # Variáveis de estado para rastrear a movimentação do objeto (usado em projetos 'live').
        self.crossed_in = False
        self.crossed_out = False
        self.flag = 0  # 0: procurando entrada, 1: procurando saída
        self.current_square = 0 # Qual quadrado o objeto entrou

        # As coordenadas são definidas em `config.py` para uma resolução base
        # e escaladas para a resolução real do vídeo pela `update_scaling`.
        self.scaled_polygon = config.POLYGON
        self.scaled_squares = config.SQUARES
        self.update_scaling(config.DESIRED_WIDTH, config.DESIRED_HEIGHT)

    def update_scaling(self, actual_width, actual_height):
        """
        Atualiza as coordenadas do polígono e dos quadrados com base na resolução real do vídeo.

        Isso permite que as áreas de interesse sejam definidas uma vez em `config.py`
        e funcionem com vídeos de diferentes tamanhos.

        Args:
            actual_width (int): A largura real da fonte de vídeo.
            actual_height (int): A altura real da fonte de vídeo.
        """
        base_width = config.DESIRED_WIDTH
        base_height = config.DESIRED_HEIGHT

        # Se a resolução já for a base, não há necessidade de escalar.
        if actual_width == base_width and actual_height == base_height:
            self.scaled_polygon = config.POLYGON
            self.scaled_squares = config.SQUARES
            return

        scale_x = actual_width / base_width
        scale_y = actual_height / base_height

        # Escala o polígono
        self.scaled_polygon = (config.POLYGON * [scale_x, scale_y]).astype(np.int32)

        # Escala os quadrados
        self.scaled_squares = []
        for (p1, p2) in config.SQUARES:
            x1, y1 = p1
            x2, y2 = p2
            scaled_p1 = (int(x1 * scale_x), int(y1 * scale_y))
            scaled_p2 = (int(x2 * scale_x), int(y2 * scale_y))
            self.scaled_squares.append((scaled_p1, scaled_p2))

        print(f"Detector coordinates scaled for resolution {actual_width}x{actual_height}")

    def _is_inside_square(self, x1, y1, x2, y2, square):
        """Verifica se uma caixa delimitadora se sobrepõe a um quadrado de área."""
        (sx1, sy1), (sx2, sy2) = square
        return not (x2 < sx1 or x1 > sx2 or y2 < sy1 or y1 > sy2)

    def _is_inside_polygon(self, x1, y1, x2, y2, polygon):
        """Verifica se pelo menos um canto da caixa delimitadora está dentro do polígono."""
        return cv2.pointPolygonTest(polygon, (x1, y1), False) >= 0 or \
               cv2.pointPolygonTest(polygon, (x2, y2), False) >= 0

    def _load_openvino_model(self, model_dir_path):
        """
        Loads the OpenVINO model from the specified directory.
        It finds the .xml file within the directory to load the model.
        """
        # The path we receive is to the directory, e.g., '.../best_openvino_model/'
        # We need to find the .xml file inside it.
        import glob
        import os
        xml_files = glob.glob(os.path.join(model_dir_path, "*.xml"))
        if not xml_files:
            raise FileNotFoundError(f"Could not find a .xml model file in directory: {model_dir_path}")

        model_xml_path = xml_files[0]
        print(f"Found OpenVINO model file: {model_xml_path}")

        core = ov.Core()
        model = core.read_model(model_xml_path)
        # Using "AUTO" allows OpenVINO to automatically select the best device (CPU, GPU, etc.)
        self.compiled_model = core.compile_model(model=model, device_name="AUTO")
        self.input_layer = self.compiled_model.input(0)
        self.output_layer = self.compiled_model.output(0)

    def _preprocess_openvino(self, frame):
        """Preprocesses a frame for OpenVINO inference."""
        # Get input size of the model, which is in NCHW format
        n, c, h, w = self.input_layer.shape

        # Convert BGR frame to RGB, as YOLO models expect RGB input.
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Resize the image to the model's input size (w, h)
        resized_image = cv2.resize(rgb_frame, (w, h))
        # Convert to float32, normalize to [0,1] and expand dimensions to create a batch.
        input_image = np.expand_dims(resized_image, axis=0).astype(np.float32) / 255.0
        input_image = input_image.transpose(0, 3, 1, 2) # From NHWC to NCHW
        return input_image, frame.shape[1], frame.shape[0]

    def _postprocess_openvino(self, result, original_w, original_h):
        """
        Postprocesses the OpenVINO model's output to extract bounding boxes,
        confidences, and class IDs. This implementation correctly handles the
        YOLOv8 output format [x, y, w, h, class1_score, class2_score, ...].
        """
        # Get the raw output tensor from the model
        output_tensor = result[self.output_layer]

        # The output shape is (1, 84, 8400) for COCO, where 84 = 4 (bbox) + 80 (classes).
        # We transpose it to (1, 8400, 84) to iterate through proposals.
        proposals = np.squeeze(output_tensor).T

        boxes = []
        confidences = []
        # In this version, we don't use class_ids, but it's good practice to extract it.
        # class_ids = []

        # Iterate over each proposal.
        for prop in proposals:
            # Extract bounding box information (center_x, center_y, width, height)
            bbox_coords = prop[:4]

            # Extract class scores.
            class_scores = prop[4:]

            # Find the class with the highest score and its value.
            max_score = np.max(class_scores)

            # Filter out proposals with low confidence.
            if max_score >= self.conf_threshold:
                # Get the bounding box values.
                center_x, center_y, w, h = bbox_coords

                # Convert normalized coordinates to pixel values for NMS.
                # The format required by cv2.dnn.NMSBoxes is (x, y, width, height)
                # where (x, y) is the top-left corner.
                x1 = int((center_x - w / 2) * original_w)
                y1 = int((center_y - h / 2) * original_h)
                width = int(w * original_w)
                height = int(h * original_h)

                boxes.append([x1, y1, width, height])
                confidences.append(float(max_score))

        # Apply Non-Maximum Suppression to filter out overlapping boxes.
        if not boxes:
            return []

        indices = cv2.dnn.NMSBoxes(boxes, confidences, self.conf_threshold, self.nms_threshold)

        if len(indices) == 0:
            return []

        # Prepare the final list of detections in (x1, y1, x2, y2, confidence) format.
        final_detections = []
        for i in indices.flatten():
            x, y, w, h = boxes[i]
            confidence = confidences[i]
            final_detections.append((x, y, x + w, y + h, confidence))

        return final_detections

    def process_frame(self, frame, project_type):
        """
        Processa um único quadro para detecção de objetos e rastreamento de estado.
        """
        if self.is_openvino:
            # --- OpenVINO Inference Path ---
            input_tensor, orig_w, orig_h = self._preprocess_openvino(frame)
            results = self.compiled_model.infer_new_request({self.input_layer.any_name: input_tensor})
            predictions = self._postprocess_openvino(results, orig_w, orig_h)
            # The output of postprocess is already in (x1, y1, x2, y2, confidence) format
        else:
            # --- Default Ultralytics Inference Path ---
            results = self.model(frame, verbose=False, conf=self.conf_threshold, iou=self.nms_threshold)
            # Convert to a common format: list of (x1, y1, x2, y2, confidence)
            predictions = []
            for det in results[0].boxes.data.cpu().numpy():
                x1, y1, x2, y2, confidence, _ = det
                predictions.append((int(x1), int(y1), int(x2), int(y2), confidence))

        # --- Common Logic for both paths ---
        detections_in_polygon = []
        command_to_send = None
        found_object_for_state_change = False # Garante que apenas um comando seja enviado por quadro

        if len(predictions) > 0:
            for det in predictions:
                x1, y1, x2, y2, confidence = det
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
        cv2.rectangle(frame, (x1, y1), (x2, y2), config.COLORS[i], 2)

    # Desenha o polígono da área de processamento
    cv2.polylines(frame, [detector_instance.scaled_polygon], isClosed=True, color=(0, 0, 0), thickness=1)

    # Desenha as caixas delimitadoras das detecções
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
