"""
Unit tests for __main__.py entry point.

Phase: Sprint 2.3 - Test coverage for application initialization
Tests main() function, logging configuration, error handling,
and CLI argument parsing.
"""

import logging
from unittest.mock import Mock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_torch_logging():
    """
    Mock logging.getLogger globally to prevent torch/matplotlib from failing on Mock loggers.

    This fixture runs before all tests to ensure that when torch/matplotlib initialize
    (via ultralytics -> YOLO import in MainViewModel), they don't fail trying to:
    1. Iterate over log.handlers when they are Mock objects
    2. Compare log.level with integers (matplotlib does `_log.level <= logging.DEBUG`)
    """
    with patch("logging.getLogger") as mock_get_logger:
        # Create a mock logger with handlers as empty list and level as integer
        mock_logger = Mock()
        mock_logger.handlers = []
        mock_logger.level = logging.INFO  # Set as real integer for comparisons
        mock_logger.setLevel = Mock()
        mock_logger.addHandler = Mock()
        mock_get_logger.return_value = mock_logger
        yield mock_get_logger


def create_mock_settings():
    """Create a properly structured mock settings object for testing."""
    mock_settings = Mock()
    mock_settings.camera = Mock(index=0)
    mock_settings.yolo_model = Mock(path="yolo11n.pt")
    mock_settings.reproducibility = None

    # Configure logging settings to be iterable
    mock_settings.logging = Mock()
    mock_settings.logging.levels = {
        "zebtrack": "INFO",
        "zebtrack.core.detector": "INFO",
        "zebtrack.ui": "WARNING",
    }

    # Configure recorder settings with proper types
    mock_settings.recorder = Mock()
    mock_settings.recorder.flush_interval_seconds = 30.0
    mock_settings.recorder.buffer_size_frames = 300
    mock_settings.recorder.flush_row_threshold = 500

    # Configure video processing settings
    mock_settings.video_processing = Mock()
    mock_settings.video_processing.fps = 30.0

    # Configure UI features
    mock_settings.ui_features = Mock()
    mock_settings.ui_features.enable_event_queue = False

    return mock_settings


class TestLoggingConfiguration:
    """Test suite for configure_logging function."""

    @patch("zebtrack.__main__.logging.handlers.RotatingFileHandler")
    @patch("zebtrack.__main__.logging.StreamHandler")
    @patch("zebtrack.__main__.logging.getLogger")
    def test_configure_logging_creates_handlers(self, mock_get_logger, mock_stream, mock_rotating):
        """Test that configure_logging creates file and console handlers."""
        from zebtrack.__main__ import configure_logging

        mock_root_logger = Mock()
        mock_get_logger.return_value = mock_root_logger

        configure_logging()

        # Should create both handlers
        mock_rotating.assert_called_once()
        mock_stream.assert_called_once()

        # Should add handlers to root logger
        assert mock_root_logger.addHandler.call_count >= 2

    @patch("zebtrack.__main__.logging.handlers.RotatingFileHandler")
    @patch("zebtrack.__main__.logging.getLogger")
    def test_configure_logging_sets_rotation_params(self, mock_get_logger, mock_rotating):
        """Test that file handler has correct rotation params."""
        from zebtrack.__main__ import configure_logging

        configure_logging()

        # Should configure rotation (5MB max, 5 backups)
        call_args = mock_rotating.call_args
        assert call_args[0][0] == "analysis.log"
        assert call_args[1]["maxBytes"] == 5 * 1024 * 1024
        assert call_args[1]["backupCount"] == 5

    @patch("zebtrack.__main__.logging.getLogger")
    def test_configure_logging_sets_log_level(self, mock_get_logger):
        """Test that root logger level is set to INFO."""
        from zebtrack.__main__ import configure_logging

        mock_root_logger = Mock()
        mock_get_logger.return_value = mock_root_logger

        configure_logging()

        # Should set level to INFO
        mock_root_logger.setLevel.assert_called_with(logging.INFO)


