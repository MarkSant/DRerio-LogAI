"""Tests for wizard Step 3 (Live Configuration).

Validates that the experimental design metadata fields (group/day/subject/
is_batch_last_session) are no longer collected by the live wizard step --
those values now come from the project batch grid defined in Step 2.
"""

import threading
from typing import Any, cast

import pytest
from tests.utils.deferring_tk import bind_deferring_tk
from tests.utils.wait_helpers import drain_background_tasks

from zebtrack.core.services.wizard_service import WizardService
from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.ui.wizard.live_config_step import (
    LiveConfigStep,
    analysis_window_hint,
    pick_default_arduino_port,
)


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

    def test_legacy_trigger_checkbox_stays_and_points_at_the_window_editor(self):
        """v8 keeps the legacy checkbox and adds a hint to the analysis-window panel."""
        step = LiveConfigStep(self.root, {})
        step.build_ui()

        assert step.external_trigger_cb.cget("text") == "External Trigger Mode"
        hint = str(step.analysis_window_hint_label.cget("text"))
        assert hint == analysis_window_hint()
        assert "'Analysis Window' panel of the Zone Configuration tab" in hint
        assert step.analysis_window_hint_label.winfo_manager() == "pack"

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
        drain_background_tasks(self.root)

        # Saved camera absent → fall back to the only available one + warn.
        assert step.camera_selection_var.get() == "USB Cam"
        assert "unavailable" in step.camera_status_label.cget("text").lower()

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
        drain_background_tasks(self.root)

        assert step.camera_selection_var.get() == "USB Cam"
        assert "unavailable" not in step.camera_status_label.cget("text").lower()

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
        drain_background_tasks(self.root)

        # Phantom port cleared + warned, not silently carried.
        assert step.arduino_port_var.get() == ""
        assert "unavailable" in step.arduino_status_label.cget("text").lower()

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
        drain_background_tasks(self.root)

        assert step.arduino_port_var.get() == "COM3 - Arduino"
        assert "unavailable" not in step.arduino_status_label.cget("text").lower()

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
        drain_background_tasks(self.root)

        assert calls["camera"] == 0
        assert step.camera_selection_var.get() == ""


@pytest.mark.gui
class TestLiveConfigDetectionOffTk:
    """A6-04/A6-05: the template restore detects hardware off the Tk thread.

    The step's ``after``/``winfo_exists`` are routed to a ``DeferringTk`` so the
    test decides when the Tk loop turns: before that, only "Detecting..." may be
    on screen, and the hardware call must have run on a worker thread.
    """

    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies):
        self.root = wizard_dependencies["root"]

    def _step(self, wizard_data=None):
        step = LiveConfigStep(self.root, wizard_data if wizard_data is not None else {})
        step.build_ui()
        return step, bind_deferring_tk(step)

    def test_template_restore_detects_off_tk_then_replays_on_tk(self, monkeypatch):
        """``set_data`` must wait for the maps: it matches the saved devices against them."""
        threads: list = []

        def _cams(*_a, **_k):
            threads.append(("cam", threading.current_thread()))
            return [{"index": 0, "description": "USB Cam", "friendly_name": "USB Cam Real"}]

        def _ports(*_a, **_k):
            threads.append(("port", threading.current_thread()))
            return [{"display_name": "COM3 - Arduino", "device": "COM3"}]

        monkeypatch.setattr(WizardService, "detect_available_cameras", _cams)
        monkeypatch.setattr(WizardService, "detect_arduino_ports", _ports)
        step, tk_loop = self._step(
            {
                "template_metadata": {"name": "T"},
                "camera_friendly_name": "USB Cam Real",
                "use_arduino": True,
                "arduino_port": "COM3",
            }
        )

        step._restore_from_template_once()
        assert step._hw_restored_from_template is True
        assert step.camera_status_label.cget("text") == "Detecting..."
        assert step.arduino_status_label.cget("text") == "Detecting..."
        assert step.camera_selection_var.get() == ""

        step._restore_from_template_once()  # one-shot: a second show does not rescan
        tk_loop.run_until_idle()

        assert [kind for kind, _t in threads] == ["cam", "port"]
        assert all(t is not threading.main_thread() for _k, t in threads)
        assert step.camera_selection_var.get() == "USB Cam"
        assert step.use_arduino_var.get() is True
        assert step.arduino_port_var.get() == "COM3 - Arduino"

    def test_template_restore_without_arduino_skips_the_port_scan(self, monkeypatch):
        monkeypatch.setattr(WizardService, "detect_available_cameras", lambda *a, **k: [])

        def _never(*_a, **_k):
            raise AssertionError("port scan must not run")

        monkeypatch.setattr(WizardService, "detect_arduino_ports", _never)
        step, tk_loop = self._step(
            {"template_metadata": {"name": "T"}, "camera_index": 4, "use_arduino": False}
        )

        step._restore_from_template_once()
        assert step.arduino_status_label.cget("text") != "Detecting..."
        tk_loop.run_until_idle()

        assert step.camera_status_label.cget("text") == "✗ No camera detected"

    def test_template_restore_failure_still_replays_the_saved_settings(self, monkeypatch):
        def _no_serial(*_a, **_k):
            raise ImportError("serial")

        monkeypatch.setattr(WizardService, "detect_available_cameras", lambda *a, **k: [])
        monkeypatch.setattr(WizardService, "detect_arduino_ports", _no_serial)
        step, tk_loop = self._step(
            {
                "template_metadata": {"name": "T"},
                "use_arduino": True,
                "recording_duration_s": 123,
            }
        )

        step._restore_from_template_once()
        tk_loop.run_until_idle()

        assert step.recording_duration_var.get() == 123
        assert step.use_arduino_var.get() is True
        assert step.camera_status_label.cget("text") == "✗ No camera detected"
        assert step.arduino_status_label.cget("text") == "✗ pyserial not installed"


