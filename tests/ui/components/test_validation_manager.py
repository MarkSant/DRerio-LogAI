"""Tests for ValidationManager component."""

from collections import Counter
from unittest.mock import Mock, patch

import pytest

from zebtrack.core.detector import ZoneData
from zebtrack.ui.components.validation_manager import (
    PROJECT_STATUS_META,
    STATUS_SYMBOLS,
    ValidationManager,
)


@pytest.fixture(autouse=True)
def block_all_dialogs():
    """Automatically block ALL dialog windows for all tests in this file."""
    with (
        patch("tkinter.messagebox.showerror"),
        patch("tkinter.messagebox.showwarning"),
        patch("tkinter.messagebox.showinfo"),
        patch("tkinter.messagebox.askyesno", return_value=False),
        patch("tkinter.messagebox.askokcancel", return_value=False),
        patch("tkinter.messagebox.askyesnocancel", return_value=None),
    ):
        yield


@pytest.fixture
def mock_controller():
    """Create a mock controller."""
    controller = Mock()
    controller.project_manager = Mock()
    controller.project_manager.get_project_type = Mock(return_value="pre-recorded")
    controller.project_manager.get_active_zone_video = Mock(return_value=None)
    controller.project_manager.get_zone_data = Mock(return_value=ZoneData())
    return controller


@pytest.fixture
def mock_gui(tkinter_root, mock_controller):
    """Create a mock ApplicationGUI instance."""
    gui = Mock()
    gui.root = tkinter_root
    gui.controller = mock_controller
    gui.project_manager = mock_controller.project_manager
    gui.state_manager = Mock()
    gui.show_info = Mock()
    gui.show_error = Mock()
    gui.show_warning = Mock()
    gui.ask_ok_cancel = Mock(return_value=False)
    gui.notebook = Mock()
    gui.zone_tab_frame = Mock()
    gui._overview_video_index = {}
    gui._roi_templates_cache = []
    gui.roi_template_var = Mock()
    gui.roi_template_var.get = Mock(return_value="")
    gui.analysis_interval_var = Mock()
    gui.analysis_interval_var.get = Mock(return_value="10")
    gui.analysis_interval_var.set = Mock()
    gui.display_interval_var = Mock()
    gui.display_interval_var.get = Mock(return_value="10")
    gui.display_interval_var.set = Mock()
    gui.roi_choice_var = Mock()
    gui.roi_choice_var.get = Mock(return_value="none")
    gui.roi_choice_var.set = Mock()
    gui.stabilization_frames_var = Mock()
    gui.stabilization_frames_var.get = Mock(return_value="10")
    gui.stabilization_frames_var.set = Mock()
    gui.pending_single_video_config = None
    gui.pending_single_video_path = None
    return gui


@pytest.fixture
def validation_manager(mock_gui):
    """Create a ValidationManager instance for testing."""
    return ValidationManager(mock_gui)


@pytest.fixture
def mock_zone_data():
    """Create mock zone data."""
    zone_data = ZoneData()
    zone_data.polygon = [[100, 100], [200, 100], [200, 200], [100, 200]]
    zone_data.roi_polygons = [
        [[120, 120], [180, 120], [180, 180], [120, 180]],
        [[220, 120], [280, 120], [280, 180], [220, 180]],
    ]
    zone_data.roi_colors = [(0, 255, 0), (255, 0, 0)]
    zone_data.roi_names = ["ROI_1", "ROI_2"]
    return zone_data


@pytest.mark.gui
class TestValidationManagerInitialization:
    """Tests for ValidationManager initialization."""

    def test_initialization(self, validation_manager, mock_gui):
        """Test that ValidationManager initializes correctly."""
        assert validation_manager.gui is mock_gui

    def test_initialization_with_real_gui(self, tkinter_root):
        """Test initialization with minimal real gui object."""
        gui = Mock()
        gui.root = tkinter_root
        manager = ValidationManager(gui)
        assert manager.gui is gui


@pytest.mark.gui
class TestComposeOverviewStatusLine:
    """Tests for compose_overview_status_line method."""

    def test_compose_overview_status_line_empty(self, validation_manager):
        """Test status line with no videos."""
        result = validation_manager.compose_overview_status_line(0, Counter())
        assert result == "Nenhum vídeo cadastrado."

    def test_compose_overview_status_line_negative_total(self, validation_manager):
        """Test status line with negative total."""
        result = validation_manager.compose_overview_status_line(-1, Counter())
        assert result == "Nenhum vídeo cadastrado."

    def test_compose_overview_status_line_single_status(self, validation_manager):
        """Test status line with single status."""
        counts = Counter({"pending": 5})
        result = validation_manager.compose_overview_status_line(5, counts)

        assert "🧮 5 vídeo(s)" in result
        assert "⏳ 5" in result

    def test_compose_overview_status_line_multiple_statuses(self, validation_manager):
        """Test status line with multiple statuses."""
        counts = Counter({"pending": 3, "processing": 1, "complete": 2})
        result = validation_manager.compose_overview_status_line(6, counts)

        assert "🧮 6 vídeo(s)" in result
        assert "⏳ 3" in result
        assert "🔁 1" in result
        assert "✅ 2" in result

    def test_compose_overview_status_line_all_statuses(self, validation_manager):
        """Test status line with all possible statuses."""
        counts = Counter(
            {
                "pending": 1,
                "processing": 2,
                "processed": 3,
                "complete": 4,
                "failed": 5,
            }
        )
        result = validation_manager.compose_overview_status_line(15, counts)

        assert "🧮 15 vídeo(s)" in result
        for icon, _ in PROJECT_STATUS_META.values():
            assert icon in result

    def test_compose_overview_status_line_unknown_status(self, validation_manager):
        """Test status line with unknown status."""
        counts = Counter({"pending": 2, "unknown_status": 3})
        result = validation_manager.compose_overview_status_line(5, counts)

        assert "🧮 5 vídeo(s)" in result
        assert "⏳ 2" in result
        assert "➕ 3" in result  # Unknown statuses grouped


