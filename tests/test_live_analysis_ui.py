"""Testes para LiveAnalysisDialog e LivePreviewWindow."""

import time
import tkinter as tk
import unittest
from unittest.mock import Mock, MagicMock, patch

import numpy as np
import pytest

from zebtrack.ui.dialogs.live_analysis_dialog import LiveAnalysisDialog
from zebtrack.ui.dialogs.live_preview_window import LivePreviewWindow


@pytest.mark.gui
class TestLiveAnalysisDialog(unittest.TestCase):
    """Testes para LiveAnalysisDialog."""

    def setUp(self):
        """Setup: Criar root window."""
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        """Cleanup: Destruir root window."""
        try:
            self.root.destroy()
        except Exception:
            pass

    @patch("zebtrack.core.wizard_service.WizardService.detect_available_cameras")
    def test_init_default_values(self, mock_detect):
        """Test: Inicialização com valores default."""
        mock_detect.return_value = []

        # Create mock settings
        mock_settings = Mock()
        mock_settings.live_analysis.default_duration_s = 300.0
        mock_settings.live_analysis.max_duration_s = 7200.0

        dialog = LiveAnalysisDialog(self.root, settings_obj=mock_settings)

        # Verificar valores default
        assert dialog.duration_var.get() == 300.0
        assert dialog.analysis_interval_var.get() == 10
        assert dialog.display_interval_var.get() == 10
        assert dialog.record_video_var.get() is True
        assert dialog.experiment_id_var.get() == ""

        dialog.destroy()

    @patch("zebtrack.core.wizard_service.WizardService.detect_available_cameras")
    def test_camera_detection_success(self, mock_detect):
        """Test: Camera detection com sucesso."""
        # Mock camera detection
        mock_cameras = [
            {"index": 0, "name": "Camera 0", "resolution": "640x480"},
            {"index": 1, "name": "Camera 1", "resolution": "1920x1080"},
        ]
        mock_detect.return_value = mock_cameras

        mock_settings = Mock()
        mock_settings.live_analysis.default_duration_s = 300.0
        mock_settings.live_analysis.max_duration_s = 7200.0

        dialog = LiveAnalysisDialog(self.root, settings_obj=mock_settings)

        # Trigger manual detection
        dialog._detect_cameras()
        self.root.update()

        # Verificar que câmeras foram detectadas
        assert len(dialog.camera_index_map) == 2
        assert "[0] Camera 0 (640x480)" in dialog.camera_index_map
        assert "[1] Camera 1 (1920x1080)" in dialog.camera_index_map

        # Verificar auto-seleção da primeira câmera
        assert dialog.camera_selection_var.get() == "[0] Camera 0 (640x480)"

        dialog.destroy()

    @patch("zebtrack.core.wizard_service.WizardService.detect_available_cameras")
    def test_camera_detection_no_cameras(self, mock_detect):
        """Test: Camera detection sem câmeras."""
        mock_detect.return_value = []

        mock_settings = Mock()
        mock_settings.live_analysis.default_duration_s = 300.0
        mock_settings.live_analysis.max_duration_s = 7200.0

        dialog = LiveAnalysisDialog(self.root, settings_obj=mock_settings)

        dialog._detect_cameras()
        self.root.update()

        # Verificar que nenhuma câmera foi detectada
        assert len(dialog.camera_index_map) == 0
        assert dialog.camera_selection_var.get() == ""

        dialog.destroy()

    @patch("zebtrack.core.wizard_service.WizardService.detect_available_cameras")
    def test_camera_detection_error_handling(self, mock_detect):
        """Test: Error handling durante camera detection."""
        mock_detect.side_effect = RuntimeError("Camera detection failed")

        mock_settings = Mock()
        mock_settings.live_analysis.default_duration_s = 300.0
        mock_settings.live_analysis.max_duration_s = 7200.0

        dialog = LiveAnalysisDialog(self.root, settings_obj=mock_settings)

        # Should not crash
        dialog._detect_cameras()
        self.root.update()

        # Verificar que status indica erro
        assert len(dialog.camera_index_map) == 0

        dialog.destroy()

    @patch("zebtrack.core.wizard_service.WizardService.detect_available_cameras")
    def test_duration_validation_positive(self, mock_detect):
        """Test: Duration validation com valor válido."""
        mock_detect.return_value = [{"index": 0, "name": "Camera 0", "resolution": "640x480"}]

        mock_settings = Mock()
        mock_settings.live_analysis.default_duration_s = 300.0
        mock_settings.live_analysis.max_duration_s = 7200.0

        dialog = LiveAnalysisDialog(self.root, settings_obj=mock_settings)
        dialog._detect_cameras()

        # Setar valores válidos
        dialog.duration_var.set(600)
        dialog.camera_selection_var.set("[0] Camera 0 (640x480)")

        # Validar
        result = dialog.validate()

        assert result is True

        dialog.destroy()

    @patch("zebtrack.core.wizard_service.WizardService.detect_available_cameras")
    def test_duration_validation_negative(self, mock_detect):
        """Test: Duration validation com valor negativo."""
        mock_detect.return_value = [{"index": 0, "name": "Camera 0", "resolution": "640x480"}]

        mock_settings = Mock()
        mock_settings.live_analysis.default_duration_s = 300.0
        mock_settings.live_analysis.max_duration_s = 7200.0

        dialog = LiveAnalysisDialog(self.root, settings_obj=mock_settings)
        dialog._detect_cameras()

        # Setar valores inválidos
        dialog.duration_var.set(-100)
        dialog.camera_selection_var.set("[0] Camera 0 (640x480)")

        # Validar (deve falhar)
        result = dialog.validate()

        assert result is False

        dialog.destroy()

    @patch("zebtrack.core.wizard_service.WizardService.detect_available_cameras")
    def test_duration_validation_exceeds_max(self, mock_detect):
        """Test: Duration validation excedendo máximo."""
        mock_detect.return_value = [{"index": 0, "name": "Camera 0", "resolution": "640x480"}]

        mock_settings = Mock()
        mock_settings.live_analysis.default_duration_s = 300.0
        mock_settings.live_analysis.max_duration_s = 7200.0

        dialog = LiveAnalysisDialog(self.root, settings_obj=mock_settings)
        dialog._detect_cameras()

        # Setar duração maior que o máximo
        dialog.duration_var.set(10000)
        dialog.camera_selection_var.set("[0] Camera 0 (640x480)")

        # Validar (deve ajustar para o máximo)
        result = dialog.validate()

        assert result is True
        assert dialog.duration_var.get() == 7200.0  # Ajustado para o máximo

        dialog.destroy()

    @patch("zebtrack.core.wizard_service.WizardService.detect_available_cameras")
    def test_validation_no_camera_selected(self, mock_detect):
        """Test: Validação falha sem câmera selecionada."""
        mock_detect.return_value = [{"index": 0, "name": "Camera 0", "resolution": "640x480"}]

        mock_settings = Mock()
        mock_settings.live_analysis.default_duration_s = 300.0
        mock_settings.live_analysis.max_duration_s = 7200.0

        dialog = LiveAnalysisDialog(self.root, settings_obj=mock_settings)

        # Não selecionar câmera
        dialog.duration_var.set(300)

        # Validar (deve falhar)
        result = dialog.validate()

        assert result is False

        dialog.destroy()

    @patch("zebtrack.core.wizard_service.WizardService.detect_available_cameras")
    def test_experiment_id_generation(self, mock_detect):
        """Test: Experiment ID generation quando não fornecido."""
        mock_detect.return_value = [{"index": 0, "name": "Camera 0", "resolution": "640x480"}]

        mock_settings = Mock()
        mock_settings.live_analysis.default_duration_s = 300.0
        mock_settings.live_analysis.max_duration_s = 7200.0

        dialog = LiveAnalysisDialog(self.root, settings_obj=mock_settings)
        dialog._detect_cameras()

        # Setar valores sem experiment ID
        dialog.duration_var.set(300)
        dialog.camera_selection_var.set("[0] Camera 0 (640x480)")
        dialog.experiment_id_var.set("")  # Vazio

        # Validar e aplicar
        if dialog.validate():
            dialog.apply()

        # Verificar que experiment ID foi gerado
        assert dialog.result is not None
        assert dialog.result["experiment_id"].startswith("camera_")

        dialog.destroy()

    @patch("zebtrack.core.wizard_service.WizardService.detect_available_cameras")
    def test_result_assembly(self, mock_detect):
        """Test: Result assembly com todos os campos."""
        mock_detect.return_value = [{"index": 0, "name": "Camera 0", "resolution": "640x480"}]

        mock_settings = Mock()
        mock_settings.live_analysis.default_duration_s = 300.0
        mock_settings.live_analysis.max_duration_s = 7200.0

        dialog = LiveAnalysisDialog(self.root, settings_obj=mock_settings)
        dialog._detect_cameras()

        # Setar todos os valores
        dialog.duration_var.set(600)
        dialog.analysis_interval_var.set(5)
        dialog.display_interval_var.set(10)
        dialog.record_video_var.set(False)
        dialog.experiment_id_var.set("test_exp_123")
        dialog.camera_selection_var.set("[0] Camera 0 (640x480)")

        # Validar e aplicar
        if dialog.validate():
            dialog.apply()

        # Verificar resultado
        assert dialog.result is not None
        assert dialog.result["camera_index"] == 0
        assert dialog.result["duration_s"] == 600.0
        assert dialog.result["analysis_interval_frames"] == 5
        assert dialog.result["display_interval_frames"] == 10
        assert dialog.result["record_video"] is False
        assert dialog.result["experiment_id"] == "test_exp_123"

        dialog.destroy()


