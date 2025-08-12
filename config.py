import numpy as np

# --- Configurações da Câmera ---
CAMERA_INDEX = 1  # O índice da câmera a ser usada (ex: 0 para a primeira, 1 para a segunda).
DESIRED_WIDTH = 1280  # A largura da resolução de vídeo com a qual as coordenadas foram definidas.
DESIRED_HEIGHT = 720 # A altura da resolução de vídeo com a qual as coordenadas foram definidas.

# --- Configurações do Arduino ---
ARDUINO_PORT = 'COM5'  # A porta serial à qual o Arduino está conectado.
BAUD_RATE = 9600       # A taxa de transmissão para a comunicação serial.

# --- Configurações do Modelo YOLO ---
YOLO_MODEL_PATH = 'best12.pt'  # Caminho para o arquivo de pesos do modelo treinado (.pt).
CONF_THRESHOLD = 0.3           # Limiar de confiança: detecções com confiança abaixo disso são ignoradas.
NMS_THRESHOLD = 0.3            # Limiar de Non-Maximum Suppression (NMS) para filtrar caixas sobrepostas.

# --- Definição das Zonas de Detecção ---
# As coordenadas são definidas para uma resolução de 1280x720 e serão escaladas se o vídeo for diferente.

# SQUARES define as áreas de interesse retangulares (caixas de entrada/saída).
SQUARES = [
    ((150, 490), (360, 660)),  # Canto inferior esquerdo
    ((385, 140), (550, 310)),  # Canto superior esquerdo
    ((630, 490), (765, 660)),  # Canto inferior direito
    ((850, 140), (1020, 310))  # Canto superior direito
]

# Cores para desenhar cada um dos quadrados na tela.
COLORS = [
    (0, 0, 255),    # Vermelho
    (255, 0, 0),    # Azul
    (0, 255, 0),    # Verde
    (0, 0, 255)     # Vermelho
]

# Comandos a serem enviados ao Arduino quando um objeto entra em um dos quadrados.
# A ordem deve corresponder à ordem dos SQUARES.
ENTER_COMMANDS = [1, 3, 5, 7]
# Comandos a serem enviados ao Arduino quando um objeto sai de um dos quadrados.
EXIT_COMMANDS = [2, 4, 6, 8]

# POLYGON define a área de processamento geral. Detecções fora deste polígono são ignoradas.
POLYGON = np.array([
    [150, 310], [385, 310], [385, 140], [550, 140],
    [550, 310], [850, 310], [850, 140], [1020, 140],
    [1020, 490], [765, 490], [765, 660], [630, 660],
    [630, 490], [360, 490], [360, 660], [150, 660]
], np.int32)

# --- Configurações de Vídeo e Processamento ---
FPS = 30  # Frames Por Segundo: usado ao salvar arquivos de vídeo.

# A detecção de objetos é executada a cada `PROCESSING_INTERVAL` quadros.
# Isso é feito para otimizar o desempenho, já que a detecção pode ser lenta.
PROCESSING_INTERVAL = 10

# Um deslocamento para o início do processamento. (frame_number - OFFSET) % INTERVAL == 0
# Com offset = 1 e interval = 10, processará os quadros 1, 11, 21, ...
PROCESSING_OFFSET = 1
