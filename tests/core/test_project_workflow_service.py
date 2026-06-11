"""
Unit tests for ProjectWorkflowService.

Phase 5: Project Workflow Simplification tests for project creation,
opening, configuration, and post-creation guide generation.
"""

import unittest
from typing import Any, cast
from unittest.mock import Mock, patch

from zebtrack.core.project.project_workflow_service import ProjectWorkflowService


class TestProjectWorkflowServiceInitialization(unittest.TestCase):
    """Test suite for ProjectWorkflowService initialization."""

    def test_init_with_all_dependencies(self):
        """Test initialization with all dependencies."""
        mock_project_manager = Mock()
        mock_model_service = Mock()
        mock_state_manager = Mock()
        mock_ui_coordinator = Mock()

        service = ProjectWorkflowService(
            project_manager=mock_project_manager,
            model_service=mock_model_service,
            state_manager=mock_state_manager,
            ui_coordinator=mock_ui_coordinator,
        )

        assert service.project_manager == mock_project_manager
        assert service.model_service == mock_model_service
        assert service.state_manager == mock_state_manager
        assert service.ui_coordinator == mock_ui_coordinator
        assert service._using_project_overrides is False
        assert service._global_model_defaults == {}

    def test_init_without_ui_coordinator(self):
        """Test initialization without UI coordinator."""
        service = ProjectWorkflowService(
            project_manager=Mock(),
            model_service=Mock(),
            state_manager=Mock(),
            ui_coordinator=None,
        )

        assert service.ui_coordinator is None

    def test_set_global_model_defaults(self):
        """Test setting global model defaults."""
        service = ProjectWorkflowService(
            project_manager=Mock(),
            model_service=Mock(),
            state_manager=Mock(),
        )

        service.set_global_model_defaults(
            active_weight="weight1.pt",
            use_openvino=True,
        )

        assert service._global_model_defaults == {
            "active_weight": "weight1.pt",
            "use_openvino": True,
        }


