"""
Unit tests for ProjectWorkflowService.

Phase 5: Project Workflow Simplification tests for project creation,
opening, configuration, and post-creation guide generation.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, cast
from unittest.mock import MagicMock, Mock, patch

import pytest

from zebtrack.core.exceptions import ProjectInvalidError
from zebtrack.core.project.project_workflow_service import (
    _VALID_OPENVINO_DEVICES,
    ProjectWorkflowService,
)


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
        assert "detection mode (det)" in error_msg
        assert "1 animal per aquarium" in error_msg

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
        # create_project now persists model_selection, so project_data is never
        # empty afterwards and apply_project_model_overrides lists the weights.
        self.mock_model_service.get_all_weight_names.return_value = ["default_weight.pt"]
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
        assert "detection mode (det)" in result["error_message"]
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

    def test_create_project_persists_the_wizard_model_selection(self):
        """The det/seg choice used to live only in _wizard_metadata (lost on reopen)."""
        self.mock_settings.model_selection.animal_method = "det"
        self.mock_settings.model_selection.aquarium_method = "det"
        self.mock_project_manager.create_new_project.return_value = True
        self.mock_project_manager.project_path = "/path/to/project"
        self.mock_project_manager.project_data = {}
        self.mock_project_manager.get_active_zone_video.return_value = None
        self.mock_model_service.get_all_weight_names.return_value = ["default_weight.pt"]

        result = self.service.create_project(
            project_path="/path/to/project",
            project_type="live",
            animals_per_aquarium=2,
            animal_method="seg",
            aquarium_method="seg",
            model_selection={"aquarium_method": "seg", "animal_method": "seg"},
        )

        assert result["success"] is True
        assert self.mock_project_manager.project_data["model_selection"] == {
            "aquarium_method": "seg",
            "animal_method": "seg",
        }
        self.mock_project_manager.save_project.assert_called()

    def test_project_method_drives_the_slot_pairs(self):
        self.mock_settings.model_selection.animal_method = "det"
        self.mock_settings.model_selection.aquarium_method = "det"
        self.mock_project_manager.project_data = {
            "model_selection": {"aquarium_method": "seg", "animal_method": "seg"}
        }

        assert self.service._get_project_slot_pairs() == [
            ("seg", "aquarium"),
            ("seg", "zebrafish"),
        ]

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
        assert guide["title"] == "Welcome to the Project!"
        assert "2" in guide["message"]  # Total videos
        assert "Recommended next steps" in guide["message"]

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
        assert "arena defined: 1" in guide["message"]
        assert "ROIs defined: 1" in guide["message"]


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
        # create_project now persists model_selection, so project_data is never
        # empty afterwards and apply_project_model_overrides lists the weights.
        self.mock_model_service.get_all_weight_names.return_value = ["default_weight.pt"]
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

    def test_prepare_parameters_keeps_the_analysis_window(self):
        """The wizard's analysis window (v8) must survive the whitelist."""
        window = {"version": 1, "start": {"kind": "external", "source": "arduino", "code": 1}}

        filtered = self.service.prepare_controller_parameters(
            project_path="/path", analysis_window=window
        )

        assert filtered["analysis_window"] is window

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
        # create_project now persists model_selection, so project_data is never
        # empty afterwards and apply_project_model_overrides lists the weights.
        self.mock_model_service.get_all_weight_names.return_value = ["default_weight.pt"]
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
        assert "Total videos: 1" in guide["message"]


if __name__ == "__main__":
    unittest.main()


WIZARD_ROLES = {"arena": "arena", "experimenter": "context", "rat": "subject"}


class TestWizardClassRoles(unittest.TestCase):
    """Class roles edited in the wizard reach model_overrides with their sha (ADR-009)."""

    def setUp(self):
        self.pm = Mock()
        self.pm.create_new_project.return_value = True
        self.pm.project_path = "/path/to/project"
        self.pm.project_data = {}
        self.pm.get_active_zone_video.return_value = None
        model_service = Mock()
        model_service.get_all_weight_names.return_value = ["rat.pt"]
        settings = Mock()
        settings.model_selection.animal_method = "det"
        settings.model_selection.aquarium_method = "det"
        self.service = ProjectWorkflowService(
            project_manager=self.pm,
            model_service=model_service,
            state_manager=Mock(),
            settings_obj=settings,
        )
        self.service.set_global_model_defaults(active_weight="rat.pt", use_openvino=False)

    def _create(self, **extra):
        return self.service.create_project(
            project_path="/path/to/project",
            project_type="live",
            animals_per_aquarium=1,
            **extra,
        )

    def test_roles_and_sha_are_stored_in_model_overrides(self):
        result = self._create(class_roles=WIZARD_ROLES, class_roles_weight_sha256="abc")

        assert result["success"] is True
        overrides = self.pm.project_data["model_overrides"]
        assert overrides["class_roles"] == WIZARD_ROLES
        assert overrides["class_roles_weight_sha256"] == "abc"
        self.pm.save_project.assert_called()

    def test_roles_never_reach_create_new_project(self):
        self._create(class_roles=WIZARD_ROLES, class_roles_weight_sha256="abc")

        kwargs = self.pm.create_new_project.call_args.kwargs
        assert "class_roles" not in kwargs
        assert "class_roles_weight_sha256" not in kwargs

    def test_untouched_section_stores_nothing(self):
        self._create(class_roles=None, class_roles_weight_sha256=None)

        overrides = self.pm.project_data.get("model_overrides") or {}
        assert overrides.get("class_roles") is None

    def test_roles_without_sha_are_dropped(self):
        roles, sha = ProjectWorkflowService._build_initial_class_roles(WIZARD_ROLES, None)
        assert (roles, sha) == (None, None)
        assert ProjectWorkflowService._build_initial_class_roles(WIZARD_ROLES, "") == (None, None)

    def test_invalid_roles_are_dropped(self):
        assert ProjectWorkflowService._build_initial_class_roles({"rat": "boss"}, "abc") == (
            None,
            None,
        )

    def test_valid_roles_are_normalised(self):
        roles, sha = ProjectWorkflowService._build_initial_class_roles(
            {"Lab Rat": "subject"}, "abc"
        )
        assert roles == {"lab_rat": "subject"}
        assert sha == "abc"

    def test_persist_writes_roles_only_with_their_sha(self):
        self.pm.project_data = {}
        self.service._persist_initial_project_overrides(
            None, None, class_roles=WIZARD_ROLES, class_roles_weight_sha256=None
        )
        assert self.pm.project_data == {}

        self.service._persist_initial_project_overrides(
            None, None, class_roles=WIZARD_ROLES, class_roles_weight_sha256="abc"
        )
        assert self.pm.project_data["model_overrides"]["class_roles"] == WIZARD_ROLES