class _FakeLabel:
    """Label stand-in: ``config`` stores options, ``cget`` reads them back."""

    def __init__(self) -> None:
        self.options: dict[str, Any] = {}

    def config(self, **kwargs: Any) -> None:
        self.options.update(kwargs)

    def cget(self, key: str) -> Any:
        return self.options.get(key, "")


class _FakeVar:
    def __init__(self, value: Any = "") -> None:
        self.value = value

    def get(self) -> Any:
        return self.value

    def set(self, value: Any) -> None:
        self.value = value


def _headless_step():
    """A LiveConfigStep with just what the detection paths touch, and no Tk root.

    The mutation runner deselects ``gui`` tests, so the thread contract of the
    two detection buttons is checked here with stub widgets; the template
    restore (which replays ``set_data`` over real widgets) stays in the GUI class.
    """
    step = cast(Any, LiveConfigStep.__new__(LiveConfigStep))
    step._camera_detection_pending = False
    step._arduino_detection_pending = False
    step.camera_status_label = _FakeLabel()
    step.arduino_status_label = _FakeLabel()
    step.camera_combo = {}
    step.arduino_port_combo = {}
    step.camera_index_map = {}
    step.camera_friendly_name_map = {}
    step.arduino_port_map = {}
    step.camera_selection_var = _FakeVar()
    step.arduino_port_var = _FakeVar()
    return step, bind_deferring_tk(step)


class TestLiveConfigDetectionButtonsOffTk:
    """A6-04/A6-05: the "Detect" buttons enumerate hardware on a worker thread.

    Until the (deferred) Tk loop turns, only "Detecting..." may be on screen;
    the hardware call must have run off the main thread.
    """

    def test_camera_button_detects_off_tk(self, monkeypatch):
        threads: list = []

        def _detect(*_a, **_k):
            threads.append(threading.current_thread())
            return [{"index": 0, "description": "USB Cam", "friendly_name": "USB Cam Real"}]

        monkeypatch.setattr(WizardService, "detect_available_cameras", _detect)
        step, tk_loop = _headless_step()

        step._detect_cameras()
        assert step.camera_status_label.cget("text") == "Detecting..."
        assert step.camera_selection_var.get() == ""
        step._detect_cameras()  # second click while in flight: ignored

        tk_loop.run_until_idle()

        assert len(threads) == 1
        assert threads[0] is not threading.main_thread()
        assert step.camera_selection_var.get() == "USB Cam"
        assert step.camera_friendly_name_map == {"USB Cam": "USB Cam Real"}
        assert step.camera_status_label.cget("text") == "✓ 1 camera detected"

    def test_camera_detection_failure_shows_no_camera(self, monkeypatch):
        def _boom(*_a, **_k):
            raise OSError("dshow")

        monkeypatch.setattr(WizardService, "detect_available_cameras", _boom)
        step, tk_loop = _headless_step()

        step._detect_cameras()
        tk_loop.run_until_idle()

        assert step.camera_status_label.cget("text") == "✗ No camera detected"
        assert step._camera_detection_pending is False

    def test_arduino_scan_runs_off_tk_and_auto_selects_on_tk(self, monkeypatch):
        threads: list = []

        def _ports(*_a, **_k):
            threads.append(threading.current_thread())
            return [{"display_name": "COM3 - Arduino", "device": "COM3", "has_handshake": True}]

        monkeypatch.setattr(WizardService, "detect_arduino_ports", _ports)
        step, tk_loop = _headless_step()

        step._detect_arduino_ports()
        assert step.arduino_status_label.cget("text") == "Detecting..."
        assert step.arduino_port_var.get() == ""
        step._detect_arduino_ports()  # ignored while in flight

        tk_loop.run_until_idle()

        assert len(threads) == 1
        assert threads[0] is not threading.main_thread()
        assert step.arduino_port_var.get() == "COM3 - Arduino"
        assert step.arduino_port_map == {"COM3 - Arduino": "COM3"}
        assert step.arduino_status_label.cget("text") == "✓ 1 port — using COM3"

    def test_arduino_scan_without_pyserial_says_so(self, monkeypatch):
        def _no_serial(*_a, **_k):
            raise ImportError("No module named 'serial'")

        monkeypatch.setattr(WizardService, "detect_arduino_ports", _no_serial)
        step, tk_loop = _headless_step()

        step._detect_arduino_ports()
        tk_loop.run_until_idle()

        assert step.arduino_status_label.cget("text") == "✗ pyserial not installed"
        assert step._arduino_detection_pending is False

    def test_arduino_scan_other_failure_shows_no_port(self, monkeypatch):
        def _boom(*_a, **_k):
            raise OSError("access denied")

        monkeypatch.setattr(WizardService, "detect_arduino_ports", _boom)
        step, tk_loop = _headless_step()

        step._detect_arduino_ports()
        tk_loop.run_until_idle()

        assert step.arduino_status_label.cget("text") == "✗ No port detected"
        assert step.arduino_port_combo["values"] == []
        assert step._arduino_detection_pending is False