class TestProjectWorkflowServiceValidation(unittest.TestCase):
    """Test suite for parameter validation methods."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = ProjectWorkflowService(
            project_manager=Mock(),
            model_service=Mock(),
            state_manager=Mock(),
        )

    def test_validate_project_parameters_valid(self):
        """Test validation with valid parameters."""
        is_valid, error_msg = self.service.validate_project_parameters(
            animal_method="det",
            animals_per_aquarium=1,
        )

        assert is_valid is True
        assert error_msg is None

    def test_validate_project_parameters_det_multi_animal_invalid(self):
        """Test validation fails for det mode with multiple animals."""
        is_valid, error_msg = self.service.validate_project_parameters(
            animal_method="det",
            animals_per_aquarium=3,
        )

        assert is_valid is False
        assert error_msg is not None
        assert "modo de detecção" in error_msg
        assert "1 animal por aquário" in error_msg

    def test_validate_project_parameters_seg_multi_animal_valid(self):
        """Test validation succeeds for seg mode with multiple animals."""
        is_valid, error_msg = self.service.validate_project_parameters(
            animal_method="seg",
            animals_per_aquarium=5,
        )

        assert is_valid is True
        assert error_msg is None

    def test_prepare_controller_parameters_whitelist(self):
        """Test parameter preparation filters using whitelist."""
        kwargs = {
            "project_path": "/path/to/project",
            "project_type": "live",
            "num_aquariums": 2,
            "animals_per_aquarium": 1,
            "use_openvino": True,
            "active_weight": "weight.pt",
            "invalid_param": "should_be_removed",
            "another_invalid": 123,
        }

        result = self.service.prepare_controller_parameters(**kwargs)

        # Valid params should be included
        assert result["project_path"] == "/path/to/project"
        assert result["project_type"] == "live"
        assert result["num_aquariums"] == 2
        assert result["use_openvino"] is True

        # Newly supported parameter should be preserved
        kwargs_with_device = kwargs | {"openvino_device": "GPU"}
        result_with_device = self.service.prepare_controller_parameters(**kwargs_with_device)
        assert result_with_device["openvino_device"] == "GPU"

        # Invalid params should be filtered out
        assert "invalid_param" not in result
        assert "another_invalid" not in result


class TestProjectWorkflowServiceModelSettings(unittest.TestCase):
    """Test suite for model settings resolution and application."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_project_manager = Mock()
        self.mock_model_service = Mock()
        self.mock_state_manager = Mock()
        self.mock_settings = Mock()
        self.mock_settings.model_selection.aquarium_method = "det"
        self.mock_settings.model_selection.animal_method = "seg"
        self.mock_model_service.weight_manager = Mock()

        self.service = ProjectWorkflowService(
            project_manager=self.mock_project_manager,
            model_service=self.mock_model_service,
            state_manager=self.mock_state_manager,
            settings_obj=self.mock_settings,
        )

    def test_resolve_project_model_settings_from_overrides(self):
        """Test resolution prioritizes explicit overrides."""
        self.mock_project_manager.project_data = {
            "active_weight": "old_weight.pt",
            "use_openvino": False,
        }
        self.mock_model_service.get_all_weight_names.return_value = [
            "override_weight.pt",
            "old_weight.pt",
        ]

        overrides = {
            "active_weight": "override_weight.pt",
            "use_openvino": True,
        }

        weight, openvino = self.service.resolve_project_model_settings(overrides)

        assert weight == "override_weight.pt"
        assert openvino is True

    def test_resolve_project_model_settings_fallback_to_project_data(self):
        """Test resolution falls back to project data."""
        self.mock_project_manager.project_data = {
            "active_weight": "project_weight.pt",
            "use_openvino": True,
        }
        self.mock_model_service.get_all_weight_names.return_value = ["project_weight.pt"]

        weight, openvino = self.service.resolve_project_model_settings(overrides=None)

        assert weight == "project_weight.pt"
        assert openvino is True

    def test_resolve_project_model_settings_prefers_active_project_slot_override(self):
        """Animal-slot overrides must outrank stale legacy snapshots."""
        self.mock_project_manager.project_data = {
            "active_weight": "stale_weight.pt",
            "use_openvino": False,
            "model_overrides": {
                "active_weight": None,
                "use_openvino": None,
                "slot_weights": {"seg:zebrafish": "project_seg.pt"},
            },
        }
        self.mock_model_service.get_all_weight_names.return_value = ["project_seg.pt", "global.pt"]

        weight, openvino = self.service.resolve_project_model_settings(overrides=None)

        assert weight == "project_seg.pt"
        assert openvino is False

    def test_resolve_project_model_settings_prefers_project_root_when_overrides_empty(self):
        """Regression (2026-06-11): when ``model_overrides["use_openvino"]``
        is ``None``, the raiz ``project_data["use_openvino"]`` is the
        canonical project choice (gravado pelo wizard ou pelo save
        anterior). Antes esse caminho caia em ``_global_model_defaults``
        e, ao reabrir um projeto OpenVINO criado pelo wizard com o
        ``detector_state`` ainda no default False, o resolve devolvia
        False e o ``apply_project_model_overrides`` sobrescrevia o True
        em disco — corrompendo a configuracao do projeto.
        """
        self.mock_project_manager.project_data = {
            "active_weight": "stale_weight.pt",
            "use_openvino": True,
            "model_overrides": {
                "active_weight": None,
                "use_openvino": None,
                "slot_weights": {},
            },
        }
        self.service._global_model_defaults = {
            "active_weight": "global_weight.pt",
            "use_openvino": False,
        }
        self.mock_model_service.get_all_weight_names.return_value = ["global_weight.pt"]

        weight, openvino = self.service.resolve_project_model_settings(overrides=None)

        # Active weight ainda segue _global_model_defaults quando o
        # override e o snapshot sao None/ausente — apenas o
        # use_openvino passou a preferir o project_data raiz.
        assert weight == "global_weight.pt"
        assert openvino is True

    def test_resolve_project_model_settings_fallback_to_global_defaults(self):
        """Test resolution falls back to global defaults."""
        self.mock_project_manager.project_data = {}
        self.service._global_model_defaults = {
            "active_weight": "global_weight.pt",
            "use_openvino": False,
        }
        self.mock_model_service.get_all_weight_names.return_value = ["global_weight.pt"]

        weight, openvino = self.service.resolve_project_model_settings(overrides=None)

        assert weight == "global_weight.pt"
        assert openvino is False

    def test_resolve_project_model_settings_weight_not_available(self):
        """Test resolution handles missing weight gracefully."""
        self.mock_project_manager.project_data = {"active_weight": "missing_weight.pt"}
        self.mock_model_service.get_all_weight_names.return_value = ["available_weight.pt"]
        self.mock_model_service.get_default_weight.return_value = ("available_weight.pt", {})

        weight, _openvino = self.service.resolve_project_model_settings(overrides=None)

        assert weight == "available_weight.pt"

    def test_apply_project_model_overrides_with_project(self):
        """Test applying overrides updates project data."""
        self.mock_project_manager.project_data = {
            "active_weight": "old_weight.pt",
            "use_openvino": False,
        }
        self.mock_project_manager.project_path = "/path/to/project"
        self.mock_model_service.get_all_weight_names.return_value = ["new_weight.pt"]

        overrides = {"active_weight": "new_weight.pt", "use_openvino": True}
        mock_weight_setter = Mock()
        mock_openvino_setter = Mock()

        weight, openvino = self.service.apply_project_model_overrides(
            overrides=overrides,
            active_weight_setter=mock_weight_setter,
            use_openvino_setter=mock_openvino_setter,
        )

        assert weight == "new_weight.pt"
        assert openvino is True
        mock_weight_setter.assert_called_once_with("new_weight.pt")
        mock_openvino_setter.assert_called_once_with(True)
        self.mock_project_manager.save_project.assert_called_once()

    def test_apply_project_model_overrides_sets_runtime_slot_overrides(self):
        """Project slot overrides must be pushed into WeightManager runtime state."""
        self.mock_project_manager.project_data = {
            "active_weight": "stale_weight.pt",
            "use_openvino": False,
            "openvino_device": "AUTO",
            "model_overrides": {
                "active_weight": None,
                "use_openvino": None,
                "device": "AUTO",
                "slot_weights": {"seg:zebrafish": "project_seg.pt"},
            },
        }
        self.mock_project_manager.project_path = "/path/to/project"
        self.mock_model_service.get_all_weight_names.return_value = ["project_seg.pt", "global.pt"]
        self.mock_model_service.is_openvino_ready.return_value = True

        self.service.apply_project_model_overrides(
            overrides=None,
            active_weight_setter=Mock(),
            use_openvino_setter=Mock(),
        )

        self.mock_model_service.weight_manager.set_runtime_slot_overrides.assert_called_once_with(
            {("seg", "zebrafish"): "project_seg.pt"}
        )

    def test_save_project_model_slot_overrides_persists_slot_weights(self):
        """Saving project slot overrides must keep explicit slot mappings."""
        self.mock_project_manager.project_data = {
            "model_overrides": {
                "active_weight": None,
                "use_openvino": None,
                "device": "AUTO",
                "slot_weights": {},
            }
        }
        self.mock_project_manager.project_path = "/path/to/project"
        self.mock_model_service.get_all_weight_names.return_value = ["project_seg.pt"]
        self.mock_model_service.is_openvino_ready.return_value = True

        weight, openvino = self.service.save_project_model_slot_overrides(
            {"seg:zebrafish": "project_seg.pt"},
            True,
        )

        assert weight == "project_seg.pt"
        assert openvino is True
        assert self.mock_project_manager.project_data["model_overrides"]["slot_weights"] == {
            "seg:zebrafish": "project_seg.pt"
        }
        assert (
            self.mock_project_manager.project_data["model_overrides"]["active_weight"]
            == "project_seg.pt"
        )
        # Persistência garantida: apply_project_model_overrides só salva
        # quando detecta diff nos espelhos-raiz; as mutações de slot_weights
        # acontecem ANTES da comparação (mesmo dict) e passavam despercebidas
        # — era assim que "Copiar globais para o projeto" se perdia ao fechar
        # o app. Pode haver um segundo save vindo do apply (inócuo).
        assert self.mock_project_manager.save_project.call_count >= 1

    def test_apply_project_model_overrides_without_project(self):
        """Test applying overrides returns globals when no project."""
        self.mock_project_manager.project_data = None
        self.service._global_model_defaults = {
            "active_weight": "global_weight.pt",
            "use_openvino": False,
        }

        weight, openvino = self.service.apply_project_model_overrides()

        assert weight == "global_weight.pt"
        assert openvino is False


