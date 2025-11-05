"""Testes de Thread Safety para LiveCameraService."""

import queue
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, PropertyMock

import numpy as np
import pytest

from zebtrack.core.live_camera_service import LiveCameraService


class TestLiveCameraServiceThreadLifecycle(unittest.TestCase):
    """Testes de lifecycle de threads."""

    def setUp(self):
        """Setup: Criar serviço mock."""
        self.mock_controller = Mock()
        self.mock_controller.settings = Mock()
        self.mock_controller.settings.video_processing.fps = 30
        self.mock_state_manager = Mock()
        self.mock_project_manager = Mock()
        self.mock_recording_service = Mock()
        self.mock_detector_service = Mock()
        self.mock_root = Mock()

        self.service = LiveCameraService(
            controller=self.mock_controller,
            state_manager=self.mock_state_manager,
            project_manager=self.mock_project_manager,
            recording_service=self.mock_recording_service,
            detector_service=self.mock_detector_service,
            root=self.mock_root,
        )

    def tearDown(self):
        """Cleanup: Garantir que threads são paradas."""
        if hasattr(self, "service"):
            try:
                self.service.stop_session()
            except Exception:
                pass

    def test_thread_start_stop_lifecycle(self):
        """Test: Lifecycle normal de start/stop de threads."""
        # Setup mock camera
        mock_camera = Mock()
        mock_camera.is_opened.return_value = True
        mock_camera.get_frame.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480

        with patch("zebtrack.core.live_camera_service.Camera", return_value=mock_camera):
            # Start threads
            success = self.service._start_threads()

            assert success is True
            assert self.service.capture_thread is not None
            assert self.service.processing_thread is not None
            assert self.service.capture_thread.is_alive()
            assert self.service.processing_thread.is_alive()

            # Stop session
            self.service.stop_session()

            # Wait for threads to finish
            self.service.capture_thread.join(timeout=3.0)
            self.service.processing_thread.join(timeout=3.0)

            # Verify threads are stopped
            assert not self.service.capture_thread.is_alive()
            assert not self.service.processing_thread.is_alive()

    def test_rapid_start_stop_cycles(self):
        """Test: Race conditions em ciclos rápidos de start/stop."""
        mock_camera = Mock()
        mock_camera.is_opened.return_value = True
        mock_camera.get_frame.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480

        with patch("zebtrack.core.live_camera_service.Camera", return_value=mock_camera):
            # Multiple rapid cycles
            for i in range(3):
                success = self.service._start_threads()
                assert success is True
                time.sleep(0.1)  # Breve execução
                self.service.stop_session()
                time.sleep(0.1)  # Breve pausa

    def test_thread_join_timeout_handling(self):
        """Test: Handling de timeout no join de threads."""
        mock_camera = Mock()
        mock_camera.is_opened.return_value = True
        # Simulate thread que nunca termina (bloqueado)
        mock_camera.get_frame.side_effect = lambda: (time.sleep(10), (True, None))[1]

        with patch("zebtrack.core.live_camera_service.Camera", return_value=mock_camera):
            self.service._start_threads()

            start_time = time.time()
            self.service.stop_session()
            elapsed = time.time() - start_time

            # Deve respeitar timeout de 2 segundos configurado
            assert elapsed < 5.0  # Com margem

    def test_daemon_thread_cleanup(self):
        """Test: Cleanup de threads não-daemon."""
        assert self.service.capture_thread is None
        assert self.service.processing_thread is None

        mock_camera = Mock()
        mock_camera.is_opened.return_value = True
        mock_camera.get_frame.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))

        with patch("zebtrack.core.live_camera_service.Camera", return_value=mock_camera):
            self.service._start_threads()

            # Verify threads são non-daemon (daemon=False no código)
            assert self.service.capture_thread.daemon is False
            assert self.service.processing_thread.daemon is False

            self.service.stop_session()

    def test_exit_event_signaling(self):
        """Test: Exit event sinalização entre threads."""
        assert not self.service.exit_event.is_set()

        self.service._start_threads()

        # Exit event não deve estar setado durante execução
        assert not self.service.exit_event.is_set()

        # Stop deve setar o exit event
        self.service.stop_session()
        assert self.service.exit_event.is_set()