@pytest.fixture
def service() -> ProjectWorkflowService:
    return ProjectWorkflowService(
        project_manager=Mock(),
        model_service=Mock(),
        state_manager=Mock(),
        ui_coordinator=None,
    )


# ---------------------------------------------------------------------------
# _build_initial_slot_weights
# ---------------------------------------------------------------------------


def test_build_initial_slot_weights_emits_4slot_keys_for_animal_and_aquarium(
    service: ProjectWorkflowService,
) -> None:
    slot_weights = service._build_initial_slot_weights(
        weight_assignments={"aquarium": "tank.pt", "animal": "fish.pt"},
        animal_method="det",
        aquarium_method="seg",
    )

    assert slot_weights == {"det:zebrafish": "fish.pt", "seg:aquarium": "tank.pt"}


def test_build_initial_slot_weights_skips_missing_entries(
    service: ProjectWorkflowService,
) -> None:
    slot_weights = service._build_initial_slot_weights(
        weight_assignments={"aquarium": None, "animal": "fish.pt"},
        animal_method="det",
        aquarium_method="seg",
    )

    assert slot_weights == {"det:zebrafish": "fish.pt"}


def test_build_initial_slot_weights_handles_invalid_methods(
    service: ProjectWorkflowService,
) -> None:
    """Bad method names should not produce slot keys with garbage."""
    slot_weights = service._build_initial_slot_weights(
        weight_assignments={"aquarium": "tank.pt", "animal": "fish.pt"},
        animal_method="bogus",
        aquarium_method=None,
    )

    assert slot_weights == {}


def test_build_initial_slot_weights_returns_empty_for_non_dict_input(
    service: ProjectWorkflowService,
) -> None:
    assert (
        service._build_initial_slot_weights(
            weight_assignments=None,
            animal_method="det",
            aquarium_method="seg",
        )
        == {}
    )


# ---------------------------------------------------------------------------
# _build_detector_hyperparam_overrides
# ---------------------------------------------------------------------------


def test_build_detector_hyperparam_overrides_keeps_in_band_values(
    service: ProjectWorkflowService,
) -> None:
    overrides = service._build_detector_hyperparam_overrides(
        {
            "confidence_threshold": 0.35,
            "nms_threshold": 0.55,
            "ignored_extra_field": "should-not-leak",
        }
    )

    assert overrides == {"confidence_threshold": 0.35, "nms_threshold": 0.55}


def test_build_detector_hyperparam_overrides_drops_out_of_range(
    service: ProjectWorkflowService,
) -> None:
    overrides = service._build_detector_hyperparam_overrides(
        {"confidence_threshold": 1.5, "nms_threshold": -0.1}
    )

    assert overrides == {}


def test_build_detector_hyperparam_overrides_handles_string_floats(
    service: ProjectWorkflowService,
) -> None:
    overrides = service._build_detector_hyperparam_overrides(
        {"confidence_threshold": "0.4", "nms_threshold": "abc"}
    )

    assert overrides == {"confidence_threshold": 0.4}


def test_build_detector_hyperparam_overrides_returns_empty_for_non_dict(
    service: ProjectWorkflowService,
) -> None:
    assert service._build_detector_hyperparam_overrides(None) == {}
    assert service._build_detector_hyperparam_overrides("not-a-dict") == {}


# ---------------------------------------------------------------------------
# _persist_initial_project_overrides
# ---------------------------------------------------------------------------


def test_persist_initial_project_overrides_writes_slot_weights_and_hyperparams(
    service: ProjectWorkflowService,
) -> None:
    project_data: dict = {}
    service.project_manager.project_data = project_data
    service.project_manager.project_path = "/tmp/p"

    service._persist_initial_project_overrides(
        slot_weights={"det:zebrafish": "fish.pt", "seg:aquarium": "tank.pt"},
        detector_hyperparams={"confidence_threshold": 0.4, "nms_threshold": 0.5},
    )

    overrides = project_data["model_overrides"]
    assert overrides["slot_weights"] == {
        "det:zebrafish": "fish.pt",
        "seg:aquarium": "tank.pt",
    }
    assert overrides["confidence_threshold"] == 0.4
    assert overrides["nms_threshold"] == 0.5
    service.project_manager.save_project.assert_called_once()


def test_persist_initial_project_overrides_no_op_when_inputs_empty(
    service: ProjectWorkflowService,
) -> None:
    service.project_manager.project_data = {}
    service.project_manager.project_path = "/tmp/p"

    service._persist_initial_project_overrides(
        slot_weights={},
        detector_hyperparams={},
    )

    # Nothing to persist → save_project not called
    service.project_manager.save_project.assert_not_called()


def test_persist_initial_project_overrides_skips_when_no_project_path(
    service: ProjectWorkflowService,
) -> None:
    project_data: dict = {}
    service.project_manager.project_data = project_data
    service.project_manager.project_path = None

    service._persist_initial_project_overrides(
        slot_weights={"det:zebrafish": "fish.pt"},
        detector_hyperparams=None,
    )

    # Slot weights still mutate the in-memory record but no save is triggered
    # (no project on disk to write to).
    assert project_data["model_overrides"]["slot_weights"] == {"det:zebrafish": "fish.pt"}
    service.project_manager.save_project.assert_not_called()