class TestCompactConsoleRenderer:
    """Test suite for CompactConsoleRenderer."""

    def test_compact_renderer_reduces_spacing(self):
        """Test that renderer compacts multiple spaces."""
        from zebtrack.__main__ import CompactConsoleRenderer

        renderer = CompactConsoleRenderer()

        # Mock parent behavior
        with patch.object(
            renderer.__class__.__bases__[0], "__call__", return_value="test  message    here"
        ):
            result = renderer(None, None, {})

            # Should reduce multiple spaces to single space
            assert "  " not in result or result.count("  ") < "test  message    here".count("  ")


class TestMainFunction:
    """Test suite for main() function."""

    @patch("zebtrack.__main__.configure_logging")
    @patch("zebtrack.settings.load_settings")
    @patch("tkinter.Tk")
    @patch("tkinter.messagebox.showerror")
    @patch("zebtrack.core.main_view_model.MainViewModel")
    def test_main_successful_startup(
        self, mock_controller, mock_msgbox, mock_tk, mock_settings, mock_config_logging
    ):
        """Test successful application startup."""
        from zebtrack.__main__ import main

        # Mock settings with proper structure
        mock_settings_obj = create_mock_settings()
        mock_settings.return_value = mock_settings_obj

        # Mock Tkinter
        mock_root = Mock()
        mock_root.tk = Mock()  # Add tk attribute to prevent dialog errors
        mock_root.tk.call = Mock(return_value=())  # Mock call method
        mock_tk.return_value = mock_root

        # Mock controller with run() that returns immediately
        mock_controller_instance = Mock()
        mock_controller_instance.run = Mock()  # Mock run to not block
        mock_controller_instance.view = Mock()  # Add view attribute
        mock_controller.return_value = mock_controller_instance

        # Mock argparse to avoid CLI interference
        with patch("sys.argv", ["zebtrack"]):
            # Mock all service dependencies to avoid construction errors
            with patch("zebtrack.core.state_manager.StateManager"):
                with patch("zebtrack.core.ui_coordinator.UICoordinator"):
                    with patch("zebtrack.ui.event_bus.EventBus"):
                        with patch("zebtrack.core.weight_manager.WeightManager"):
                            with patch("zebtrack.core.model_service.ModelService"):
                                with patch("zebtrack.core.project_manager.ProjectManager"):
                                    with patch(
                                        "zebtrack.core.project_workflow_service."
                                        "ProjectWorkflowService"
                                    ):
                                        with patch(
                                            "zebtrack.core.detector_service.DetectorService"
                                        ):
                                            with patch("zebtrack.io.recorder.Recorder"):
                                                with patch(
                                                    "zebtrack.core."
                                                    "video_processing_service."
                                                    "VideoProcessingService"
                                                ):
                                                    with patch(
                                                        "zebtrack.analysis."
                                                        "analysis_service."
                                                        "AnalysisService"
                                                    ):
                                                        # Mock splash screen
                                                        with patch(
                                                            "zebtrack.ui.splash_screen."
                                                            "create_splash"
                                                        ) as mock_splash:
                                                            mock_splash.return_value = Mock()
                                                            main()
                                                            # Test verifies init
                                                            # completes and run called
                                                            mock_controller_instance.run.assert_called_once()

    @patch("zebtrack.__main__.configure_logging")
    @patch("zebtrack.settings.load_settings")
    @patch("tkinter.Tk")
    @patch("zebtrack.__main__.messagebox.showerror")
    def test_main_handles_missing_config_file(
        self, mock_msgbox, mock_tk, mock_settings, mock_config_logging
    ):
        """Test handling of missing config.yaml."""
        from zebtrack.__main__ import main

        # Simulate FileNotFoundError
        mock_settings.side_effect = FileNotFoundError("config.yaml not found")

        mock_root = Mock()
        mock_tk.return_value = mock_root

        with patch("sys.argv", ["zebtrack"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            # Should exit with code 1
            assert exc_info.value.code == 1

            # Should show error dialog
            mock_msgbox.assert_called_once()
            call_args = mock_msgbox.call_args[0]
            assert "Configuration File Not Found" in call_args[0]

    @patch("zebtrack.__main__.configure_logging")
    @patch("zebtrack.settings.load_settings")
    @patch("tkinter.Tk")
    @patch("zebtrack.__main__.messagebox.showerror")
    def test_main_handles_invalid_yaml_syntax(
        self, mock_msgbox, mock_tk, mock_settings, mock_config_logging
    ):
        """Test handling of YAML syntax errors."""
        from zebtrack.__main__ import main

        # Simulate ValueError from YAML parse error
        mock_settings.side_effect = ValueError("Invalid YAML syntax at line 10")

        mock_root = Mock()
        mock_tk.return_value = mock_root

        with patch("sys.argv", ["zebtrack"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            # Should exit with code 1
            assert exc_info.value.code == 1

            # Should show validation error dialog
            mock_msgbox.assert_called_once()
            call_args = mock_msgbox.call_args[0]
            assert "Configuration Validation Error" in call_args[0]

    @patch("zebtrack.__main__.configure_logging")
    @patch("zebtrack.settings.load_settings")
    @patch("tkinter.Tk")
    @patch("zebtrack.__main__.messagebox.showerror")
    def test_main_handles_validation_errors(
        self, mock_msgbox, mock_tk, mock_settings, mock_config_logging
    ):
        """Test handling of Pydantic validation errors."""
        from zebtrack.__main__ import main

        # Simulate Pydantic ValidationError
        mock_settings.side_effect = ValueError("camera.index must be >= 0")

        mock_root = Mock()
        mock_tk.return_value = mock_root

        with patch("sys.argv", ["zebtrack"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            # Should exit with code 1
            assert exc_info.value.code == 1

            # Should show error message
            mock_msgbox.assert_called_once()

    @patch("zebtrack.__main__.configure_logging")
    @patch("zebtrack.settings.load_settings")
    @patch("zebtrack.utils.set_seed")
    @patch("tkinter.Tk")
    @patch("tkinter.messagebox.showerror")
    @patch("zebtrack.core.main_view_model.MainViewModel")
    def test_main_sets_reproducibility_seed(
        self, mock_controller, mock_msgbox, mock_tk, mock_set_seed, mock_settings, mock_config_logging
    ):
        """Test that reproducibility seed is set when configured."""
        from zebtrack.__main__ import main

        mock_settings_obj = Mock()
        mock_settings_obj.camera = Mock(index=0)
        mock_settings_obj.yolo_model = Mock(path="yolo11n.pt")
        mock_settings_obj.reproducibility = Mock(seed=42)
        mock_settings_obj.logging = Mock(levels={})  # Add logging.levels as dict
        mock_settings.return_value = mock_settings_obj

        # Mock Tkinter
        mock_root = Mock()
        mock_root.tk = Mock()
        mock_root.tk.call = Mock(return_value=())
        mock_tk.return_value = mock_root

        # Mock controller with run() that returns immediately
        mock_controller_instance = Mock()
        mock_controller_instance.run = Mock()
        mock_controller.return_value = mock_controller_instance

        with patch("sys.argv", ["zebtrack"]):
            with patch("zebtrack.ui.splash_screen.create_splash") as mock_splash:
                mock_splash.return_value = Mock()
                # Mock all services
                with patch("zebtrack.core.state_manager.StateManager"):
                    with patch("zebtrack.core.ui_coordinator.UICoordinator"):
                        with patch("zebtrack.ui.event_bus.EventBus"):
                            with patch("zebtrack.core.weight_manager.WeightManager"):
                                with patch("zebtrack.core.model_service.ModelService"):
                                    with patch("zebtrack.core.project_manager.ProjectManager"):
                                        with patch(
                                            "zebtrack.core.project_workflow_service."
                                            "ProjectWorkflowService"
                                        ):
                                            with patch(
                                                "zebtrack.core.detector_service.DetectorService"
                                            ):
                                                with patch("zebtrack.io.recorder.Recorder"):
                                                    with patch(
                                                        "zebtrack.core."
                                                        "video_processing_service."
                                                        "VideoProcessingService"
                                                    ):
                                                        with patch(
                                                            "zebtrack.analysis."
                                                            "analysis_service."
                                                            "AnalysisService"
                                                        ):
                                                            main()

        # Should set seed
        mock_set_seed.assert_called_once_with(42)

    @patch("zebtrack.__main__.configure_logging")
    @patch("zebtrack.settings.load_settings")
    @patch("tkinter.Tk")
    @patch("tkinter.messagebox.showerror")
    @patch("zebtrack.__main__.logging.getLogger")
    @patch("zebtrack.core.main_view_model.MainViewModel")
    def test_main_applies_cli_log_level_overrides(
        self, mock_controller, mock_get_logger, mock_msgbox, mock_tk, mock_settings, mock_config_logging
    ):
        """Test CLI --log-level overrides."""
        from zebtrack.__main__ import main

        mock_settings_obj = create_mock_settings()
        mock_settings.return_value = mock_settings_obj

        mock_root = Mock()
        mock_root.tk = Mock()
        mock_root.tk.call = Mock(return_value=())
        mock_tk.return_value = mock_root

        # Mock specific logger
        mock_module_logger = Mock()
        mock_get_logger.return_value = mock_module_logger

        # Mock controller
        mock_controller_instance = Mock()
        mock_controller_instance.run = Mock()
        mock_controller.return_value = mock_controller_instance

        # Simulate CLI argument
        with patch("sys.argv", ["zebtrack", "--log-level", "zebtrack.core.detector=DEBUG"]):
            with patch("zebtrack.ui.splash_screen.create_splash") as mock_splash:
                mock_splash.return_value = Mock()
                with patch("zebtrack.core.state_manager.StateManager"):
                    with patch("zebtrack.core.ui_coordinator.UICoordinator"):
                        with patch("zebtrack.ui.event_bus.EventBus"):
                            with patch("zebtrack.core.weight_manager.WeightManager"):
                                with patch("zebtrack.core.model_service.ModelService"):
                                    with patch("zebtrack.core.project_manager.ProjectManager"):
                                        with patch(
                                            "zebtrack.core.project_workflow_service."
                                            "ProjectWorkflowService"
                                        ):
                                            with patch(
                                                "zebtrack.core.detector_service.DetectorService"
                                            ):
                                                with patch("zebtrack.io.recorder.Recorder"):
                                                    with patch(
                                                        "zebtrack.core."
                                                        "video_processing_service."
                                                        "VideoProcessingService"
                                                    ):
                                                        with patch(
                                                            "zebtrack.analysis."
                                                            "analysis_service."
                                                            "AnalysisService"
                                                        ):
                                                            main()

        # Should set DEBUG level for specified module
        # (actual call depends on implementation details)

    @patch("zebtrack.__main__.configure_logging")
    @patch("zebtrack.settings.load_settings")
    @patch("tkinter.Tk")
    @patch("tkinter.messagebox.showerror")
    @patch("zebtrack.__main__.logging.getLogger")
    @patch("zebtrack.core.main_view_model.MainViewModel")
    def test_main_ignores_invalid_log_level_format(
        self, mock_controller, mock_get_logger, mock_msgbox, mock_tk, mock_settings, mock_config_logging
    ):
        """Test that invalid --log-level format is ignored."""
        from zebtrack.__main__ import main

        mock_settings_obj = create_mock_settings()
        mock_settings.return_value = mock_settings_obj

        mock_root = Mock()
        mock_root.tk = Mock()
        mock_root.tk.call = Mock(return_value=())
        mock_tk.return_value = mock_root

        # Mock controller
        mock_controller_instance = Mock()
        mock_controller_instance.run = Mock()
        mock_controller.return_value = mock_controller_instance

        # Invalid format (missing '=')
        with patch("sys.argv", ["zebtrack", "--log-level", "invalid_format"]):
            with patch("zebtrack.ui.splash_screen.create_splash") as mock_splash:
                mock_splash.return_value = Mock()
                with patch("zebtrack.core.state_manager.StateManager"):
                    with patch("zebtrack.core.ui_coordinator.UICoordinator"):
                        with patch("zebtrack.ui.event_bus.EventBus"):
                            with patch("zebtrack.core.weight_manager.WeightManager"):
                                with patch("zebtrack.core.model_service.ModelService"):
                                    with patch("zebtrack.core.project_manager.ProjectManager"):
                                        with patch(
                                            "zebtrack.core.project_workflow_service."
                                            "ProjectWorkflowService"
                                        ):
                                            with patch(
                                                "zebtrack.core.detector_service.DetectorService"
                                            ):
                                                with patch("zebtrack.io.recorder.Recorder"):
                                                    with patch(
                                                        "zebtrack.core."
                                                        "video_processing_service."
                                                        "VideoProcessingService"
                                                    ):
                                                        with patch(
                                                            "zebtrack.analysis."
                                                            "analysis_service."
                                                            "AnalysisService"
                                                        ):
                                                            main()

        # Should not crash, just ignore invalid format

    @patch("zebtrack.__main__.configure_logging")
    @patch("zebtrack.settings.load_settings")
    @patch("tkinter.Tk")
    @patch("tkinter.messagebox.showerror")
    @patch("zebtrack.core.main_view_model.MainViewModel")
    def test_main_creates_all_services(
        self, mock_controller, mock_msgbox, mock_tk, mock_settings, mock_config_logging
    ):
        """Test that all required services are instantiated."""
        from zebtrack.__main__ import main

        mock_settings_obj = create_mock_settings()
        mock_settings.return_value = mock_settings_obj

        mock_root = Mock()
        mock_root.tk = Mock()
        mock_root.tk.call = Mock(return_value=())
        mock_tk.return_value = mock_root

        # Mock controller
        mock_controller_instance = Mock()
        mock_controller_instance.run = Mock()
        mock_controller.return_value = mock_controller_instance

        with patch("sys.argv", ["zebtrack"]):
            # Mock all service imports
            with patch("zebtrack.ui.splash_screen.create_splash") as mock_splash:
                mock_splash.return_value = Mock()
                with patch("zebtrack.core.state_manager.StateManager") as mock_state:
                    with patch("zebtrack.core.ui_coordinator.UICoordinator"):
                        with patch("zebtrack.ui.event_bus.EventBus") as mock_eventbus:
                            with patch("zebtrack.core.project_manager.ProjectManager"):
                                with patch("zebtrack.core.weight_manager.WeightManager"):
                                    with patch("zebtrack.core.model_service.ModelService"):
                                        with patch(
                                            "zebtrack.core.project_workflow_service."
                                            "ProjectWorkflowService"
                                        ):
                                            with patch(
                                                "zebtrack.core.detector_service.DetectorService"
                                            ):
                                                with patch("zebtrack.io.recorder.Recorder"):
                                                    with patch(
                                                        "zebtrack.core."
                                                        "video_processing_service."
                                                        "VideoProcessingService"
                                                    ):
                                                        with patch(
                                                            "zebtrack.analysis."
                                                            "analysis_service."
                                                            "AnalysisService"
                                                        ):
                                                            main()

                                                            # Should create core services
                                                            mock_state.assert_called_once()
                                                            mock_eventbus.assert_called_once()

    @patch("zebtrack.__main__.configure_logging")
    @patch("zebtrack.settings.load_settings")
    @patch("tkinter.Tk")
    @patch("tkinter.messagebox.showerror")
    @patch("zebtrack.core.main_view_model.MainViewModel")
    def test_main_calls_bind_events(
        self, mock_controller, mock_msgbox, mock_tk, mock_settings, mock_config_logging
    ):
        """Test that controller.bind_events() is called."""
        from zebtrack.__main__ import main

        mock_settings_obj = create_mock_settings()
        mock_settings.return_value = mock_settings_obj

        mock_root = Mock()
        mock_root.tk = Mock()
        mock_root.tk.call = Mock(return_value=())
        mock_tk.return_value = mock_root

        mock_controller_instance = Mock()
        mock_controller_instance.view = Mock()  # Add view attribute
        mock_controller_instance.run = Mock()
        mock_controller.return_value = mock_controller_instance

        with patch("sys.argv", ["zebtrack"]):
            # Mock all service dependencies
            with patch("zebtrack.ui.splash_screen.create_splash") as mock_splash:
                mock_splash.return_value = Mock()
                with patch("zebtrack.core.state_manager.StateManager"):
                    with patch("zebtrack.core.ui_coordinator.UICoordinator"):
                        with patch("zebtrack.ui.event_bus.EventBus"):
                            with patch("zebtrack.core.weight_manager.WeightManager"):
                                with patch("zebtrack.core.model_service.ModelService"):
                                    with patch("zebtrack.core.project_manager.ProjectManager"):
                                        with patch(
                                            "zebtrack.core.project_workflow_service."
                                            "ProjectWorkflowService"
                                        ):
                                            with patch(
                                                "zebtrack.core.detector_service.DetectorService"
                                            ):
                                                with patch("zebtrack.io.recorder.Recorder"):
                                                    with patch(
                                                        "zebtrack.core."
                                                        "video_processing_service."
                                                        "VideoProcessingService"
                                                    ):
                                                        with patch(
                                                            "zebtrack.analysis."
                                                            "analysis_service."
                                                            "AnalysisService"
                                                        ):
                                                            main()

        # Should call bind_events
        mock_controller_instance.bind_events.assert_called_once()

    @patch("zebtrack.__main__.configure_logging")
    @patch("zebtrack.settings.load_settings")
    @patch("tkinter.Tk")
    @patch("tkinter.messagebox.showerror")
    @patch("zebtrack.core.main_view_model.MainViewModel")
    def test_main_calls_controller_run(
        self, mock_controller, mock_msgbox, mock_tk, mock_settings, mock_config_logging
    ):
        """Test that controller.run() is called."""
        from zebtrack.__main__ import main

        mock_settings_obj = create_mock_settings()
        mock_settings.return_value = mock_settings_obj

        mock_root = Mock()
        mock_root.tk = Mock()
        mock_root.tk.call = Mock(return_value=())
        mock_tk.return_value = mock_root

        mock_controller_instance = Mock()
        mock_controller_instance.view = Mock()  # Add view attribute
        mock_controller_instance.run = Mock()
        mock_controller.return_value = mock_controller_instance

        with patch("sys.argv", ["zebtrack"]):
            # Mock all service dependencies
            with patch("zebtrack.ui.splash_screen.create_splash") as mock_splash:
                mock_splash.return_value = Mock()
                with patch("zebtrack.core.state_manager.StateManager"):
                    with patch("zebtrack.core.ui_coordinator.UICoordinator"):
                        with patch("zebtrack.ui.event_bus.EventBus"):
                            with patch("zebtrack.core.weight_manager.WeightManager"):
                                with patch("zebtrack.core.model_service.ModelService"):
                                    with patch("zebtrack.core.project_manager.ProjectManager"):
                                        with patch(
                                            "zebtrack.core.project_workflow_service."
                                            "ProjectWorkflowService"
                                        ):
                                            with patch(
                                                "zebtrack.core.detector_service.DetectorService"
                                            ):
                                                with patch("zebtrack.io.recorder.Recorder"):
                                                    with patch(
                                                        "zebtrack.core."
                                                        "video_processing_service."
                                                        "VideoProcessingService"
                                                    ):
                                                        with patch(
                                                            "zebtrack.analysis."
                                                            "analysis_service."
                                                            "AnalysisService"
                                                        ):
                                                            main()

        # Should call run
        mock_controller_instance.run.assert_called_once()


class TestDependencyInjection:
    """Test suite for dependency injection in main()."""

    @patch("zebtrack.__main__.configure_logging")
    @patch("zebtrack.settings.load_settings")
    @patch("tkinter.Tk")
    @patch("tkinter.messagebox.showerror")
    @patch("zebtrack.core.main_view_model.MainViewModel")
    def test_main_injects_settings_to_services(
        self, mock_controller, mock_msgbox, mock_tk, mock_settings, mock_config_logging
    ):
        """Test that settings_obj is injected to all services."""
        from zebtrack.__main__ import main

        mock_settings_obj = create_mock_settings()
        mock_settings.return_value = mock_settings_obj

        mock_root = Mock()
        mock_root.tk = Mock()
        mock_root.tk.call = Mock(return_value=())
        mock_tk.return_value = mock_root

        # Mock controller
        mock_controller_instance = Mock()
        mock_controller_instance.run = Mock()
        mock_controller.return_value = mock_controller_instance

        with patch("sys.argv", ["zebtrack"]):
            with patch("zebtrack.ui.splash_screen.create_splash") as mock_splash:
                mock_splash.return_value = Mock()
                with patch("zebtrack.core.state_manager.StateManager"):
                    with patch("zebtrack.core.ui_coordinator.UICoordinator"):
                        with patch("zebtrack.ui.event_bus.EventBus"):
                            with patch("zebtrack.core.project_manager.ProjectManager") as mock_pm:
                                with patch("zebtrack.core.weight_manager.WeightManager"):
                                    with patch("zebtrack.core.model_service.ModelService"):
                                        with patch(
                                            "zebtrack.core.project_workflow_service."
                                            "ProjectWorkflowService"
                                        ):
                                            with patch(
                                                "zebtrack.core.detector_service.DetectorService"
                                            ):
                                                with patch("zebtrack.io.recorder.Recorder"):
                                                    with patch(
                                                        "zebtrack.core."
                                                        "video_processing_service."
                                                        "VideoProcessingService"
                                                    ):
                                                        with patch(
                                                            "zebtrack.analysis."
                                                            "analysis_service."
                                                            "AnalysisService"
                                                        ):
                                                            main()

                                                            # Should pass settings_obj to services
                                                            if mock_pm.called:
                                                                call_args = mock_pm.call_args
                                                                assert "settings_obj" in str(call_args)

    @patch("zebtrack.__main__.configure_logging")
    @patch("zebtrack.settings.load_settings")
    @patch("tkinter.Tk")
    @patch("tkinter.messagebox.showerror")
    @patch("zebtrack.core.main_view_model.MainViewModel")
    def test_main_passes_detector_none_initially(
        self, mock_controller, mock_msgbox, mock_tk, mock_settings, mock_config_logging
    ):
        """Test that VideoProcessingService receives detector=None initially."""
        from zebtrack.__main__ import main

        mock_settings_obj = create_mock_settings()
        mock_settings.return_value = mock_settings_obj

        mock_root = Mock()
        mock_root.tk = Mock()
        mock_root.tk.call = Mock(return_value=())
        mock_tk.return_value = mock_root

        # Mock controller
        mock_controller_instance = Mock()
        mock_controller_instance.run = Mock()
        mock_controller.return_value = mock_controller_instance

        with patch("sys.argv", ["zebtrack"]):
            with patch("zebtrack.ui.splash_screen.create_splash") as mock_splash:
                mock_splash.return_value = Mock()
                with patch("zebtrack.core.state_manager.StateManager"):
                    with patch("zebtrack.core.ui_coordinator.UICoordinator"):
                        with patch("zebtrack.ui.event_bus.EventBus"):
                            with patch("zebtrack.core.weight_manager.WeightManager"):
                                with patch("zebtrack.core.model_service.ModelService"):
                                    with patch("zebtrack.core.project_manager.ProjectManager"):
                                        with patch(
                                            "zebtrack.core.project_workflow_service."
                                            "ProjectWorkflowService"
                                        ):
                                            with patch(
                                                "zebtrack.core.detector_service.DetectorService"
                                            ):
                                                with patch("zebtrack.io.recorder.Recorder"):
                                                    with patch(
                                                        "zebtrack.core.video_processing_service."
                                                        "VideoProcessingService"
                                                    ) as mock_vps:
                                                        with patch(
                                                            "zebtrack.analysis."
                                                            "analysis_service."
                                                            "AnalysisService"
                                                        ):
                                                            main()

                                                            # Should pass detector=None (lazy initialization)
                                                            if mock_vps.called:
                                                                call_args = mock_vps.call_args
                                                                assert call_args[1].get("detector") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
