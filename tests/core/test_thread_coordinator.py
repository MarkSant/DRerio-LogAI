"""Testes para ThreadCoordinator.

Testes unitários para o coordenador de threads,
extraído do MainViewModel na Fase 1 da refatoração.
"""

import threading
import time
from unittest.mock import MagicMock

import pytest

from tests.utils.wait_helpers import wait_for_thread_exit
from zebtrack.core.thread_coordinator import ThreadCoordinator


@pytest.fixture
def thread_coordinator():
    """Cria instância de ThreadCoordinator para testes."""
    return ThreadCoordinator()


@pytest.fixture
def mock_camera():
    """Cria câmera mockada."""
    camera = MagicMock()
    camera.release = MagicMock()
    return camera


class TestThreadCoordinatorInitialization:
    """Testes de inicialização do coordenador."""

    def test_init(self, thread_coordinator):
        """Testa inicialização."""
        assert thread_coordinator.program_exit_event is not None
        assert thread_coordinator.processing_thread is None
        assert thread_coordinator.capture_thread is None
        assert thread_coordinator.camera is None
        assert thread_coordinator.log is not None


class TestRegisterThreads:
    """Testes de registro de threads."""

    def test_register_processing_thread(self, thread_coordinator):
        """Testa registro de thread de processamento."""
        thread = threading.Thread(target=lambda: time.sleep(0.1))  # intentional test worker delay

        thread_coordinator.register_processing_thread(thread)

        assert thread_coordinator.processing_thread is thread

    def test_register_capture_thread(self, thread_coordinator):
        """Testa registro de thread de captura."""
        thread = threading.Thread(target=lambda: time.sleep(0.1))  # intentional test worker delay

        thread_coordinator.register_capture_thread(thread)

        assert thread_coordinator.capture_thread is thread

    def test_register_camera(self, thread_coordinator, mock_camera):
        """Testa registro de câmera."""
        thread_coordinator.register_camera(mock_camera)

        assert thread_coordinator.camera is mock_camera


class TestSignalExit:
    """Testes de sinalização de saída."""

    def test_signal_exit(self, thread_coordinator):
        """Testa sinalização de saída."""
        assert not thread_coordinator.program_exit_event.is_set()

        thread_coordinator.signal_exit()

        assert thread_coordinator.program_exit_event.is_set()


class TestJoinThreads:
    """Testes de join de threads."""

    def test_join_threads_no_threads(self, thread_coordinator):
        """Testa join quando não há threads."""
        thread_coordinator.join_threads()

        assert thread_coordinator.program_exit_event.is_set()

    def test_join_threads_with_processing_thread(self, thread_coordinator):
        """Testa join com thread de processamento."""
        def worker():
            while not thread_coordinator.program_exit_event.is_set():
                time.sleep(0.01)  # intentional interleaving delay

        thread = threading.Thread(target=worker)
        thread.start()
        thread_coordinator.register_processing_thread(thread)

        thread_coordinator.join_threads()

        assert thread_coordinator.processing_thread is None
        assert thread_coordinator.program_exit_event.is_set()

    def test_join_threads_with_camera(self, thread_coordinator, mock_camera):
        """Testa join com câmera."""
        thread_coordinator.register_camera(mock_camera)

        thread_coordinator.join_threads()

        mock_camera.release.assert_called_once()
        assert thread_coordinator.camera is None


class TestReleaseCamera:
    """Testes de liberação de câmera."""

    def test_release_camera_success(self, thread_coordinator, mock_camera):
        """Testa liberação bem-sucedida de câmera."""
        thread_coordinator.register_camera(mock_camera)

        thread_coordinator._release_camera()

        mock_camera.release.assert_called_once()
        assert thread_coordinator.camera is None

    def test_release_camera_error(self, thread_coordinator):
        """Testa tratamento de erro ao liberar câmera."""
        camera = MagicMock()
        camera.release.side_effect = Exception("Test error")
        thread_coordinator.register_camera(camera)

        # Não deve lançar exceção
        thread_coordinator._release_camera()

        assert thread_coordinator.camera is None


class TestCleanup:
    """Testes de cleanup."""

    def test_cleanup(self, thread_coordinator):
        """Testa cleanup."""
        thread_coordinator.cleanup()

        assert thread_coordinator.program_exit_event.is_set()


class TestThreadStatus:
    """Testes de status de threads."""

    def test_is_processing_active_false(self, thread_coordinator):
        """Testa status de processamento quando inativo."""
        assert thread_coordinator.is_processing_active() is False

    def test_is_processing_active_true(self, thread_coordinator):
        """Testa status de processamento quando ativo."""
        thread = threading.Thread(target=lambda: time.sleep(0.2))  # intentional test worker delay
        thread.start()
        thread_coordinator.register_processing_thread(thread)

        assert thread_coordinator.is_processing_active() is True

        wait_for_thread_exit(thread, timeout=1.0)

    def test_is_capture_active_false(self, thread_coordinator):
        """Testa status de captura quando inativo."""
        assert thread_coordinator.is_capture_active() is False

    def test_get_active_thread_count_zero(self, thread_coordinator):
        """Testa contagem quando nenhuma thread ativa."""
        assert thread_coordinator.get_active_thread_count() == 0

    def test_get_active_thread_count_one(self, thread_coordinator):
        """Testa contagem com uma thread ativa."""
        thread = threading.Thread(target=lambda: time.sleep(0.2))  # intentional test worker delay
        thread.start()
        thread_coordinator.register_processing_thread(thread)

        assert thread_coordinator.get_active_thread_count() == 1

        wait_for_thread_exit(thread, timeout=1.0)
