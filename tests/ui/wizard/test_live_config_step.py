"""Tests for wizard Step 3 (Live Configuration).

Validates that the experimental design metadata fields (group/day/subject/
is_batch_last_session) are no longer collected by the live wizard step --
those values now come from the project batch grid defined in Step 2.
"""

from typing import Any

import pytest

from zebtrack.core.services.wizard_service import WizardService
from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.ui.wizard.live_config_step import LiveConfigStep


@pytest.mark.gui
class TestLiveConfigStep:
    """Tests for the live recording configuration step."""

    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies):
        self.root = wizard_dependencies["root"]

    def test_live_config_step_builds_ui_without_error(self):
        wizard_data: dict[str, Any] = {}
        step = LiveConfigStep(self.root, wizard_data)
        step.build_ui()
        assert step.step_id == WizardStepID.LIVE_CONFIG

    def test_get_data_omits_experimental_metadata_fields(self):
        """`get_data()` must not expose the legacy experimental design keys.

        Group/day/subject/is_batch_last_session belong to the project batch
        grid (Step 2) -- exposing them here duplicated state and let the user
        drift the live session metadata away from the slot being recorded.
        """
        wizard_data: dict[str, Any] = {}
        step = LiveConfigStep(self.root, wizard_data)
        step.build_ui()

        data = step.get_data()

        for legacy_key in (
            "experimental_group",
            "experiment_day",
            "subject_id",
            "is_batch_last_session",
        ):
            assert legacy_key not in data, (
                f"{legacy_key!r} leaked into LiveConfigStep.get_data(); it must "
                "be sourced from the batch grid (Step 2), not the live config step."
            )

    def test_step_does_not_define_experimental_design_vars(self):
        wizard_data: dict[str, Any] = {}
        step = LiveConfigStep(self.root, wizard_data)
        step.build_ui()

        for attr in (
            "experimental_group_var",
            "experiment_day_var",
            "subject_id_var",
            "is_batch_last_session_var",
        ):
            assert not hasattr(step, attr), (
                f"LiveConfigStep should not own {attr!r}; the field was removed "
                "when the redundant experimental design box was dropped."
            )

    def test_step_does_not_define_processing_interval_vars(self):
        """Intervals moved to CalibrationStep to mirror the pre-recorded flow."""
        wizard_data: dict[str, Any] = {}
        step = LiveConfigStep(self.root, wizard_data)
        step.build_ui()

        for attr in ("analysis_interval_var", "display_interval_var"):
            assert not hasattr(step, attr), (
                f"LiveConfigStep should not own {attr!r}; intervals are now "
                "collected by CalibrationStep so live and pre-recorded "
                "projects share the same configuration surface."
            )

    def test_get_data_omits_processing_intervals(self):
        """``get_data`` must not emit interval keys — that's CalibrationStep's job now."""
        wizard_data: dict[str, Any] = {}
        step = LiveConfigStep(self.root, wizard_data)
        step.build_ui()

        data = step.get_data()

        for legacy_key in ("analysis_interval_frames", "display_interval_frames"):
            assert legacy_key not in data, (
                f"{legacy_key!r} leaked into LiveConfigStep.get_data(); intervals "
                "now belong to CalibrationStep."
            )

    def test_restore_advanced_settings_tolerates_legacy_interval_keys(self):
        """Loading a legacy project_data dict that still carries the interval keys
        must not crash this step — they are silently ignored (CalibrationStep
        will pick them up via its own set_data/on_show)."""
        wizard_data: dict[str, Any] = {}
        step = LiveConfigStep(self.root, wizard_data)
        step.build_ui()

        # Must not raise even though the keys are no longer mapped to vars.
        step._restore_advanced_settings(
            {
                "analysis_interval_frames": 25,
                "display_interval_frames": 30,
                "preserve_real_aquarium_shape": True,
            }
        )

        assert step.preserve_real_aquarium_shape_var.get() is True

    def test_set_data_does_not_crash_on_legacy_batch_metadata(self):
        """Copilot review: ``set_data()`` used to call
        ``_restore_batch_metadata`` which touched ``experimental_group_var``
        et al — but those Tk vars were removed when the redundant
        experimental-design block was dropped. Back-navigation or loading
        legacy project data containing those keys would raise AttributeError.

        Fix: ``_restore_batch_metadata`` removed and its call site dropped.
        This test guards the regression by feeding all four legacy keys
        into set_data — it must complete without exception."""
        wizard_data: dict[str, Any] = {}
        step = LiveConfigStep(self.root, wizard_data)
        step.build_ui()

        # Must not raise.
        step.set_data(
            {
                "camera_index": 0,
                "use_arduino": False,
                "use_timed_recording": True,
                "recording_duration_s": 300.0,
                "use_countdown": True,
                "countdown_duration_s": 10,
                # Legacy batch metadata that used to populate removed vars:
                "experimental_group": "Controle",
                "experiment_day": "Dia_1",
                "subject_id": "1",
                "is_batch_last_session": False,
            }
        )

        # And the step still must not own the removed vars.
        for attr in (
            "experimental_group_var",
            "experiment_day_var",
            "subject_id_var",
            "is_batch_last_session_var",
        ):
            assert not hasattr(step, attr)