class TestProjectWorkflowServiceProjectCreation(unittest.TestCase):
    """Test suite for project creation workflow."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_project_manager = Mock()
        self.mock_model_service = Mock()
        self.mock_state_manager = Mock()
        self.mock_settings = Mock()
        self.mock_settings.model_selection.animal_method = "det"

        self.service = ProjectWorkflowService(
            project_manager=self.mock_project_manager,
            model_service=self.mock_model_service,
            state_manager=self.mock_state_manager,
            settings_obj=self.mock_settings,
        )

        self.service.set_global_model_defaults(
            active_weight="default_weight.pt",
            use_openvino=False,
        )

    def test_create_project_success(self):
        """Test successful project creation."""
        self.mock_project_manager.create_new_project.return_value = True
        self.mock_project_manager.project_path = "/path/to/project"
        self.mock_project_manager.project_data = {"num_aquariums": 2}
        self.mock_project_manager.get_active_zone_video.return_value = None
        # Mock get_all_weight_names to return a list
        self.mock_model_service.get_all_weight_names.return_value = ["default_weight.pt"]

        result = self.service.create_project(
            project_path="/path/to/project",
            project_type="live",
            animals_per_aquarium=1,
        )

        assert result["success"] is True
        assert result["error_message"] is None
        assert result["animal_method"] == "det"
        self.mock_project_manager.create_new_project.assert_called_once()
        self.mock_state_manager.update_project_state.assert_called_once()

    def test_create_project_validation_failure(self):
        """Test project creation fails validation."""
        result = self.service.create_project(
            animal_method="det",  # Explicitly pass animal_method
            animals_per_aquarium=5,  # Invalid for det mode
        )

        assert result["success"] is False
        assert "modo de detecção" in result["error_message"]
        self.mock_project_manager.create_new_project.assert_not_called()

    def test_create_project_creation_failure(self):
        """Test project creation fails at ProjectManager level."""
        from zebtrack.core.project.project_manager import ProjectInvalidError

        # Make create_new_project raise an exception
        self.mock_project_manager.create_new_project.side_effect = ProjectInvalidError(
            message="Falha ao criar o projeto"
        )

        result = self.service.create_project(
            project_path="/path/to/project",
            animals_per_aquarium=1,
        )

        assert result["success"] is False
        assert "Falha ao criar" in result["error_message"]

    def test_create_project_with_wizard_metadata(self):
        """Test project creation with wizard import.

        Phase 7: Updated to pass wizard data directly (no adapter).
        The service now constructs _wizard_metadata internally from kwargs.
        """
        self.mock_settings.model_selection.animal_method = "seg"
        self.mock_project_manager.create_new_project.return_value = True
        self.mock_project_manager.project_path = "/path/to/project"
        self.mock_project_manager.project_data = {}
        self.mock_project_manager.get_active_zone_video.return_value = None
        self.mock_project_manager.import_parquets_from_wizard.return_value = True

        # Pass wizard data as kwargs (simulating direct wizard output)
        result = self.service.create_project(
            project_path="/path/to/project",
            animals_per_aquarium=2,
            import_config=[{"video": "/path/to/video.mp4", "import_arena": True}],
            roi_merge_strategy="replace",
            scanned_videos=[],
        )

        assert result["success"] is True
        assert result["wizard_metadata"] is not None
        assert result["import_success"] is True
        self.mock_project_manager.import_parquets_from_wizard.assert_called_once()

    def test_prepare_project_input_generates_video_files_without_detected_design(self):
        """Pre-recorded flow must include video_files even when design detection is absent."""
        kwargs, _context = self.service._prepare_project_input(
            project_path="/tmp/project",
            project_type="experimental",
            scanned_videos=[
                {
                    "path": "/tmp/video1.mp4",
                    "filename": "video1.mp4",
                    "has_complete_data": True,
                }
            ],
            parquet_import_scope=None,
        )

        assert "video_files" in kwargs
        assert len(kwargs["video_files"]) == 1
        assert kwargs["video_files"][0]["path"] == "/tmp/video1.mp4"
        assert kwargs["video_files"][0]["has_data"] is False

    def test_prepare_project_input_propagates_openvino_device_from_model_selection(self):
        """Model selection should propagate OpenVINO device when top-level value is absent."""
        kwargs, _context = self.service._prepare_project_input(
            project_path="/tmp/project",
            project_type="experimental",
            model_selection={"use_openvino": True, "openvino_device": "NPU"},
        )

        assert kwargs["openvino_device"] == "NPU"


class TestProjectWorkflowServiceProjectOpening(unittest.TestCase):
    """Test suite for project opening workflow."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_project_manager = Mock()
        self.mock_model_service = Mock()
        self.mock_state_manager = Mock()

        self.service = ProjectWorkflowService(
            project_manager=self.mock_project_manager,
            model_service=self.mock_model_service,
            state_manager=self.mock_state_manager,
        )

    def test_open_project_success(self):
        """Test successful project opening."""
        self.mock_project_manager.load_project.return_value = True
        self.mock_project_manager.project_data = {
            "active_weight": "project_weight.pt",
            "use_openvino": True,
        }
        self.mock_project_manager.get_project_name.return_value = "Test Project"
        self.mock_project_manager.get_all_videos.return_value = [
            {"path": "/video1.mp4"},
            {"path": "/video2.mp4"},
        ]
        self.mock_project_manager.get_zone_data.return_value = Mock(
            polygon=[(0, 0), (100, 100)],
            roi_polygons=[],
        )
        self.mock_project_manager.get_active_zone_video.return_value = None
        self.mock_model_service.get_all_weight_names.return_value = ["project_weight.pt"]

        result = self.service.open_project(
            project_path="/path/to/project",
        )

        assert result["success"] is True
        assert result["project_info"]["name"] == "Test Project"
        assert result["project_info"]["videos_count"] == 2
        assert result["project_info"]["zone_status"] == "✓"
        assert result["resolved_weight"] == "project_weight.pt"
        assert result["resolved_openvino"] is True
        self.mock_project_manager.load_project.assert_called_once()
        self.mock_state_manager.update_project_state.assert_called_once()

    def test_open_project_failure(self):
        """Test project opening fails."""
        from zebtrack.core.project.project_manager import ProjectInvalidError

        # Make load_project raise an exception instead of returning False
        self.mock_project_manager.load_project.side_effect = ProjectInvalidError(
            message="Não foi possível carregar o projeto"
        )
        # Add mock for get_all_weight_names to prevent TypeError
        self.mock_model_service.get_all_weight_names.return_value = ["default_weight.pt"]

        result = self.service.open_project(
            project_path="/path/to/project",
        )

        assert result["success"] is False
        assert "Não foi possível carregar" in result["error_message"]
        assert result["project_info"] is None

    def test_open_project_with_detector_restoration(self):
        """Test project opening with detector restoration callback."""
        self.mock_project_manager.load_project.return_value = True
        self.mock_project_manager.project_data = {}
        self.mock_project_manager.get_project_name.return_value = "Test"
        self.mock_project_manager.get_all_videos.return_value = []
        self.mock_project_manager.get_zone_data.return_value = None
        self.mock_project_manager.get_active_zone_video.return_value = None
        self.mock_project_manager.get_detector_state.return_value = {
            "confidence_threshold": 0.5,
        }

        mock_restore_callback = Mock()

        result = self.service.open_project(
            project_path="/path/to/project",
            restore_detector_callback=mock_restore_callback,
        )

        assert result["success"] is True
        mock_restore_callback.assert_called_once_with({"confidence_threshold": 0.5})

    def test_open_project_with_zones(self):
        """Test project opening with zones setup."""
        self.mock_project_manager.load_project.return_value = True
        self.mock_project_manager.project_data = {}
        self.mock_project_manager.get_project_name.return_value = "Test"
        self.mock_project_manager.get_all_videos.return_value = []
        self.mock_project_manager.get_active_zone_video.return_value = None

        mock_zone_data = Mock()
        mock_zone_data.polygon = [(0, 0), (100, 100)]
        mock_zone_data.roi_polygons = [[(10, 10), (50, 50)]]
        self.mock_project_manager.get_zone_data.return_value = mock_zone_data

        mock_setup_zones = Mock()

        result = self.service.open_project(
            project_path="/path/to/project",
            setup_zones_callback=mock_setup_zones,
        )

        assert result["success"] is True
        assert result["project_info"]["roi_count"] == 1
        mock_setup_zones.assert_called_once()