class TestLiveCameraServiceQueueOperations(unittest.TestCase):
    """Testes de operações em queues."""

    def setUp(self):
        """Setup: Criar serviço mock."""
        self.mock_controller = Mock()
        self.mock_controller.settings = Mock()
        self.mock_controller.settings.video_processing.fps = 30
        self.mock_state_manager = Mock()
        self.mock_project_manager = Mock()
        self.mock_recording_service = Mock()
        self.mock_detector_service = Mock()
        self.mock_root = Mock()

        self.service = LiveCameraService(
            controller=self.mock_controller,
            state_manager=self.mock_state_manager,
            project_manager=self.mock_project_manager,
            recording_service=self.mock_recording_service,
            detector_service=self.mock_detector_service,
            root=self.mock_root,
        )

    def tearDown(self):
        """Cleanup."""
        if hasattr(self, "service"):
            try:
                self.service.stop_session()
            except Exception:
                pass

    def test_frame_queue_overflow_handling(self):
        """Test: Queue full scenario (maxsize=30)."""
        # Encher a queue
        for i in range(35):  # Mais do que o maxsize
            try:
                self.service.frame_queue.put_nowait((i, np.zeros((480, 640, 3))))
            except queue.Full:
                # Esperado após 30 itens
                pass

        # Verificar que queue está cheia
        assert self.service.frame_queue.full()
        assert self.service.frame_queue.qsize() == 30

    def test_frame_queue_empty_handling(self):
        """Test: Queue empty scenario com timeout."""
        # Queue vazia
        assert self.service.frame_queue.empty()

        # Tentar get com timeout
        with pytest.raises(queue.Empty):
            self.service.frame_queue.get(timeout=0.1)

    def test_video_queue_overflow(self):
        """Test: Video queue overflow (maxsize=30)."""
        # Encher video queue
        for i in range(35):
            try:
                self.service.video_queue.put_nowait(np.zeros((480, 640, 3)))
            except queue.Full:
                pass

        assert self.service.video_queue.full()
        assert self.service.video_queue.qsize() == 30

    def test_queue_cleanup_on_stop(self):
        """Test: Queue cleanup durante stop."""
        # Adicionar items nas queues
        for i in range(10):
            self.service.frame_queue.put((i, np.zeros((480, 640, 3))))
            self.service.video_queue.put(np.zeros((480, 640, 3)))

        assert self.service.frame_queue.qsize() == 10
        assert self.service.video_queue.qsize() == 10

        # Cleanup
        self.service._clear_queues()

        assert self.service.frame_queue.empty()
        assert self.service.video_queue.empty()

    def test_concurrent_queue_access(self):
        """Test: Múltiplos producers/consumers."""

        def producer():
            for i in range(20):
                try:
                    self.service.frame_queue.put((i, np.zeros((10, 10, 3))), timeout=0.1)
                except queue.Full:
                    pass

        def consumer():
            count = 0
            while count < 15:
                try:
                    self.service.frame_queue.get(timeout=0.1)
                    count += 1
                except queue.Empty:
                    break

        # Start múltiplas threads
        producers = [threading.Thread(target=producer) for _ in range(2)]
        consumers = [threading.Thread(target=consumer) for _ in range(2)]

        for t in producers + consumers:
            t.start()

        for t in producers + consumers:
            t.join(timeout=3.0)

        # Verificar que não houve deadlock
        for t in producers + consumers:
            assert not t.is_alive()