@pytest.mark.gui
class TestLivePreviewWindow(unittest.TestCase):
    """Testes para LivePreviewWindow."""

    def setUp(self):
        """Setup: Criar root window."""
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        """Cleanup: Destruir root window."""
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_window_creation(self):
        """Test: Window creation e layout."""
        preview = LivePreviewWindow(
            parent=self.root,
            camera_index=0,
            duration_s=60.0,
            on_stop_callback=None,
        )

        # Verificar que window foi criada
        assert preview.window is not None
        assert preview.camera_index == 0
        assert preview.duration_s == 60.0
        assert preview.is_stopped is False

        preview.destroy()

    def test_timer_update(self):
        """Test: Timer update e countdown."""
        preview = LivePreviewWindow(
            parent=self.root,
            camera_index=0,
            duration_s=1.0,  # Curta duração para teste
            on_stop_callback=None,
        )

        # Aguardar um pouco para timer atualizar
        self.root.update()
        time.sleep(0.2)
        self.root.update()

        # Verificar que timer está funcionando
        assert preview.start_time is not None

        preview.destroy()

    def test_manual_stop_button(self):
        """Test: Stop button callback."""
        callback_called = [False]

        def on_stop():
            callback_called[0] = True

        preview = LivePreviewWindow(
            parent=self.root,
            camera_index=0,
            duration_s=60.0,
            on_stop_callback=on_stop,
        )

        self.root.update()

        # Clicar no stop button
        preview._on_stop_clicked()
        self.root.update()

        # Verificar que callback foi chamado
        assert callback_called[0] is True
        assert preview.is_stopped is True

        preview.destroy()

    def test_frame_update_with_detections(self):
        """Test: Frame update com detections."""
        preview = LivePreviewWindow(
            parent=self.root,
            camera_index=0,
            duration_s=60.0,
            on_stop_callback=None,
        )

        self.root.update()

        # Criar frame de teste
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Criar detections de teste
        detections = [
            [100, 100, 200, 200, 0.95],  # x1, y1, x2, y2, conf
            [300, 300, 400, 400, 0.85],
        ]

        # Update frame
        preview.update_frame(frame, detections)
        self.root.update()

        # Verificar que stats foram atualizados
        assert preview.frame_count == 1
        assert preview.detection_count == 2

        preview.destroy()

    def test_frame_update_no_detections(self):
        """Test: Frame update sem detections."""
        preview = LivePreviewWindow(
            parent=self.root,
            camera_index=0,
            duration_s=60.0,
            on_stop_callback=None,
        )

        self.root.update()

        # Criar frame de teste
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Update frame sem detections
        preview.update_frame(frame, None)
        self.root.update()

        # Verificar que frame foi processado
        assert preview.frame_count == 1
        assert preview.detection_count == 0

        preview.destroy()

    def test_fps_calculation(self):
        """Test: FPS calculation."""
        preview = LivePreviewWindow(
            parent=self.root,
            camera_index=0,
            duration_s=60.0,
            on_stop_callback=None,
        )

        self.root.update()

        # Processar múltiplos frames
        for _ in range(5):
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            preview.update_frame(frame, [])
            self.root.update()
            time.sleep(0.1)

        # Verificar que FPS foi calculado
        assert preview.current_fps > 0

        preview.destroy()

    def test_auto_stop_on_duration_complete(self):
        """Test: Auto-close quando duração completa."""
        callback_called = [False]

        def on_stop():
            callback_called[0] = True

        preview = LivePreviewWindow(
            parent=self.root,
            camera_index=0,
            duration_s=0.5,  # Muito curta para teste
            on_stop_callback=on_stop,
        )

        # Aguardar duração expirar
        start = time.time()
        while time.time() - start < 1.0:  # Timeout de segurança
            self.root.update()
            time.sleep(0.1)
            if callback_called[0]:
                break

        # Verificar que callback foi chamado
        assert callback_called[0] is True
        assert preview.is_stopped is True

        preview.destroy()

    def test_update_frame_after_stop(self):
        """Test: Update frame após stop não deve crashar."""
        preview = LivePreviewWindow(
            parent=self.root,
            camera_index=0,
            duration_s=60.0,
            on_stop_callback=None,
        )

        self.root.update()

        # Stop preview
        preview._on_stop_clicked()
        self.root.update()

        # Tentar update após stop (não deve crashar)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        preview.update_frame(frame, [])
        self.root.update()

        # Verificar que frame não foi processado após stop
        assert preview.frame_count == 0

        preview.destroy()

    def test_window_close_triggers_stop(self):
        """Test: Window close trigger stop callback."""
        callback_called = [False]

        def on_stop():
            callback_called[0] = True

        preview = LivePreviewWindow(
            parent=self.root,
            camera_index=0,
            duration_s=60.0,
            on_stop_callback=on_stop,
        )

        self.root.update()

        # Close window
        preview._on_window_close()

        # Verificar que callback foi chamado
        assert callback_called[0] is True

        # Note: não chamar destroy() pois _on_window_close já destruiu


if __name__ == "__main__":
    unittest.main()