class TestProjectWorkflowServiceExtended:
    @pytest.fixture
    def mock_deps(self) -> tuple[MagicMock, MagicMock, MagicMock]:
        pm = MagicMock()
        pm.project_data = {}
        pm.project_path = None
        ms = MagicMock()
        ms.get_all_weight_names.return_value = ["best_seg.pt", "best_det.pt"]
        ms.is_openvino_ready.return_value = True
        ms.get_default_weight.return_value = "best_seg.pt"
        sm = MagicMock()
        return pm, ms, sm

    @pytest.fixture
    def workflow_service(
        self, mock_deps: tuple[MagicMock, MagicMock, MagicMock]
    ) -> ProjectWorkflowService:
        pm, ms, sm = mock_deps
        return ProjectWorkflowService(
            project_manager=pm,
            model_service=ms,
            state_manager=sm,
        )

    def test_validate_project_parameters_detection_mode_single_animal(
        self, workflow_service: ProjectWorkflowService
    ):
        is_valid, msg = workflow_service.validate_project_parameters(
            animal_method="det", animals_per_aquarium=1
        )
        assert is_valid is True
        assert msg is None

    def test_validate_project_parameters_detection_mode_multi_animal_invalid(
        self, workflow_service: ProjectWorkflowService
    ):
        is_valid, msg = workflow_service.validate_project_parameters(
            animal_method="det", animals_per_aquarium=2
        )
        assert is_valid is False
        assert msg is not None
        assert "compatible with 1 animal" in msg

    def test_validate_project_parameters_segmentation_mode_multi_animal_valid(
        self, workflow_service: ProjectWorkflowService
    ):
        is_valid, msg = workflow_service.validate_project_parameters(
            animal_method="seg", animals_per_aquarium=4
        )
        assert is_valid is True
        assert msg is None

    def test_prepare_controller_parameters_whitelist(
        self, workflow_service: ProjectWorkflowService
    ):
        raw_params = {
            "project_path": "/path/to/proj",
            "project_type": "single",
            "num_aquariums": 1,
            "animals_per_aquarium": 1,
            "_wizard_metadata": {"step": 2},
            "unauthorized_key": "injected_val",
            "another_random_key": 999,
        }
        filtered = workflow_service.prepare_controller_parameters(**raw_params)
        assert "project_path" in filtered
        assert "project_type" in filtered
        assert "num_aquariums" in filtered
        assert "_wizard_metadata" in filtered
        assert "unauthorized_key" not in filtered
        assert "another_random_key" not in filtered

    def test_set_global_model_defaults(self, workflow_service: ProjectWorkflowService):
        workflow_service.set_global_model_defaults("custom_model.pt", use_openvino=True)
        assert workflow_service._global_model_defaults["active_weight"] == "custom_model.pt"
        assert workflow_service._global_model_defaults["use_openvino"] is True

    def test_normalize_weight_name(self):
        assert ProjectWorkflowService._normalize_weight_name("") is None
        assert ProjectWorkflowService._normalize_weight_name("   ") is None
        assert ProjectWorkflowService._normalize_weight_name(None) is None
        assert ProjectWorkflowService._normalize_weight_name("yolov8n.pt") == "yolov8n.pt"
        assert ProjectWorkflowService._normalize_weight_name("None") == "None"

    def test_normalize_openvino_override(self):
        assert ProjectWorkflowService._normalize_openvino_override(None) is None
        assert ProjectWorkflowService._normalize_openvino_override(True) is True
        assert ProjectWorkflowService._normalize_openvino_override(False) is False
        assert ProjectWorkflowService._normalize_openvino_override("True") is True
        assert ProjectWorkflowService._normalize_openvino_override("1") is True
        assert ProjectWorkflowService._normalize_openvino_override("false") is False
        assert ProjectWorkflowService._normalize_openvino_override("0") is False

    def test_resolve_openvino_device(self, workflow_service: ProjectWorkflowService):
        assert workflow_service._resolve_openvino_device({"device": "CPU"}) == "CPU"
        assert workflow_service._resolve_openvino_device({"device": "GPU"}) == "GPU"
        assert workflow_service._resolve_openvino_device({"device": "NPU"}) == "NPU"
        assert workflow_service._resolve_openvino_device({"device": "INVALID"}) == "AUTO"
        assert workflow_service._resolve_openvino_device(None) == "AUTO"

    def test_resolve_project_model_settings_explicit_override(
        self,
        workflow_service: ProjectWorkflowService,
        mock_deps: tuple[MagicMock, MagicMock, MagicMock],
    ):
        pm, ms, sm = mock_deps
        overrides = {"active_weight": "best_det.pt", "use_openvino": True}
        weight, use_ov = workflow_service.resolve_project_model_settings(overrides=overrides)
        assert weight == "best_det.pt"
        assert use_ov is True

    def test_resolve_project_model_settings_fallback_to_global_defaults(
        self,
        workflow_service: ProjectWorkflowService,
        mock_deps: tuple[MagicMock, MagicMock, MagicMock],
    ):
        pm, ms, sm = mock_deps
        workflow_service.set_global_model_defaults("best_seg.pt", use_openvino=False)
        weight, use_ov = workflow_service.resolve_project_model_settings(overrides=None)
        assert weight == "best_seg.pt"
        assert use_ov is False

    def test_slot_key_formatting(self):
        key = ProjectWorkflowService._slot_key("seg", "zebrafish")
        assert key == "seg:zebrafish"

    def test_save_project_model_slot_overrides_without_project_path(
        self, workflow_service: ProjectWorkflowService
    ):
        workflow_service.set_global_model_defaults("best_seg.pt", use_openvino=False)
        weight, use_ov = workflow_service.save_project_model_slot_overrides(
            slot_weights={"seg:zebrafish": "best_seg.pt"},
            use_openvino_override=True,
        )
        assert weight == "best_seg.pt"
        assert use_ov is True

    def test_save_project_model_slot_overrides_with_active_project(
        self,
        workflow_service: ProjectWorkflowService,
        mock_deps: tuple[MagicMock, MagicMock, MagicMock],
    ):
        pm, ms, sm = mock_deps
        pm.project_path = "/path/to/project"
        pm.project_data = {"animal_method": "seg"}

        active_setter = MagicMock()
        ov_setter = MagicMock()

        weight, use_ov = workflow_service.save_project_model_slot_overrides(
            slot_weights={"seg:zebrafish": "best_seg.pt"},
            use_openvino_override=True,
            active_weight_setter=active_setter,
            use_openvino_setter=ov_setter,
        )
        assert weight == "best_seg.pt"
        assert use_ov is True
        active_setter.assert_called_with("best_seg.pt")
        ov_setter.assert_called_with(True)
        pm.save_project.assert_called()

    def test_create_project_validation_failure(self, workflow_service: ProjectWorkflowService):
        res = workflow_service.create_project(
            project_path="/tmp/test",
            animal_method="det",
            animals_per_aquarium=3,
        )
        assert res["success"] is False
        assert "compatible with 1 animal" in str(res["error_message"])


class TestProjectWorkflowServiceExtended2:
    def test_constants(self):
        assert "CPU" in _VALID_OPENVINO_DEVICES
        assert "GPU" in _VALID_OPENVINO_DEVICES
        assert "AUTO" in _VALID_OPENVINO_DEVICES
        assert "NPU" in _VALID_OPENVINO_DEVICES
        assert ProjectWorkflowService._SLOT_SEPARATOR == ":"

    def test_set_global_model_defaults(self):
        svc = ProjectWorkflowService(
            project_manager=MagicMock(),
            model_service=MagicMock(),
            state_manager=MagicMock(),
        )

        svc.set_global_model_defaults("best_seg.pt", True)
        assert svc._global_model_defaults == {
            "active_weight": "best_seg.pt",
            "use_openvino": True,
        }

    def test_validate_project_parameters_det_with_multiple_animals_fails(self):
        svc = ProjectWorkflowService(
            project_manager=MagicMock(),
            model_service=MagicMock(),
            state_manager=MagicMock(),
        )

        is_valid, msg = svc.validate_project_parameters(
            animal_method="det",
            animals_per_aquarium=2,
        )
        assert is_valid is False
        assert msg is not None
        assert "compatible with 1 animal" in msg or "compatível com 1 animal" in msg

    def test_validate_project_parameters_valid_configs(self):
        svc = ProjectWorkflowService(
            project_manager=MagicMock(),
            model_service=MagicMock(),
            state_manager=MagicMock(),
        )

        # Single animal + det
        is_valid, msg = svc.validate_project_parameters(
            animal_method="det",
            animals_per_aquarium=1,
        )
        assert is_valid is True
        assert msg is None

        # Multi animal + seg
        is_valid_seg, msg_seg = svc.validate_project_parameters(
            animal_method="seg",
            animals_per_aquarium=4,
        )
        assert is_valid_seg is True
        assert msg_seg is None

    def test_prepare_controller_parameters_filters_unwanted_keys(self):
        svc = ProjectWorkflowService(
            project_manager=MagicMock(),
            model_service=MagicMock(),
            state_manager=MagicMock(),
        )

        raw = {
            "project_path": "/path/proj",
            "num_aquariums": 2,
            "arbitrary_garbage_key": 12345,
            "another_random_field": "hello",
        }

        filtered = svc.prepare_controller_parameters(**raw)
        assert "project_path" in filtered
        assert "num_aquariums" in filtered
        assert "arbitrary_garbage_key" not in filtered
        assert "another_random_field" not in filtered