class TestProjectWorkflowServicePostCreationGuide(unittest.TestCase):
    """Test suite for post-creation guide generation."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_project_manager = Mock()
        self.service = ProjectWorkflowService(
            project_manager=self.mock_project_manager,
            model_service=Mock(),
            state_manager=Mock(),
        )

    def test_generate_guide_with_videos(self):
        """Test guide generation with videos."""
        self.mock_project_manager.get_all_videos.return_value = [
            {"path": "/video1.mp4", "has_arena": True, "has_rois": True, "has_trajectory": True},
            {"path": "/video2.mp4", "has_arena": True, "has_rois": False, "has_trajectory": False},
        ]

        wizard_metadata: dict[str, Any] = {
            "import_config": [],
            "scanned_videos": [],
        }

        guide = self.service.generate_post_creation_guide(
            wizard_metadata=wizard_metadata,
            check_suppression=False,
        )

        assert guide is not None
        assert guide["title"] == "Bem-vindo ao Projeto!"
        assert "2" in guide["message"]  # Total videos
        assert "Próximos passos" in guide["message"]

    def test_generate_guide_suppressed_by_env(self):
        """Test guide generation suppressed by environment variable."""
        with patch("os.environ.get") as mock_env:
            mock_env.return_value = "1"

            guide = self.service.generate_post_creation_guide(
                wizard_metadata={"scanned_videos": []},
                check_suppression=True,
            )

            assert guide is None

    def test_generate_guide_without_metadata(self):
        """Test guide generation without wizard metadata."""
        guide = self.service.generate_post_creation_guide(
            wizard_metadata=cast(dict[str, Any], None),
            check_suppression=False,
        )

        assert guide is None

    def test_generate_guide_without_videos(self):
        """Test guide generation without videos."""
        self.mock_project_manager.get_all_videos.return_value = []

        guide = self.service.generate_post_creation_guide(
            wizard_metadata={"import_config": [], "scanned_videos": []},
            check_suppression=False,
        )

        assert guide is None

    def test_generate_guide_with_import_config(self):
        """Test guide generation considers import configuration."""
        self.mock_project_manager.get_all_videos.return_value = []

        wizard_metadata: dict[str, Any] = {
            "import_config": [
                {
                    "video": "/video1.mp4",
                    "import_arena": True,
                    "import_rois": True,
                    "import_trajectory": False,
                }
            ],
            "scanned_videos": [{"video": "/video1.mp4", "path": "/video1.mp4"}],
        }

        guide = self.service.generate_post_creation_guide(
            wizard_metadata=wizard_metadata,
            check_suppression=False,
        )

        assert guide is not None
        assert "arena definida: 1" in guide["message"]
        assert "ROIs definidas: 1" in guide["message"]


class TestProjectWorkflowServiceProjectLoadFailures(unittest.TestCase):
    """Test suite for project loading failures."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_project_manager = Mock()
        self.mock_model_service = Mock()
        self.mock_state_manager = Mock()

        self.service = ProjectWorkflowService(
            project_manager=self.mock_project_manager,
            model_service=self.mock_model_service,
            state_manager=self.mock_state_manager,
        )

    def test_open_project_file_not_found(self):
        """Test opening project when project.json doesn't exist."""
        from zebtrack.core.project.project_manager import ProjectInvalidError

        self.mock_project_manager.load_project.side_effect = ProjectInvalidError(
            message="project.json não encontrado"
        )
        self.mock_model_service.get_all_weight_names.return_value = ["default_weight.pt"]

        result = self.service.open_project(
            project_path="/nonexistent/project",
        )

        assert result["success"] is False
        assert "não encontrado" in result["error_message"]
        assert result["project_info"] is None

    def test_open_project_corrupted_json(self):
        """Test opening project with corrupted project.json."""
        from zebtrack.core.project.project_manager import ProjectInvalidError

        self.mock_project_manager.load_project.side_effect = ProjectInvalidError(
            message="Arquivo de projeto corrompido"
        )
        self.mock_model_service.get_all_weight_names.return_value = ["default_weight.pt"]

        result = self.service.open_project(
            project_path="/corrupted/project",
        )

        assert result["success"] is False
        assert "corrompido" in result["error_message"].lower()

    def test_open_project_missing_videos(self):
        """Test opening project with missing video files."""
        self.mock_project_manager.load_project.return_value = True
        self.mock_project_manager.project_data = {}
        self.mock_project_manager.get_project_name.return_value = "Test"
        # Return videos but they don't exist on disk
        self.mock_project_manager.get_all_videos.return_value = [
            {"path": "/missing/video1.mp4"},
            {"path": "/missing/video2.mp4"},
        ]
        self.mock_project_manager.get_zone_data.return_value = None
        self.mock_project_manager.get_active_zone_video.return_value = None

        result = self.service.open_project(
            project_path="/path/to/project",
        )

        # Should still succeed but with warnings
        assert result["success"] is True
        assert result["project_info"]["videos_count"] == 2

    def test_open_project_restore_detector_callback_fails(self):
        """Test opening project when restore_detector_callback raises exception."""
        self.mock_project_manager.load_project.return_value = True
        self.mock_project_manager.project_data = {}
        self.mock_project_manager.get_project_name.return_value = "Test"
        self.mock_project_manager.get_all_videos.return_value = []
        self.mock_project_manager.get_zone_data.return_value = None
        self.mock_project_manager.get_active_zone_video.return_value = None
        self.mock_project_manager.get_detector_state.return_value = {
            "confidence_threshold": 0.5,
        }

        def failing_restore(config):
            raise RuntimeError("Detector restore failed")

        # Should propagate exception
        with self.assertRaises(RuntimeError):
            self.service.open_project(
                project_path="/path/to/project",
                restore_detector_callback=failing_restore,
            )