@pytest.mark.gui
class TestPrepareOverviewHierarchyForWidget:
    """Tests for prepare_overview_hierarchy_for_widget method."""

    def test_prepare_overview_hierarchy_empty_videos(self, validation_manager):
        """Test hierarchy with no videos."""
        result = validation_manager.prepare_overview_hierarchy_for_widget([])

        assert "groups" in result
        assert result["groups"] == []

    def test_prepare_overview_hierarchy_single_video(self, validation_manager):
        """Test hierarchy with single video."""
        videos = [
            {
                "path": "/path/to/video1.mp4",
                "filename": "video1.mp4",
                "metadata": {"group": "G1", "day": 1, "subject": 1},
                "status": "pending",
                "has_arena": False,
                "has_rois": False,
                "has_trajectory": False,
            }
        ]

        result = validation_manager.prepare_overview_hierarchy_for_widget(videos)

        assert "groups" in result
        assert len(result["groups"]) == 1
        group = result["groups"][0]
        assert group["id"] == "G1"
        assert group["display"] == "G1"
        assert len(group["days"]) == 1
        assert len(group["days"][0]["videos"]) == 1

    def test_prepare_overview_hierarchy_multiple_groups(self, validation_manager):
        """Test hierarchy with multiple groups."""
        videos = [
            {
                "path": "/path/to/video1.mp4",
                "filename": "video1.mp4",
                "metadata": {"group": "G1", "day": 1, "subject": 1},
                "status": "pending",
            },
            {
                "path": "/path/to/video2.mp4",
                "filename": "video2.mp4",
                "metadata": {"group": "G2", "day": 1, "subject": 1},
                "status": "complete",
            },
        ]

        result = validation_manager.prepare_overview_hierarchy_for_widget(videos)

        assert len(result["groups"]) == 2
        group_ids = [g["id"] for g in result["groups"]]
        assert "G1" in group_ids
        assert "G2" in group_ids

    def test_prepare_overview_hierarchy_multiple_days(self, validation_manager):
        """Test hierarchy with multiple days."""
        videos = [
            {
                "path": "/path/to/video1.mp4",
                "filename": "video1.mp4",
                "metadata": {"group": "G1", "day": 1, "subject": 1},
                "status": "pending",
            },
            {
                "path": "/path/to/video2.mp4",
                "filename": "video2.mp4",
                "metadata": {"group": "G1", "day": 2, "subject": 2},
                "status": "pending",
            },
        ]

        result = validation_manager.prepare_overview_hierarchy_for_widget(videos)

        assert len(result["groups"]) == 1
        assert len(result["groups"][0]["days"]) == 2

    def test_prepare_overview_hierarchy_video_index(self, validation_manager, mock_gui):
        """Test that video index is populated."""
        videos = [
            {
                "path": "/path/to/video1.mp4",
                "filename": "video1.mp4",
                "metadata": {"group": "G1", "day": 1, "subject": 1},
                "status": "pending",
            }
        ]

        validation_manager.prepare_overview_hierarchy_for_widget(videos)

        assert "/path/to/video1.mp4" in mock_gui._overview_video_index

    def test_prepare_overview_hierarchy_status_summary(self, validation_manager):
        """Test that status summary is calculated correctly."""
        videos = [
            {
                "path": "/path/to/video1.mp4",
                "filename": "video1.mp4",
                "metadata": {"group": "G1", "day": 1, "subject": 1},
                "status": "pending",
            },
            {
                "path": "/path/to/video2.mp4",
                "filename": "video2.mp4",
                "metadata": {"group": "G1", "day": 1, "subject": 2},
                "status": "complete",
            },
        ]

        result = validation_manager.prepare_overview_hierarchy_for_widget(videos)

        group = result["groups"][0]
        assert "status_summary" in group
        assert "⏳" in group["status_summary"]
        assert "✅" in group["status_summary"]

    def test_prepare_overview_hierarchy_data_summary(self, validation_manager):
        """Test that data summary includes all symbols."""
        videos = [
            {
                "path": "/path/to/video1.mp4",
                "filename": "video1.mp4",
                "metadata": {"group": "G1", "day": 1, "subject": 1},
                "status": "complete",
                "has_arena": True,
                "has_rois": True,
                "has_trajectory": True,
            }
        ]

        result = validation_manager.prepare_overview_hierarchy_for_widget(videos)

        group = result["groups"][0]
        assert "data_summary" in group
        # Should contain all status symbols
        for symbol in STATUS_SYMBOLS.values():
            assert symbol in group["data_summary"]


