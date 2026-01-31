"""Coordenador para gerenciamento de threads de background.

Este coordenador foi extraído do MainViewModel como parte da Fase 1 do
plano de refatoração (PLANO_REFATORACAO_MAINVIEWMODEL.md).
Responsável por gerenciar o ciclo de vida de threads de background.
"""

import threading
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.io.camera import Camera

log = structlog.get_logger()


class ThreadCoordinator:
    """Coordenador para gerenciar threads de background.

    Centraliza o gerenciamento de ciclo de vida de threads,
    incluindo join, cleanup e liberação de recursos.

    Attributes:
        program_exit_event: Evento para sinalizar saída do programa
        processing_thread: Thread de processamento de vídeo
        capture_thread: Thread de captura de frames (opcional)
        camera: Instância da câmera (opcional)
    """

    def __init__(self) -> None:
        """Inicializa o coordenador de threads."""
        self.program_exit_event = threading.Event()
        self.processing_thread: threading.Thread | None = None
        self.capture_thread: threading.Thread | None = None
        self.camera: Camera | None = None
        self.log = structlog.get_logger()

    def register_processing_thread(self, thread: threading.Thread) -> None:
        """Registra thread de processamento.

        Args:
            thread: Thread de processamento a registrar
        """
        self.processing_thread = thread
        self.log.debug("thread_coordinator.processing_thread_registered")

    def register_capture_thread(self, thread: threading.Thread) -> None:
        """Registra thread de captura.

        Args:
            thread: Thread de captura a registrar
        """
        self.capture_thread = thread
        self.log.debug("thread_coordinator.capture_thread_registered")

    def register_camera(self, camera: "Camera") -> None:
        """Registra instância da câmera.

        Args:
            camera: Instância da câmera a registrar
        """
        self.camera = camera
        self.log.debug("thread_coordinator.camera_registered")

    def signal_exit(self) -> None:
        """Sinaliza todas as threads para parar."""
        self.log.info("thread_coordinator.signal_exit")
        self.program_exit_event.set()

    def join_threads(self) -> None:
        """Sinaliza todas as threads para parar e aguarda finalização.

        Realiza:
        - Define evento de saída
        - Aguarda conclusão de threads com timeout
        - Libera recursos de câmera
        - Previne deadlocks com timeout de 2 segundos por thread

        Note:
            Se threads não terminarem dentro do timeout, logs de warning são emitidos
            e o programa continua o shutdown (evita travamento indefinido).
        """
        self.log.info("thread_coordinator.shutdown.start")
        self.program_exit_event.set()

        # Join background threads (processamento de vídeo) com timeout
        if self.processing_thread is not None and self.processing_thread.is_alive():
            self.log.info("thread_coordinator.join_processing_thread")
            self.processing_thread.join(timeout=2.0)
            if self.processing_thread.is_alive():
                self.log.warning(
                    "thread_coordinator.processing_thread.timeout",
                    message="Processing thread did not exit within 2 seconds",
                )
            self.processing_thread = None

        if self.capture_thread is not None and self.capture_thread.is_alive():
            self.log.info("thread_coordinator.join_capture_thread")
            self.capture_thread.join(timeout=2.0)
            if self.capture_thread.is_alive():
                self.log.warning(
                    "thread_coordinator.capture_thread.timeout",
                    message="Capture thread did not exit within 2 seconds",
                )
            self.capture_thread = None

        # Libera recursos da câmera
        self._release_camera()

        self.log.info("thread_coordinator.shutdown.complete")

    def _release_camera(self) -> None:
        """Libera recursos da câmera."""
        if self.camera:
            self.log.info("thread_coordinator.release_camera")
            try:
                self.camera.release()
            except Exception as e:
                self.log.warning(
                    "thread_coordinator.camera_release_error",
                    error=str(e),
                )
            finally:
                self.camera = None

    def cleanup(self) -> None:
        """Limpa todos os recursos e threads.

        Método de conveniência que chama join_threads().
        """
        self.join_threads()

    def is_processing_active(self) -> bool:
        """Verifica se thread de processamento está ativa.

        Returns:
            True se thread de processamento está viva, False caso contrário
        """
        return self.processing_thread is not None and self.processing_thread.is_alive()

    def is_capture_active(self) -> bool:
        """Verifica se thread de captura está ativa.

        Returns:
            True se thread de captura está viva, False caso contrário
        """
        return self.capture_thread is not None and self.capture_thread.is_alive()

    def get_active_thread_count(self) -> int:
        """Retorna número de threads ativas.

        Returns:
            Número de threads ativas (processamento + captura)
        """
        count = 0
        if self.is_processing_active():
            count += 1
        if self.is_capture_active():
            count += 1
        return count
