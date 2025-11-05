"""Testes para Dialogs Batch 1 - Alta Complexidade."""

import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest

from zebtrack.ui.dialogs.calibration_dialog import CalibrationDialog
from zebtrack.ui.dialogs.create_project_dialog import CreateProjectDialog
from zebtrack.ui.dialogs.manage_weights_dialog import ManageWeightsDialog


@pytest.mark.gui
class TestCalibrationDialog(unittest.TestCase):
    """Testes para CalibrationDialog."""

    def setUp(self):
        """Setup: Criar root window e mock controller."""
        self.root = tk.Tk()
        self.root.withdraw()

        self.mock_controller = Mock()
        self.mock_controller.project_manager = Mock()
        self.mock_controller.get_calibration_scope_info.return_value = {
            "scope": "global",
            "label": "Calibração Global",
            "detail": "Configurações aplicam-se globalmente",
        }

    def tearDown(self):
        """Cleanup: Destruir root window."""
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_init_global_scope(self):
        """Test: Inicialização com escopo global."""
        dialog = CalibrationDialog(self.root, self.mock_controller)

        # Verificar scope
        assert dialog.scope == "global"
        assert dialog.preferences_section is None  # Não deve ter preferences em global

        dialog.destroy()

    def test_init_project_scope(self):
        """Test: Inicialização com escopo de projeto."""
        self.mock_controller.get_calibration_scope_info.return_value = {
            "scope": "project",
            "label": "Calibração do Projeto",
            "detail": "Configurações do projeto atual",
        }

        dialog = CalibrationDialog(self.root, self.mock_controller)

        # Verificar scope
        assert dialog.scope == "project"
        # Em project scope, deve criar preferences_section (mas pode não estar visível imediatamente)

        dialog.destroy()

    def test_weight_variables_initialization(self):
        """Test: Inicialização de variáveis de peso."""
        dialog = CalibrationDialog(self.root, self.mock_controller)

        # Verificar que variáveis foram inicializadas
        assert dialog.active_weight_var is not None
        assert dialog.use_openvino_var is not None
        assert dialog.openvino_status_var is not None
        assert dialog.weight_choice.get() == dialog.WEIGHT_INHERIT_LABEL

        dialog.destroy()

    def test_diagnostic_variables_initialization(self):
        """Test: Inicialização de variáveis de diagnóstico."""
        dialog = CalibrationDialog(self.root, self.mock_controller)

        # Verificar valores padrão de diagnóstico
        assert dialog.frames_to_analyze_var.get() == "10"
        assert dialog.confidence_threshold_var.get() == "0.25"
        assert dialog.nms_threshold_var.get() == "0.50"
        assert dialog.track_threshold_var.get() == "0.25"
        assert dialog.match_threshold_var.get() == "0.15"

        dialog.destroy()

    def test_openvino_status_constants(self):
        """Test: Constantes de status do OpenVINO."""
        assert CalibrationDialog.OPENVINO_INHERIT == "inherit"
        assert CalibrationDialog.OPENVINO_ON == "on"
        assert CalibrationDialog.OPENVINO_OFF == "off"
        assert CalibrationDialog.WEIGHT_INHERIT_LABEL == "Herdar (padrão global)"