class TestProjectWorkflowServiceZoneImportFailures(unittest.TestCase):
    """Test suite for zone import failures."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_project_manager = Mock()
        self.mock_model_service = Mock()
        self.mock_state_manager = Mock()
        self.mock_settings = Mock()
        self.mock_settings.model_selection.animal_method = "det"

        self.service = ProjectWorkflowService(
            project_manager=self.mock_project_manager,
            model_service=self.mock_model_service,
            state_manager=self.mock_state_manager,
            settings_obj=self.mock_settings,
        )

        self.service.set_global_model_defaults(
            active_weight="default_weight.pt",
            use_openvino=False,
        )

    def test_create_project_import_invalid_geometry(self):
        """Test project creation with invalid zone geometry in import config."""
        self.mock_project_manager.create_new_project.return_value = True
        self.mock_project_manager.project_path = "/path/to/project"
        self.mock_project_manager.project_data = {}
        self.mock_project_manager.get_active_zone_video.return_value = None

        # Import config with invalid polygon (single point)
        import_config = [
            {
                "video": "/path/to/video.mp4",
                "import_arena": True,
                "arena_polygon": [[100, 100]],  # Invalid: single point
            }
        ]

        # Import should fail
        self.mock_project_manager.import_parquets_from_wizard.return_value = False

        result = self.service.create_project(
            project_path="/path/to/project",
            animals_per_aquarium=1,
            import_config=import_config,
            roi_merge_strategy="replace",
            scanned_videos=[],
        )

        assert result["success"] is True
        assert result["import_success"] is False

    def test_create_project_import_incompatible_roi_merge_strategy(self):
        """Test project creation with invalid ROI merge strategy."""
        self.mock_project_manager.create_new_project.return_value = True
        self.mock_project_manager.project_path = "/path/to/project"
        self.mock_project_manager.project_data = {}
        self.mock_project_manager.get_active_zone_video.return_value = None

        import_config = [
            {
                "video": "/path/to/video.mp4",
                "import_rois": True,
            }
        ]

        # Simulate import failure due to invalid strategy
        self.mock_project_manager.import_parquets_from_wizard.side_effect = ValueError(
            "Invalid merge strategy"
        )

        # Should propagate exception
        with self.assertRaises(ValueError):
            self.service.create_project(
                project_path="/path/to/project",
                animals_per_aquarium=1,
                import_config=import_config,
                roi_merge_strategy="invalid_strategy",
                scanned_videos=[],
            )

    def test_create_project_import_parquet_not_found(self):
        """Test project creation when parquet files are missing."""
        self.mock_project_manager.create_new_project.return_value = True
        self.mock_project_manager.project_path = "/path/to/project"
        self.mock_project_manager.project_data = {}
        self.mock_project_manager.get_active_zone_video.return_value = None

        import_config = [
            {
                "video": "/path/to/video.mp4",
                "import_trajectory": True,
                "trajectory_parquet": "/missing/trajectory.parquet",
            }
        ]

        # Import fails due to missing file
        self.mock_project_manager.import_parquets_from_wizard.return_value = False

        result = self.service.create_project(
            project_path="/path/to/project",
            animals_per_aquarium=1,
            import_config=import_config,
            scanned_videos=[],
        )

        assert result["success"] is True
        assert result["import_success"] is False


class TestProjectWorkflowServiceModelSettingsFailures(unittest.TestCase):
    """Test suite for model settings resolution failures."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_project_manager = Mock()
        self.mock_model_service = Mock()
        self.mock_state_manager = Mock()

        self.service = ProjectWorkflowService(
            project_manager=self.mock_project_manager,
            model_service=self.mock_model_service,
            state_manager=self.mock_state_manager,
        )

    def test_resolve_model_settings_weight_unavailable(self):
        """Test resolving model settings when weight is unavailable."""
        self.mock_project_manager.project_data = {
            "active_weight": "missing_weight.pt",
        }
        self.mock_model_service.get_all_weight_names.return_value = ["available_weight.pt"]
        self.mock_model_service.get_default_weight.return_value = ("available_weight.pt", {})

        # Should fallback to default weight
        weight, _openvino = self.service.resolve_project_model_settings()

        assert weight == "available_weight.pt"

    def test_apply_model_overrides_no_project(self):
        """Test applying model overrides when no project is loaded."""
        self.mock_project_manager.project_data = None
        self.service._global_model_defaults = {
            "active_weight": "global_weight.pt",
            "use_openvino": True,
        }

        weight, openvino = self.service.apply_project_model_overrides()

        # Should return global defaults
        assert weight == "global_weight.pt"
        assert openvino is True

    def test_apply_model_overrides_save_fails(self):
        """Test applying overrides when project save fails."""
        self.mock_project_manager.project_data = {
            "active_weight": "old_weight.pt",
            "use_openvino": False,
        }
        self.mock_project_manager.project_path = "/path/to/project"
        self.mock_model_service.get_all_weight_names.return_value = ["new_weight.pt"]

        # Save raises exception
        self.mock_project_manager.save_project.side_effect = RuntimeError("Save failed")

        overrides = {"active_weight": "new_weight.pt", "use_openvino": True}

        # Should propagate exception
        with self.assertRaises(RuntimeError):
            self.service.apply_project_model_overrides(
                overrides=overrides,
                active_weight_setter=Mock(),
                use_openvino_setter=Mock(),
            )