@pytest.mark.gui
class TestCheckLiveProjectCalibration:
    """Tests for check_live_project_calibration method."""

    def test_check_live_project_calibration_not_live(self, validation_manager, mock_controller):
        """Test that method returns early for non-live projects."""
        mock_controller.project_manager.get_project_type.return_value = "pre-recorded"

        validation_manager.check_live_project_calibration()

        # Should not prompt user
        validation_manager.gui.ask_ok_cancel.assert_not_called()

    def test_check_live_project_calibration_has_arena(
        self, validation_manager, mock_controller, mock_zone_data
    ):
        """Test that method returns early when arena exists."""
        mock_controller.project_manager.get_project_type.return_value = "live"
        mock_controller.project_manager.get_zone_data.return_value = mock_zone_data

        validation_manager.check_live_project_calibration()

        # Should not prompt user
        validation_manager.gui.ask_ok_cancel.assert_not_called()

    def test_check_live_project_calibration_no_arena_declined(
        self, validation_manager, mock_controller, mock_gui
    ):
        """Test user declining auto-calibration."""
        mock_controller.project_manager.get_project_type.return_value = "live"
        mock_controller.project_manager.get_zone_data.return_value = ZoneData()
        mock_gui.ask_ok_cancel.return_value = False

        validation_manager.check_live_project_calibration()

        # Should prompt user
        mock_gui.ask_ok_cancel.assert_called_once()
        # Should not switch tabs
        mock_gui.notebook.select.assert_not_called()

    def test_check_live_project_calibration_no_arena_accepted(
        self, validation_manager, mock_controller, mock_gui
    ):
        """Test user accepting auto-calibration."""
        mock_controller.project_manager.get_project_type.return_value = "live"
        mock_controller.project_manager.get_zone_data.return_value = ZoneData()
        mock_gui.ask_ok_cancel.return_value = True

        validation_manager.check_live_project_calibration()

        # Should prompt user
        mock_gui.ask_ok_cancel.assert_called_once()
        # Should switch to zone tab
        mock_gui.notebook.select.assert_called_once_with(mock_gui.zone_tab_frame)
        # Should show info message
        mock_gui.show_info.assert_called_once()


@pytest.mark.gui
class TestComposeSingleVideoRuntimeConfig:
    """Tests for compose_single_video_runtime_config method."""

    def test_compose_single_video_runtime_config_no_pending(self, validation_manager, mock_gui):
        """Test when no pending config."""
        mock_gui.pending_single_video_config = None

        result = validation_manager.compose_single_video_runtime_config()

        assert result is None

    def test_compose_single_video_runtime_config_valid(self, validation_manager, mock_gui):
        """Test with valid configuration."""
        mock_gui.pending_single_video_config = {"video_path": "/path/to/video.mp4"}
        mock_gui.zone_controls = None

        result = validation_manager.compose_single_video_runtime_config()

        assert result is not None
        assert result["analysis_interval_frames"] == 10
        assert result["display_interval_frames"] == 10
        assert result["stabilization_frames"] == 10

    def test_compose_single_video_runtime_config_with_zone_controls(
        self, validation_manager, mock_gui
    ):
        """Test with zone controls."""
        mock_gui.pending_single_video_config = {"video_path": "/path/to/video.mp4"}

        mock_zone_controls = Mock()
        mock_zone_controls.analysis_interval_var = Mock()
        mock_zone_controls.analysis_interval_var.get = Mock(return_value="20")
        mock_zone_controls.display_interval_var = Mock()
        mock_zone_controls.display_interval_var.get = Mock(return_value="15")
        mock_zone_controls.roi_choice_var = Mock()
        mock_zone_controls.roi_choice_var.get = Mock(return_value="template")
        mock_zone_controls.stabilization_frames_var = Mock()
        mock_zone_controls.stabilization_frames_var.get = Mock(return_value="5")
        mock_gui.zone_controls = mock_zone_controls

        result = validation_manager.compose_single_video_runtime_config()

        assert result is not None
        assert result["analysis_interval_frames"] == 20
        assert result["display_interval_frames"] == 15
        assert result["roi_choice"] == "template"
        assert result["stabilization_frames"] == 5

    def test_compose_single_video_runtime_config_invalid_interval(
        self, validation_manager, mock_gui
    ):
        """Test with invalid interval values."""
        mock_gui.pending_single_video_config = {"video_path": "/path/to/video.mp4"}
        mock_gui.analysis_interval_var.get = Mock(return_value="abc")
        mock_gui.zone_controls = None

        result = validation_manager.compose_single_video_runtime_config()

        assert result is None
        mock_gui.show_error.assert_called_once()

    def test_compose_single_video_runtime_config_negative_interval(
        self, validation_manager, mock_gui
    ):
        """Test with negative interval values."""
        mock_gui.pending_single_video_config = {"video_path": "/path/to/video.mp4"}
        mock_gui.analysis_interval_var.get = Mock(return_value="-5")
        mock_gui.zone_controls = None

        result = validation_manager.compose_single_video_runtime_config()

        assert result is None
        mock_gui.show_error.assert_called_once()

    def test_compose_single_video_runtime_config_zero_interval(self, validation_manager, mock_gui):
        """Test with zero interval values."""
        mock_gui.pending_single_video_config = {"video_path": "/path/to/video.mp4"}
        mock_gui.analysis_interval_var.get = Mock(return_value="0")
        mock_gui.zone_controls = None

        result = validation_manager.compose_single_video_runtime_config()

        assert result is None
        mock_gui.show_error.assert_called_once()