@pytest.mark.gui
class TestLiveConfigTemplateReconcile:
    """Hardware reconciliation when a template seeds the live-config step.

    A template may carry a camera/Arduino chosen on another machine. On load we
    auto-detect the host hardware once and reconcile: present devices are
    selected, absent ones degrade gracefully (fallback + warning) instead of
    being applied blindly.
    """

    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies):
        self.root = wizard_dependencies["root"]

    @staticmethod
    def _one_camera():
        return [{"index": 0, "description": "USB Cam", "friendly_name": "USB Cam Real"}]

    def test_template_camera_unavailable_falls_back_and_warns(self, monkeypatch):
        monkeypatch.setattr(
            WizardService, "detect_available_cameras", lambda *a, **k: self._one_camera()
        )
        wizard_data: dict[str, Any] = {
            "template_metadata": {"name": "T"},
            "camera_friendly_name": "Camera Que Nao Existe",
            "camera_index": 9,
        }
        step = LiveConfigStep(self.root, wizard_data)
        step.build_ui()

        step.on_show()

        # Saved camera absent → fall back to the only available one + warn.
        assert step.camera_selection_var.get() == "USB Cam"
        assert "indispon" in step.camera_status_label.cget("text").lower()

    def test_template_camera_available_is_selected_without_warning(self, monkeypatch):
        monkeypatch.setattr(
            WizardService, "detect_available_cameras", lambda *a, **k: self._one_camera()
        )
        wizard_data: dict[str, Any] = {
            "template_metadata": {"name": "T"},
            "camera_friendly_name": "USB Cam Real",
            "camera_index": 0,
        }
        step = LiveConfigStep(self.root, wizard_data)
        step.build_ui()

        step.on_show()

        assert step.camera_selection_var.get() == "USB Cam"
        assert "indispon" not in step.camera_status_label.cget("text").lower()

    def test_template_arduino_port_unavailable_is_cleared_and_blocks_validation(self, monkeypatch):
        monkeypatch.setattr(WizardService, "detect_available_cameras", lambda *a, **k: [])
        monkeypatch.setattr(
            WizardService,
            "detect_arduino_ports",
            lambda *a, **k: [{"display_name": "COM3 - Arduino", "device": "COM3"}],
        )
        wizard_data: dict[str, Any] = {
            "template_metadata": {"name": "T"},
            "use_arduino": True,
            "arduino_port": "COM99",  # absent on this machine
        }
        step = LiveConfigStep(self.root, wizard_data)
        step.build_ui()

        step.on_show()

        # Phantom port cleared + warned, not silently carried.
        assert step.arduino_port_var.get() == ""
        assert "indispon" in step.arduino_status_label.cget("text").lower()

        # End-to-end safety: validation blocks advancing (Arduino on, no port).
        is_valid, _msg = WizardService.validate_live_config(step.get_data())
        assert is_valid is False

    def test_template_arduino_port_available_is_selected(self, monkeypatch):
        monkeypatch.setattr(WizardService, "detect_available_cameras", lambda *a, **k: [])
        monkeypatch.setattr(
            WizardService,
            "detect_arduino_ports",
            lambda *a, **k: [{"display_name": "COM3 - Arduino", "device": "COM3"}],
        )
        wizard_data: dict[str, Any] = {
            "template_metadata": {"name": "T"},
            "use_arduino": True,
            "arduino_port": "COM3",
        }
        step = LiveConfigStep(self.root, wizard_data)
        step.build_ui()

        step.on_show()

        assert step.arduino_port_var.get() == "COM3 - Arduino"
        assert "indispon" not in step.arduino_status_label.cget("text").lower()

    def test_no_template_metadata_skips_reconciliation(self, monkeypatch):
        """Normal flow (no template): must not force detection or warn."""
        calls = {"camera": 0}

        def _spy(*_a, **_k):
            calls["camera"] += 1
            return self._one_camera()

        monkeypatch.setattr(WizardService, "detect_available_cameras", _spy)
        wizard_data: dict[str, Any] = {"camera_index": 0}  # no template_metadata
        step = LiveConfigStep(self.root, wizard_data)
        step.build_ui()

        step.on_show()

        assert calls["camera"] == 0
        assert step.camera_selection_var.get() == ""
