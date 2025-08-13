"""
Este módulo define a interface gráfica principal (GUI) para a aplicação Zebtrack.

A classe `ApplicationGUI` gerencia a janela principal, os widgets da interface,
a inicialização dos módulos de backend (câmera, detector, etc.) e a coordenação
das threads de processamento de vídeo e detecção de objetos.
"""
import tkinter as tk
from tkinter import (filedialog, simpledialog, messagebox, Button, Label, Frame,
                     StringVar, OptionMenu, Toplevel, Scale, Checkbutton,
                     IntVar, BooleanVar, Entry)
import threading
import queue
import time
import os
import cv2
import logging

# Import custom modules
import config
from camera import Camera
from arduino import Arduino
from detector import Detector, draw_overlay
from recorder import Recorder
from project_manager import ProjectManager
from video_source import VideoFileSource

class ApplicationGUI:
    """
    A classe principal que gerencia a interface gráfica e a lógica da aplicação.

    Esta classe é responsável por:
    - Construir a janela principal e as visualizações da interface (boas-vindas e controle principal).
    - Inicializar e gerenciar os módulos de backend como câmera, detector e gravador.
    - Manter o estado da aplicação através de variáveis de controle.
    - Orquestrar as threads para captura de quadros, detecção de objetos e gravação de vídeo
      para garantir que a interface do usuário permaneça responsiva.
    """
    def __init__(self, root):
        """
        Inicializa a ApplicationGUI.

        Args:
            root (tk.Tk): A janela raiz do Tkinter para a aplicação.
        """
        self.root = root
        self.root.title("Zebtrack Controller")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # --- Inicialização dos Módulos ---
        # Cada módulo lida com uma parte específica da lógica do backend.
        self.camera = None  # Câmera será inicializada apenas se um projeto 'live' for criado.
        self.arduino = Arduino()
        self.detector = None # Detector será inicializado após o carregamento de um projeto.
        self.recorder = Recorder()
        self.project_manager = ProjectManager()

        # --- Variáveis de Estado ---
        # Controlam o fluxo e o comportamento da aplicação em tempo de execução.
        self.is_processing = True  # Flag para habilitar/desabilitar a detecção de objetos.
        self.is_capturing_for_video = False  # Flag para indicar se os quadros devem ser salvos em um vídeo.
        self.is_recording = False  # Flag mestre para indicar se os dados (CSV, vídeo) devem ser gravados.
        self.active_frame_source = None  # Armazena a fonte de quadros ativa (câmera ou arquivo de vídeo).
        self.welcome_frame = None  # Contêiner para a tela de boas-vindas.
        self.main_controls_frame = None  # Contêiner para os controles principais da aplicação.
        self.currently_processing_video = None  # Caminho para o arquivo de vídeo sendo processado no momento.

        # --- Threads e Filas ---
        # Usado para executar tarefas demoradas (como processamento de vídeo) sem bloquear a GUI.
        self.program_exit_event = threading.Event()  # Sinaliza para todas as threads que o programa está fechando.
        self.video_stop_event = threading.Event()  # Sinaliza para a thread de gravação de vídeo parar.
        self.frame_queue = queue.Queue(maxsize=10)  # Fila para passar quadros da thread de captura para a de detecção.
        self.video_queue = queue.Queue(maxsize=300)  # Fila para passar quadros para a thread de gravação de vídeo.

        # --- Variáveis de UI para Opções de Processamento ---
        self.processing_interval_var = StringVar(value=str(config.PROCESSING_INTERVAL))
        self.show_preview_var = BooleanVar(value=True)
        self.use_openvino_var = BooleanVar(value=True)

        # --- Elementos da UI ---
        # Inicia a aplicação mostrando a tela de boas-vindas.
        self._create_welcome_frame()

    def _create_welcome_frame(self):
        """Creates the initial UI for project selection."""
        if self.main_controls_frame:
            self.main_controls_frame.destroy()

        self.root.geometry("400x150")
        self.welcome_frame = Frame(self.root)
        self.welcome_frame.pack(expand=True)

        Label(self.welcome_frame, text="Welcome to Zebtrack Controller", font=("Helvetica", 16)).pack(pady=10)

        btn_frame = Frame(self.welcome_frame)
        btn_frame.pack(pady=10)

        Button(btn_frame, text="Create New Project", command=self._create_project_workflow).pack(side="left", padx=10)
        Button(btn_frame, text="Open Existing Project", command=self._open_project_workflow).pack(side="left", padx=10)

    def _create_main_control_frame(self):
        """Creates the main UI for controlling the application after a project is loaded."""
        if self.welcome_frame:
            self.welcome_frame.destroy()

        self.root.geometry("") # Reset geometry
        self.main_controls_frame = Frame(self.root)
        self.main_controls_frame.pack(padx=10, pady=10)

        project_type = self.project_manager.get_project_type()

        if project_type == "live":
            Button(self.main_controls_frame, text="Define Groups", command=self._define_groups).pack(side="left", padx=5)
            self.start_rec_btn = Button(self.main_controls_frame, text="Start Recording", command=self._start_recording)
            self.start_rec_btn.pack(side="left", padx=5)
            self.stop_rec_btn = Button(self.main_controls_frame, text="Stop Recording", command=self._stop_recording, state="disabled")
            self.stop_rec_btn.pack(side="left", padx=5)
        elif project_type == "pre-recorded":
            # Frame for pre-recorded controls, separating buttons and options
            prerecorded_controls_frame = Frame(self.main_controls_frame)
            prerecorded_controls_frame.pack(side="left")

            # --- Row 1: Buttons ---
            button_frame = Frame(prerecorded_controls_frame)
            button_frame.pack(fill="x", padx=5, pady=2)
            Button(button_frame, text="Define Groups", command=self._define_groups).pack(side="left")
            self.process_video_btn = Button(button_frame, text="Process Next Video", command=self._process_next_video)
            self.process_video_btn.pack(side="left", padx=5)

            # --- Row 2: Options ---
            options_frame = Frame(prerecorded_controls_frame)
            options_frame.pack(fill="x", padx=5, pady=2)
            Label(options_frame, text="Frame Interval:").pack(side="left")
            Entry(options_frame, textvariable=self.processing_interval_var, width=5).pack(side="left")
            Checkbutton(options_frame, text="Show Preview", variable=self.show_preview_var).pack(side="left", padx=10)

        Button(self.main_controls_frame, text="Close Project", command=self._close_project).pack(side="left", padx=5)

        status_text = f"Project: {self.project_manager.get_project_name()} ({project_type})"
        self.status_var = StringVar(value=status_text)
        Label(self.root, textvariable=self.status_var).pack(pady=5)

    def _load_project_view(self):
        """
        Transiciona da tela de boas-vindas para a visualização de controle principal.

        Este método é chamado após um projeto ser criado ou carregado. Ele configura
        a fonte de quadros (câmera ou prepara para arquivos de vídeo) e inicia as
        threads de núcleo para captura e processamento de quadros.
        """
        # O Detector é inicializado aqui porque agora temos as informações do projeto
        # (incluindo se deve usar OpenVINO ou não).
        self.detector = Detector(self.project_manager)

        self._create_main_control_frame()

        project_type = self.project_manager.get_project_type()
        if project_type == "live":
            # For live projects, attempt to connect to the Arduino.
            if not self.arduino.connect():
                messagebox.showwarning("Arduino Warning", "Could not connect to Arduino. Running in offline mode.")

            try:
                self.camera = Camera()
                self.active_frame_source = self.camera
                # Update detector scaling for the live camera resolution
                self.detector.update_scaling(self.camera.actual_width, self.camera.actual_height)
            except IOError as e:
                messagebox.showerror("Camera Error", str(e))
                self._create_welcome_frame() # Go back to welcome screen
                return
        elif project_type == "pre-recorded":
            # Update UI based on project state
            next_video = self.project_manager.get_next_video()
            if next_video is None:
                self.process_video_btn.config(state="disabled")
                self.status_var.set(f"Project: {self.project_manager.get_project_name()} - All videos processed.")
            else:
                self.status_var.set(f"Project: {self.project_manager.get_project_name()} - Ready to process: {os.path.basename(next_video)}")

        # --- Inicia as Threads de Núcleo ---
        self.capture_thread = None
        self.processing_thread = None

        if project_type == "live":
            # Para projetos ao vivo, a thread de captura e processamento são iniciadas
            # imediatamente e rodam durante toda a vida do projeto.
            self.capture_thread = threading.Thread(target=self._live_frame_capture_loop, name="CaptureThread", daemon=True)
            self.processing_thread = threading.Thread(target=self._live_processing_loop, name="ProcessingThread", daemon=True)
            logging.info("Starting core threads for LIVE project.")
            self.capture_thread.start()
            self.processing_thread.start()

        # Para projetos pré-gravados, a thread de processamento é criada e iniciada
        # apenas quando o usuário clica em "Process Next Video".

    # --- Core Application Loops (run in threads) ---
    def _live_frame_capture_loop(self):
        """
        Loop para capturar quadros de uma fonte AO VIVO (câmera).

        Esta função é executada em uma thread separada para não bloquear a GUI.
        Ela lê continuamente da câmera e coloca os quadros em uma fila
        para serem processados pela `_live_processing_loop`.
        """
        live_frame_count = 0
        while not self.program_exit_event.is_set():
            if not self.active_frame_source:
                time.sleep(0.1)
                continue

            ret, frame = self.active_frame_source.get_frame()
            if not ret:
                logging.error("Capture thread: Failed to get frame from live source.")
                time.sleep(0.5)
                continue

            live_frame_count += 1

            if not self.frame_queue.full():
                self.frame_queue.put((live_frame_count, frame.copy()))
            if self.is_capturing_for_video and not self.video_queue.full():
                self.video_queue.put(frame.copy())

            time.sleep(1 / (config.FPS * 1.5))

    def _live_processing_loop(self):
        """
        Loop para processar quadros de uma fonte AO VIVO.

        Consome quadros da `frame_queue`, executa a detecção, desenha
        sobreposições e exibe o resultado.
        """
        while not self.program_exit_event.is_set():
            try:
                frame_number, frame = self.frame_queue.get(timeout=1)
            except queue.Empty:
                continue

            if self.is_processing:
                detections, command = self.detector.process_frame(frame, 'live')
                if command is not None:
                    self.arduino.send_command(command)
                if self.is_recording and detections:
                    timestamp = time.time() - self.recorder.start_time
                    self.recorder.write_detection_data(timestamp, frame_number, detections)
                draw_overlay(frame, detections, self.detector)

            cv2.imshow('Live View', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self._on_close()
                break
        cv2.destroyAllWindows()
        logging.info("Live processing loop finished and destroyed CV2 windows.")

    def _file_processing_loop(self):
        """
        Loop para processar um ARQUIVO de vídeo de forma eficiente.

        Este loop é executado em uma única thread e gerencia todo o processo:
        1. Lê as opções da GUI (intervalo, pré-visualização).
        2. Calcula o próximo frame a ser processado com base no intervalo.
        3. Usa `cap.set()` para "saltar" diretamente para o frame de interesse.
        4. Lê, processa, grava dados e, opcionalmente, exibe o frame.
        5. Repete até o final do vídeo e realiza a limpeza.
        """
        if not self.is_recording or not isinstance(self.active_frame_source, VideoFileSource):
            logging.error("File processing loop started in an invalid state.")
            return

        # --- Obter opções da GUI ---
        show_preview = self.show_preview_var.get()
        # The value from the Entry widget is a string, so it must be converted to an integer.
        # Validation is handled before this thread starts, so we can safely convert.
        try:
            processing_interval = int(self.processing_interval_var.get())
        except ValueError:
            # Fallback in case of an unlikely error, though validation should prevent this.
            processing_interval = 1

        if processing_interval < 1:  # Garante que o intervalo seja pelo menos 1
            processing_interval = 1

        video_source = self.active_frame_source
        total_frames = video_source.get_properties()['frame_count']
        frame_number = -1  # Começa em -1 para que o primeiro frame seja o de offset

        while not self.program_exit_event.is_set() and frame_number < total_frames:

            if frame_number < 0:
                # Define o primeiro frame a ser processado
                target_frame = config.PROCESSING_OFFSET if config.PROCESSING_OFFSET > 0 else 1
            else:
                target_frame = frame_number + processing_interval

            if target_frame >= total_frames:
                logging.info(f"Target frame {target_frame} exceeds total frames {total_frames}. Finishing.")
                break

            # Pula para o frame alvo
            video_source.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

            ret, frame = video_source.get_frame()
            if not ret:
                logging.warning(f"Could not read frame {target_frame} even though it's within total_frames.")
                break

            # `get_current_frame_number` pode não ser exato após um `set`, então usamos o target como referência
            frame_number = target_frame
            logging.info(f"Processing frame {frame_number}...")

            # Se a pré-visualização estiver desativada, atualiza a barra de status com o progresso
            if not show_preview:
                if total_frames > 0:
                    progress_percent = int((frame_number / total_frames) * 100)
                    video_name = os.path.basename(self.currently_processing_video)
                    status_msg = f"Processing: {video_name} ({progress_percent}%)"
                    self.root.after(0, self.status_var.set, status_msg)

            # Processamento e gravação
            detections, _ = self.detector.process_frame(frame, 'pre-recorded')
            if detections:
                props = video_source.get_properties()
                timestamp = frame_number / props['fps'] if props['fps'] > 0 else 0
                self.recorder.write_detection_data(timestamp, frame_number, detections)

            # Desenho e exibição (condicional)
            if show_preview:
                draw_overlay(frame, detections, self.detector)
                progress = frame_number / total_frames
                bar_width = int(progress * frame.shape[1])
                bar_height = 20
                cv2.rectangle(frame, (0, frame.shape[0] - bar_height), (frame.shape[1], frame.shape[0]), (50, 50, 50), -1)
                cv2.rectangle(frame, (0, frame.shape[0] - bar_height), (bar_width, frame.shape[0]), (0, 255, 0), -1)
                cv2.imshow('File Processing', frame)

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    logging.info("User requested to stop processing.")
                    self.program_exit_event.set()

        # --- Limpeza Pós-Loop ---
        # Garante que a UI seja atualizada e os recursos liberados
        if show_preview:
            cv2.destroyAllWindows()
        self.root.after(0, self._cleanup_after_processing)

    def _video_recording_loop(self):
        """
        Loop executado em uma thread para gravar quadros em um arquivo de vídeo.

        Esta função é usada apenas para projetos 'live' para salvar a gravação da câmera.
        Ela consome quadros da `video_queue` e os escreve no arquivo de vídeo
        usando o `recorder`.
        """
        logging.info("Video recording thread started.")
        while not self.video_stop_event.is_set():
            try:
                frame = self.video_queue.get(timeout=1)
                self.recorder.write_video_frame(frame)
            except queue.Empty:
                continue
        logging.info("Video recording thread finished.")

    # --- Métodos de Fluxo de Trabalho do Projeto ---
    def _create_project_workflow(self):
        """
        Guia o usuário através do processo de criação de um novo projeto.

        Isso inclui selecionar um diretório, nomear o projeto, escolher o tipo
        (live ou pré-gravado) e, se aplicável, selecionar os arquivos de vídeo.
        """
        base_path = filedialog.askdirectory(title="Select a Parent Folder for the Project")
        if not base_path: return

        project_name = simpledialog.askstring("Project Name", "Enter a name for the new project:")
        if not project_name: return

        project_path = os.path.join(base_path, project_name)
        if os.path.exists(project_path) and os.listdir(project_path):
            messagebox.showerror("Error", "A project folder with this name already exists and is not empty.")
            return

        type_window = Toplevel(self.root)
        type_window.title("Project Type")
        type_var = StringVar()
        Label(type_window, text="Choose the project type:").pack(padx=20, pady=10)

        # Add the OpenVINO checkbox
        Checkbutton(type_window, text="Optimize with OpenVINO (for Intel GPUs)", variable=self.use_openvino_var).pack(padx=20, pady=5)

        Button(type_window, text="Live Analysis", command=lambda: [type_var.set("live"), type_window.destroy()]).pack(fill="x", padx=20, pady=5)
        Button(type_window, text="Pre-recorded Analysis", command=lambda: [type_var.set("pre-recorded"), type_window.destroy()]).pack(fill="x", padx=20, pady=5)
        self.root.wait_window(type_window)
        project_type = type_var.get()

        if not project_type: return

        video_files = []
        if project_type == "pre-recorded":
            video_files = filedialog.askopenfilenames(title="Select Video Files", filetypes=[("Video files", "*.mp4 *.avi")])
            if not video_files: return

        use_openvino = self.use_openvino_var.get()
        success = self.project_manager.create_new_project(
            project_path,
            project_type,
            use_openvino=use_openvino,
            video_files=video_files
        )
        if success:
            logging.info(f"Successfully created project '{project_name}' at {project_path}")
            self._load_project_view()
        else:
            logging.error(f"Failed to create project '{project_name}'")
            messagebox.showerror("Error", "Failed to create the new project.")

    def _open_project_workflow(self):
        """Abre um projeto existente a partir de um diretório selecionado pelo usuário."""
        project_path = filedialog.askdirectory(title="Select an Existing Project Folder")
        if not project_path: return

        if self.project_manager.load_project(project_path):
            logging.info(f"Successfully opened project at {project_path}")
            self._load_project_view()
        else:
            logging.error(f"Failed to load project at {project_path}")
            messagebox.showerror("Error", "Failed to load the project. Check if it's a valid project folder.")

    def _close_project(self):
        """Fecha o projeto atual, para as threads e retorna à tela de boas-vindas."""
        logging.info("Closing project.")

        # Sinaliza para todas as threads que devem terminar.
        self.program_exit_event.set()

        # Lida com o estado de gravação antes de esperar pelas threads
        if self.is_recording:
            logging.info("Recording is active, stopping it before closing.")
            if self.project_manager.get_project_type() == 'live':
                self._stop_recording()
            # Para arquivos, a `program_exit_event` fará com que o loop pare.
            # O cleanup ocorrerá, mas talvez não a atualização da UI, o que é aceitável ao fechar.

        # Espera que as threads terminem de forma segura.
        self._join_threads()
        self.program_exit_event.clear()

        # Libera recursos
        if self.camera:
            self.camera.release()
            self.camera = None
        if self.active_frame_source:
             self.active_frame_source.release()
        self.active_frame_source = None

        # Reseta o estado para um novo projeto
        self.project_manager = ProjectManager()
        self._create_welcome_frame()
        logging.info("Project closed and welcome screen recreated.")

    # --- Métodos de Comando da UI ---
    def _define_groups(self):
        """Permite que o usuário defina nomes para os grupos de tratamento do projeto."""
        group_count = simpledialog.askinteger("Number of Groups", "Enter the total number of groups:")
        if group_count is not None:
            group_names = []
            for i in range(group_count):
                name = simpledialog.askstring("Group Name", f"Enter name for group {i + 1}:")
                if name: group_names.append(name)
            self.project_manager.project_data["groups"] = group_names
            self.project_manager.save_project()
            messagebox.showinfo("Success", "Group names have been updated.")

    def _start_recording(self):
        """Inicia a gravação para um projeto 'live'."""
        if not self.project_manager.project_data.get("groups"):
            messagebox.showwarning("Setup Required", "Please define groups for this project first.")
            return

        selection_window = Toplevel(self.root)
        selection_window.title("Select Group")
        group_names = self.project_manager.project_data["groups"]
        group_var = StringVar(value=group_names[0])
        Label(selection_window, text="Select Group:").pack(padx=10, pady=5)
        OptionMenu(selection_window, group_var, *group_names).pack(padx=10, pady=5)

        def on_confirm():
            cobaia_number = simpledialog.askstring("Cobaia Number", "Enter the cobaia number:")
            if not cobaia_number: return
            selection_window.destroy()

            group_name = group_var.get()
            output_folder = os.path.join(self.project_manager.project_path, f"{group_name}_{cobaia_number}")

            cam_props = self.camera.get_properties()
            success = self.recorder.start_recording(output_folder, cam_props['width'], cam_props['height'])

            if success:
                # Limpa as filas para garantir que a gravação comece do zero
                with self.frame_queue.mutex: self.frame_queue.queue.clear()
                with self.video_queue.mutex: self.video_queue.queue.clear()

                # Ativa as flags de gravação
                self.is_recording = True
                self.is_capturing_for_video = True

                # Inicia a thread de gravação de vídeo
                self.video_stop_event.clear()
                self.video_thread = threading.Thread(target=self._video_recording_loop, daemon=True)
                self.video_thread.start()

                # Atualiza o estado da UI
                self.start_rec_btn.config(state="disabled")
                self.stop_rec_btn.config(state="normal")
                self.status_var.set(f"Recording to: {os.path.basename(output_folder)}")
            else:
                messagebox.showerror("Error", "Failed to start recorder.")

        Button(selection_window, text="Confirm", command=on_confirm).pack(pady=10)

    def _stop_recording(self):
        """Para a gravação de um projeto 'live'."""
        self.is_recording = False
        self.is_capturing_for_video = False

        # Para a thread de gravação de vídeo
        self.video_stop_event.set()
        if hasattr(self, 'video_thread') and self.video_thread.is_alive():
            self.video_thread.join(timeout=5)

        self.recorder.stop_recording()

        # Atualiza o estado da UI
        self.start_rec_btn.config(state="normal")
        self.stop_rec_btn.config(state="disabled")
        self.status_var.set(f"Project: {self.project_manager.get_project_name()} (live) - Ready")
        messagebox.showinfo("Success", "Recording stopped and files saved.")

    def _process_next_video(self):
        """
        Inicia o fluxo de trabalho para processar o próximo vídeo em um projeto 'pre-gravado'.
        """
        if self.is_recording:
            messagebox.showwarning("Busy", "A video is already being processed.")
            return

        video_path = self.project_manager.get_next_video()
        if not video_path:
            messagebox.showinfo("Project Complete", "All videos in this project have been processed.")
            return

        if not self.project_manager.project_data.get("groups"):
            messagebox.showwarning("Setup Required", "Please define groups for this project first.")
            return

        selection_window = Toplevel(self.root)
        selection_window.title("Select Group for this Run")
        group_names = self.project_manager.project_data["groups"]
        group_var = StringVar(value=group_names[0])
        Label(selection_window, text="Select Group:").pack(padx=10, pady=5)
        OptionMenu(selection_window, group_var, *group_names).pack(padx=10, pady=5)

        def on_confirm():
            cobaia_number = simpledialog.askstring("Cobaia Number", "Enter the cobaia number for this run:")
            if not cobaia_number: return
            selection_window.destroy()

            # Validate the frame interval input BEFORE starting the thread
            try:
                interval = int(self.processing_interval_var.get())
                if interval < 1:
                    messagebox.showwarning("Invalid Input", "Frame interval must be 1 or greater.")
                    return
            except ValueError:
                messagebox.showerror("Invalid Input", f"Frame interval must be a valid number. You entered: '{self.processing_interval_var.get()}'")
                return

            try:
                video_source = VideoFileSource(video_path)
                video_props = video_source.get_properties()
                self.detector.update_scaling(video_props['width'], video_props['height'])
            except (IOError, FileNotFoundError) as e:
                messagebox.showerror("Error", f"Could not open video file: {e}")
                return

            self.currently_processing_video = video_path
            video_basename = os.path.splitext(os.path.basename(video_path))[0]
            group_name = group_var.get()
            output_folder_name = f"{video_basename}_{group_name}_{cobaia_number}"
            output_path = os.path.join(self.project_manager.project_path, output_folder_name)

            success = self.recorder.start_recording(output_path, video_props['width'], video_props['height'], is_video_file=True)

            if success:
                logging.info(f"Starting analysis for video: {video_path}")
                self.project_manager.update_video_status(video_path, "processing")
                self.is_recording = True
                self.active_frame_source = video_source

                # Cria e inicia a thread de processamento de arquivo AQUI.
                self.processing_thread = threading.Thread(target=self._file_processing_loop, name="ProcessingThread", daemon=True)
                self.processing_thread.start()

                self.process_video_btn.config(state="disabled")
                self.status_var.set(f"Processing: {os.path.basename(video_path)}")
            else:
                logging.error(f"Failed to start recorder for video processing: {video_path}")
                messagebox.showerror("Error", "Failed to start recorder for video processing.")
                video_source.release()

        Button(selection_window, text="Confirm", command=on_confirm).pack(pady=10)

    def _cleanup_after_processing(self):
        """
        Executa a limpeza necessária após o término do processamento de um arquivo.
        Este método é chamado a partir da thread de processamento através de `root.after()`.
        """
        logging.info(f"Cleaning up after processing video: {os.path.basename(self.currently_processing_video)}.")

        self.is_recording = False
        self.recorder.stop_recording()
        self.project_manager.update_video_status(self.currently_processing_video, "complete")

        if self.active_frame_source:
            self.active_frame_source.release()
            self.active_frame_source = None

        self.currently_processing_video = None
        self.process_video_btn.config(state="normal")

        next_video = self.project_manager.get_next_video()
        if next_video:
            status_msg = f"Ready to process: {os.path.basename(next_video)}"
            self.status_var.set(f"Project: {self.project_manager.get_project_name()} - {status_msg}")
            logging.info(f"Analysis complete. {status_msg}")
        else:
            status_msg = "All videos processed."
            self.status_var.set(f"Project: {self.project_manager.get_project_name()} - {status_msg}")
            logging.info(f"Analysis complete. {status_msg}")

    def _handle_source_finished(self):
        """
        Manipula o fim de uma fonte de quadros.
        Na nova arquitetura, este método é usado principalmente como um placeholder
        ou para cenários de erro em fontes ao vivo, já que a limpeza de arquivos
        é tratada por `_cleanup_after_processing`.
        """
        logging.warning("'_handle_source_finished' was called. This should typically not happen for file processing anymore.")
        if self.is_recording:
            self.is_recording = False
            self.recorder.stop_recording()


    def _on_close(self):
        logging.info("Close button clicked.")
        if messagebox.askokcancel("Quit", "Do you want to exit the program?"):
            logging.info("User confirmed quit.")

            # Sinaliza para todas as threads que devem terminar.
            self.program_exit_event.set()

            # Se uma gravação ao vivo estiver em andamento, pare-a de forma limpa.
            if self.is_recording and self.project_manager.get_project_type() == 'live':
                self._stop_recording()

            # Espera pelas threads e depois destrói a janela.
            # É melhor fazer a junção final em um local para evitar lógicas duplicadas.
            self._join_threads()

            # Libera TODOS os recursos antes de fechar
            if self.camera:
                self.camera.release()
            if self.active_frame_source and not isinstance(self.active_frame_source, Camera):
                self.active_frame_source.release()
            self.arduino.close()

            self.root.destroy()
            logging.info("Application shutdown complete.")

    def _join_threads(self):
        """Espera que todas as threads de núcleo terminem."""
        logging.info("Waiting for core threads to join.")
        if hasattr(self, 'capture_thread') and self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join()
        if hasattr(self, 'processing_thread') and self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join()
        logging.info("Core threads joined.")

if __name__ == '__main__':
    print("This file is intended to be imported, not run directly.")
    print("Run main.py to start the application.")