class TestProjectWorkflowServiceParameterValidationEdgeCases(unittest.TestCase):
    """Test suite for parameter validation edge cases."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = ProjectWorkflowService(
            project_manager=Mock(),
            model_service=Mock(),
            state_manager=Mock(),
        )

    def test_validate_parameters_boundary_animals_per_aquarium(self):
        """Test validation with boundary values for animals_per_aquarium."""
        # Zero animals
        is_valid, _error = self.service.validate_project_parameters(
            animal_method="det",
            animals_per_aquarium=0,
        )
        assert is_valid is False

        # Negative animals
        is_valid, _error = self.service.validate_project_parameters(
            animal_method="det",
            animals_per_aquarium=-1,
        )
        assert is_valid is False

        # Very large number
        is_valid, _error = self.service.validate_project_parameters(
            animal_method="seg",
            animals_per_aquarium=1000,
        )
        assert is_valid is True

    def test_prepare_parameters_filters_unknown(self):
        """Test parameter preparation filters unknown keys."""
        kwargs = {
            "project_path": "/path",
            "unknown_param1": "value1",
            "unknown_param2": 123,
            "num_aquariums": 2,
        }

        filtered = self.service.prepare_controller_parameters(**kwargs)

        assert "project_path" in filtered
        assert "num_aquariums" in filtered
        assert "unknown_param1" not in filtered
        assert "unknown_param2" not in filtered

    def test_prepare_parameters_empty_input(self):
        """Test parameter preparation with empty input."""
        filtered = self.service.prepare_controller_parameters()

        # Should return empty dict
        assert filtered == {}


class TestProjectWorkflowServiceConcurrentOperations(unittest.TestCase):
    """Test suite for concurrent project operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_project_manager = Mock()
        self.mock_model_service = Mock()
        self.mock_state_manager = Mock()
        self.mock_settings = Mock()
        self.mock_settings.model_selection.animal_method = "det"

        self.service = ProjectWorkflowService(
            project_manager=self.mock_project_manager,
            model_service=self.mock_model_service,
            state_manager=self.mock_state_manager,
            settings_obj=self.mock_settings,
        )

        self.service.set_global_model_defaults(
            active_weight="default_weight.pt",
            use_openvino=False,
        )

    def test_create_project_during_open(self):
        """Test creating project while another is being opened (simulated)."""
        # First open starts
        self.mock_project_manager.load_project.return_value = True
        self.mock_project_manager.project_data = {}

        # Then create is called (should use different project_manager state)
        self.mock_project_manager.create_new_project.return_value = True

        # Both operations should succeed independently
        # This is a simplified test - real concurrency would require threading

    def test_multiple_model_override_applications(self):
        """Test multiple rapid model override applications."""
        self.mock_project_manager.project_data = {
            "active_weight": "weight1.pt",
            "use_openvino": False,
        }
        self.mock_project_manager.project_path = "/path/to/project"
        self.mock_model_service.get_all_weight_names.return_value = [
            "weight1.pt",
            "weight2.pt",
            "weight3.pt",
        ]

        # Apply multiple overrides in sequence
        for i in range(3):
            overrides = {"active_weight": f"weight{i + 1}.pt"}
            weight, _openvino = self.service.apply_project_model_overrides(
                overrides=overrides,
                active_weight_setter=Mock(),
            )
            assert weight == f"weight{i + 1}.pt"