class TestProjectWorkflowServiceExtended3:
    def test_normalize_weight_name(self):
        assert ProjectWorkflowService._normalize_weight_name("weight.pt") == "weight.pt"
        assert ProjectWorkflowService._normalize_weight_name("  ") is None
        assert ProjectWorkflowService._normalize_weight_name(None) is None

    def test_normalize_openvino_override(self):
        assert ProjectWorkflowService._normalize_openvino_override(True) is True
        assert ProjectWorkflowService._normalize_openvino_override(False) is False
        assert ProjectWorkflowService._normalize_openvino_override("true") is True
        assert ProjectWorkflowService._normalize_openvino_override("0") is False
        assert ProjectWorkflowService._normalize_openvino_override(None) is None

    def test_normalize_slot_weights_tuple_and_string_keys(self):
        raw = {
            ("seg", "zebrafish"): "seg_fish.pt",
            "det:aquarium": "det_aq.pt",
            "invalid_key": "junk.pt",
        }
        svc = object.__new__(ProjectWorkflowService)
        normalized = svc._normalize_slot_weights(raw)
        assert normalized["seg:zebrafish"] == "seg_fish.pt"
        assert normalized["det:aquarium"] == "det_aq.pt"
        assert "invalid_key" not in normalized

    def test_normalize_slot_weights_invalid_input(self):
        svc = object.__new__(ProjectWorkflowService)
        assert svc._normalize_slot_weights(None) == {}
        assert svc._normalize_slot_weights([]) == {}

    def test_normalize_openvino_override_case_insensitive(self):
        assert ProjectWorkflowService._normalize_openvino_override("TRUE") is True
        assert ProjectWorkflowService._normalize_openvino_override("False") is False
        assert ProjectWorkflowService._normalize_openvino_override("inherit") is None


class TestProjectWorkflowServiceExtended4:
    def test_build_initial_slot_weights_valid(self):
        svc = object.__new__(ProjectWorkflowService)
        raw_assignments = {
            "animal": "yolov8n_fish.pt",
            "aquarium": "yolov8n_aq.pt",
        }
        res = svc._build_initial_slot_weights(
            weight_assignments=raw_assignments,
            animal_method="det",
            aquarium_method="seg",
        )
        assert res["det:zebrafish"] == "yolov8n_fish.pt"
        assert res["seg:aquarium"] == "yolov8n_aq.pt"

    def test_build_initial_slot_weights_invalid_input(self):
        svc = object.__new__(ProjectWorkflowService)
        assert (
            svc._build_initial_slot_weights(
                weight_assignments=None,
                animal_method="det",
                aquarium_method="seg",
            )
            == {}
        )

    def test_build_detector_hyperparam_overrides(self):
        svc = object.__new__(ProjectWorkflowService)
        params = {
            "confidence_threshold": 0.35,
            "nms_threshold": 0.45,
            "unsupported_param": 100,
        }
        overrides = svc._build_detector_hyperparam_overrides(params)
        assert overrides["confidence_threshold"] == 0.35
        assert overrides["nms_threshold"] == 0.45
        assert "unsupported_param" not in overrides

    def test_build_detector_hyperparam_overrides_invalid_type(self):
        svc = object.__new__(ProjectWorkflowService)
        assert svc._build_detector_hyperparam_overrides(None) == {}
        assert svc._build_detector_hyperparam_overrides("string") == {}


class TestProjectWorkflowServiceExtended5:
    def test_persist_initial_project_overrides_empty(self):
        svc = object.__new__(ProjectWorkflowService)
        svc.project_manager = MagicMock()
        # With empty args, returns without modifying project data
        svc._persist_initial_project_overrides(None, None)
        svc.project_manager.save_project.assert_not_called()

    def test_persist_initial_project_overrides_updates_and_saves(self):
        svc = object.__new__(ProjectWorkflowService)
        svc.project_manager = MagicMock()
        svc.project_manager.project_path = "/path/to/project.zeb"
        svc.project_manager.project_data = {}

        slot_weights = {"det:zebrafish": "fish_v8.pt"}
        hyperparams = {"confidence_threshold": 0.40}

        svc._persist_initial_project_overrides(slot_weights, hyperparams)

        overrides = svc.project_manager.project_data["model_overrides"]
        assert overrides["slot_weights"]["det:zebrafish"] == "fish_v8.pt"
        assert overrides["confidence_threshold"] == 0.40
        svc.project_manager.save_project.assert_called_once()

    def test_persist_initial_project_overrides_no_changes(self):
        svc = object.__new__(ProjectWorkflowService)
        svc.project_manager = MagicMock()
        svc.project_manager.project_path = "/path/to/project.zeb"
        svc.project_manager.project_data = {
            "model_overrides": {
                "slot_weights": {"det:zebrafish": "fish_v8.pt"},
                "confidence_threshold": 0.40,
            }
        }

        # Passing identical overrides should not trigger save_project
        svc._persist_initial_project_overrides(
            {"det:zebrafish": "fish_v8.pt"},
            {"confidence_threshold": 0.40},
        )
        svc.project_manager.save_project.assert_not_called()

    def test_normalize_weight_name(self):
        assert ProjectWorkflowService._normalize_weight_name("  model.pt  ") == "model.pt"
        assert ProjectWorkflowService._normalize_weight_name("") is None
        assert ProjectWorkflowService._normalize_weight_name("   ") is None
        assert ProjectWorkflowService._normalize_weight_name(123) is None

    def test_normalize_openvino_override(self):
        assert ProjectWorkflowService._normalize_openvino_override("true") is True
        assert ProjectWorkflowService._normalize_openvino_override("1") is True
        assert ProjectWorkflowService._normalize_openvino_override("yes") is True
        assert ProjectWorkflowService._normalize_openvino_override("false") is False
        assert ProjectWorkflowService._normalize_openvino_override("0") is False
        assert ProjectWorkflowService._normalize_openvino_override("auto") is None
        assert ProjectWorkflowService._normalize_openvino_override("inherit") is None
        assert ProjectWorkflowService._normalize_openvino_override(None) is None

    def test_normalize_slot_weights(self):
        svc = object.__new__(ProjectWorkflowService)
        raw = {
            ("det", "zebrafish"): " fish.pt ",
            "seg:aquarium": "aq.pt",
            "invalid_key": "bad.pt",
            ("det", "invalid_target"): "bad2.pt",
        }
        normalized = svc._normalize_slot_weights(raw)
        assert normalized["det:zebrafish"] == "fish.pt"
        assert normalized["seg:aquarium"] == "aq.pt"
        assert "invalid_key" not in normalized


