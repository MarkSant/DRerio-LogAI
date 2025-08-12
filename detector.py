"""
Este módulo contém a classe Detector, responsável por usar o modelo YOLO
para detectar objetos em quadros de vídeo e a lógica associada para rastrear
a entrada e saída de áreas de interesse.
"""
import cv2
import numpy as np
from ultralytics import YOLO
import config

class Detector:
    """
    Encapsula o modelo YOLO e a lógica de detecção.

    Esta classe carrega o modelo de detecção de objetos, gerencia as coordenadas
    das áreas de interesse (escalando-as para a resolução do vídeo) e processa
    quadros individuais para encontrar objetos. Para projetos 'live', também
    implementa uma máquina de estados simples para gerar comandos para o Arduino
    baseado na movimentação do objeto detectado entre as áreas.
    """
    def __init__(self):
        """
        Inicializa o detector de objetos.

        - Carrega o modelo YOLO a partir do caminho especificado em `config.py`.
        - Define os limiares de confiança e Non-Maximum Suppression (NMS).
        - Inicializa variáveis de estado para rastrear a movimentação do objeto.
        - Define as coordenadas das áreas de interesse com base na resolução padrão.
        """
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

    def process_frame(self, frame, project_type):
        """
        Processa um único quadro para detecção de objetos e rastreamento de estado.

        Args:
            frame: O quadro de vídeo a ser processado.
            project_type (str): O tipo do projeto ('live' ou 'pre-recorded').
                                A lógica de comando do Arduino só é executada para 'live'.

        Returns:
            tuple: Uma tupla contendo:
                - detections_in_polygon (list): Lista de detecções encontradas dentro do polígono.
                - command_to_send (int or None): O comando a ser enviado para o Arduino, ou None.
        """
        # Executa o modelo YOLO no quadro. `verbose=False` desativa a impressão de logs do YOLO.
        results = self.model(frame, verbose=False, conf=self.conf_threshold, iou=self.nms_threshold)
        predictions = results[0].boxes.data.cpu().numpy()

        detections_in_polygon = []
        command_to_send = None
        found_object_for_state_change = False # Garante que apenas um comando seja enviado por quadro

        if len(predictions) > 0:
            for det in predictions:
                x1, y1, x2, y2, confidence, _ = det
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

                # Considera apenas detecções dentro da área de processamento principal (polígono).
                if self._is_inside_polygon(x1, y1, x2, y2, self.scaled_polygon):
                    detections_in_polygon.append((x1, y1, x2, y2, confidence))

                    # A lógica de máquina de estados abaixo só é relevante para projetos 'live'.
                    if project_type == 'live' and not found_object_for_state_change:
                        # Estado 0: Procurando por um objeto entrando em um quadrado.
                        if self.flag == 0:
                            for index, square in enumerate(self.scaled_squares):
                                if self._is_inside_square(x1, y1, x2, y2, square):
                                    self.crossed_in = True
                                    self.flag = 1  # Muda para o estado 1 (procurando saída)
                                    self.current_square = index + 1
                                    command_to_send = config.ENTER_COMMANDS[index]
                                    found_object_for_state_change = True
                                    break
                        # Estado 1: Procurando pelo objeto saindo de todos os quadrados.
                        elif self.flag == 1:
                            is_in_any_square = any(self._is_inside_square(x1, y1, x2, y2, sq) for sq in self.scaled_squares)
                            if not is_in_any_square:
                                self.crossed_out = True
                                self.flag = 0  # Retorna para o estado 0
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