@pytest.mark.gui
class TestGetZoneDataForActiveContext:
    """Tests for get_zone_data_for_active_context method."""

    def test_get_zone_data_no_project_manager(self, validation_manager, mock_gui):
        """Test when project_manager is None."""
        mock_gui.controller.project_manager = None

        result = validation_manager.get_zone_data_for_active_context()

        assert isinstance(result, ZoneData)
        assert result.polygon == []  # Returns empty list, not None

    def test_get_zone_data_no_active_video(
        self, validation_manager, mock_controller, mock_zone_data
    ):
        """Test without active video."""
        mock_controller.project_manager.get_active_zone_video.return_value = None
        mock_controller.project_manager.get_zone_data.return_value = mock_zone_data

        result = validation_manager.get_zone_data_for_active_context()

        assert result is mock_zone_data

    def test_get_zone_data_with_active_video(
        self, validation_manager, mock_controller, mock_zone_data
    ):
        """Test with active video."""
        mock_controller.project_manager.get_active_zone_video.return_value = "/path/to/video.mp4"
        mock_controller.project_manager.get_zone_data.return_value = mock_zone_data

        validation_manager.get_zone_data_for_active_context()

        mock_controller.project_manager.get_zone_data.assert_called_with(
            video_path="/path/to/video.mp4", fallback_to_global=False
        )

    def test_get_zone_data_with_pending_video(
        self, validation_manager, mock_controller, mock_gui, mock_zone_data
    ):
        """Test with pending video."""
        mock_controller.project_manager.get_active_zone_video.return_value = None
        mock_gui.pending_single_video_path = "/path/to/pending.mp4"
        mock_controller.project_manager.get_zone_data.return_value = mock_zone_data

        validation_manager.get_zone_data_for_active_context()

        mock_controller.project_manager.get_zone_data.assert_called_with(
            video_path="/path/to/pending.mp4", fallback_to_global=False
        )

    def test_get_zone_data_exception_handling(
        self, validation_manager, mock_controller, mock_zone_data
    ):
        """Test exception handling."""
        mock_controller.project_manager.get_active_zone_video.return_value = "/path/to/video.mp4"
        mock_controller.project_manager.get_zone_data.side_effect = [
            Exception("Test error"),
            mock_zone_data,
        ]

        result = validation_manager.get_zone_data_for_active_context()

        # Should fall back to global zone data
        assert isinstance(result, ZoneData) or result is mock_zone_data


@pytest.mark.gui
class TestGetSelectedRoiTemplate:
    """Tests for get_selected_roi_template method."""

    def test_get_selected_roi_template_empty_cache(self, validation_manager, mock_gui):
        """Test with empty template cache."""
        mock_gui._roi_templates_cache = []

        result = validation_manager.get_selected_roi_template()

        assert result is None

    def test_get_selected_roi_template_no_selection(self, validation_manager, mock_gui):
        """Test with no template selected."""
        mock_gui._roi_templates_cache = [{"name": "Template1", "display_name": "Template 1"}]
        mock_gui.roi_template_var.get.return_value = ""

        result = validation_manager.get_selected_roi_template()

        assert result is None

    def test_get_selected_roi_template_found(self, validation_manager, mock_gui):
        """Test finding selected template."""
        template = {"name": "Template1", "display_name": "Template 1"}
        mock_gui._roi_templates_cache = [template]
        mock_gui.roi_template_var.get.return_value = "Template 1"

        result = validation_manager.get_selected_roi_template()

        assert result is template

    def test_get_selected_roi_template_not_found(self, validation_manager, mock_gui):
        """Test when selected template not in cache."""
        mock_gui._roi_templates_cache = [{"name": "Template1", "display_name": "Template 1"}]
        mock_gui.roi_template_var.get.return_value = "NonExistent"

        result = validation_manager.get_selected_roi_template()

        assert result is None


@pytest.mark.gui
class TestValidateRoiTemplateData:
    """Tests for validate_roi_template_data method."""

    def test_validate_roi_template_data_none(self, validation_manager):
        """Test with None zone data."""
        is_valid, error = validation_manager.validate_roi_template_data(None)

        assert is_valid is False
        assert "Desenhe" in error

    def test_validate_roi_template_data_no_polygon_no_rois(self, validation_manager):
        """Test with no polygon and no ROIs."""
        zone_data = ZoneData()
        is_valid, error = validation_manager.validate_roi_template_data(zone_data)

        assert is_valid is False
        assert "Desenhe" in error

    def test_validate_roi_template_data_with_polygon(self, validation_manager, mock_zone_data):
        """Test with valid polygon."""
        is_valid, error = validation_manager.validate_roi_template_data(mock_zone_data)

        assert is_valid is True
        assert error == ""

    def test_validate_roi_template_data_with_rois_only(self, validation_manager):
        """Test with ROIs but no arena polygon."""
        zone_data = ZoneData()
        zone_data.roi_polygons = [[[100, 100], [200, 200]]]

        is_valid, error = validation_manager.validate_roi_template_data(zone_data)

        assert is_valid is True
        assert error == ""


@pytest.mark.gui
class TestValidateArenaForAnalysis:
    """Tests for validate_arena_for_analysis method."""

    def test_validate_arena_for_analysis_none(self, validation_manager):
        """Test with None arena ID."""
        is_valid, error = validation_manager.validate_arena_for_analysis(None)

        assert is_valid is False
        assert "Selecione" in error

    def test_validate_arena_for_analysis_empty(self, validation_manager):
        """Test with empty arena ID."""
        is_valid, error = validation_manager.validate_arena_for_analysis("")

        assert is_valid is False
        assert "Selecione" in error

    def test_validate_arena_for_analysis_valid(self, validation_manager):
        """Test with valid arena ID."""
        is_valid, error = validation_manager.validate_arena_for_analysis("arena_1")

        assert is_valid is True
        assert error == ""


@pytest.mark.gui
class TestValidateArenaPolygonData:
    """Tests for validate_arena_polygon_data method."""

    def test_validate_arena_polygon_data_none(self, validation_manager):
        """Test with None arena data."""
        is_valid, error, data = validation_manager.validate_arena_polygon_data(None)

        assert is_valid is False
        assert "polígono" in error
        assert data is None

    def test_validate_arena_polygon_data_no_polygon(self, validation_manager):
        """Test with arena data but no polygon."""
        arena_data = {"name": "Arena1"}
        is_valid, error, data = validation_manager.validate_arena_polygon_data(arena_data)

        assert is_valid is False
        assert "polígono" in error
        assert data is None

    def test_validate_arena_polygon_data_valid(self, validation_manager):
        """Test with valid polygon data."""
        arena_data = {"name": "Arena1", "polygon_px": [[100, 100], [200, 200]]}
        is_valid, error, data = validation_manager.validate_arena_polygon_data(arena_data)

        assert is_valid is True
        assert error == ""
        assert data is arena_data