class TestProjectWorkflowServicePostCreationGuideEdgeCases(unittest.TestCase):
    """Test suite for post-creation guide edge cases."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_project_manager = Mock()
        self.service = ProjectWorkflowService(
            project_manager=self.mock_project_manager,
            model_service=Mock(),
            state_manager=Mock(),
        )

    def test_generate_guide_empty_scanned_videos(self):
        """Test guide generation with empty scanned videos."""
        self.mock_project_manager.get_all_videos.return_value = []

        wizard_metadata: dict[str, Any] = {
            "import_config": [],
            "scanned_videos": [],  # Empty
        }

        guide = self.service.generate_post_creation_guide(
            wizard_metadata=wizard_metadata,
            check_suppression=False,
        )

        # Should return None for empty videos
        assert guide is None

    def test_generate_guide_malformed_import_config(self):
        """Test guide generation with malformed import config."""
        self.mock_project_manager.get_all_videos.return_value = [
            {"path": "/video1.mp4"},
        ]

        wizard_metadata: dict[str, Any] = {
            "import_config": [
                {"invalid_key": "value"},  # Missing 'video' key
            ],
            "scanned_videos": [{"video": "/video1.mp4", "path": "/video1.mp4"}],
        }

        guide = self.service.generate_post_creation_guide(
            wizard_metadata=wizard_metadata,
            check_suppression=False,
        )

        # Should still generate guide
        assert guide is not None
        assert "Total de vídeos: 1" in guide["message"]


if __name__ == "__main__":
    unittest.main()