class TestProjectWorkflowServiceExtended6:
    def test_get_default_weight_name_tuple(self):
        svc = object.__new__(ProjectWorkflowService)
        svc.model_service = MagicMock()
        svc.model_service.get_default_weight.return_value = ("model_v8.pt", {"type": "det"})

        assert svc._get_default_weight_name() == "model_v8.pt"

    def test_get_default_weight_name_none(self):
        svc = object.__new__(ProjectWorkflowService)
        svc.model_service = MagicMock()
        svc.model_service.get_default_weight.return_value = None

        assert svc._get_default_weight_name() is None

    def test_set_runtime_slot_overrides(self):
        svc = object.__new__(ProjectWorkflowService)
        svc._SLOT_SEPARATOR = ":"
        svc.model_service = MagicMock()
        weight_manager = MagicMock()
        svc.model_service.weight_manager = weight_manager

        slot_weights = {"det:zebrafish": "fish_v8.pt", "seg:aquarium": "aq_v8.pt"}
        svc._set_runtime_slot_overrides(slot_weights)

        weight_manager.set_runtime_slot_overrides.assert_called_once_with(
            {("det", "zebrafish"): "fish_v8.pt", ("seg", "aquarium"): "aq_v8.pt"}
        )

    def test_normalize_openvino_override_strings(self):
        assert ProjectWorkflowService._normalize_openvino_override("inherit") is None
        assert ProjectWorkflowService._normalize_openvino_override("auto") is None
        assert ProjectWorkflowService._normalize_openvino_override("") is None
        assert ProjectWorkflowService._normalize_openvino_override("true") is True
        assert ProjectWorkflowService._normalize_openvino_override("1") is True
        assert ProjectWorkflowService._normalize_openvino_override("yes") is True
        assert ProjectWorkflowService._normalize_openvino_override("false") is False
        assert ProjectWorkflowService._normalize_openvino_override("0") is False
        assert ProjectWorkflowService._normalize_openvino_override("no") is False
        assert ProjectWorkflowService._normalize_openvino_override(None) is None
        assert ProjectWorkflowService._normalize_openvino_override(True) is True
        assert ProjectWorkflowService._normalize_openvino_override(False) is False

    def test_resolve_slot_weights_from_overrides_empty(self, monkeypatch: pytest.MonkeyPatch):
        svc = object.__new__(ProjectWorkflowService)
        monkeypatch.setattr(svc, "_normalize_slot_weights", lambda val: {})
        monkeypatch.setattr(svc, "_normalize_weight_name", lambda val: None)
        monkeypatch.setattr(svc, "_get_legacy_animal_slot_key", lambda val: None)

        res = svc._resolve_slot_weights_from_overrides({})
        assert res == {}

    def test_resolve_slot_weights_from_overrides_with_legacy_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        svc = object.__new__(ProjectWorkflowService)
        monkeypatch.setattr(svc, "_normalize_slot_weights", lambda val: {})
        monkeypatch.setattr(svc, "_normalize_weight_name", lambda val: "legacy_fish.pt")
        monkeypatch.setattr(svc, "_get_legacy_animal_slot_key", lambda val: "det:zebrafish")

        res = svc._resolve_slot_weights_from_overrides({"active_weight": "legacy_fish.pt"})
        assert res == {"det:zebrafish": "legacy_fish.pt"}


class TestProjectWorkflowServiceExtended7:
    def test_normalize_weight_name_none_or_blank(self):
        assert ProjectWorkflowService._normalize_weight_name(None) is None
        assert ProjectWorkflowService._normalize_weight_name("") is None
        assert ProjectWorkflowService._normalize_weight_name("   ") is None
        assert ProjectWorkflowService._normalize_weight_name("  model.pt  ") == "model.pt"

    def test_normalize_openvino_override_values(self):
        assert ProjectWorkflowService._normalize_openvino_override(None) is None
        assert ProjectWorkflowService._normalize_openvino_override("auto") is None
        assert ProjectWorkflowService._normalize_openvino_override("inherit") is None
        assert ProjectWorkflowService._normalize_openvino_override("") is None
        assert ProjectWorkflowService._normalize_openvino_override("true") is True
        assert ProjectWorkflowService._normalize_openvino_override("1") is True
        assert ProjectWorkflowService._normalize_openvino_override("false") is False

    def test_normalize_slot_weights_none(self):
        pws: Any = object.__new__(ProjectWorkflowService)
        assert pws._normalize_slot_weights(None) == {}
        assert pws._normalize_slot_weights("not_a_dict") == {}

    def test_get_legacy_animal_slot_key_none(self):
        pws: Any = object.__new__(ProjectWorkflowService)
        pws._get_project_slot_pairs = lambda: []

        key = pws._get_legacy_animal_slot_key(None)
        assert key is None


class TestProjectWorkflowServiceExtended8:
    def test_slot_key_formatting(self):
        key = ProjectWorkflowService._slot_key("det", "zebrafish")
        assert key == "det:zebrafish"

        key2 = ProjectWorkflowService._slot_key("seg", "aquarium")
        assert key2 == "seg:aquarium"

    def test_slot_separator_constant(self):
        assert ProjectWorkflowService._SLOT_SEPARATOR == ":"

    def test_slot_key_empty_inputs(self):
        assert ProjectWorkflowService._slot_key("", "") == ":"
        assert ProjectWorkflowService._slot_key("det", "") == "det:"

    def test_slot_key_custom_labels(self):
        res = ProjectWorkflowService._slot_key("segmentation", "subject_01")
        assert res == "segmentation:subject_01"


class TestProjectWorkflowServiceExtended9:
    def test_slot_separator_constant(self):
        assert ProjectWorkflowService._SLOT_SEPARATOR == ":"

    def test_valid_openvino_devices_tuple(self):
        assert "AUTO" in _VALID_OPENVINO_DEVICES
        assert "CPU" in _VALID_OPENVINO_DEVICES
        assert "GPU" in _VALID_OPENVINO_DEVICES
        assert "NPU" in _VALID_OPENVINO_DEVICES