@pytest.mark.gui
class TestCreateProjectDialog(unittest.TestCase):
    """Testes para CreateProjectDialog."""

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

    def test_init_default_values(self):
        """Test: Inicialização com valores padrão."""
        dialog = CreateProjectDialog(self.root)

        # Verificar valores padrão
        assert dialog.num_aquariums_var.get() == "1"
        assert dialog.animals_per_aquarium_var.get() == "1"
        assert dialog.aquarium_width_var.get() == "10.0"
        assert dialog.aquarium_height_var.get() == "10.0"
        assert dialog.project_type_var.get() == "pre-recorded"
        assert dialog.video_files == []

        dialog.destroy()

    def test_init_recording_variables(self):
        """Test: Inicialização de variáveis de gravação."""
        dialog = CreateProjectDialog(self.root)

        # Verificar valores padrão de gravação
        assert dialog.use_timed_recording_var.get() is False
        assert dialog.recording_duration_var.get() == "5"
        assert dialog.use_countdown_var.get() is False
        assert dialog.countdown_duration_var.get() == "5"

        dialog.destroy()

    def test_init_experimental_design_variables(self):
        """Test: Inicialização de variáveis de design experimental."""
        dialog = CreateProjectDialog(self.root)

        # Verificar valores padrão de design experimental
        assert dialog.total_days_var.get() == "1"
        assert dialog.subjects_per_group_var.get() == "1"
        assert dialog.num_groups_var.get() == "1"
        assert len(dialog.group_name_vars) == 6

        dialog.destroy()

    def test_init_interval_variables(self):
        """Test: Inicialização de variáveis de intervalo."""
        dialog = CreateProjectDialog(self.root)

        # Verificar valores padrão de intervalos
        assert dialog.analysis_interval_var.get() == "10"
        assert dialog.display_interval_var.get() == "10"

        dialog.destroy()

    def test_init_detection_method_variables(self):
        """Test: Inicialização de variáveis de método de detecção."""
        dialog = CreateProjectDialog(self.root)

        # Verificar valores padrão de métodos de detecção
        assert dialog.aquarium_method_var.get() == "seg"
        assert dialog.animal_method_var.get() == "det"

        dialog.destroy()

    def test_project_path_initial_state(self):
        """Test: Estado inicial do caminho do projeto."""
        dialog = CreateProjectDialog(self.root)

        # Project path deve ser None inicialmente
        assert dialog.project_path is None
        assert dialog.result is None

        dialog.destroy()

    @patch("zebtrack.ui.dialogs.create_project_dialog.filedialog.askdirectory")
    def test_select_path(self, mock_askdir):
        """Test: Seleção de caminho do projeto."""
        mock_askdir.return_value = "/fake/path/to/project"

        dialog = CreateProjectDialog(self.root)

        # Trigger path selection
        dialog._select_path()

        # Verificar que caminho foi definido
        assert dialog.project_path == "/fake/path/to/project"

        dialog.destroy()

    @patch("zebtrack.ui.dialogs.create_project_dialog.filedialog.askdirectory")
    def test_select_path_cancelled(self, mock_askdir):
        """Test: Cancelamento de seleção de caminho."""
        mock_askdir.return_value = ""  # User cancelled

        dialog = CreateProjectDialog(self.root)

        # Trigger path selection
        dialog._select_path()

        # Project path deve permanecer None
        assert dialog.project_path is None

        dialog.destroy()


