import cv2
import numpy as np
import serial
from ultralytics import YOLO
import os
import csv
from tkinter import Tk, filedialog, simpledialog, messagebox, Button, Label, Frame, StringVar, OptionMenu, Toplevel
import time
import threading
import queue

# Variáveis globais
video_queue = queue.Queue()
detection_queue = queue.Queue()
capturing = False  # Inicialmente não estamos capturando
processing = True
stop_event = threading.Event()
program_exit_event = threading.Event()
video_stop_event = threading.Event()  # Novo evento para a thread de gravação

# Configuração da câmera USB
camera_index = 1  # Índice da câmera USB
cap = cv2.VideoCapture(camera_index)

# Definir a resolução desejada para a Logitech C270 HD Webcam
desired_width = 1280  # Largura máxima suportada pela câmera
desired_height = 720  # Altura máxima suportada pela câmera

# Set the resolution
cap.set(cv2.CAP_PROP_FRAME_WIDTH, desired_width)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, desired_height)

# Capturar um frame para obter as dimensões reais
ret, frame = cap.read()
if not ret:
    print("Falha ao capturar imagem da câmera")
    cap.release()
    exit()

actual_height, actual_width = frame.shape[:2]
print(f"Resolução real do frame: {actual_width} x {actual_height}")

arduino_port = 'COM13'  # Modify this with the appropriate serial port
baud_rate = 9600  # Modify this with the appropriate baud rate

confThreshold = 0.3
nmsThreshold = 0.3

crossed_in = False
crossed_out = False
flag = 0
current_square = 0

# Coordinates for lines forming squares
squares = [
    ((150, 490), (360, 660)),  # Quadrado inferior esquerdo
    ((385, 140), (550, 310)),  # Quadrado superior esquerdo
    ((630, 490), (765, 660)),  # Quadrado inferior direito
    ((850, 140), (1020, 310))  # Quadrado superior direito
]

# Colors for the squares
colors = [
    (0, 0, 255),    # Vermelho
    (255, 0, 0),    # Azul
    (0, 255, 0),    # Verde
    (0, 0, 255)     # Vermelho
]

# Commands for entering and exiting each square
enter_commands = [1, 3, 5, 7]
exit_commands = [2, 4, 6, 8]

# Polygon coordinates
polygon = np.array([
    [150, 310],
    [385, 310],
    [385, 140],
    [550, 140],
    [550, 310],
    [850, 310],
    [850, 140],
    [1020, 140],
    [1020, 490],
    [765, 490],
    [765, 660],
    [630, 660],
    [630, 490],
    [360, 490],
    [360, 660],
    [150, 660]
], np.int32)

# Initialize Tkinter
root = Tk()
root.title("Controle de Gravação")

processing_status = StringVar()
processing_status_label = Label(root, textvariable=processing_status)
processing_status_label.pack()

recording = False
out = None
csv_file = None
csv_writer = None
frame_count = 0
recording_start_frame_count = None  # Adicione esta linha
fps = 30  # Taxa de quadros alvo
start_time = 0  # Inicialização da variável
#stop_event = threading.Event()
recording_start_time = None

# Estabelecer conexão serial com o Arduino Nano
arduino = serial.Serial(arduino_port, baud_rate, timeout=1)

def send_servo_command(boxNumber):
    command = f"{boxNumber}\n"  # Adicionar caractere de nova linha ao comando
    print(f"Enviando comando para Arduino: {command}")  # Para depuração
    arduino.write(command.encode('utf-8'))

def is_inside_square(x1, y1, x2, y2, square):
    (sx1, sy1), (sx2, sy2) = square
    return not (x2 < sx1 or x1 > sx2 or y2 < sy1 or y1 > sy2)

def is_inside_polygon(x1, y1, x2, y2, polygon):
    rect = np.array([
        [x1, y1],
        [x2, y1],
        [x2, y2],
        [x1, y2]
    ], np.int32)
    return cv2.pointPolygonTest(polygon, (x1, y1), False) >= 0 or cv2.pointPolygonTest(polygon, (x2, y2), False) >= 0