class TestOpenProjectZoneSetup:
    """Opening a project must APPLY its zones — including "it has none".

    The callback used to be gated on the opened project already having an arena
    or ROIs, with no ``else``. A project without zones therefore left the
    detector configured with whatever the previous session installed, most
    damagingly an ad-hoc single-video run.
    """

    @pytest.fixture
    def service(self) -> ProjectWorkflowService:
        pm = MagicMock()
        pm.project_data = {}
        pm.project_path = None
        pm.get_detector_state.return_value = None
        pm.get_project_name.return_value = "Experiment"
        pm.get_all_videos.return_value = []
        pm.get_active_zone_video.return_value = None
        ms = MagicMock()
        ms.get_all_weight_names.return_value = ["best_seg.pt"]
        ms.is_openvino_ready.return_value = True
        ms.get_default_weight.return_value = "best_seg.pt"
        return ProjectWorkflowService(
            project_manager=pm, model_service=ms, state_manager=MagicMock()
        )

    @staticmethod
    def _zone_data(*, polygon=None, rois=None):
        zone = MagicMock()
        zone.polygon = polygon or []
        zone.roi_polygons = rois or []
        return zone

    def test_callback_runs_when_the_project_has_zones(self, service, tmp_path):
        service.project_manager.get_zone_data.return_value = self._zone_data(
            polygon=[[0, 0], [1, 0], [1, 1], [0, 1]]
        )
        setup_zones = MagicMock()

        result = service.open_project(tmp_path, setup_zones_callback=setup_zones)

        assert result["success"] is True
        setup_zones.assert_called_once()

    def test_callback_still_runs_when_the_project_has_no_zones(self, service, tmp_path):
        """ "No zones" must actively CLEAR, not skip the step."""
        service.project_manager.get_zone_data.return_value = self._zone_data()
        setup_zones = MagicMock()

        result = service.open_project(tmp_path, setup_zones_callback=setup_zones)

        assert result["success"] is True
        setup_zones.assert_called_once()
        assert result["project_info"]["zone_status"] == "✗"


# ---------------------------------------------------------------------------
# TASK-087: wizard enrichment, model resolution and creation side effects,
# driven with small fakes and a real ProjectManager on tmp_path.
# ---------------------------------------------------------------------------


class _FakeWeightManager:
    def __init__(self, defaults: dict[tuple[str, str], str | None]):
        self.defaults = defaults
        self.runtime: dict | None = None

    def get_default_weight_for(self, method: str, target: str):
        return self.defaults.get((method, target)), {}

    def set_runtime_slot_overrides(self, overrides: dict) -> None:
        self.runtime = dict(overrides)


class _FakeModelService:
    def __init__(self, weights=("a.pt", "b.pt"), ready=(), default="a.pt", weight_manager=None):
        self.weights = list(weights)
        self.ready = set(ready)
        self.default = default
        self.weight_manager = weight_manager

    def get_all_weight_names(self):
        return list(self.weights)

    def is_openvino_ready(self, name):
        return name in self.ready

    def get_default_weight(self):
        return (self.default, {}) if self.default else None


class _FakeState:
    def __init__(self):
        self.updates: list[dict] = []

    def update_project_state(self, **kwargs):
        self.updates.append(kwargs)


def _service(project_manager=None, model_service=None, settings=None) -> ProjectWorkflowService:
    return ProjectWorkflowService(
        project_manager=project_manager or SimpleNamespace(project_data={}, project_path=None),
        model_service=model_service or _FakeModelService(),
        state_manager=_FakeState(),
        settings_obj=settings,
    )


def _real_pm(tmp_path, **project_fields):
    from zebtrack.core.project.project_manager import ProjectManager

    pm = ProjectManager(settings_obj=None)
    pm.create_new_project(tmp_path / "proj", "Pre-recorded")
    pm.project_data.update(project_fields)
    pm.save_project()
    return pm


class TestNormalisers:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(None, None), ("  ", None), ("subject07", "S07"), (" s 3", "S03"), ("abc", "abc")],
    )
    def test_subject_id(self, raw, expected):
        assert _service()._normalise_subject_id(raw) == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (None, None),
            ("", None),
            ("   ", None),
            (3, "03"),
            (2.0, "02"),
            (True, "True"),
            ("SEM DIA", "Sem Dia"),
            ("Dia 7", "07"),
            ("Final", "Final"),
        ],
    )
    def test_day_label(self, raw, expected):
        assert _service()._normalise_day_label(raw) == expected

    def test_pattern_prefers_the_explicit_one_and_escapes_values(self):
        service = _service()

        assert service._build_pattern("X(\\d)", ["a"]) == "X(\\d)"
        assert service._build_pattern(None, ["G.1", "", 3, "B"]) == "(G\\.1|B)"
        assert service._build_pattern(None, []) is None

    def test_design_lookups(self):
        groups, days, subjects = _service()._build_design_lookups(
            ["Ctrl", 5], ["Day02", "Final"], {"Ctrl": ["S1", None], "Bad": "S2"}
        )

        assert groups == {"ctrl": "Ctrl"}
        assert days == {"day02": "Day02", "final": "Final", "02": "Day02"}
        assert subjects == {"Ctrl": {"s1": "S1"}}