@pytest.mark.gui
class TestValidatePositiveInteger:
    """Tests for validate_positive_integer method."""

    @pytest.mark.parametrize(
        "value,expected_valid,expected_int",
        [
            ("10", True, 10),
            ("1", True, 1),
            ("100", True, 100),
            ("999", True, 999),
            (10, True, 10),
            (1, True, 1),
        ],
    )
    def test_validate_positive_integer_valid(
        self, validation_manager, value, expected_valid, expected_int
    ):
        """Test with valid positive integers."""
        is_valid, error, result = validation_manager.validate_positive_integer(value)

        assert is_valid == expected_valid
        assert error == ""
        assert result == expected_int

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "abc",
            "0",
            "-5",
            "-1",
            "1.5",
            None,
            [],
            {},
        ],
    )
    def test_validate_positive_integer_invalid(self, validation_manager, value):
        """Test with invalid values."""
        is_valid, error, result = validation_manager.validate_positive_integer(value)

        assert is_valid is False
        assert "inteiro positivo" in error
        assert result is None

    def test_validate_positive_integer_custom_field_name(self, validation_manager):
        """Test with custom field name."""
        is_valid, error, result = validation_manager.validate_positive_integer(
            "abc", field_name="intervalo"
        )

        assert is_valid is False
        assert "intervalo" in error
        assert result is None


@pytest.mark.gui
class TestValidateActiveVideoSelection:
    """Tests for validate_active_video_selection method."""

    def test_validate_active_video_selection_none(self, validation_manager):
        """Test with None video."""
        is_valid, error = validation_manager.validate_active_video_selection(None)

        assert is_valid is False
        assert "Selecione" in error

    def test_validate_active_video_selection_empty(self, validation_manager):
        """Test with empty video path."""
        is_valid, error = validation_manager.validate_active_video_selection("")

        assert is_valid is False
        assert "Selecione" in error

    def test_validate_active_video_selection_valid(self, validation_manager):
        """Test with valid video path."""
        is_valid, error = validation_manager.validate_active_video_selection("/path/to/video.mp4")

        assert is_valid is True
        assert error == ""


@pytest.mark.gui
class TestFormatStatusLabel:
    """Tests for format_status_label method."""

    @pytest.mark.parametrize(
        "status_key,expected_icon",
        [
            ("pending", "⏳"),
            ("processing", "🔁"),
            ("processed", "📦"),
            ("complete", "✅"),
            ("failed", "⚠️"),
        ],
    )
    def test_format_status_label_known_statuses(
        self, validation_manager, status_key, expected_icon
    ):
        """Test formatting of known status keys."""
        result = validation_manager.format_status_label(status_key)

        assert expected_icon in result
        assert len(result) > len(expected_icon)  # Should have label text too

    def test_format_status_label_unknown_status(self, validation_manager):
        """Test formatting of unknown status."""
        result = validation_manager.format_status_label("unknown_status")

        assert "•" in result  # Default icon


@pytest.mark.gui
class TestFormatStatusSummary:
    """Tests for format_status_summary method."""

    def test_format_status_summary_empty(self, validation_manager):
        """Test with empty counter."""
        result = validation_manager.format_status_summary(Counter())

        assert result == "-"

    def test_format_status_summary_single_status(self, validation_manager):
        """Test with single status."""
        counts = Counter({"pending": 5})
        result = validation_manager.format_status_summary(counts)

        assert "⏳ 5" in result

    def test_format_status_summary_multiple_statuses(self, validation_manager):
        """Test with multiple statuses."""
        counts = Counter({"pending": 3, "complete": 2})
        result = validation_manager.format_status_summary(counts)

        assert "⏳ 3" in result
        assert "✅ 2" in result
        assert "|" in result

    def test_format_status_summary_unknown_status(self, validation_manager):
        """Test with unknown status."""
        counts = Counter({"unknown": 5})
        result = validation_manager.format_status_summary(counts)

        assert "➕ 5" in result


@pytest.mark.gui
class TestFormatStatusRatio:
    """Tests for format_status_ratio method."""

    def test_format_status_ratio_normal(self, validation_manager):
        """Test normal ratio formatting."""
        result = validation_manager.format_status_ratio("arena", 3, 5)

        assert STATUS_SYMBOLS["arena"] in result
        assert "3/5" in result

    def test_format_status_ratio_zero_total(self, validation_manager):
        """Test with zero total."""
        result = validation_manager.format_status_ratio("arena", 0, 0)

        assert STATUS_SYMBOLS["arena"] in result
        assert "0/0" in result

    def test_format_status_ratio_complete(self, validation_manager):
        """Test with all completed."""
        result = validation_manager.format_status_ratio("arena", 5, 5)

        assert "5/5" in result

    def test_format_status_ratio_clamping(self, validation_manager):
        """Test that completed is clamped to total."""
        result = validation_manager.format_status_ratio("arena", 10, 5)

        assert "5/5" in result  # Should clamp to total

    def test_format_status_ratio_negative_completed(self, validation_manager):
        """Test with negative completed value."""
        result = validation_manager.format_status_ratio("arena", -5, 10)

        assert "0/10" in result  # Should clamp to 0