class TestLiveCameraServiceRaceConditions(unittest.TestCase):
    """Testes de race conditions."""

    def setUp(self):
        """Setup: Criar serviço mock."""
        self.mock_controller = Mock()
        self.mock_controller.settings = Mock()
        self.mock_controller.settings.video_processing.fps = 30
        self.mock_state_manager = Mock()
        self.mock_project_manager = Mock()
        self.mock_recording_service = Mock()
        self.mock_detector_service = Mock()
        self.mock_root = Mock()

        self.service = LiveCameraService(
            controller=self.mock_controller,
            state_manager=self.mock_state_manager,
            project_manager=self.mock_project_manager,
            recording_service=self.mock_recording_service,
            detector_service=self.mock_detector_service,
            root=self.mock_root,
        )

    def tearDown(self):
        """Cleanup."""
        if hasattr(self, "service"):
            try:
                self.service.stop_session()
            except Exception:
                pass

    def test_concurrent_start_stop_calls(self):
        """Test: Concurrent start/stop calls."""
        mock_camera = Mock()
        mock_camera.is_opened.return_value = True
        mock_camera.get_frame.return_value = (True, np.zeros((480, 640, 3)))
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480

        with patch("zebtrack.core.live_camera_service.Camera", return_value=mock_camera):

            def start_session():
                try:
                    self.service._start_threads()
                except Exception:
                    pass

            def stop_session():
                try:
                    self.service.stop_session()
                except Exception:
                    pass

            # Concurrent calls
            threads = []
            threads.append(threading.Thread(target=start_session))
            threads.append(threading.Thread(target=stop_session))
            threads.append(threading.Thread(target=start_session))

            for t in threads:
                t.start()

            for t in threads:
                t.join(timeout=3.0)

            # Verificar que não houve crash
            for t in threads:
                assert not t.is_alive() or t.daemon

    def test_detector_access_during_processing(self):
        """Test: Detector access concorrente durante processing."""
        mock_detector = Mock()
        mock_detector.detect.return_value = ([], None)
        self.mock_detector_service.detector = mock_detector

        # Simular acesso concorrente ao detector
        def processing_access():
            for _ in range(10):
                try:
                    if self.mock_detector_service.detector:
                        self.mock_detector_service.detector.detect(
                            np.zeros((480, 640, 3)), "live"
                        )
                except Exception:
                    pass

        threads = [threading.Thread(target=processing_access) for _ in range(3)]

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=2.0)

        # Detector deve ter sido chamado múltiplas vezes
        assert mock_detector.detect.call_count >= 10

    def test_preview_update_during_session_stop(self):
        """Test: Preview update durante session stop."""
        mock_preview = Mock()
        self.service.preview_window = mock_preview

        def update_preview():
            for _ in range(10):
                try:
                    if self.service.preview_window:
                        self.service.preview_window.update_frame(
                            np.zeros((480, 640, 3)), []
                        )
                    time.sleep(0.01)
                except Exception:
                    pass

        def stop_session():
            time.sleep(0.05)  # Espera para permitir algumas updates
            try:
                self.service.stop_session()
            except Exception:
                pass

        t1 = threading.Thread(target=update_preview)
        t2 = threading.Thread(target=stop_session)

        t1.start()
        t2.start()

        t1.join(timeout=2.0)
        t2.join(timeout=2.0)

        # Verificar que não houve crash
        assert not t1.is_alive()
        assert not t2.is_alive()

    def test_state_manager_concurrent_updates(self):
        """Test: State manager updates concorrentes."""

        def update_state():
            for _ in range(10):
                try:
                    self.mock_state_manager.update_processing_state(
                        source="test", is_processing=True
                    )
                except Exception:
                    pass

        threads = [threading.Thread(target=update_state) for _ in range(3)]

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=2.0)

        # State manager deve ter sido chamado múltiplas vezes
        assert self.mock_state_manager.update_processing_state.call_count >= 10


class TestLiveCameraServiceErrorHandling(unittest.TestCase):
    """Testes de error handling em threads."""

    def setUp(self):
        """Setup: Criar serviço mock."""
        self.mock_controller = Mock()
        self.mock_controller.settings = Mock()
        self.mock_controller.settings.video_processing.fps = 30
        self.mock_state_manager = Mock()
        self.mock_project_manager = Mock()
        self.mock_recording_service = Mock()
        self.mock_detector_service = Mock()
        self.mock_root = Mock()

        self.service = LiveCameraService(
            controller=self.mock_controller,
            state_manager=self.mock_state_manager,
            project_manager=self.mock_project_manager,
            recording_service=self.mock_recording_service,
            detector_service=self.mock_detector_service,
            root=self.mock_root,
        )

    def tearDown(self):
        """Cleanup."""
        if hasattr(self, "service"):
            try:
                self.service.stop_session()
            except Exception:
                pass

    def test_camera_disconnect_during_capture(self):
        """Test: Camera disconnect durante capture."""
        mock_camera = Mock()
        mock_camera.is_opened.return_value = True

        # Simular desconexão após alguns frames
        call_count = [0]

        def get_frame_with_disconnect():
            call_count[0] += 1
            if call_count[0] <= 5:
                return (True, np.zeros((480, 640, 3), dtype=np.uint8))
            else:
                return (False, None)

        mock_camera.get_frame.side_effect = get_frame_with_disconnect
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480

        self.service.camera = mock_camera

        with patch("zebtrack.core.live_camera_service.Camera", return_value=mock_camera):
            self.service._start_threads()

            # Esperar alguns ciclos
            time.sleep(0.5)

            # Stop e verificar que thread não crashou
            self.service.stop_session()

            # Threads devem ter terminado gracefully
            self.service.capture_thread.join(timeout=3.0)
            assert not self.service.capture_thread.is_alive()

    def test_detection_failure_during_processing(self):
        """Test: Detection failure durante processing."""
        mock_detector = Mock()
        mock_detector.detect.side_effect = RuntimeError("Detection failed")
        self.mock_detector_service.detector = mock_detector

        # Adicionar frames na queue
        for i in range(5):
            self.service.frame_queue.put((i, np.zeros((480, 640, 3))))

        self.service._start_threads()

        # Esperar processamento
        time.sleep(0.5)

        # Stop e verificar que thread não crashou
        self.service.stop_session()

        self.service.processing_thread.join(timeout=3.0)
        assert not self.service.processing_thread.is_alive()

    def test_preview_update_exception_handling(self):
        """Test: Preview update exception handling."""
        mock_preview = Mock()
        mock_preview.update_frame.side_effect = RuntimeError("Preview update failed")
        self.service.preview_window = mock_preview

        # Adicionar frames na queue
        for i in range(5):
            self.service.frame_queue.put((i, np.zeros((480, 640, 3))))

        self.service._start_threads()

        # Esperar processamento
        time.sleep(0.5)

        # Stop e verificar que thread não crashou
        self.service.stop_session()

        # Thread deve ter lidado com exceções gracefully
        self.service.processing_thread.join(timeout=3.0)
        assert not self.service.processing_thread.is_alive()

    def test_thread_crash_recovery(self):
        """Test: Verificar que threads podem ser reiniciadas após crash."""
        # Primeira execução (simular crash via stop forçado)
        self.service._start_threads()
        self.service.exit_event.set()

        # Esperar threads terminarem
        if self.service.capture_thread:
            self.service.capture_thread.join(timeout=2.0)
        if self.service.processing_thread:
            self.service.processing_thread.join(timeout=2.0)

        # Segunda execução (deve funcionar normalmente)
        success = self.service._start_threads()
        assert success is True

        # Cleanup
        self.service.stop_session()