class TestEnrichVideos:
    DESIGN: ClassVar[dict[str, Any]] = {
        "groups": ["Controle", "Tratamento"],
        "days": ["Day02", "Day03"],
        "subjects_per_group": {"Controle": ["S01", "S02"], "Tratamento": ["rato7"]},
    }

    def test_without_design_the_videos_are_copied_unchanged(self):
        videos = [{"path": "a.mp4", "metadata": {"x": 1}}]

        result = _service()._enrich_videos_with_design_metadata(videos, None)

        assert result == videos and result[0] is not videos[0]
        assert _service()._enrich_videos_with_design_metadata([], self.DESIGN) == []

    def test_group_day_and_subject_are_read_from_the_path(self):
        videos = [{"path": "C:/data/controle/day03/S02_video.mp4"}]

        (video,) = _service()._enrich_videos_with_design_metadata(
            videos, self.DESIGN, group_display_names={"controle": "Grupo Controle"}
        )

        assert video["metadata"] == {
            "group": "Controle",
            "group_display_name": "Grupo Controle",
            "day": "Day03",
            "day_label": "03",
            "subject": "S02",
        }
        assert (video["group"], video["day"], video["subject"]) == ("Controle", "Day03", "S02")
        assert "metadata" not in videos[0]

    def test_numeric_day_capture_and_subject_found_by_name(self):
        videos = [{"path": "C:/x/Tratamento_D3_rato7.mp4"}]
        patterns = {"day_pattern": "D(\\d+)", "subject_pattern": "Z(\\d+)"}

        (video,) = _service()._enrich_videos_with_design_metadata(videos, self.DESIGN, patterns)

        assert (video["group"], video["day"], video["subject"]) == ("Tratamento", "Day03", "rato7")
        assert video["group_display_name"] == "Tratamento"

    def test_values_already_present_are_kept(self):
        videos = [{"path": "C:/controle/day02/S01.mp4", "metadata": {"group": "Outro", "day": 9}}]

        (video,) = _service()._enrich_videos_with_design_metadata(videos, self.DESIGN)

        assert (video["metadata"]["group"], video["metadata"]["day"]) == ("Outro", 9)
        assert video["metadata"]["day_label"] == "09"

    def test_multi_subject_mapping_found_through_a_windows_key(self):
        path = "C:/v/G1_D1_S1--G1_D1_S2.mp4"
        entries = [
            {"group": "G1", "day": "1", "subject": "1"},
            {"group": "G1", "day": "1", "subject": "2"},
        ]
        design = {**self.DESIGN, "subject_mappings": {"C:\\v\\G1_D1_S1--G1_D1_S2.mp4": entries}}

        (video,) = _service()._enrich_videos_with_design_metadata(
            [{"path": path, "subject": "old", "metadata": {"subject": "old"}}],
            design,
            group_display_names={"G1": "Grupo 1"},
        )

        assert video["is_multi_subject"] is True
        assert video["subject_entries"] == entries
        assert video["subject"] is None and "subject" not in video["metadata"]
        assert (video["group"], video["group_display_name"], video["day"]) == ("G1", "Grupo 1", "1")

    def test_single_subject_mapping(self):
        design = {
            **self.DESIGN,
            "subject_mappings": {"C:/v/a.mp4": [{"group": "G2", "day": "4", "subject": "9"}]},
        }

        (video,) = _service()._enrich_videos_with_design_metadata([{"path": "C:/v/a.mp4"}], design)

        assert video["metadata"] == {"group": "G2", "day": "4", "subject": "9"}
        assert "is_multi_subject" not in video

    def test_regex_fallback_finds_every_subject_in_the_file_name(self):
        patterns = {
            "group_pattern": "G(\\d+)",
            "day_pattern": "D(\\d+)",
            "subject_pattern": "S(\\d+)",
        }

        (video,) = _service()._enrich_videos_with_design_metadata(
            [{"path": "C:/v/G1_D2_S3--G1_D2_S4.mp4"}], self.DESIGN, patterns
        )

        assert video["subject_entries"] == [
            {"group": "1", "subject": "3", "day": "2"},
            {"group": "1", "subject": "4", "day": "2"},
        ]


class TestPrepareProjectInput:
    def test_design_counts_weights_and_device_are_derived(self):
        kwargs, context = _service()._prepare_project_input(
            project_type="experimental",
            animals_per_aquarium=2,
            detected_design={
                "groups": ["A", "B", "C"],
                "days": ["D1", "D2"],
                "subjects_per_group": {"A": ["1", "2", "3"], "B": ["1"], "C": []},
            },
            weight_assignments={"animal": " rat.pt ", "aquarium": "arena.pt"},
            animal_method="seg",
            aquarium_method="det",
            model_selection={"openvino_device": "gpu"},
            class_roles={"rat": "subject"},
        )

        assert kwargs["project_type"] == "pre-recorded"
        assert (kwargs["num_groups"], kwargs["group_names"]) == (3, ["A", "B", "C"])
        assert (kwargs["experiment_days"], kwargs["subjects_per_group"]) == (2, 3)
        assert kwargs["active_weight"] == " rat.pt "
        assert kwargs["openvino_device"] == "gpu"
        assert kwargs["use_single_subject_tracker"] is False
        assert context["initial_slot_weights"] == {
            "seg:zebrafish": "rat.pt",
            "det:aquarium": "arena.pt",
        }
        assert context["initial_class_roles"] == (None, None)

    def test_explicit_values_win_and_live_keeps_raw_scans(self):
        scans = [{"path": "C:/a.mp4", "has_arena": True}]
        kwargs, context = _service()._prepare_project_input(
            project_type="live",
            use_single_subject_tracker=0,
            num_groups=1,
            experiment_days=7,
            subjects_per_group=4,
            active_weight="mine.pt",
            weight_assignments={"animal": "rat.pt"},
            detected_design={"groups": ["A"], "days": ["D1"], "subjects_per_group": {"A": ["1"]}},
            scanned_videos=scans,
        )

        assert kwargs["project_type"] == "live"
        assert (kwargs["num_groups"], kwargs["experiment_days"]) == (1, 7)
        assert kwargs["subjects_per_group"] == 4
        assert kwargs["active_weight"] == "mine.pt"
        assert kwargs["use_single_subject_tracker"] is False
        assert "video_files" not in kwargs
        assert context["wizard_metadata"]["scanned_videos"] is scans

    def test_refused_import_clears_the_parquet_flags(self):
        kwargs, _context = _service()._prepare_project_input(
            scanned_videos=[{"path": "C:/a.mp4", "has_arena": True, "has_data": True}],
            parquet_import_scope=None,
        )

        (video,) = kwargs["video_files"]
        assert (video["has_arena"], video["has_data"], video["has_complete_data"]) == (
            False,
            False,
            False,
        )