@pytest.mark.gui
class TestSummarizeBatchData:
    """Tests for summarize_batch_data method."""

    def test_summarize_batch_data_empty(self, validation_manager):
        """Test with empty video list."""
        result = validation_manager.summarize_batch_data([])

        assert result == "-"

    def test_summarize_batch_data_single_video_no_data(self, validation_manager):
        """Test with single video without data."""
        videos = [
            {
                "has_arena": False,
                "has_rois": False,
                "has_trajectory": False,
            }
        ]
        result = validation_manager.summarize_batch_data(videos)

        assert "0/1" in result
        for symbol in STATUS_SYMBOLS.values():
            assert symbol in result

    def test_summarize_batch_data_all_complete(self, validation_manager):
        """Test with all videos complete."""
        videos = [
            {
                "has_arena": True,
                "has_rois": True,
                "has_trajectory": True,
            },
            {
                "has_arena": True,
                "has_rois": True,
                "has_trajectory": True,
            },
        ]
        result = validation_manager.summarize_batch_data(videos)

        assert "2/2" in result  # All ratios should be 2/2

    def test_summarize_batch_data_mixed(self, validation_manager):
        """Test with mixed completion."""
        videos = [
            {
                "has_arena": True,
                "has_rois": False,
                "has_trajectory": True,
            },
            {
                "has_arena": True,
                "has_rois": True,
                "has_trajectory": False,
            },
        ]
        result = validation_manager.summarize_batch_data(videos)

        # Should have different ratios for each type
        assert "2/2" in result  # Arena
        assert "1/2" in result  # ROIs or trajectory


@pytest.mark.gui
class TestFormatDataBadges:
    """Tests for format_data_badges method."""

    def test_format_data_badges_no_data(self, validation_manager):
        """Test with video having no data."""
        video = {
            "has_arena": False,
            "has_rois": False,
            "has_trajectory": False,
        }
        result = validation_manager.format_data_badges(video)

        assert "✗" in result
        assert result.count("✗") == 4  # All 4 badges should be ✗

    def test_format_data_badges_complete(self, validation_manager):
        """Test with complete video data."""
        video = {
            "has_arena": True,
            "has_rois": True,
            "has_trajectory": True,
        }
        result = validation_manager.format_data_badges(video)

        assert "✓" in result
        assert result.count("✓") == 4  # All 4 badges should be ✓

    def test_format_data_badges_partial(self, validation_manager):
        """Test with partial video data."""
        video = {
            "has_arena": True,
            "has_rois": False,
            "has_trajectory": True,
        }
        result = validation_manager.format_data_badges(video)

        assert "✓" in result
        assert "✗" in result
        assert result.count("✓") == 2  # Arena and trajectory
        assert result.count("✗") == 2  # ROIs and summary


@pytest.mark.gui
class TestFormatVideoMetadata:
    """Tests for format_video_metadata method."""

    def test_format_video_metadata_empty(self, validation_manager):
        """Test with empty metadata."""
        result = validation_manager.format_video_metadata({})

        assert result == ""

    def test_format_video_metadata_none(self, validation_manager):
        """Test with None metadata."""
        result = validation_manager.format_video_metadata(None)

        assert result == ""

    def test_format_video_metadata_group_only(self, validation_manager):
        """Test with group only."""
        metadata = {"group": "G1"}
        result = validation_manager.format_video_metadata(metadata)

        assert "G:G1" in result

    def test_format_video_metadata_day_only(self, validation_manager):
        """Test with day only."""
        metadata = {"day": 3}
        result = validation_manager.format_video_metadata(metadata)

        assert "D:03" in result

    def test_format_video_metadata_subject_only(self, validation_manager):
        """Test with subject only."""
        metadata = {"subject": 5}
        result = validation_manager.format_video_metadata(metadata)

        assert "S:05" in result

    def test_format_video_metadata_all_fields(self, validation_manager):
        """Test with all fields."""
        metadata = {"group": "G1", "day": 3, "subject": 5}
        result = validation_manager.format_video_metadata(metadata)

        assert "G:G1" in result
        assert "D:03" in result
        assert "S:05" in result


@pytest.mark.gui
class TestFormatStatusToken:
    """Tests for format_status_token method."""

    @pytest.mark.parametrize(
        "symbol_key",
        ["arena", "rois", "trajectory", "summary"],
    )
    def test_format_status_token_has_data(self, validation_manager, symbol_key):
        """Test token with data present."""
        result = validation_manager.format_status_token(True, symbol_key)

        assert STATUS_SYMBOLS[symbol_key] in result
        assert "✓" in result

    @pytest.mark.parametrize(
        "symbol_key",
        ["arena", "rois", "trajectory", "summary"],
    )
    def test_format_status_token_no_data(self, validation_manager, symbol_key):
        """Test token without data."""
        result = validation_manager.format_status_token(False, symbol_key)

        assert STATUS_SYMBOLS[symbol_key] in result
        assert "✗" in result


@pytest.mark.gui
class TestFormatSubjectLabel:
    """Tests for format_subject_label method."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, "??"),
            (0, "00"),
            (1, "01"),
            (5, "05"),
            (10, "10"),
            (99, "99"),
            (1.0, "01"),
            (5.0, "05"),
            ("", "??"),
            ("5", "05"),
            ("05", "05"),
            ("10", "10"),
            ("abc", "abc"),
        ],
    )
    def test_format_subject_label_variations(self, validation_manager, value, expected):
        """Test subject label formatting with various inputs."""
        result = validation_manager.format_subject_label(value)

        assert result == expected

    def test_format_subject_label_float_not_integer(self, validation_manager):
        """Test with float that's not an integer."""
        result = validation_manager.format_subject_label(5.5)

        assert result == "5.5"


