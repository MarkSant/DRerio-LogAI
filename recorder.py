import os
import cv2
import csv
import time
import logging
from datetime import datetime
import config

class Recorder:
    """
    Gerencia a gravação dos dados da análise, incluindo arquivos de vídeo e CSV.

    Esta classe lida com a criação de arquivos de saída, escrita de dados de detecção
    e de quadros de vídeo, e o fechamento adequado dos arquivos ao final da gravação.
    """
    def __init__(self):
        """Inicializa o gravador com seu estado padrão."""
        self.is_recording = False
        self.video_writer = None
        self.csv_writer = None
        self.csv_file = None
        self.base_name = ""
        self.start_time = 0
        self.frame_count = 0
        self.recording_start_frame = 0

    def start_recording(self, output_folder, frame_width, frame_height, is_video_file=False):
        """
        Prepara e inicia uma nova sessão de gravação.

        Cria o diretório de saída e inicializa os escritores de CSV e, opcionalmente,
        de vídeo. Salva também os arquivos de definição de área.

        Args:
            output_folder (str): O caminho para a pasta onde os arquivos serão salvos.
            frame_width (int): A largura dos quadros de vídeo.
            frame_height (int): A altura dos quadros de vídeo.
            is_video_file (bool): Se True, pula a criação do arquivo de vídeo,
                                  usado para análises de vídeos pré-gravados.

        Returns:
            bool: True se a gravação começou com sucesso, False caso contrário.
        """
        if self.is_recording:
            logging.warning("Attempted to start recording while already recording.")
            return False

        os.makedirs(output_folder, exist_ok=True)
        self.base_name = os.path.basename(output_folder)

        # 1. Configura o VideoWriter, apenas se não for uma análise de arquivo de vídeo.
        if not is_video_file:
            video_filename = os.path.join(output_folder, f"{self.base_name}.mp4")
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self.video_writer = cv2.VideoWriter(video_filename, fourcc, config.FPS, (frame_width, frame_height))
            if not self.video_writer.isOpened():
                logging.error(f"Error: Could not open video writer for {video_filename}")
                return False
        else:
            self.video_writer = None  # Garante que o writer seja None para análises de arquivos

        # 2. Configura o CSVWriter para os dados de detecção.
        # Este arquivo registra cada detecção com seu timestamp, número de quadro e coordenadas.
        csv_filename = os.path.join(output_folder, f"3_CoordMovimento_{self.base_name}.csv")
        try:
            self.csv_file = open(csv_filename, 'w', newline='')
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(['timestamp', 'frame', 'x1', 'y1', 'x2', 'y2', 'confidence'])
            self.csv_file.flush()
        except IOError as e:
            logging.error(f"Error: Could not open CSV file {csv_filename}. {e}")
            if self.video_writer:
                self.video_writer.release()
            return False

        # 3. Salva os arquivos CSV de definição de área.
        self._save_area_definitions(output_folder)

        self.is_recording = True
        self.start_time = time.time()
        logging.info(f"Started recording. Output folder: {output_folder}")
        return True

    def stop_recording(self):
        """Para a gravação e libera todos os manipuladores de arquivo."""
        if not self.is_recording:
            return

        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None

        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None

        self.is_recording = False
        logging.info(f"Stopped recording for {self.base_name}.")

    def write_video_frame(self, frame):
        """
        Escreve um único quadro no arquivo de vídeo, se o VideoWriter estiver ativo.

        Args:
            frame: O quadro de vídeo (array numpy) a ser escrito.
        """
        if self.is_recording and self.video_writer:
            self.video_writer.write(frame)

    def write_detection_data(self, timestamp, frame_number, detections):
        """
        Escreve os dados de uma ou mais detecções no arquivo CSV.

        Args:
            timestamp (float): O timestamp da detecção em segundos.
            frame_number (int): O número do quadro em que a detecção ocorreu.
            detections (list): Uma lista de tuplas, onde cada tupla representa
                               uma detecção (x1, y1, x2, y2, confidence).
        """
        if self.is_recording and self.csv_writer:
            for (x1, y1, x2, y2, confidence) in detections:
                self.csv_writer.writerow([f"{timestamp:.4f}", frame_number, x1, y1, x2, y2, int(confidence * 100)])
            logging.info(f"Wrote {len(detections)} detections for frame {frame_number}")

    def _save_area_definitions(self, folder_path):
        """
        Salva as definições de área de processamento e áreas de interesse em arquivos CSV.

        - `1_ProcessingArea_...csv`: Salva as coordenadas do polígono que define
          a área total onde a detecção de objetos é realizada.
        - `2_AreasOfInterest_...csv`: Salva as coordenadas dos quadrados (retângulos)
          que definem as áreas de interesse específicas dentro da área de processamento.

        Args:
            folder_path (str): O caminho para a pasta onde os arquivos CSV serão salvos.
        """
        # Salva a Área de Processamento (Polígono)
        processing_area_filename = os.path.join(folder_path, f"1_ProcessingArea_{self.base_name}.csv")
        with open(processing_area_filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['x', 'y'])
            writer.writerows(config.POLYGON)
            f.flush()
            os.fsync(f.fileno())

        # Salva as Áreas de Interesse (Quadrados)
        areas_of_interest_filename = os.path.join(folder_path, f"2_AreasOfInterest_{self.base_name}.csv")
        with open(areas_of_interest_filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['area', 'x1', 'y1', 'x2', 'y2'])
            for i, ((x1, y1), (x2, y2)) in enumerate(config.SQUARES):
                writer.writerow([f'Area {i+1}', x1, y1, x2, y2])
            f.flush()
            os.fsync(f.fileno())

        logging.info(f"Saved area definitions to {folder_path}")

if __name__ == '__main__':
    # Example usage for testing the Recorder module
    print("Testing Recorder module...")

    # Dummy data
    test_output_dir = "test_project/group1_cobaia1"
    frame_width, frame_height = 640, 480

    # Create a dummy frame
    dummy_frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)

    recorder = Recorder()

    # Test start recording
    success = recorder.start_recording(test_output_dir, frame_width, frame_height)

    if success:
        print("\nRecording started successfully.")

        # Test writing data
        recorder.recording_start_frame = 100 # Simulate starting mid-stream
        for i in range(10): # Simulate 10 frames
            frame_num = 100 + i
            # Add some changing element to the frame
            cv2.putText(dummy_frame, f"Frame {frame_num}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            recorder.write_video_frame(dummy_frame)

            # Simulate a detection
            if i % 2 == 0:
                detections = [(100+i, 150, 200+i, 250, 0.95)]
                recorder.write_detection_data(frame_num, detections)

            time.sleep(0.1)

        print("\nFinished writing test data.")

        # Test stop recording
        recorder.stop_recording()

        print(f"\nCheck the '{test_output_dir}' directory for output files.")

    else:
        print("\nFailed to start recording.")

    print("\nRecorder test finished.")
