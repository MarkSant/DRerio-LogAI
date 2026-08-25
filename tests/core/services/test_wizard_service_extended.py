"""
Extended unit tests for WizardService.

Tests validation, hardware discovery edge cases, interval calculation,
camera index resolution, and multi-aquarium configuration rules.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, ClassVar, cast
from unittest.mock import MagicMock, patch

import numpy as np

from zebtrack.core.services.wizard_service import WizardService
from zebtrack.ui.wizard.models import MultiAquariumData


class TestWizardServiceValidation:
    """Test all validation methods in WizardService."""

    def test_validate_live_config_success(self):
        data = {
            "camera_index": 0,
            "use_arduino": True,
            "arduino_port": "COM3",
            "use_timed_recording": True,
            "recording_duration_s": 300.0,
            "use_countdown": True,
            "countdown_duration_s": 10,
            "external_trigger_mode": True,
        }
        valid, msg = WizardService.validate_live_config(data)
        assert valid is True
        assert msg == ""

    def test_validate_live_config_invalid_camera(self):
        # Missing or non-int
        valid, msg = WizardService.validate_live_config({"camera_index": None})
        assert valid is False
        assert "camera" in msg.lower()

        valid, msg = WizardService.validate_live_config({"camera_index": "0"})
        assert valid is False

        # Out of bounds
        valid, msg = WizardService.validate_live_config({"camera_index": -1})
        assert valid is False

        valid, msg = WizardService.validate_live_config({"camera_index": 11})
        assert valid is False

    def test_validate_live_config_arduino_errors(self):
        # Arduino enabled but no port
        valid, msg = WizardService.validate_live_config(
            {"camera_index": 0, "use_arduino": True, "arduino_port": ""}
        )
        assert valid is False
        assert "arduino" in msg.lower()

        # External trigger without Arduino
        valid, msg = WizardService.validate_live_config(
            {"camera_index": 0, "use_arduino": False, "external_trigger_mode": True}
        )
        assert valid is False
        assert "external trigger" in msg.lower()

    def test_validate_live_config_timed_recording_errors(self):
        # Zero or negative duration
        valid, msg = WizardService.validate_live_config(
            {"camera_index": 0, "use_timed_recording": True, "recording_duration_s": 0}
        )
        assert valid is False

        valid, msg = WizardService.validate_live_config(
            {"camera_index": 0, "use_timed_recording": True, "recording_duration_s": -5}
        )
        assert valid is False

        # Exceeds max 7200s (2 hours)
        valid, msg = WizardService.validate_live_config(
            {"camera_index": 0, "use_timed_recording": True, "recording_duration_s": 7201}
        )
        assert valid is False

    def test_validate_live_config_countdown_errors(self):
        valid, msg = WizardService.validate_live_config(
            {"camera_index": 0, "use_countdown": True, "countdown_duration_s": 0}
        )
        assert valid is False

        valid, msg = WizardService.validate_live_config(
            {"camera_index": 0, "use_countdown": True, "countdown_duration_s": 61}
        )
        assert valid is False

    def test_validate_experimental_design_success(self):
        data = {
            "experiment_days": 5,
            "num_groups": 2,
            "subjects_per_group": 10,
            "group_names": ["Control", "Treated"],
        }
        valid, msg = WizardService.validate_experimental_design(data)
        assert valid is True
        assert msg == ""

    def test_validate_experimental_design_failures(self):
        # Invalid days
        valid, _ = WizardService.validate_experimental_design({"experiment_days": 0})
        assert valid is False
        valid, _ = WizardService.validate_experimental_design({"experiment_days": 366})
        assert valid is False

        # Invalid num_groups
        valid, _ = WizardService.validate_experimental_design(
            {"experiment_days": 1, "num_groups": 0}
        )
        assert valid is False
        valid, _ = WizardService.validate_experimental_design(
            {"experiment_days": 1, "num_groups": 7}
        )
        assert valid is False

        # Invalid subjects_per_group
        valid, _ = WizardService.validate_experimental_design(
            {"experiment_days": 1, "num_groups": 2, "subjects_per_group": 0}
        )
        assert valid is False
        valid, _ = WizardService.validate_experimental_design(
            {"experiment_days": 1, "num_groups": 2, "subjects_per_group": 21}
        )
        assert valid is False

        # Invalid group_names
        valid, _ = WizardService.validate_experimental_design(
            {"experiment_days": 1, "num_groups": 2, "subjects_per_group": 5, "group_names": "bad"}
        )
        assert valid is False

        # Length mismatch
        valid, _ = WizardService.validate_experimental_design(
            {
                "experiment_days": 1,
                "num_groups": 2,
                "subjects_per_group": 5,
                "group_names": ["OnlyOne"],
            }
        )
        assert valid is False

        # Duplicate names
        valid, _ = WizardService.validate_experimental_design(
            {
                "experiment_days": 1,
                "num_groups": 2,
                "subjects_per_group": 5,
                "group_names": ["A", "A"],
            }
        )
        assert valid is False

        # Empty group name
        valid, _ = WizardService.validate_experimental_design(
            {
                "experiment_days": 1,
                "num_groups": 2,
                "subjects_per_group": 5,
                "group_names": ["A", "   "],
            }
        )
        assert valid is False

    def test_validate_calibration_data_success_and_failures(self):
        valid_data = {
            "num_aquariums": 1,
            "animals_per_aquarium": 1,
            "aquarium_width_cm": 30.0,
            "aquarium_height_cm": 15.0,
            "analysis_interval_frames": 10,
            "display_interval_frames": 2,
            "roi_inclusion_rule": "centroid_in",
        }
        valid, msg = WizardService.validate_calibration_data(valid_data)
        assert valid is True
        assert msg == ""

        # Aquariums out of range
        d = dict(valid_data, num_aquariums=0)
        assert WizardService.validate_calibration_data(d)[0] is False
        d = dict(valid_data, num_aquariums=101)
        assert WizardService.validate_calibration_data(d)[0] is False

        # Animals out of range
        d = dict(valid_data, animals_per_aquarium=0)
        assert WizardService.validate_calibration_data(d)[0] is False
        d = dict(valid_data, animals_per_aquarium=101)
        assert WizardService.validate_calibration_data(d)[0] is False

        # Dimensions <= 0
        d = dict(valid_data, aquarium_width_cm=0)
        assert WizardService.validate_calibration_data(d)[0] is False
        d = dict(valid_data, aquarium_height_cm=-1.0)
        assert WizardService.validate_calibration_data(d)[0] is False

        # Intervals
        d = dict(valid_data, analysis_interval_frames=0)
        assert WizardService.validate_calibration_data(d)[0] is False
        d = dict(valid_data, display_interval_frames=31)
        assert WizardService.validate_calibration_data(d)[0] is False

        # Invalid roi_inclusion_rule
        d = dict(valid_data, roi_inclusion_rule="invalid_rule")
        assert WizardService.validate_calibration_data(d)[0] is False

    def test_validate_basic_calibration(self):
        valid, msg = WizardService.validate_basic_calibration(
            {
                "num_aquariums": 2,
                "animals_per_aquarium": 1,
                "aquarium_width_cm": 25.0,
                "aquarium_height_cm": 15.0,
            }
        )
        assert valid is True

        assert (
            WizardService.validate_basic_calibration(
                {
                    "num_aquariums": 0,
                    "animals_per_aquarium": 1,
                    "aquarium_width_cm": 10,
                    "aquarium_height_cm": 10,
                }
            )[0]
            is False
        )
        assert (
            WizardService.validate_basic_calibration(
                {
                    "num_aquariums": 105,
                    "animals_per_aquarium": 1,
                    "aquarium_width_cm": 10,
                    "aquarium_height_cm": 10,
                }
            )[0]
            is False
        )
        assert (
            WizardService.validate_basic_calibration(
                {
                    "num_aquariums": 1,
                    "animals_per_aquarium": 0,
                    "aquarium_width_cm": 10,
                    "aquarium_height_cm": 10,
                }
            )[0]
            is False
        )
        assert (
            WizardService.validate_basic_calibration(
                {
                    "num_aquariums": 1,
                    "animals_per_aquarium": 105,
                    "aquarium_width_cm": 10,
                    "aquarium_height_cm": 10,
                }
            )[0]
            is False
        )
        # Largura 0 é VÁLIDA: ``ProjectLifecycleManager`` documenta zero como
        # "sem calibração" (análise em pixels). Esta asserção esperava False e
        # com isso fixava um bug — o assistente recusava a única forma de
        # exprimir um projeto não calibrado, embora o domínio a suporte.
        assert (
            WizardService.validate_basic_calibration(
                {
                    "num_aquariums": 1,
                    "animals_per_aquarium": 1,
                    "aquarium_width_cm": 0,
                    "aquarium_height_cm": 10,
                }
            )[0]
            is True
        )
        assert (
            WizardService.validate_basic_calibration(
                {
                    "num_aquariums": 1,
                    "animals_per_aquarium": 1,
                    "aquarium_width_cm": 10,
                    "aquarium_height_cm": -1,
                }
            )[0]
            is False
        )


class TestWizardServiceMultiAquariumValidation:
    """Test validate_multi_aquarium_config."""

    def test_disabled_multi_aquarium(self):
        config = MultiAquariumData(enabled=False)
        valid, errors, warnings = WizardService.validate_multi_aquarium_config(config)
        assert valid is True
        assert errors == []
        assert warnings == []

    def test_dict_config_enabled_with_wrong_count(self):
        dict_config = {"enabled": True, "aquarium_configs": []}
        valid, errors, _ = WizardService.validate_multi_aquarium_config(dict_config)  # type: ignore[arg-type]
        assert valid is False
        assert any("2 aquariums" in err for err in errors)

    def test_dict_config_small_polygon_warning_and_overlap_warning(self):
        # Small polygon area (< 10000 px^2)
        small_poly = [(0, 0), (20, 0), (20, 20), (0, 20)]
        overlap_poly = [(10, 10), (30, 10), (30, 30), (10, 30)]

        dict_config = {
            "enabled": True,
            "aquarium_configs": [
                {"aquarium_id": 0, "name": "Aq0", "group": "G1", "polygon": small_poly},
                {"aquarium_id": 1, "name": "Aq1", "group": "G2", "polygon": overlap_poly},
            ],
            "regex_pattern": "",
        }
        valid, errors, warnings = WizardService.validate_multi_aquarium_config(dict_config)  # type: ignore[arg-type]
        assert valid is True
        assert len(warnings) >= 2  # area warning + overlap warning


class TestWizardServiceHardwareAndIntervals:
    """Test camera and arduino hardware discovery routines."""

    def setup_method(self):
        WizardService.clear_hardware_cache()

    def teardown_method(self):
        WizardService.clear_hardware_cache()

    def test_suggest_analysis_interval(self):
        assert WizardService.suggest_analysis_interval(0.0) == 10
        assert WizardService.suggest_analysis_interval(-5.0) == 10
        assert WizardService.suggest_analysis_interval(30.0) == 10
        assert WizardService.suggest_analysis_interval(60.0) == 20
        assert WizardService.suggest_analysis_interval(120.0) == 40

    def test_resolve_camera_index_legacy(self):
        index, status = WizardService.resolve_camera_index(2, "")
        assert index == 2
        assert status == "MATCH"

    @patch("zebtrack.core.services.wizard_service.WizardService._get_dshow_friendly_names")
    def test_resolve_camera_index_matching_and_shifted(self, mock_dshow):
        mock_dshow.return_value = ["Integrated Webcam", "USB Camera"]

        # Exact match
        index, status = WizardService.resolve_camera_index(0, "Integrated Webcam")
        assert index == 0
        assert status == "MATCH"

        # Shifted index
        index, status = WizardService.resolve_camera_index(0, "USB Camera")
        assert index == 1
        assert status == "SHIFTED"

        # Missing
        index, status = WizardService.resolve_camera_index(0, "Nonexistent Cam")
        assert index == 0
        assert status == "MISSING"

    @patch("zebtrack.io.arduino.Arduino.scan_available_ports")
    def test_detect_arduino_ports_with_fallback_and_settings(self, mock_scan):
        mock_port1 = MagicMock(device="COM1", description="USB Serial")
        mock_port2 = MagicMock(device="COM2", description="Arduino Nano")
        mock_scan.return_value = ([mock_port2], [mock_port1])

        settings = SimpleNamespace(arduino=SimpleNamespace(baud_rate=115200))
        ports = WizardService.detect_arduino_ports(
            use_cache=False, settings_obj=cast(Any, settings)
        )

        assert len(ports) == 2
        assert ports[0]["device"] == "COM2"
        assert ports[0]["has_handshake"] is True
        assert ports[1]["device"] == "COM1"
        assert ports[1]["has_handshake"] is False

    @patch("zebtrack.io.arduino.Arduino.scan_available_ports")
    @patch("serial.tools.list_ports.comports")
    def test_detect_arduino_ports_fallback_only(self, mock_comports, mock_scan):
        mock_scan.return_value = ([], [])
        mock_port = MagicMock(device="COM4", description="Generic Serial")
        mock_comports.return_value = [mock_port]

        ports = WizardService.detect_arduino_ports(use_cache=False)
        assert len(ports) == 1
        assert ports[0]["device"] == "COM4"
        assert ports[0]["has_handshake"] is False

    @patch("cv2.VideoCapture")
    @patch("zebtrack.core.services.wizard_service.WizardService._get_dshow_friendly_names")
    def test_detect_available_cameras_black_frame_rejection(self, mock_dshow, mock_cap_class):
        mock_dshow.return_value = ["Webcam"]
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        # Black frame (mean = 0.0)
        black_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, black_frame)
        mock_cap_class.return_value = mock_cap

        cameras = WizardService.detect_available_cameras(use_cache=False)
        assert len(cameras) == 0  # Rejects black frame


class TestBasicCalibrationMatchesTheDomain:
    """O assistente e a criação de projeto precisam recusar as MESMAS coisas.

    Enquanto as faixas viviam só em ``ProjectLifecycleManager``, um intervalo
    fora delas atravessava os cinco passos do assistente e só era recusado na
    criação — por um ``ValueError`` cru que o event bus engolia. O usuário
    clicava em "Criar Projeto", a janela fechava, e não havia projeto nem
    mensagem.
    """

    BASE: ClassVar[dict[str, Any]] = {
        "num_aquariums": 1,
        "animals_per_aquarium": 1,
        "aquarium_width_cm": 10.0,
        "aquarium_height_cm": 10.0,
    }

    def _check(self, **overrides):
        return WizardService.validate_basic_calibration({**self.BASE, **overrides})

    def test_interval_above_domain_maximum_is_rejected(self):
        """60 é o valor plausível que a própria dica do campo sugeria."""
        valid, msg = self._check(analysis_interval_frames=60, display_interval_frames=10)
        assert valid is False
        assert "30" in msg, "a mensagem precisa dizer qual é o limite"

    def test_interval_zero_is_rejected(self):
        """Intervalo 0 chega a ``frame % 0`` na análise: ZeroDivisionError."""
        assert self._check(analysis_interval_frames=0, display_interval_frames=10)[0] is False

    def test_negative_interval_is_rejected(self):
        assert self._check(analysis_interval_frames=-5, display_interval_frames=10)[0] is False

    def test_display_interval_is_checked_too(self):
        assert self._check(analysis_interval_frames=10, display_interval_frames=99)[0] is False

    def test_boolean_is_not_a_valid_interval(self):
        """``True`` é ``int`` em Python e passaria pela faixa 1..30 sem o guarda."""
        assert self._check(analysis_interval_frames=True, display_interval_frames=10)[0] is False

    def test_interval_inside_the_range_passes(self):
        assert self._check(analysis_interval_frames=1, display_interval_frames=30) == (True, "")
        assert self._check(analysis_interval_frames=30, display_interval_frames=1) == (True, "")

    def test_missing_intervals_are_not_invented(self):
        """Passos que não coletam intervalo não podem ser reprovados por isso."""
        assert self._check() == (True, "")

    def test_zero_dimension_means_no_calibration_and_is_accepted(self):
        assert self._check(aquarium_width_cm=0.0, aquarium_height_cm=0.0) == (True, "")

    def test_dimension_above_domain_maximum_is_rejected(self):
        valid, msg = self._check(aquarium_width_cm=900.0)
        assert valid is False
        assert "500" in msg

    def test_negative_dimension_is_rejected(self):
        assert self._check(aquarium_height_cm=-0.5)[0] is False

    def test_the_wizard_accepts_exactly_what_the_domain_accepts(self):
        """Amarra os dois validadores: divergir é o bug, não o detalhe."""
        from zebtrack.core.project.project_lifecycle_manager import ProjectLifecycleManager

        for interval in (0, 1, 15, 30, 31, 60):
            wizard_ok = self._check(analysis_interval_frames=interval, display_interval_frames=10)[
                0
            ]
            try:
                ProjectLifecycleManager.validate_project_parameters(
                    num_aquariums=1,
                    animals_per_aquarium=1,
                    aquarium_width_cm=10.0,
                    aquarium_height_cm=10.0,
                    analysis_interval_frames=interval,
                    display_interval_frames=10,
                    camera_index=0,
                    project_type="Pre-recorded",
                    video_files=["a.mp4"],
                )
                domain_ok = True
            except ValueError:
                domain_ok = False

            assert wizard_ok == domain_ok, (
                f"intervalo {interval}: assistente={wizard_ok}, domínio={domain_ok}"
            )