@pytest.mark.gui
class TestFormatDayDisplay:
    """Tests for format_day_display method."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, ""),
            ("", ""),
            (0, "00"),
            (1, "01"),
            (3, "03"),
            (10, "10"),
            (99, "99"),
            ("3", "03"),
            ("03", "03"),
            ("10", "10"),
            ("sem dia", "Sem Dia"),
            ("SEM DIA", "Sem Dia"),
            ("abc", "abc"),
        ],
    )
    def test_format_day_display_variations(self, validation_manager, value, expected):
        """Test day display formatting with various inputs."""
        result = validation_manager.format_day_display(value)

        assert result == expected

    def test_format_day_display_extract_number(self, validation_manager):
        """Test extracting number from string."""
        result = validation_manager.format_day_display("Day 5")

        assert result == "05"


@pytest.mark.gui
class TestFormatRoiTemplateDisplay:
    """Tests for format_roi_template_display method."""

    def test_format_roi_template_display_basic(self, validation_manager):
        """Test basic template display."""
        template = {
            "name": "Template1",
            "location": "project",
            "includes_arena": True,
            "includes_rois": False,
        }
        result = validation_manager.format_roi_template_display(template)

        assert "Template1" in result
        assert "Arena" in result

    def test_format_roi_template_display_arena_and_rois(self, validation_manager):
        """Test template with both arena and ROIs."""
        template = {
            "name": "Complete",
            "location": "project",
            "includes_arena": True,
            "includes_rois": True,
        }
        result = validation_manager.format_roi_template_display(template)

        assert "Complete" in result
        assert "Arena + ROIs" in result

    def test_format_roi_template_display_global(self, validation_manager):
        """Test global template display."""
        template = {
            "name": "GlobalTemplate",
            "location": "global",
            "includes_arena": True,
            "includes_rois": True,
        }
        result = validation_manager.format_roi_template_display(template)

        assert "GlobalTemplate" in result
        assert "Global" in result

    def test_format_roi_template_display_no_data(self, validation_manager):
        """Test template with no data."""
        template = {
            "name": "Empty",
            "location": "project",
            "includes_arena": False,
            "includes_rois": False,
        }
        result = validation_manager.format_roi_template_display(template)

        assert "Empty" in result
        assert "Sem dados" in result


@pytest.mark.gui
class TestBuildRoiTemplateIdentifier:
    """Tests for build_roi_template_identifier method."""

    def test_build_roi_template_identifier_project_with_slug(self, validation_manager):
        """Test identifier for project template with slug."""
        template = {
            "location": "project",
            "slug": "template_slug",
            "name": "Template",
        }
        result = validation_manager.build_roi_template_identifier(template)

        assert result == "project:template_slug"

    def test_build_roi_template_identifier_with_file(self, validation_manager):
        """Test identifier with file reference."""
        template = {
            "location": "global",
            "file": "template_file.json",
            "name": "Template",
        }
        result = validation_manager.build_roi_template_identifier(template)

        assert result == "global:template_file.json"

    def test_build_roi_template_identifier_fallback_to_name(self, validation_manager):
        """Test identifier fallback to name."""
        template = {
            "location": "project",
            "name": "Template",
        }
        result = validation_manager.build_roi_template_identifier(template)

        assert result == "project:Template"


@pytest.mark.gui
class TestFormatTime:
    """Tests for format_time method."""

    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (None, "-"),
            (-1, "-"),
            (0, "0s"),
            (30, "30s"),
            (59, "59s"),
            (60, "1m 00s"),
            (90, "1m 30s"),
            (3600, "1h 00m 00s"),
            (3661, "1h 01m 01s"),
            (7200, "2h 00m 00s"),
            (7325, "2h 02m 05s"),
        ],
    )
    def test_format_time_variations(self, validation_manager, seconds, expected):
        """Test time formatting with various durations."""
        result = validation_manager.format_time(seconds)

        assert result == expected


@pytest.mark.gui
class TestFormatSubjectForReports:
    """Tests for format_subject_for_reports method (alias test)."""

    def test_format_subject_for_reports_is_alias(self, validation_manager):
        """Test that format_subject_for_reports is alias for format_subject_label."""
        # Should produce same results as format_subject_label
        assert validation_manager.format_subject_for_reports(5) == "05"
        assert validation_manager.format_subject_for_reports(None) == "??"
        assert validation_manager.format_subject_for_reports("abc") == "abc"


@pytest.mark.gui
class TestInternalHelpers:
    """Tests for internal helper methods."""

    def test_get_status_meta_known_statuses(self, validation_manager):
        """Test _get_status_meta with known statuses."""
        icon, label = validation_manager._get_status_meta("pending")
        assert icon == "⏳"
        assert label == "Pendentes"

    def test_get_status_meta_special_keys(self, validation_manager):
        """Test _get_status_meta with special keys."""
        icon, label = validation_manager._get_status_meta("arena")
        assert icon == STATUS_SYMBOLS["arena"]
        assert label == "Arena"

    def test_get_status_meta_unknown(self, validation_manager):
        """Test _get_status_meta with unknown status."""
        icon, label = validation_manager._get_status_meta("unknown")
        assert icon == "•"
        assert label == "Unknown"

    @pytest.mark.parametrize(
        "value,expected_type,expected_value",
        [
            (5, 0, 5),
            ("5", 0, 5),
            (10, 0, 10),
            ("abc", 1, "abc"),
            (None, 1, ""),
        ],
    )
    def test_video_sort_key(self, validation_manager, value, expected_type, expected_value):
        """Test _video_sort_key sorting logic."""
        result = validation_manager._video_sort_key(value)

        assert result[0] == expected_type
        assert result[1] == expected_value or result[1] == expected_value.lower()

    def test_format_day_display_wrapper(self, validation_manager):
        """Test _format_day_display wrapper method."""
        # Should call the static method
        result = validation_manager._format_day_display(3)
        assert result == "03"

    def test_build_day_title_basic(self, validation_manager):
        """Test _build_day_title with basic input."""
        result = validation_manager._build_day_title(3)
        assert result == "Dia 03"

    def test_build_day_title_with_metadata(self, validation_manager):
        """Test _build_day_title with metadata."""
        metadata = {"day": 5, "day_label": "Dia 05"}
        result = validation_manager._build_day_title(5, metadata)
        assert result == "Dia 05"

    def test_build_day_title_sem_dia(self, validation_manager):
        """Test _build_day_title with 'Sem Dia'."""
        result = validation_manager._build_day_title("sem dia")
        assert result == "Sem Dia"

    def test_build_video_hierarchy_data_empty(self, validation_manager):
        """Test _build_video_hierarchy_data with empty list."""
        result = validation_manager._build_video_hierarchy_data([], "")
        assert result == {}

    def test_build_video_hierarchy_data_single_video(self, validation_manager):
        """Test _build_video_hierarchy_data with single video."""
        videos = [
            {
                "path": "/path/to/video.mp4",
                "metadata": {"group": "G1", "day": 1, "subject": 1},
                "status": "pending",
            }
        ]
        result = validation_manager._build_video_hierarchy_data(videos, "")

        assert "G1" in result
        assert "days" in result["G1"]

    def test_build_video_hierarchy_data_with_search(self, validation_manager):
        """Test _build_video_hierarchy_data with search filter."""
        videos = [
            {
                "path": "/path/to/video1.mp4",
                "metadata": {"group": "G1", "day": 1, "subject": 1},
                "status": "pending",
            },
            {
                "path": "/path/to/video2.mp4",
                "metadata": {"group": "G2", "day": 1, "subject": 2},
                "status": "complete",
            },
        ]
        result = validation_manager._build_video_hierarchy_data(videos, "G1")

        # Should only include G1
        assert "G1" in result
        assert "G2" not in result


@pytest.mark.gui
class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_format_subject_label_with_whitespace(self, validation_manager):
        """Test subject label with whitespace."""
        result = validation_manager.format_subject_label("  5  ")
        assert result == "05"

    def test_format_day_display_with_whitespace(self, validation_manager):
        """Test day display with whitespace."""
        result = validation_manager.format_day_display("  3  ")
        assert result == "03"

    def test_validate_positive_integer_with_float_string(self, validation_manager):
        """Test validate_positive_integer with float string."""
        is_valid, _error, result = validation_manager.validate_positive_integer("10.5")

        assert is_valid is False
        assert result is None

    def test_summarize_batch_data_with_complete_flag(self, validation_manager):
        """Test summarize_batch_data with has_complete_data flag."""
        videos = [
            {
                "has_arena": False,
                "has_rois": False,
                "has_trajectory": False,
                "has_complete_data": True,
            }
        ]
        result = validation_manager.summarize_batch_data(videos)

        # Should count as complete even without individual flags
        assert "1/1" in result  # For summary

    def test_format_data_badges_with_complete_flag(self, validation_manager):
        """Test format_data_badges with has_complete_data flag."""
        video = {
            "has_arena": False,
            "has_rois": False,
            "has_trajectory": False,
            "has_complete_data": True,
        }
        result = validation_manager.format_data_badges(video)

        # Summary should be ✓ due to has_complete_data
        tokens = result.split("  ")
        assert "✓" in tokens[-1]  # Last token is summary

    def test_prepare_overview_hierarchy_no_metadata(self, validation_manager):
        """Test hierarchy preparation with video missing metadata."""
        videos = [
            {
                "path": "/path/to/video.mp4",
                "filename": "video.mp4",
                "status": "pending",
            }
        ]

        # Should handle missing metadata gracefully
        result = validation_manager.prepare_overview_hierarchy_for_widget(videos)

        assert "groups" in result
        assert len(result["groups"]) == 1  # Should use "Sem Grupo"

    def test_get_zone_data_for_active_context_empty_zone_data(
        self, validation_manager, mock_controller
    ):
        """Test get_zone_data with empty zone data from active video."""
        mock_controller.project_manager.get_active_zone_video.return_value = "/path/to/video.mp4"
        empty_zone_data = ZoneData()
        global_zone_data = ZoneData()
        global_zone_data.polygon = [[100, 100], [200, 200]]

        mock_controller.project_manager.get_zone_data.side_effect = [
            empty_zone_data,
            global_zone_data,
        ]

        result = validation_manager.get_zone_data_for_active_context()

        # Should fall back to global since active video has no zones
        assert result is global_zone_data

    def test_compose_overview_status_line_only_unknown_statuses(self, validation_manager):
        """Test status line with only unknown statuses."""
        counts = Counter({"custom_status_1": 3, "custom_status_2": 2})
        result = validation_manager.compose_overview_status_line(5, counts)

        assert "🧮 5 vídeo(s)" in result
        assert "➕ 5" in result  # All 5 are unknown

    def test_format_video_metadata_with_day_label(self, validation_manager):
        """Test video metadata formatting with day_label override."""
        metadata = {"day": 3, "day_label": "Custom Day"}
        result = validation_manager.format_video_metadata(metadata)

        assert "D:Custom Day" in result

    def test_build_roi_template_identifier_empty_template(self, validation_manager):
        """Test identifier building with minimal template."""
        template: dict[str, object] = {}
        result = validation_manager.build_roi_template_identifier(template)

        assert result == "project:"  # Default location with empty name
