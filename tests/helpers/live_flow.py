"""Shared harness for the end-to-end LIVE flow tests.

Both live flows (live PROJECT and AD-HOC session) start in
``LiveCameraSessionCoordinator`` and run on the same ``LiveCameraService``:
capture, processing and video threads, ``Recorder``, ``FrameLedger``, the
"Encerrar e Salvar" completion (``finish_session_early`` ->
``_on_session_complete``) and the post-analysis thread that writes the reports
and registers the session. All of that runs for real here. Only the hardware
and the model are replaced:

* the CAMERA: ``zebtrack.io.camera.Camera`` (imported inside
  ``_setup_camera``) becomes :class:`ScriptedCamera`, which hands out exactly
  ``frames`` synthetic frames through ``read_next_frame`` once the test opens
  its gate, with real ``perf_counter``/``time`` stamps;
* the MODEL: ``DETECTOR_PLUGINS["YOLO (Ultralytics)"]`` becomes
  ``GoldenDeterministicPlugin``, and the weight registry answers with one fake
  ``.pt`` path (``DetectorService.initialize_detector`` itself runs);
* no Arduino (``use_arduino`` is off), no Tk root, no view.

Why the gate: frames handed out before the recorder opens would be legal
(``not_recording`` rows) but would make the frame count depend on thread
scheduling. Opening the gate after ``start_*`` returns makes "frames fed" an
input of the test.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

import zebtrack.plugins as plugins_package
from tests.helpers.prerecorded_pipeline import (
    HEIGHT,
    WIDTH,
    GoldenDeterministicPlugin,
    subject_center,
)
from zebtrack.coordinators.live_camera_session_coordinator import LiveCameraSessionCoordinator
from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.core.recording.live_camera_service import LiveCameraService
from zebtrack.core.services.detector_service import DetectorService
from zebtrack.core.state_manager import StateManager
from zebtrack.io.camera import CapturedFrame
from zebtrack.io.recorder import Recorder
from zebtrack.ui.event_bus_v2 import EventBusV2

__all__ = [
    "CAMERA_FPS",
    "LiveRig",
    "ScriptedCamera",
    "build_live_rig",
    "drive_live_session",
]

#: The scripted camera's frame rate (it really paces at this rate).
CAMERA_FPS = 25.0


@dataclass
class CameraScript:
    """What the scripted camera hands out, and what it has handed out so far."""

    frames: int
    gate: threading.Event = field(default_factory=threading.Event)
    delivered: int = 0
    done: threading.Event = field(default_factory=threading.Event)
    opened: int = 0


def _draw(index: int) -> np.ndarray:
    frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    cx, cy = subject_center(index)
    cv2.rectangle(frame, (cx - 12, cy - 12), (cx + 12, cy + 12), (255, 255, 255), -1)
    return frame


class ScriptedCamera:
    """Stands in for ``zebtrack.io.camera.Camera`` at the hardware boundary.

    ``get_frame`` serves the warm-up reads of ``_setup_camera``;
    ``read_next_frame`` is the session's frame source (the same API the real
    ``Camera`` exposes, so ``_read_camera_frame`` takes its camera-paced branch).
    """

    script: CameraScript  # set by build_live_rig

    def __init__(self, settings_obj: Any = None) -> None:
        self._camera_index = int(getattr(getattr(settings_obj, "camera", None), "index", 0) or 0)
        self.actual_width = WIDTH
        self.actual_height = HEIGHT
        self.actual_fps = CAMERA_FPS
        self._seq = 0
        type(self).script.opened += 1

    def is_opened(self) -> bool:
        return True

    def get_frame(self) -> tuple[bool, np.ndarray]:
        return True, _draw(0)

    def read_next_frame(self, after_seq: int, timeout: float = 0.5) -> CapturedFrame | None:
        script = type(self).script
        if not script.gate.wait(timeout):
            return None
        if script.delivered >= script.frames:
            script.done.set()
            time.sleep(timeout)
            return None
        time.sleep(1.0 / CAMERA_FPS)
        frame = _draw(script.delivered)
        script.delivered += 1
        self._seq += 1
        if script.delivered >= script.frames:
            script.done.set()
        return CapturedFrame(frame, self._seq, time.perf_counter(), time.time())

    def release(self) -> None:
        return None


@dataclass
class LiveRig:
    """A wired coordinator + service, and the camera script it reads."""

    coordinator: LiveCameraSessionCoordinator
    service: LiveCameraService
    project_manager: ProjectManager
    script: CameraScript


def build_live_rig(
    monkeypatch: pytest.MonkeyPatch,
    project_manager: ProjectManager,
    settings: Any,
    *,
    frames: int,
    weight_file: Path,
) -> LiveRig:
    """Wire ``LiveCameraSessionCoordinator`` -> ``LiveCameraService`` as the DI does.

    ``weight_file`` must exist: ``initialize_detector`` checks the ``.pt`` path
    before handing it to the (replaced) plugin class.
    """
    script = CameraScript(frames=frames)
    camera_cls = type("ScriptedCameraForTest", (ScriptedCamera,), {"script": script})
    monkeypatch.setattr("zebtrack.io.camera.Camera", camera_cls)

    def _plugin_factory(model_path: Any = "", settings_obj: Any = None, **_: Any) -> Any:
        return GoldenDeterministicPlugin(str(model_path or ""))

    # A fresh registry instead of patching the real one: reading
    # ``zebtrack.plugins.DETECTOR_PLUGINS`` would import torch/ultralytics.
    monkeypatch.setattr(
        plugins_package, "DETECTOR_PLUGINS", {"YOLO (Ultralytics)": _plugin_factory}, raising=False
    )

    weight_manager = MagicMock(name="weight_manager")
    weight_manager.get_weight_path_by_method.return_value = str(weight_file)
    model_service = MagicMock(name="model_service")
    model_service.find_weight_by_path.return_value = (
        "scripted.pt",
        {"path": str(weight_file)},
    )

    state_manager = StateManager()
    event_bus = EventBusV2()
    detector_service = DetectorService(
        state_manager=state_manager,
        project_manager=project_manager,
        weight_manager=weight_manager,
        model_service=model_service,
        settings_obj=settings,
    )
    service = LiveCameraService(
        controller=None,
        state_manager=state_manager,
        project_manager=project_manager,
        recording_service=MagicMock(name="recording_service"),
        detector_service=detector_service,
        settings_obj=settings,
        recorder=Recorder(settings_obj=settings),
        event_bus=event_bus,
        root=None,
        settings_baseline=settings,
    )
    # The scripted camera stops after ``frames``; the real one never does. The
    # 2 s gap rule would pause the recorder while the test is still collecting.
    service._camera_disconnect_threshold_s = 60.0

    calibration = MagicMock(name="live_calibration_coordinator")
    calibration.last_polygon_source = "manual"
    calibration.pending_zone_confirmation = False
    coordinator = LiveCameraSessionCoordinator(
        state_manager=state_manager,
        live_camera_service=service,
        project_manager=project_manager,
        detector_service=detector_service,
        settings_obj=settings,
        live_calibration_coordinator=cast(Any, calibration),
        event_bus=event_bus,
        live_batch_coordinator=None,
        root=None,
        view=None,
    )
    return LiveRig(coordinator, service, project_manager, script)


def _post_analysis_threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == "PostAnalysisThread"]


def drive_live_session(rig: LiveRig, start: Any, *, timeout: float = 120.0) -> Path:
    """Start through ``start()``, feed the frames, "Encerrar e Salvar", wait for reports.

    Returns:
        The session folder the service wrote into.
    """
    assert start() is True, "the coordinator refused to start the live session"
    output_dir = rig.service.current_output_dir
    assert output_dir is not None

    rig.script.gate.set()
    assert rig.script.done.wait(timeout), "the capture loop stopped reading the camera"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not (
        rig.service.frame_queue.empty() and rig.service.video_queue.empty()
    ):
        time.sleep(0.05)
    # Let the processing thread finish the frame it took off the queue.
    time.sleep(0.3)

    before = set(_post_analysis_threads())
    assert rig.coordinator._finish_live_session_keeping_data() is True
    for thread in set(_post_analysis_threads()) - before:
        thread.join(timeout)
        assert not thread.is_alive(), "the post-analysis thread did not finish"
    return Path(output_dir)