# Função findObject
def findObject(outputs, img, csv_writer=None, frame_count=0, timestamp=0):
    global crossed_in, crossed_out, flag, current_square
    
    hT, wT, cT = img.shape
    bbox = []
    confs = []

    for det in outputs:
        x1, y1, x2, y2, confidence = det[:5]
        
        if confidence > confThreshold:
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            bbox.append([x1, y1, x2, y2])
            confs.append(float(confidence))

    indices = cv2.dnn.NMSBoxes(bbox, confs, confThreshold, nmsThreshold)

    if len(indices) > 0:
        for i in indices:
            i = i[0] if isinstance(i, list) else i  # Lidar com diferentes tipos de retorno de NMSBoxes
            box = bbox[i]
            x1, y1, x2, y2 = box[0], box[1], box[2], box[3]
            
            if is_inside_polygon(x1, y1, x2, y2, polygon):  # Proceder apenas se a bounding box estiver dentro do polígono
                cv2.rectangle(img, (x1, y1), (x2, y2), (255, 0, 255), 2)
                cv2.putText(img, f'{int(confs[i] * 100)}%', (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
                
                if csv_writer:
                    csv_writer.writerow([timestamp, frame_count, x1, y1, x2, y2, int(confs[i] * 100)])
 
                if flag == 0:
                    for index, square in enumerate(squares):
                        if is_inside_square(x1, y1, x2, y2, square):
                            crossed_in = True
                            flag = 1
                            current_square = index + 1
                            print(f"BoxNumber {enter_commands[index]} ON")
                            send_servo_command(enter_commands[index])
                            break  # Sair do loop uma vez dentro de um quadrado
                elif flag == 1:
                    if not any(is_inside_square(x1, y1, x2, y2, square) for square in squares):
                        crossed_out = True
                        flag = 0
                        print(f"BoxNumber {exit_commands[current_square - 1]} OFF")
                        send_servo_command(exit_commands[current_square - 1])
                        current_square = 0

# Variável global para o intervalo de processamento
processing_interval = 10  # Processar a cada x frames
processing_offset = 1     # Começar no frame y


def frame_capture_thread():
    global cap, program_exit_event, frame_count, capturing, processing
    while not program_exit_event.is_set():
        ret, frame = cap.read()
        if not ret:
            print("Falha ao capturar imagem da câmera no thread de captura")
            break
        frame_count += 1

        # Colocar frames na detection_queue se processing for true
        if processing:
            try:
                detection_frame = frame.copy()
                detection_queue.put((frame_count, detection_frame))
            except Exception as e:
                print(f"Erro ao colocar frame na fila de detecção: {e}")
                continue

        # Colocar frames na video_queue se capturing for True
        if capturing:
            try:
                video_frame = frame.copy()
                video_queue.put((frame_count, video_frame))
            except Exception as e:
                print(f"Erro ao colocar frame na fila de vídeo: {e}")
                continue



def video_recording_thread():
    global out, video_stop_event, recording, frame_count
    print("Video recording thread started")
    while not video_stop_event.is_set() and recording:
        try:
            frame_count, frame = video_queue.get(timeout=1)
            if frame is None or out is None or not out.isOpened():
                print("Frame ou 'out' inválido, não será gravado.")
                continue
            out.write(frame)
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Erro ao escrever frame no vídeo: {e}")
            break
    print("Video recording thread finished")
    # Liberar recursos ao terminar
    if out:
        out.release()
    if csv_file is not None:
        csv_file.close()



# Thread para processamento de objetos e exibição em tempo real
def object_detection_thread():
    global stop_event, recording_start_time, processing, recording_start_frame_count

    model = YOLO('C:\\Users\\santa\\OneDrive\\Desktop\\Codigos_Prontos\\best12.pt')
    print("Object detection thread started")

    while not stop_event.is_set():
        if not processing:
            time.sleep(0.1)
            continue
        try:
            frame_count, frame = detection_queue.get(timeout=1)
            current_time = time.time()
            timestamp = current_time - (recording_start_time or current_time)

            # Calcular o número do frame relativo à gravação atual
            if recording and recording_start_frame_count is not None:
                adjusted_frame_count = frame_count - recording_start_frame_count
            else:
                adjusted_frame_count = 0

            # Realizar a inferência
            if (frame_count - processing_offset) % processing_interval == 0:
                results = model(frame)
                predictions = results[0].boxes.data.cpu().numpy()
                findObject(predictions, frame, csv_writer if recording else None, adjusted_frame_count, timestamp)
                print(f"Processando frame {frame_count}")

            # Desenhar quadrados e polígono
            for i, ((x1, y1), (x2, y2)) in enumerate(squares):
                cv2.rectangle(frame, (x1, y1), (x2, y2), colors[i], 2)
            cv2.polylines(frame, [polygon], isClosed=True, color=(0, 0, 0), thickness=1)

            cv2.imshow('Image', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                stop_event.set()
                break
        except queue.Empty:
            time.sleep(0.1)
            continue
    print("Object detection thread finished")
    cv2.destroyAllWindows()



#def detection_complete():
#    processing_status.set("")  # Limpar o status de processamento
#    root.after(0, lambda: messagebox.showinfo("Informação", "Processamento de detecção concluído."))


def wait_for_detection_to_finish():
    global detection_thread, stop_event
    detection_thread.join()
    stop_event.clear()  # Limpa o evento para permitir que o thread seja iniciado novamente
#    detection_complete()


def start_detection_thread():
    global detection_thread, stop_event
    stop_event.clear()  # Limpa o stop_event para que a thread de detecção funcione
    detection_thread = threading.Thread(target=object_detection_thread)
    detection_thread.start()



# Variável global para armazenar os nomes dos grupos
group_names = []

# Function to create a project
def create_project_button():
    global group_names, project_folder_path
    
    # Abrir uma janela para selecionar uma pasta
    selected_folder = filedialog.askdirectory(title="Selecione a pasta onde criar o novo projeto")
    
    # Se o usuário não selecionou nada, retornar
    if not selected_folder:
        return

    # Pedir ao usuário um nome para a nova pasta
    new_folder_name = simpledialog.askstring("Nome da Pasta", "Digite o nome para a nova pasta:")

    # Se o usuário não fornecer um nome, retornar
    if not new_folder_name:
        return

    # Criar a nova pasta no diretório selecionado
    new_folder_path = os.path.join(selected_folder, new_folder_name)
    
    try:
        os.makedirs(new_folder_path, exist_ok=False)
        messagebox.showinfo("Sucesso", f"Pasta '{new_folder_name}' criada com sucesso em:\n{new_folder_path}")
        project_folder_path = new_folder_path
    except FileExistsError:
        messagebox.showerror("Erro", "A pasta já existe. Tente outro nome.")
    except Exception as e:
        messagebox.showerror("Erro", f"Erro ao criar a pasta: {str(e)}")
    
    # Perguntar ao usuário a quantidade de grupos
    group_count = simpledialog.askinteger("Quantidade de Grupos", "Digite a quantidade de grupos:")
    if group_count is not None:
        group_names = []
        for i in range(group_count):
            group_name = simpledialog.askstring("Nome do Grupo", f"Digite o nome do grupo {i + 1}:")
            if group_name:
                group_names.append(group_name)
        messagebox.showinfo("Informação", f"Você especificou os seguintes grupos:\n" + "\n".join(group_names))
    else:
        messagebox.showwarning("Atenção", "Nenhuma quantidade de grupos foi especificada.")

# Function to start recording
def start_recording_button(use_timer=False):
    global recording, capturing, group_names, project_folder_path
    if not recording:
        if not group_names:
            messagebox.showwarning("Aviso", "Nenhum grupo foi criado. Crie um projeto primeiro.")
            return

        # Janela para seleção de grupo
        group_var = StringVar(root)
        group_var.set(group_names[0])  # Valor padrão
        group_selection_window = Toplevel(root)
        group_selection_window.title("Selecionar Grupo")

        Label(group_selection_window, text="Selecione o grupo:").pack()
        group_dropdown = OptionMenu(group_selection_window, group_var, *group_names)
        group_dropdown.pack()

        def confirm_group():
            global out, csv_file, csv_writer, frame_count, recording, recording_start_time, video_stop_event
            global capturing, recording_start_frame_count, stop_event, base_name
            global timer_running, timer_window, processing, capturing

            cobaia_number = simpledialog.askstring("Número da Cobaia", "Digite o número da cobaia:")
            if not cobaia_number:
                messagebox.showwarning("Aviso", "Você deve fornecer um número para a cobaia.")
                return

            # Fechar a janela de seleção de grupo
            group_selection_window.destroy()

            # Definir 'recording_start_time' e 'recording_start_frame_count' aqui
            recording_start_time = time.time()
            recording_start_frame_count = frame_count  # Captura o frame_count no início da gravação

            # Criar a nova pasta no diretório do projeto
            new_folder_name = f"{group_var.get()}_{cobaia_number}"
            new_folder_path = os.path.join(project_folder_path, new_folder_name)
            try:
                os.makedirs(new_folder_path, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao criar a pasta: {str(e)}")
                return

            # Configurar o caminho e nome do arquivo de vídeo
            out_filename = f"{group_var.get()}_{cobaia_number}.mp4"
            out_full_path = os.path.join(new_folder_path, out_filename)
            folder_path = os.path.dirname(out_full_path)

            # Configurar o gravador de vídeo
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            frame_width, frame_height = actual_width, actual_height
            out = cv2.VideoWriter(out_full_path, fourcc, fps, (frame_width, frame_height))

            if not out.isOpened():
                messagebox.showerror("Erro", "Não foi possível inicializar o gravador de vídeo.")
                return

            # Criar o arquivo CSV
            base_name = f"{group_var.get()}_{cobaia_number}"
            csv_filename = os.path.join(folder_path, f"3_CoordMovimento_{base_name}.csv")
            csv_file = open(csv_filename, mode='w', newline='')
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(['timestamp', 'frame', 'x1', 'y1', 'x2', 'y2', 'confidence'])

            # Criar arquivos CSV adicionais conforme necessário

            # Function to create CSV files
            def create_csv(filename, headers):
                with open(filename, mode='w', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(headers)

            # Construct the filenames with the desired structure
            processing_area_filename = os.path.join(folder_path, f"1_ProcessingArea_{base_name}.csv")
            areas_of_interest_filename = os.path.join(folder_path, f"2_AreasOfInterest_{base_name}.csv")

            # Create CSV files for coordinates with the new filenames
            create_csv(processing_area_filename, ['x', 'y'])
            create_csv(areas_of_interest_filename, ['area', 'x1', 'y1', 'x2', 'y2'])

            # Save the coordinates of the processing area (polygon)
            with open(processing_area_filename, mode='a', newline='') as file:
                writer = csv.writer(file)
                for point in polygon:
                    writer.writerow(point)

            # Save the coordinates of the areas of interest (squares)
            with open(areas_of_interest_filename, mode='a', newline='') as file:
                writer = csv.writer(file)
                for i, ((x1, y1), (x2, y2)) in enumerate(squares):
                    writer.writerow([f'Area {i+1}', x1, y1, x2, y2])

            print(f"Files '{processing_area_filename}' and '{areas_of_interest_filename}' have been created.")

            # Limpar a fila de detecção antes de iniciar a nova gravação.
            with detection_queue.mutex:
                detection_queue.queue.clear()

            # Definir 'capturing' e 'recording' como True
            capturing = True  # Iniciar a captura de frames
            recording = True  # Iniciar gravação
            processing = True  # Iniciar o processamento de frames

            # Limpar o evento de parada antes de iniciar os threads
            stop_event.clear()

            # Iniciar o thread de detecção após configurar tudo
            #start_detection_thread()
            video_stop_event.clear()  # Limpar o evento antes de iniciar a thread
            # Iniciar thread de gravação de vídeo
            global video_thread  # Adicione esta linha
            video_thread = threading.Thread(target=video_recording_thread)
            video_thread.start()

            # Iniciar o timer se use_timer for True
            if use_timer:
                # Criar uma janela para mostrar o timer
                timer_window = Toplevel(root)
                timer_window.title("Timer de Gravação")
                timer_label = Label(timer_window, text="Tempo Restante: 5:00", font=("Helvetica", 16))
                timer_label.pack()

                # Iniciar o timer em uma thread separada
                timer_running = True
                threading.Thread(target=run_timer, args=(timer_label,), daemon=True).start()

        Button(group_selection_window, text="Confirmar", command=confirm_group).pack()



# Function to stop recording
def stop_recording_button():
    global recording, out, csv_file, csv_writer, capturing, processing
    global recording_start_frame_count
    global timer_running, timer_window
    global video_stop_event, video_thread, detection_queue

    if recording:
        recording = False
        capturing = False  # Parar de capturar frames para gravação
        processing = False  # Parar de processar frames
        # Limpar a fila de detecção
        with detection_queue.mutex:
            detection_queue.queue.clear()
        recording_start_frame_count = None
        processing_status.set("Processando frames restantes...")

        # Sinalizar para que a thread de gravação finalize
        video_stop_event.set()

        # Aguarda a conclusão da thread de gravação
        if video_thread.is_alive():
            video_thread.join()

        # Liberar recursos relacionados ao vídeo
        if out is not None:
            out.release()
            out = None
        if csv_file is not None:
            csv_file.close()
            csv_file = None
        csv_writer = None

        # Informar o usuário
        root.after(0, lambda: messagebox.showinfo("Informação", "Arquivos de vídeo e CSV gravados."))

        # Limpa o status de processamento após o término
        root.after(0, lambda: processing_status.set(""))

        # Parar o timer se estiver em execução
        if timer_running:
            timer_running = False
            if timer_window:
                timer_window.destroy()
                timer_window = None

        # Limpar o evento para a próxima gravação
        video_stop_event.clear()




#def restart_camera():
#    global cap, capturing, processing, detection_thread

    # Reabre a captura de vídeo se foi liberada
#    if not cap.isOpened():
#        cap.open(camera_index)

    # Reinicia a captura e processamento para exibição em tempo real
#    capturing = False
#    processing = True  # Permitindo a captura para visualização ao vivo
#    stop_event.clear()  # Limpar sinal para iniciar nova detecção

    # Inicia uma nova thread de detecção
    #start_detection_thread()





# Function to end the project
def end_project_button():
    global recording, group_names, project_folder_path, out, csv_file, csv_writer
    if recording:
        stop_recording_button()
        print("e1")
    # Resetar variáveis relacionadas ao projeto
    group_names = []
    project_folder_path = None
    print("e2")
    # Opcionalmente, resetar outras variáveis se necessário
    # Informar o usuário
    messagebox.showinfo("Informação", "Projeto encerrado. As configurações foram reiniciadas.")
    # O programa permanece em execução, pronto para iniciar um novo projeto
    print("e3")


# Function to end the program
def end_program_button():
    global stop_event, program_exit_event, recording, cap
    stop_event.set()
    program_exit_event.set()
    print("e4")
    if recording:
        stop_recording_button()
        print("e5")
    # Liberar recursos
    cap.release()
    print("e6")
    cv2.destroyAllWindows()
    print("e7")
    # Encerrar a interface Tkinter
    root.quit()
    print("e8")
    # Sair do programa
    import sys
    print("e9")
    sys.exit()


# Variáveis globais para o timer
timer_window = None
timer_running = False

# Função para iniciar a gravação com timer
def start_recording_with_timer():
    start_recording_button(use_timer=True)
    

# Função para o timer
def run_timer(label):
    global timer_running, timer_window
    total_seconds = 5 * 60  # 5 minutos

    while total_seconds > 0 and timer_running:
        mins, secs = divmod(total_seconds, 60)
        label.config(text=f"Tempo Restante: {mins:02}:{secs:02}")
        time.sleep(1)
        total_seconds -= 1

    if timer_running:  # Timer terminou naturalmente
        label.config(text="Tempo Esgotado!")
        stop_recording_button()  # Parar gravação automaticamente

    # Fechar a janela do timer independentemente do estado de timer_running
    if timer_window:
        timer_window.destroy()
        timer_window = None  # Opcionalmente, redefina para None



# Função para parar a gravação e o timer
#def stop_recording_with_timer():
#    global timer_running, timer_window

    # Parar o timer
#    timer_running = False

    # Fechar a janela do timer, se aberta
#    if timer_window:
#        timer_window.destroy()
#        timer_window = None

    # Parar a gravação
#    stop_recording_button()

# Iniciar threads
threading.Thread(target=frame_capture_thread, daemon=True).start()
detection_thread = threading.Thread(target=object_detection_thread)
detection_thread.start()

# Create buttons
def create_buttons():
    create_project_btn = Button(root, text="Criar Projeto", command=create_project_button)
    create_project_btn.pack(side="left")

    start_recording_btn = Button(root, text="Iniciar Gravação", command=start_recording_button)
    start_recording_btn.pack(side="left")

    start_recording_with_timer_btn = Button(root, text="Iniciar Gravação (com Timer)", command=start_recording_with_timer)
    start_recording_with_timer_btn.pack(side="left")

    stop_recording_btn = Button(root, text="Parar Gravação", command=stop_recording_button)
    stop_recording_btn.pack(side="left")

    end_project_btn = Button(root, text="Terminar Projeto", command=end_project_button)
    end_project_btn.pack(side="left")

    end_program_btn = Button(root, text="Terminar Programa", command=end_program_button)
    end_program_btn.pack(side="left")

#    stop_recording_btn = Button(root, text="Parar Gravação (com Timer)", command=stop_recording_with_timer)
#    stop_recording_btn.pack(side="left")


create_buttons()



# Start the update loop
root.mainloop()