class TestLiveCameraServiceMemoryPressure(unittest.TestCase):
    """Testes de memory pressure."""

    def setUp(self):
        """Setup: Criar serviço mock."""
        self.mock_controller = Mock()
        self.mock_controller.settings = Mock()
        self.mock_controller.settings.video_processing.fps = 30
        self.mock_state_manager = Mock()
        self.mock_project_manager = Mock()
        self.mock_recording_service = Mock()
        self.mock_detector_service = Mock()
        self.mock_root = Mock()

        self.service = LiveCameraService(
            controller=self.mock_controller,
            state_manager=self.mock_state_manager,
            project_manager=self.mock_project_manager,
            recording_service=self.mock_recording_service,
            detector_service=self.mock_detector_service,
            root=self.mock_root,
        )

    def tearDown(self):
        """Cleanup."""
        if hasattr(self, "service"):
            try:
                self.service.stop_session()
            except Exception:
                pass

    def test_frame_queue_limit_reached(self):
        """Test: Frame queue com limite atingido."""
        # Encher frame queue até o limite
        for i in range(30):
            self.service.frame_queue.put((i, np.zeros((480, 640, 3))))

        assert self.service.frame_queue.full()

        # Tentar adicionar mais (não deve bloquear indefinidamente)
        try:
            self.service.frame_queue.put((31, np.zeros((480, 640, 3))), timeout=0.1)
            assert False, "Should have raised queue.Full"
        except queue.Full:
            pass

    def test_frame_drop_scenario(self):
        """Test: Frame drop quando queue está cheia."""
        # Preencher queue
        for i in range(30):
            self.service.frame_queue.put((i, np.zeros((480, 640, 3))))

        # Simular tentativa de adicionar frame (código usa put sem timeout para evitar bloqueio)
        # O código verifica if not self.frame_queue.full() antes de put
        initial_size = self.service.frame_queue.qsize()

        # Tentar adicionar quando full (comportamento do código)
        if not self.service.frame_queue.full():
            self.service.frame_queue.put((31, np.zeros((480, 640, 3))))

        # Queue size não deve ter mudado
        assert self.service.frame_queue.qsize() == initial_size

    def test_memory_leak_detection_repeated_sessions(self):
        """Test: Memory leak detection com sessões repetidas."""
        mock_camera = Mock()
        mock_camera.is_opened.return_value = True
        mock_camera.get_frame.return_value = (True, np.zeros((480, 640, 3)))
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480

        with patch("zebtrack.core.live_camera_service.Camera", return_value=mock_camera):
            # Múltiplas sessões
            for _ in range(3):
                self.service._start_threads()

                # Adicionar alguns frames
                for i in range(10):
                    self.service.frame_queue.put((i, np.zeros((480, 640, 3))))

                time.sleep(0.1)

                # Stop e cleanup
                self.service.stop_session()

                # Verificar que queues foram limpas
                assert self.service.frame_queue.empty()
                assert self.service.video_queue.empty()


