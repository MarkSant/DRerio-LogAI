"""
Unit tests for ProjectWorkflowService.

Phase 5: Project Workflow Simplification tests for project creation,
opening, configuration, and post-creation guide generation.
"""

import unittest
from unittest.mock import Mock, patch

from zebtrack.core.project_workflow_service import ProjectWorkflowService


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

        self.service = ProjectWorkflowService(
            project_manager=self.mock_project_manager,
            model_service=self.mock_model_service,
            state_manager=self.mock_state_manager,
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

        weight, openvino = self.service.resolve_project_model_settings(overrides=None)

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

        mock_setup_detector = Mock(return_value=True)

        result = self.service.create_project(
            setup_detector_callback=mock_setup_detector,
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
            setup_detector_callback=Mock(),
            animal_method="det",  # Explicitly pass animal_method
            animals_per_aquarium=5,  # Invalid for det mode
        )

        assert result["success"] is False
        assert "modo de detecção" in result["error_message"]
        self.mock_project_manager.create_new_project.assert_not_called()

    def test_create_project_creation_failure(self):
        """Test project creation fails at ProjectManager level."""
        from zebtrack.core.project_manager import ProjectInvalidError

        # Make create_new_project raise an exception
        self.mock_project_manager.create_new_project.side_effect = ProjectInvalidError(
            message="Falha ao criar o projeto"
        )

        result = self.service.create_project(
            setup_detector_callback=Mock(),
            project_path="/path/to/project",
            animals_per_aquarium=1,
        )

        assert result["success"] is False
        assert "Falha ao criar" in result["error_message"]

    def test_create_project_with_wizard_metadata(self):
        """Test project creation with wizard import."""
        self.mock_settings.model_selection.animal_method = "seg"
        self.mock_project_manager.create_new_project.return_value = True
        self.mock_project_manager.project_path = "/path/to/project"
        self.mock_project_manager.project_data = {}
        self.mock_project_manager.get_active_zone_video.return_value = None
        self.mock_project_manager.import_parquets_from_wizard.return_value = True

        wizard_metadata = {
            "import_config": [{"video": "/path/to/video.mp4", "import_arena": True}],
            "roi_merge_strategy": "replace",
            "scanned_videos": [],
        }

        result = self.service.create_project(
            setup_detector_callback=Mock(),
            project_path="/path/to/project",
            animals_per_aquarium=2,
            _wizard_metadata=wizard_metadata,
        )

        assert result["success"] is True
        assert result["wizard_metadata"] is not None
        assert result["import_success"] is True
        self.mock_project_manager.import_parquets_from_wizard.assert_called_once()


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
        from zebtrack.core.project_manager import ProjectInvalidError

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

        wizard_metadata = {
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
            wizard_metadata=None,
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

        wizard_metadata = {
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


if __name__ == "__main__":
    unittest.main()