class TestModelResolution:
    def test_missing_weight_falls_back_to_the_global_default(self, tmp_path):
        pm = _real_pm(tmp_path, model_overrides={"active_weight": "gone.pt", "slot_weights": {}})
        service = _service(pm, _FakeModelService(weights=["b.pt"]))
        service.set_global_model_defaults("b.pt", False)

        assert service.resolve_project_model_settings() == ("b.pt", False)

    def test_missing_weight_without_usable_global_uses_the_service_default(self, tmp_path):
        pm = _real_pm(tmp_path, model_overrides={"active_weight": "gone.pt"})
        service = _service(pm, _FakeModelService(weights=["a.pt"], default=None))

        assert service.resolve_project_model_settings() == (None, False)

    def test_openvino_follows_the_project_unless_not_converted(self, tmp_path):
        pm = _real_pm(tmp_path, use_openvino=True, model_overrides={"use_openvino": None})
        ready = _service(pm, _FakeModelService(ready=["a.pt"]))
        not_ready = _service(pm, _FakeModelService(ready=[]))

        assert ready.resolve_project_model_settings() == ("a.pt", True)
        assert not_ready.resolve_project_model_settings() == ("a.pt", False)
        assert ready.resolve_project_model_settings({"use_openvino": "off"}) == ("a.pt", False)

    def test_device_resolution_order(self, tmp_path):
        pm = _real_pm(tmp_path, model_overrides={"device": "bogus"}, openvino_device=" npu ")
        settings = SimpleNamespace(openvino=SimpleNamespace(device="gpu"))
        service = _service(pm, settings=settings)

        assert service._resolve_openvino_device() == "NPU"
        assert service._resolve_openvino_device({"device": " cpu"}) == "CPU"
        pm.project_data["openvino_device"] = 7
        assert service._resolve_openvino_device() == "GPU"
        settings.openvino.device = "tpu"
        assert service._resolve_openvino_device() == "AUTO"

    def test_apply_persists_resolved_values_and_syncs_settings(self, tmp_path):
        pm = _real_pm(tmp_path, model_overrides={"active_weight": "b.pt", "device": "cpu"})
        settings = SimpleNamespace(openvino=SimpleNamespace(device="AUTO", device_batch="AUTO"))
        weights = _FakeWeightManager({})
        service = _service(pm, _FakeModelService(weight_manager=weights), settings)
        applied: list = []

        result = service.apply_project_model_overrides(
            active_weight_setter=applied.append, use_openvino_setter=applied.append
        )

        assert result == ("b.pt", False)
        assert applied == ["b.pt", False]
        assert (settings.openvino.device, settings.openvino.device_batch) == ("CPU", "CPU")
        from zebtrack.core.project.project_manager import ProjectManager

        reloaded = ProjectManager(settings_obj=None)
        reloaded.load_project(pm.project_path)
        assert reloaded.project_data["active_weight"] == "b.pt"
        assert reloaded.project_data["model_overrides"]["device"] == "CPU"
        assert reloaded.project_data["openvino_device"] == "CPU"
        assert weights.runtime == {}

    def test_global_slot_weights_follow_the_project_methods(self, tmp_path):
        pm = _real_pm(tmp_path, model_selection={"animal_method": "seg", "aquarium_method": "det"})
        weights = _FakeWeightManager(
            {("seg", "zebrafish"): "rat-seg.pt", ("det", "aquarium"): None}
        )
        settings = SimpleNamespace(
            model_selection=SimpleNamespace(aquarium_method="seg", animal_method="det")
        )

        service = _service(pm, _FakeModelService(weight_manager=weights), settings)

        assert service.get_global_project_slot_weights() == {"seg:zebrafish": "rat-seg.pt"}
        assert _service(pm).get_global_project_slot_weights() == {}

    def test_slot_override_save_failure_still_applies_at_runtime(self, tmp_path):
        pm = _real_pm(tmp_path)
        weights = _FakeWeightManager({})
        service = _service(pm, _FakeModelService(weight_manager=weights))

        original_save = pm.save_project
        saves: list[int] = []

        def flaky_save():
            saves.append(1)
            if len(saves) == 1:
                raise ProjectInvalidError(message="disk full")
            original_save()

        pm.save_project = flaky_save  # type: ignore[method-assign]

        result = service.save_project_model_slot_overrides({"det:zebrafish": "b.pt"}, None)

        assert result == ("b.pt", False)
        assert saves == [1, 1]
        assert pm.project_data["model_overrides"]["slot_weights"] == {"det:zebrafish": "b.pt"}
        assert weights.runtime == {("det", "zebrafish"): "b.pt"}

    def test_detector_hyperparams_keep_only_the_unit_band(self):
        service = _service()

        assert service._build_detector_hyperparam_overrides(
            {"confidence_threshold": "0.25", "nms_threshold": "x", "imgsz": 640}
        ) == {"confidence_threshold": 0.25}
        assert service._build_detector_hyperparam_overrides({"nms_threshold": 1.5}) == {}
        assert service._build_detector_hyperparam_overrides(None) == {}

    def test_initial_overrides_skip_a_non_dict_project(self):
        pm = SimpleNamespace(project_data=None, project_path=None)

        _service(pm)._persist_initial_project_overrides({"det:zebrafish": "a.pt"}, {})

        assert pm.project_data is None

    def test_slot_keys_accept_tuples_and_reject_bad_entries(self):
        service = _service()

        assert service._normalize_slot_weights(
            {
                ("DET", " Zebrafish "): " a.pt ",
                "seg:aquarium": "b.pt",
                "nocolon": "c.pt",
                ("det", 1): "d.pt",
                "det:fish": "e.pt",
                "det:aquarium": "  ",
            }
        ) == {"det:zebrafish": "a.pt", "seg:aquarium": "b.pt"}


class TestCreationSideEffects:
    def test_behavioral_config_and_live_defaults_are_persisted(self, tmp_path):
        pm = _real_pm(tmp_path)
        service = _service(pm)

        service._persist_project_data(
            {
                "model_selection": {"animal_method": "seg"},
                "aquarium_method": "det",
                "behavioral_analysis": {"freezing": True},
                "selected_live_mode": "timed",
            }
        )

        from zebtrack.core.project.project_manager import ProjectManager

        reloaded = ProjectManager(settings_obj=None)
        reloaded.load_project(pm.project_path)
        assert reloaded.project_data["model_selection"] == {
            "aquarium_method": "det",
            "animal_method": "seg",
        }
        assert reloaded.project_data["behavioral_config"] == {"freezing": True}
        assert reloaded.project_data["live_session_defaults"] == {"selected_live_mode": "timed"}
        (update,) = service.state_manager.updates
        assert update["project_path"] == Path(pm.project_path)

    def test_runtime_defaults_fill_missing_values(self):
        service = _service(settings=SimpleNamespace(openvino=SimpleNamespace(device=None)))
        service.set_global_model_defaults("g.pt", True)
        kwargs: dict = {}
        flags: list = []

        service._apply_runtime_model_defaults(
            kwargs, active_weight_setter=flags.append, use_openvino_setter=flags.append
        )

        assert kwargs == {"active_weight": "g.pt", "use_openvino": True, "openvino_device": "AUTO"}
        assert flags == []
        explicit = {"use_openvino": False, "openvino_device": "CPU"}
        service._apply_runtime_model_defaults(
            explicit, active_weight_setter=None, use_openvino_setter=flags.append
        )
        assert flags == [False]


class TestPostCreationGuideCounts:
    def test_counts_combine_flags_metadata_and_import_config(self, monkeypatch):
        monkeypatch.delenv("ZEBTRACK_SUPPRESS_POST_CREATION_GUIDE", raising=False)
        pm = SimpleNamespace(get_all_videos=lambda: [])
        service = _service(pm)
        wizard = {
            "scanned_videos": [
                {"video": "C:/a.mp4", "has_arena": True},
                {"path": "C:/b.mp4", "metadata": {"has_rois": True}},
                {"path": "C:/c.mp4"},
                {},
            ],
            "import_config": [
                {"video": "C:/c.mp4", "import_trajectory": True},
                {"video": None},
            ],
        }

        guide = service.generate_post_creation_guide(wizard, check_suppression=False)

        message = guide["message"]
        assert "  • Total videos: 4" in message
        assert "  • With arena defined: 1" in message
        assert "  • With ROIs defined: 1" in message
        assert "  • With trajectory ready: 1" in message
        assert "  • Pending processing: 3" in message
        assert (
            message.index("1. Review")
            < message.index("2. Process")
            < message.index("Generate reports")
        )
