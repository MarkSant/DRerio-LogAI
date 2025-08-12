"""
Este módulo define a interface gráfica principal (GUI) para a aplicação Zebtrack.

A classe `ApplicationGUI` gerencia a janela principal, os widgets da interface,
a inicialização dos módulos de backend (câmera, detector, etc.) e a coordenação
das threads de processamento de vídeo e detecção de objetos.
"""
import tkinter as tk
from tkinter import (filedialog, simpledialog, messagebox, Button, Label, Frame,
                     StringVar, OptionMenu, Toplevel)
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
        self.detector = Detector()
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
        self.source_finished_event = threading.Event()  # Sinaliza que a fonte de vídeo (arquivo) terminou.
        self.frame_queue = queue.Queue(maxsize=10)  # Fila para passar quadros da thread de captura para a de detecção.
        self.video_queue = queue.Queue(maxsize=300)  # Fila para passar quadros para a thread de gravação de vídeo.

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
            Button(self.main_controls_frame, text="Define Groups", command=self._define_groups).pack(side="left", padx=5)
            self.process_video_btn = Button(self.main_controls_frame, text="Process Next Video", command=self._process_next_video)
            self.process_video_btn.pack(side="left", padx=5)

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
        self._create_main_control_frame()

        project_type = self.project_manager.get_project_type()
        if project_type == "live":
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

        # --- Start Core Threads ---
        self.capture_thread = threading.Thread(target=self._frame_capture_loop, name="CaptureThread", daemon=True)
        self.processing_thread = threading.Thread(target=self._object_detection_loop, name="ProcessingThread", daemon=True)

        logging.info("Starting core threads.")
        self.capture_thread.start()
        self.processing_thread.start()

    # --- Core Application Loops (run in threads) ---
    def _frame_capture_loop(self):
        """
        Loop executado em uma thread para capturar quadros da fonte ativa.

        Esta função continuamente:
        1. Verifica se há uma fonte de quadros ativa (`self.active_frame_source`).
        2. Obtém o número do quadro (do arquivo de vídeo ou de um contador para live).
        3. Lê o quadro da fonte.
        4. Se a fonte terminar, sinaliza `_handle_source_finished`.
        5. Coloca o par (número do quadro, imagem do quadro) na `frame_queue` para
           ser consumido pela thread de detecção.
        6. Se a gravação de vídeo estiver ativa, também coloca o quadro na `video_queue`.
        """
        live_frame_count = 0
        while not self.program_exit_event.is_set():
            if not self.active_frame_source:
                time.sleep(0.1)  # Aguarda por uma fonte ativa.
                continue

            is_file_source = isinstance(self.active_frame_source, VideoFileSource)

            frame_number = 0
            if is_file_source:
                # Para arquivos de vídeo, o número do quadro da fonte é a autoridade.
                frame_number = int(self.active_frame_source.get_current_frame_number())
            else:
                # Para fontes ao vivo, usamos um contador simples.
                live_frame_count += 1
                frame_number = live_frame_count

            ret, frame = self.active_frame_source.get_frame()
            if not ret:
                logging.info(f"Capture thread: end of source at frame number {frame_number}.")
                if is_file_source:
                    # Notifica a thread principal da GUI que a fonte terminou.
                    self.root.after(0, self._handle_source_finished)
                self.active_frame_source = None
                continue

            # Coloca o quadro na fila para processamento.
            if not self.frame_queue.full():
                self.frame_queue.put((frame_number, frame.copy()))

            # Se a gravação de vídeo estiver habilitada, coloca o quadro na fila de vídeo.
            if self.is_capturing_for_video and not self.video_queue.full():
                self.video_queue.put(frame.copy())

            # Para fontes ao vivo, um pequeno delay evita o uso excessivo da CPU.
            # Para arquivos, processamos o mais rápido possível.
            if not is_file_source:
                time.sleep(1 / (config.FPS * 1.5))

    def _object_detection_loop(self):
        """
        Loop executado em uma thread para processar quadros e detectar objetos.

        Esta função continuamente:
        1. Pega um quadro da `frame_queue`.
        2. Se a fonte terminou e a fila está vazia, o loop termina.
        3. A cada `PROCESSING_INTERVAL` quadros, executa o modelo de detecção.
        4. Se detecções são encontradas durante a gravação, as envia para o `recorder`.
        5. Desenha as sobreposições (caixas de detecção, etc.) e a barra de progresso no quadro.
        6. Exibe o quadro processado em uma janela do OpenCV.
        """
        while not self.program_exit_event.is_set():
            try:
                frame_number, frame = self.frame_queue.get(timeout=1)
            except queue.Empty:
                # Se a fonte de vídeo terminou e a fila está vazia, podemos sair.
                if self.source_finished_event.is_set():
                    logging.info("Source is finished and queue is empty, exiting detection loop.")
                    break  # Saída graciosa do loop.
                continue  # Caso contrário, continue esperando por quadros.

            # Determine if the source is a file before processing
            is_file_source = isinstance(self.active_frame_source, VideoFileSource)
            project_type = self.project_manager.get_project_type()

            if self.is_processing:
                # Use a consistent processing interval, respecting the config file
                if (frame_number - config.PROCESSING_OFFSET) % config.PROCESSING_INTERVAL == 0:
                    logging.info(f"Detection loop: Processing frame {frame_number} for detection.")
                    # Pass project_type to the detector
                    detections, command = self.detector.process_frame(frame, project_type)

                    # Arduino command is now only generated for 'live' projects inside detector
                    if command is not None:
                        self.arduino.send_command(command)

                    if self.is_recording and detections:
                        timestamp = 0
                        # For video files, the frame number is the ground truth
                        if is_file_source and self.active_frame_source:
                            props = self.active_frame_source.get_properties()
                            timestamp = frame_number / props['fps'] if props['fps'] > 0 else 0
                        else:
                            # For live video, it's based on time
                            timestamp = time.time() - self.recorder.start_time

                        self.recorder.write_detection_data(timestamp, frame_number, detections)
                else:
                    detections = []

                # Always draw the overlay with detections
                draw_overlay(frame, detections, self.detector)

            # Add progress bar for file sources
            if is_file_source and self.active_frame_source:
                props = self.active_frame_source.get_properties()
                total_frames = props.get('frame_count', 0)
                current_frame_num = self.active_frame_source.get_current_frame_number()
                if total_frames > 0:
                    progress = current_frame_num / total_frames
                    bar_width = int(progress * frame.shape[1])
                    bar_height = 20
                    # Draw background
                    cv2.rectangle(frame, (0, frame.shape[0] - bar_height), (frame.shape[1], frame.shape[0]), (50, 50, 50), -1)
                    # Draw foreground
                    cv2.rectangle(frame, (0, frame.shape[0] - bar_height), (bar_width, frame.shape[0]), (0, 255, 0), -1)

            # Optimize Video Display Speed
            if is_file_source:
                # Display every 2nd frame for smoother playback
                if frame_number % 2 == 0:
                    cv2.imshow('Live View', frame)
            else:
                # For live sources, show every frame
                cv2.imshow('Live View', frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                self._on_close()
                break
        cv2.destroyAllWindows()
        logging.info("Object detection loop finished and destroyed CV2 windows.")

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
        Button(type_window, text="Live Analysis", command=lambda: [type_var.set("live"), type_window.destroy()]).pack(fill="x", padx=20, pady=5)
        Button(type_window, text="Pre-recorded Analysis", command=lambda: [type_var.set("pre-recorded"), type_window.destroy()]).pack(fill="x", padx=20, pady=5)
        self.root.wait_window(type_window)
        project_type = type_var.get()

        if not project_type: return

        video_files = []
        if project_type == "pre-recorded":
            video_files = filedialog.askopenfilenames(title="Select Video Files", filetypes=[("Video files", "*.mp4 *.avi")])
            if not video_files: return

        success = self.project_manager.create_new_project(project_path, project_type, video_files)
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
        if self.is_recording:
            logging.info("Recording is active, stopping it before closing.")
            if self.project_manager.get_project_type() == 'live':
                self._stop_recording()
            else:
                self._handle_source_finished()

        # Para as threads de núcleo de forma limpa
        self.program_exit_event.set()
        logging.info("Waiting for core threads to join.")
        if self.capture_thread and self.capture_thread.is_alive(): self.capture_thread.join()
        if self.processing_thread and self.processing_thread.is_alive(): self.processing_thread.join()
        logging.info("Core threads joined.")
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

            try:
                # Instantiate the source but don't assign it to the active source yet
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

            # Pass the video properties to the recorder, indicating it's a pre-recorded file
            success = self.recorder.start_recording(output_path, video_props['width'], video_props['height'], is_video_file=True)

            if success:
                logging.info(f"Starting analysis for video: {video_path}")
                self.source_finished_event.clear() # Reset for the new analysis
                self.project_manager.update_video_status(video_path, "processing")
                with self.frame_queue.mutex: self.frame_queue.queue.clear()
                with self.video_queue.mutex: self.video_queue.queue.clear() # Keep this clear, just in case

                self.is_recording = True
                self.is_capturing_for_video = False # Do not save the video file again

                # The video recording thread is not needed for pre-recorded files
                # self.video_stop_event.clear()
                # self.video_thread = threading.Thread(target=self._video_recording_loop, daemon=True)
                # self.video_thread.start()

                self.process_video_btn.config(state="disabled")
                self.status_var.set(f"Processing: {os.path.basename(video_path)}")

                # NOW, activate the frame source. The capture loop will start picking it up.
                self.active_frame_source = video_source
            else:
                logging.error(f"Failed to start recorder for video processing: {video_path}")
                messagebox.showerror("Error", "Failed to start recorder for video processing.")
                # Ensure the unopened source is released
                video_source.release()
                self.active_frame_source = None

        Button(selection_window, text="Confirm", command=on_confirm).pack(pady=10)

    def _handle_source_finished(self):
        """Called from the capture thread when a video file ends."""
        if not self.is_recording:
            logging.warning("Source finished but was not in a recording state.")
            return

        logging.info(f"Source finished: {os.path.basename(self.currently_processing_video)}. Cleaning up.")
        self.is_recording = False
        self.is_capturing_for_video = False
        self.video_stop_event.set()
        if hasattr(self, 'video_thread') and self.video_thread.is_alive():
            logging.info("Waiting for video thread to join.")
            self.video_thread.join(timeout=5)
            logging.info("Video thread joined.")

        self.recorder.stop_recording()
        self.project_manager.update_video_status(self.currently_processing_video, "complete")

        # Signal to the detection thread that the source is done.
        # The detection thread will be responsible for closing the window.
        self.source_finished_event.set()

        self.currently_processing_video = None
        self.process_video_btn.config(state="normal")

        # Update status bar to indicate completion and readiness for the next video
        next_video = self.project_manager.get_next_video()
        if next_video:
            status_msg = f"Ready to process: {os.path.basename(next_video)}"
            self.status_var.set(f"Project: {self.project_manager.get_project_name()} - {status_msg}")
            logging.info(f"Analysis complete. {status_msg}")
        else:
            status_msg = "All videos processed."
            self.status_var.set(f"Project: {self.project_manager.get_project_name()} - {status_msg}")
            logging.info(f"Analysis complete. {status_msg}")


    def _on_close(self):
        logging.info("Close button clicked.")
        if messagebox.askokcancel("Quit", "Do you want to exit the program?"):
            logging.info("User confirmed quit.")
            if self.is_recording:
                logging.info("Recording is active, stopping it before closing.")
                if self.project_manager.get_project_type() == 'live':
                    self._stop_recording()
                else:
                    self._handle_source_finished()

            self.program_exit_event.set()
            logging.info("Waiting for core threads to join.")
            if hasattr(self, 'capture_thread') and self.capture_thread.is_alive(): self.capture_thread.join()
            if hasattr(self, 'processing_thread') and self.processing_thread.is_alive(): self.processing_thread.join()
            logging.info("Core threads joined.")

            if self.camera: self.camera.release()
            if self.active_frame_source and not isinstance(self.active_frame_source, Camera):
                self.active_frame_source.release()
            self.arduino.close()
            self.root.destroy()
            logging.info("Application shutdown complete.")

if __name__ == '__main__':
    print("This file is intended to be imported, not run directly.")
    print("Run main.py to start the application.")