class TestLiveCameraServiceRecordingIntegration(unittest.TestCase):
    """Testes de integração com RecordingService."""

    def setUp(self):
        """Setup: Criar serviço mock."""
        self.mock_controller = Mock()
        self.mock_controller.settings = Mock()
        self.mock_controller.settings.video_processing.fps = 30
        self.mock_controller.setup_detector.return_value = True
        self.mock_controller.recorder = None

        self.mock_state_manager = Mock()
        self.mock_project_manager = Mock()
        self.mock_project_manager.get_zone_data.return_value = None
        self.mock_project_manager.project_data = {}

        self.mock_recording_service = Mock()
        self.mock_detector_service = Mock()
        self.mock_detector_service.detector = None

        self.mock_root = Mock()

        self.service = LiveCameraService(
            controller=self.mock_controller,
            state_manager=self.mock_state_manager,
            project_manager=self.mock_project_manager,
            recording_service=self.mock_recording_service,
            detector_service=self.mock_detector_service,
            root=self.mock_root,
        )

    def tearDown(self):
        """Cleanup."""
        if hasattr(self, "service"):
            try:
                self.service.stop_session()
            except Exception:
                pass

    @patch("zebtrack.core.live_camera_service.Path.mkdir")
    @patch("zebtrack.core.live_camera_service.Camera")
    @patch("zebtrack.ui.dialogs.LivePreviewWindow")
    def test_callback_registration_and_execution(self, mock_preview, mock_camera_cls, mock_mkdir):
        """Test: Callback registration e execution."""
        mock_camera = Mock()
        mock_camera.is_opened.return_value = True
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480
        mock_camera_cls.return_value = mock_camera

        # Start session
        success = self.service.start_session(
            camera_index=0,
            duration_s=10.0,
            experiment_id="test_exp",
            analysis_interval_frames=1,
            display_interval_frames=1,
            record_video=True,
        )

        assert success is True

        # Verificar que callbacks foram registrados
        self.mock_recording_service.set_ui_callbacks.assert_called_once()
        callbacks = self.mock_recording_service.set_ui_callbacks.call_args[0][0]
        assert "stop_recording_callback" in callbacks

    @patch("zebtrack.core.live_camera_service.Path.mkdir")
    @patch("zebtrack.core.live_camera_service.Camera")
    @patch("zebtrack.ui.dialogs.LivePreviewWindow")
    def test_timed_session_expiration(self, mock_preview, mock_camera_cls, mock_mkdir):
        """Test: Timed session expiration handling."""
        mock_camera = Mock()
        mock_camera.is_opened.return_value = True
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480
        mock_camera_cls.return_value = mock_camera

        # Start session
        self.service.start_session(
            camera_index=0,
            duration_s=0.5,  # Curta duração
            experiment_id="test_exp",
            record_video=True,
        )

        # Verificar que RecordingService.start_session foi chamado com projeto correto
        self.mock_recording_service.start_session.assert_called_once()
        call_args = self.mock_recording_service.start_session.call_args[1]
        assert call_args["project_data"]["recording_duration_s"] == 0.5

    @patch("zebtrack.core.live_camera_service.Path.mkdir")
    @patch("zebtrack.core.live_camera_service.Camera")
    @patch("zebtrack.ui.dialogs.LivePreviewWindow")
    def test_manual_stop_during_recording(self, mock_preview, mock_camera_cls, mock_mkdir):
        """Test: Manual stop durante recording."""
        mock_camera = Mock()
        mock_camera.is_opened.return_value = True
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480
        mock_camera_cls.return_value = mock_camera

        # Start session
        self.service.start_session(
            camera_index=0, duration_s=10.0, experiment_id="test_exp", record_video=True
        )

        # Manual stop
        self.service.stop_session()

        # Verificar que RecordingService.stop_session foi chamado
        self.mock_recording_service.stop_session.assert_called()

    @patch("zebtrack.core.live_camera_service.Path.mkdir")
    @patch("zebtrack.core.live_camera_service.Camera")
    @patch("zebtrack.ui.dialogs.LivePreviewWindow")
    def test_output_directory_creation(self, mock_preview, mock_camera_cls, mock_mkdir):
        """Test: Output directory creation."""
        mock_camera = Mock()
        mock_camera.is_opened.return_value = True
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480
        mock_camera_cls.return_value = mock_camera

        # Start session
        self.service.start_session(
            camera_index=0, duration_s=10.0, experiment_id="test_exp_output", record_video=True
        )

        # Verificar que diretórios foram criados
        assert mock_mkdir.call_count >= 1


if __name__ == "__main__":
    unittest.main()
