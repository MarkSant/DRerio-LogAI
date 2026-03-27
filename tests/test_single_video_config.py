from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.settings import BehavioralAnalysisSettings, Settings
from zebtrack.ui.dialogs.single_video_config_dialog import SingleVideoConfigDialog


class TestSingleVideoConfigPersistence:
    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock(spec=Settings)
        # Create a real BehavioralAnalysisSettings object to test its mutation
        settings.behavioral_analysis = BehavioralAnalysisSettings(
            default_thigmotaxis_distance_cm=1.5,
            default_geotaxis_distance_cm=1.5,
            default_geotaxis_num_zones=3,
            default_geotaxis_bottom_zones=1,
            aquarium_perspective="lateral",
            geotaxis_mode="zones",
        )
        settings.roi_inclusion_rule = "bbox_intersects"
        settings.roi_buffer_radius_value = 0.5
        settings.roi_min_bbox_overlap_ratio = 0.1
        return settings

    @pytest.fixture
    def mock_gui(self):
        gui = MagicMock()
        gui.root = MagicMock()
        return gui

    def test_apply_persists_behavioral_settings(self, mock_settings, mock_gui):
        """
        Verify that SingleVideoConfigDialog.apply() correctly updates
        the Settings object with values from the behavioral config widget.
        """
        with patch(
            "zebtrack.ui.dialogs.single_video_config_dialog.SingleVideoConfigDialog.__init__",
            return_value=None,
        ):
            dialog = SingleVideoConfigDialog(mock_gui, mock_settings)

            # Set attributes required by apply()
            dialog.settings = mock_settings
            dialog_any = cast(Any, dialog)
            dialog_any.result = None

            # behavioral_config_widget (correct attribute name used by apply())
            dialog_any.behavioral_config_widget = MagicMock()
            dialog_any.behavioral_config_widget.get_values = MagicMock(
                return_value={
                    "aquarium_perspective": "lateral",
                    "geotaxis_mode": "zones",
                    "geotaxis_num_zones": 4,
                    "geotaxis_bottom_zones": 1,
                    "thigmotaxis_distance_cm": 2.0,
                    "geotaxis_distance_cm": 1.0,
                }
            )

            # Mock all tk variable attributes read by apply()
            dialog.video_path_var = MagicMock(get=MagicMock(return_value="c:/video.mp4"))
            dialog.num_aquariums_var = MagicMock(get=MagicMock(return_value="1"))
            dialog.analysis_interval_var = MagicMock(get=MagicMock(return_value="10"))
            dialog.display_interval_var = MagicMock(get=MagicMock(return_value="10"))
            dialog.animals_per_aquarium_var = MagicMock(get=MagicMock(return_value="1"))
            dialog.aquarium_width_var = MagicMock(get=MagicMock(return_value="20.0"))
            dialog.aquarium_height_var = MagicMock(get=MagicMock(return_value="10.0"))
            dialog.sharp_turn_var = MagicMock(get=MagicMock(return_value="90"))
            dialog.freeze_thresh_var = MagicMock(get=MagicMock(return_value="0.5"))
            dialog.freeze_dur_var = MagicMock(get=MagicMock(return_value="1.0"))
            dialog.smoothing_window_var = MagicMock(get=MagicMock(return_value="5"))
            dialog.smoothing_polyorder_var = MagicMock(get=MagicMock(return_value="2"))
            dialog.aquarium_method_var = MagicMock(get=MagicMock(return_value="seg"))
            dialog.animal_method_var = MagicMock(get=MagicMock(return_value="det"))
            dialog.use_openvino_var = MagicMock(get=MagicMock(return_value=False))

            SingleVideoConfigDialog.apply(dialog)

            # Verify behavioral settings were persisted to the Settings object
            assert mock_settings.behavioral_analysis.aquarium_perspective == "lateral"
            assert mock_settings.behavioral_analysis.geotaxis_mode == "zones"
            assert mock_settings.behavioral_analysis.default_geotaxis_num_zones == 4
            assert mock_settings.behavioral_analysis.default_thigmotaxis_distance_cm == 2.0
            assert mock_settings.behavioral_analysis.default_geotaxis_distance_cm == 1.0

            # Verify result dict was set
            assert dialog.result is not None
            assert dialog.result["video_path"] == "c:/video.mp4"
            assert dialog.result["behavioral_analysis"]["aquarium_perspective"] == "lateral"
            assert dialog.result["behavioral_analysis"]["geotaxis_num_zones"] == 4