def _picked_device(ports: list[dict[str, Any]]) -> str:
    """Device da porta escolhida — falha explicitamente se nada foi escolhido."""
    chosen = pick_default_arduino_port(ports)
    assert chosen is not None, "esperava uma porta escolhida"
    return str(chosen["device"])


class TestPickDefaultArduinoPort:
    """Precedência da auto-seleção da porta do Arduino (helper puro, sem Tk)."""

    @staticmethod
    def _port(device: str, description: str, has_handshake: bool) -> dict[str, Any]:
        return {
            "device": device,
            "description": description,
            "has_handshake": has_handshake,
            "display_name": f"{device} - {description}",
        }

    def test_empty_list_returns_none(self):
        assert pick_default_arduino_port([]) is None

    def test_prefers_handshake_and_arduino_name(self):
        ports = [
            self._port("COM1", "USB-SERIAL CH340", True),
            self._port("COM5", "Arduino Uno", False),
            self._port("COM3", "Arduino Mega 2560", True),
        ]
        assert _picked_device(ports) == "COM3"

    def test_handshake_beats_arduino_name_alone(self):
        """Um clone que RESPONDEU é evidência melhor que um nome de driver mudo."""
        ports = [
            self._port("COM5", "Arduino Uno", False),
            self._port("COM1", "USB-SERIAL CH340", True),
        ]
        assert _picked_device(ports) == "COM1"

    def test_falls_back_to_arduino_name_without_handshake(self):
        ports = [
            self._port("COM1", "Dispositivo Serial USB", False),
            self._port("COM7", "Arduino Uno", False),
        ]
        assert _picked_device(ports) == "COM7"

    def test_falls_back_to_first_port(self):
        ports = [
            self._port("COM8", "Dispositivo Serial USB", False),
            self._port("COM9", "Conversor FTDI", False),
        ]
        assert _picked_device(ports) == "COM8"

    def test_ties_resolve_to_first_listed(self):
        """Havendo mais de uma porta 'Arduino', vence a primeira listada."""
        ports = [
            self._port("COM3", "Arduino Uno", True),
            self._port("COM4", "Arduino Nano", True),
        ]
        assert _picked_device(ports) == "COM3"

    def test_name_match_is_case_insensitive_and_tolerates_missing_fields(self):
        ports = [
            {"device": "COM2", "display_name": "COM2"},  # sem description/handshake
            self._port("COM6", "ARDUINO LEONARDO", False),
        ]
        assert _picked_device(ports) == "COM6"


def test_hardware_is_probed_once_per_wizard_and_retried_after_a_failure(monkeypatch):
    """A6-01: the probe blocks the Tk thread (0.5 s cpu sample + GPU probe).

    It used to run on every Back/Next into the step; now one report is kept,
    and only a failed probe (no report) is tried again on the next visit. The
    real method runs on a plain object: it reads only ``settings_obj`` and
    ``hardware_report``, and an EXCELLENT report opens no dialog.
    """
    from types import SimpleNamespace

    from zebtrack.ui.wizard import live_config_step as module
    from zebtrack.utils.hardware_capability import MultiAquariumCapability

    report = SimpleNamespace(
        capability=MultiAquariumCapability.EXCELLENT,
        max_aquariums_recommended=2,
        can_process_realtime=True,
    )
    outcomes: list[Any] = [RuntimeError("no GPU driver")]
    calls: list[str] = []

    class _Detector:
        def __init__(self, settings_obj):
            pass

        def assess_capability(self):
            calls.append("probe")
            outcome = outcomes.pop(0) if outcomes else report
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(module, "HardwareCapabilityDetector", _Detector)
    step = SimpleNamespace(settings_obj=object(), hardware_report=None)

    LiveConfigStep._detect_hardware_capability(step)  # type: ignore[arg-type]
    assert step.hardware_report is None
    for _visit in range(3):
        LiveConfigStep._detect_hardware_capability(step)  # type: ignore[arg-type]

    assert calls == ["probe", "probe"]
    assert step.hardware_report is report