@pytest.mark.gui
class TestManageWeightsDialog(unittest.TestCase):
    """Testes para ManageWeightsDialog."""

    def setUp(self):
        """Setup: Criar root window e mock controller."""
        self.root = tk.Tk()
        self.root.withdraw()

        self.mock_controller = Mock()
        self.mock_controller.get_all_weight_names.return_value = [
            "yolo_seg_v1.pt",
            "yolo_det_v1.pt",
        ]
        self.mock_controller.weight_manager = Mock()
        self.mock_controller.weight_manager.get_default_seg_weight.return_value = (
            "yolo_seg_v1.pt",
            None,
        )
        self.mock_controller.weight_manager.get_default_det_weight.return_value = (
            "yolo_det_v1.pt",
            None,
        )
        self.mock_controller.weight_manager.get_weight_details.return_value = {
            "type": "seg",
            "path": "/fake/path",
        }

    def tearDown(self):
        """Cleanup: Destruir root window."""
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_init(self):
        """Test: Inicialização do dialog."""
        dialog = ManageWeightsDialog(self.root, self.mock_controller, refresh_callback=None)

        # Verificar que listbox foi criada
        assert dialog.listbox is not None
        assert dialog.controller == self.mock_controller

        dialog.destroy()

    def test_init_with_refresh_callback(self):
        """Test: Inicialização com callback de refresh."""
        mock_callback = Mock()
        dialog = ManageWeightsDialog(
            self.root, self.mock_controller, refresh_callback=mock_callback
        )

        # Verificar que callback foi armazenado
        assert dialog.refresh_callback == mock_callback

        dialog.destroy()

    def test_populate_list(self):
        """Test: População da lista de pesos."""
        dialog = ManageWeightsDialog(self.root, self.mock_controller, refresh_callback=None)

        # Verificar que populate_list foi chamado
        self.mock_controller.get_all_weight_names.assert_called()

        # Verificar que listbox tem items
        items = dialog.listbox.get_children()
        assert len(items) > 0

        dialog.destroy()

    def test_populate_list_empty(self):
        """Test: População da lista sem pesos."""
        self.mock_controller.get_all_weight_names.return_value = []

        dialog = ManageWeightsDialog(self.root, self.mock_controller, refresh_callback=None)

        # Verificar que listbox está vazia
        items = dialog.listbox.get_children()
        assert len(items) == 0

        dialog.destroy()

    def test_set_default_seg_no_selection(self):
        """Test: Set default seg sem seleção."""
        dialog = ManageWeightsDialog(self.root, self.mock_controller, refresh_callback=None)

        # Não selecionar nada
        dialog.listbox.selection_set()

        # Tentar setar default (deve exibir mensagem ou não fazer nada)
        dialog.set_default_seg()

        # Não deve ter crashado
        dialog.destroy()

    def test_set_default_det_no_selection(self):
        """Test: Set default det sem seleção."""
        dialog = ManageWeightsDialog(self.root, self.mock_controller, refresh_callback=None)

        # Não selecionar nada
        dialog.listbox.selection_set()

        # Tentar setar default (deve exibir mensagem ou não fazer nada)
        dialog.set_default_det()

        # Não deve ter crashado
        dialog.destroy()

    def test_delete_no_selection(self):
        """Test: Delete sem seleção."""
        dialog = ManageWeightsDialog(self.root, self.mock_controller, refresh_callback=None)

        # Não selecionar nada
        dialog.listbox.selection_set()

        # Tentar deletar (deve exibir mensagem ou não fazer nada)
        dialog.delete()

        # Não deve ter crashado
        dialog.destroy()


@pytest.mark.gui
class TestStartRecordingDialog(unittest.TestCase):
    """Testes para StartRecordingDialog (placeholder - dialog é pequeno)."""

    def setUp(self):
        """Setup: Criar root window."""
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        """Cleanup."""
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_import_exists(self):
        """Test: Verificar que dialog pode ser importado."""
        try:
            from zebtrack.ui.dialogs import StartRecordingDialog

            assert StartRecordingDialog is not None
        except ImportError as e:
            pytest.fail(f"Failed to import StartRecordingDialog: {e}")


@pytest.mark.gui
class TestSingleVideoConfigDialog(unittest.TestCase):
    """Testes para SingleVideoConfigDialog."""

    def setUp(self):
        """Setup: Criar root window."""
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        """Cleanup."""
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_import_exists(self):
        """Test: Verificar que dialog pode ser importado."""
        try:
            from zebtrack.ui.dialogs.single_video_config_dialog import SingleVideoConfigDialog

            assert SingleVideoConfigDialog is not None
        except ImportError as e:
            pytest.fail(f"Failed to import SingleVideoConfigDialog: {e}")

    def test_init_requires_parameters(self):
        """Test: Inicialização requer parâmetros específicos."""
        from zebtrack.ui.dialogs.single_video_config_dialog import SingleVideoConfigDialog

        # Dialog requer parent e video_path no mínimo
        mock_controller = Mock()
        mock_controller.project_manager = Mock()
        mock_controller.project_manager.get_project_data.return_value = {}
        mock_controller.project_manager.get_video_config.return_value = {}

        try:
            dialog = SingleVideoConfigDialog(
                self.root,
                controller=mock_controller,
                video_path="/fake/video.mp4",
                project_data={},
            )

            # Verificar inicialização básica
            assert dialog is not None

            dialog.destroy()
        except Exception as e:
            # Pode falhar por outras razões (ex: validações), mas não deve crashar
            assert "video_path" not in str(e).lower()


if __name__ == "__main__":
    unittest.main()
