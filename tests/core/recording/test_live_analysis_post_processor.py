"""Unit tests for ``core/recording/live_analysis_post_processor.py``."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from zebtrack.core.recording.live_analysis_post_processor import LiveAnalysisPostProcessorMixin

ARENA_400PX = [[100, 100], [500, 100], [500, 500], [100, 500]]


class DummyPostProcessor(LiveAnalysisPostProcessorMixin):
    """Minimal host exposing only what the scale resolver touches."""

    def __init__(self, *, project_data: dict, polygon: list | None, analysis_params: dict):
        self.project_manager = MagicMock()
        self.project_manager.project_data = project_data
        self.project_manager.get_zone_data.return_value = SimpleNamespace(polygon=polygon)
        self._analysis_params = analysis_params


class TestResolvePostAnalysisScale:
    def test_project_calibration_wins_over_dialog_dimensions(self):
        """A live PROJECT is calibrated by the wizard; the dialog must not override it."""
        service = DummyPostProcessor(
            project_data={"calibration": {"pixelcm_x": 7.5, "pixelcm_y": 8.5}},
            polygon=ARENA_400PX,
            # Dimensions that would resolve to 20.0/40.0 if they were consulted.
            analysis_params={"aquarium_width_cm": 20.0, "aquarium_height_cm": 10.0},
        )

        pixelcm_x, pixelcm_y, is_calibrated = service._resolve_post_analysis_scale()

        assert (pixelcm_x, pixelcm_y) == (7.5, 8.5)
        assert is_calibrated is True

    def test_adhoc_session_falls_back_to_dialog_dimensions(self):
        """No project => the typed aquarium size is the only scale available."""
        service = DummyPostProcessor(
            project_data={},
            polygon=ARENA_400PX,
            analysis_params={"aquarium_width_cm": 20.0, "aquarium_height_cm": 10.0},
        )

        pixelcm_x, pixelcm_y, is_calibrated = service._resolve_post_analysis_scale()

        assert pixelcm_x == pytest.approx(20.0)
        assert pixelcm_y == pytest.approx(40.0)
        assert is_calibrated is True

    def test_without_dimensions_reports_uncalibrated(self):
        service = DummyPostProcessor(
            project_data={},
            polygon=ARENA_400PX,
            analysis_params={},
        )

        pixelcm_x, pixelcm_y, is_calibrated = service._resolve_post_analysis_scale()

        assert (pixelcm_x, pixelcm_y) == (1.0, 1.0)
        assert is_calibrated is False

    def test_without_polygon_reports_uncalibrated(self):
        service = DummyPostProcessor(
            project_data={},
            polygon=None,
            analysis_params={"aquarium_width_cm": 20.0, "aquarium_height_cm": 10.0},
        )

        assert service._resolve_post_analysis_scale() == (1.0, 1.0, False)

    def test_partial_project_calibration_does_not_count_as_calibrated(self):
        """Only ``pixelcm_x`` stored: falling through is safer than a half scale."""
        service = DummyPostProcessor(
            project_data={"calibration": {"pixelcm_x": 7.5}},
            polygon=ARENA_400PX,
            analysis_params={"aquarium_width_cm": 20.0, "aquarium_height_cm": 10.0},
        )

        pixelcm_x, pixelcm_y, is_calibrated = service._resolve_post_analysis_scale()

        assert pixelcm_x == pytest.approx(20.0)
        assert is_calibrated is True

    def test_zero_project_calibration_is_not_trusted(self):
        """``pixelcm_x == 0`` would make every cm conversion divide by zero."""
        service = DummyPostProcessor(
            project_data={"calibration": {"pixelcm_x": 0, "pixelcm_y": 0}},
            polygon=None,
            analysis_params={},
        )

        assert service._resolve_post_analysis_scale() == (1.0, 1.0, False)


class TestDefineArenaCalibration:
    """``_define_arena_from_detections`` must tolerate absent/None dimensions."""

    def _build(self, analysis_params: dict) -> DummyPostProcessor:
        service = DummyPostProcessor(project_data={}, polygon=None, analysis_params=analysis_params)
        service._actual_width = 640
        service._actual_height = 480
        service._detected_aquarium_bboxes = [(100, 100, 500, 500)]
        service.detector_service = MagicMock()
        service.camera = None
        service._arena_defined_event = MagicMock()
        service._animals_per_aquarium = 1
        service.project_manager.project_path = None
        return service

    def test_none_dimensions_do_not_raise(self):
        service = self._build({"aquarium_width_cm": None, "aquarium_height_cm": None})

        service._define_arena_from_detections()

        assert "calibration" not in service.project_manager.project_data

    def test_valid_dimensions_persist_the_scale(self):
        service = self._build({"aquarium_width_cm": 20.0, "aquarium_height_cm": 20.0})

        service._define_arena_from_detections()

        calib = service.project_manager.project_data["calibration"]
        # Detected bbox spans 400 px over 20 cm on both axes.
        assert calib["pixelcm_x"] == pytest.approx(20.0)
        assert calib["pixelcm_y"] == pytest.approx(20.0)
        assert calib["aquarium_width_cm"] == 20.0


class _ImmediateThread:
    """Runs the target inline so the post-analysis is testable end to end."""

    def __init__(self, target=None, name=None, daemon=None, **_kwargs):
        self._target = target
        self.name = name
        self.daemon = daemon

    def start(self) -> None:
        if self._target is not None:
            self._target()


class PostAnalysisHost(LiveAnalysisPostProcessorMixin):
    """LiveCameraService stand-in wired for the post-analysis path."""

    def __init__(self, output_dir, *, project_data: dict, analysis_params: dict):
        import threading

        self._lock = threading.Lock()
        self._analysis_completed = False
        self.root = None
        self.event_bus: Any = None
        self.settings = MagicMock()
        self.project_manager = MagicMock()
        self.project_manager.project_data = project_data
        self.project_manager.project_path = None
        self.project_manager.get_zone_data.return_value = SimpleNamespace(
            polygon=ARENA_400PX, roi_polygons=[], roi_names=[], roi_colors=[]
        )
        self._analysis_params = analysis_params
        self._experiment_id = "adhoc_exp"
        self._animals_per_aquarium = 1
        self._actual_fps = 30.0
        self._actual_height = 480
        self.current_output_dir = output_dir
        self.stopped_with: list[bool] = []

    def stop_session(
        self, *, cancelled: bool = False, keep_data: bool = False, on_stopped=None
    ) -> bool:
        self.stopped_with.append(keep_data)
        if on_stopped is not None:
            on_stopped(True)
        return True


def _write_trajectory(output_dir):
    import pandas as pd

    df = pd.DataFrame(
        {
            "timestamp": [0.0, 0.1],
            "frame": [1, 2],
            "track_id": [1, 1],
            "x1": [10.0, 12.0],
            "y1": [10.0, 12.0],
            "x2": [20.0, 22.0],
            "y2": [20.0, 22.0],
            "confidence": [0.9, 0.9],
        }
    )
    df.to_parquet(output_dir / "3_CoordMovimento_adhoc_exp.parquet")


def _write_ledger(output_dir, captures=(100.5, 101.0), origin=100.0):
    """``6_FrameLedger_adhoc_exp`` with frames 1..n captured at ``captures``."""
    from zebtrack.core.recording.frame_ledger import FrameLedger

    ledger = FrameLedger(output_dir, "adhoc_exp", flush_interval_s=0.01)
    ledger.pin_origin(origin, 1_700_000_000.0)
    for index, t_perf in enumerate(captures, start=1):
        ledger.record(
            index,
            t_perf,
            1_700_000_000.0 + (t_perf - origin),
            "written",
            video_frame_index=index - 1,
            is_analysis_frame=True,
            queued_for_analysis=True,
        )
    ledger.finalize()


class TestPostAnalysisWiring:
    """``_on_session_complete`` → ``_run_post_analysis`` → reports."""

    def _run(self, tmp_path, monkeypatch, *, project_data, analysis_params, ledger=True):
        from unittest.mock import patch

        output_dir = tmp_path / "live_20260822_120000"
        output_dir.mkdir()
        _write_trajectory(output_dir)
        if ledger:
            _write_ledger(output_dir)

        host = PostAnalysisHost(
            output_dir, project_data=project_data, analysis_params=analysis_params
        )

        analysis_result = SimpleNamespace(validation_warnings=[])
        analysis_service = MagicMock()
        analysis_service.collect_analysis_parameters.return_value = {
            "freezing_vel_threshold": 0.5,
            "freezing_min_duration": 1.0,
            "smoothing_window_length": 5,
            "smoothing_polyorder": 2,
            "behavioral_config": {},
        }
        analysis_service.run_full_analysis_as_dto.return_value = analysis_result
        host._build_post_analysis_service = lambda: analysis_service  # type: ignore[method-assign]

        monkeypatch.setattr(
            "zebtrack.core.recording.live_analysis_post_processor.threading.Thread",
            _ImmediateThread,
        )

        with (
            patch("zebtrack.analysis.reporters.ExcelReporter"),
            patch("zebtrack.analysis.reporters.WordReporter"),
            patch("zebtrack.analysis.reporters.ReporterContext"),
        ):
            host._on_session_complete(output_dir, keep_data=True)

        return host, analysis_service, analysis_result

    def test_keep_data_is_forwarded_to_stop_session(self, tmp_path, monkeypatch):
        """Sem isto, a heuristica dos 50%% marcaria ``.cancelled`` no meio do caminho."""
        host, _service, _result = self._run(
            tmp_path, monkeypatch, project_data={}, analysis_params={}
        )

        assert host.stopped_with == [True]

    def test_dialog_dimensions_reach_the_analysis(self, tmp_path, monkeypatch):
        """A ponta a ponta do bug: cm digitado no dialogo -> pixelcm da analise."""
        _host, service, _result = self._run(
            tmp_path,
            monkeypatch,
            project_data={},
            analysis_params={"aquarium_width_cm": 20.0, "aquarium_height_cm": 10.0},
        )

        kwargs = service.run_full_analysis_as_dto.call_args.kwargs
        assert kwargs["pixelcm_x"] == pytest.approx(20.0)
        assert kwargs["pixelcm_y"] == pytest.approx(40.0)

    def test_uncalibrated_session_is_flagged_in_the_report(self, tmp_path, monkeypatch):
        """1 px = 1 cm precisa aparecer no relatorio, nao passar por medida real."""
        _host, _service, result = self._run(
            tmp_path, monkeypatch, project_data={}, analysis_params={}
        )

        assert len(result.validation_warnings) == 1
        assert "calibration" in result.validation_warnings[0].lower()

    def test_calibrated_session_has_no_warning(self, tmp_path, monkeypatch):
        _host, service, result = self._run(
            tmp_path,
            monkeypatch,
            project_data={"calibration": {"pixelcm_x": 12.0, "pixelcm_y": 12.0}},
            analysis_params={},
        )

        assert result.validation_warnings == []
        assert service.run_full_analysis_as_dto.call_args.kwargs["pixelcm_x"] == 12.0

    def test_trajectory_is_retimed_on_the_capture_clock(self, tmp_path, monkeypatch):
        """v8 F5: live ``timestamp`` is a processing clock; the ledger dates the frames."""
        _host, service, _result = self._run(
            tmp_path, monkeypatch, project_data={}, analysis_params={}
        )

        kwargs = service.run_full_analysis_as_dto.call_args.kwargs
        assert list(kwargs["trajectory_df"]["timestamp"]) == pytest.approx([0.5, 1.0])
        # the recording's own rate (1 frame / 0.5 s), not the camera's nominal 30
        assert kwargs["fps"] == pytest.approx(2.0)

    def test_missing_ledger_is_reported_and_keeps_the_nominal_fps(self, tmp_path, monkeypatch):
        _host, service, result = self._run(
            tmp_path,
            monkeypatch,
            project_data={"calibration": {"pixelcm_x": 12.0, "pixelcm_y": 12.0}},
            analysis_params={},
            ledger=False,
        )

        kwargs = service.run_full_analysis_as_dto.call_args.kwargs
        assert list(kwargs["trajectory_df"]["timestamp"]) == pytest.approx([0.0, 0.1])
        assert len(result.validation_warnings) == 1
        assert "ledger" in result.validation_warnings[0].lower()

    def test_cancelled_session_skips_the_whole_post_analysis(self, tmp_path, monkeypatch):
        output_dir = tmp_path / "live_20260822_130000"
        output_dir.mkdir()
        _write_trajectory(output_dir)
        (output_dir / ".cancelled").write_text("forced=True", encoding="utf-8")

        host = PostAnalysisHost(output_dir, project_data={}, analysis_params={})
        host._build_post_analysis_service = MagicMock()  # type: ignore[method-assign]

        host._on_session_complete(output_dir)

        host._build_post_analysis_service.assert_not_called()
        assert host.stopped_with == [False]


def _frame_spec():
    from zebtrack.core.conditions import FrameReached, WindowSpec

    return WindowSpec(start=FrameReached(frame=1), stop=FrameReached(frame=2))


def _seed_online(output_dir, spec, *, start_frame: int) -> None:
    """The artifact the processing thread writes before the post-analysis starts."""
    from zebtrack.core.conditions import (
        AnalysisWindowArtifact,
        ArtifactEvent,
        OnlineWindow,
        artifact_path,
        write_artifact,
    )

    artifact = AnalysisWindowArtifact.for_spec(
        spec,
        clock="capture_perf",
        online=OnlineWindow(start=ArtifactEvent(frame=start_frame, t_s=0.5, reason="frame")),
    )
    write_artifact(artifact_path(output_dir, "adhoc_exp"), artifact)


class TestPostAnalysisWindow:
    """ADR-011: the live post-analysis applies the OFFLINE window (F4b + F5)."""

    def _run(self, tmp_path, monkeypatch, raw, *, online_start: int | None = None):
        from unittest.mock import patch

        output_dir = tmp_path / "live_20260822_140000"
        output_dir.mkdir()
        _write_trajectory(output_dir)
        _write_ledger(output_dir)
        if online_start is not None:
            _seed_online(output_dir, _frame_spec(), start_frame=online_start)
        host = PostAnalysisHost(
            output_dir,
            project_data={"calibration": {"pixelcm_x": 12.0, "pixelcm_y": 12.0}},
            analysis_params={},
        )
        host._analysis_window_raw = raw  # type: ignore[attr-defined]
        result = SimpleNamespace(validation_warnings=[])
        service = MagicMock()
        service.collect_analysis_parameters.return_value = {
            "freezing_vel_threshold": 0.5,
            "freezing_min_duration": 1.0,
            "smoothing_window_length": 5,
            "smoothing_polyorder": 2,
            "behavioral_config": {},
        }
        service.run_full_analysis_as_dto.return_value = result
        host._build_post_analysis_service = lambda: service  # type: ignore[method-assign]
        monkeypatch.setattr(
            "zebtrack.core.recording.live_analysis_post_processor.threading.Thread",
            _ImmediateThread,
        )
        with (
            patch("zebtrack.analysis.reporters.ExcelReporter"),
            patch("zebtrack.analysis.reporters.WordReporter"),
            patch("zebtrack.analysis.reporters.ReporterContext"),
        ):
            host._on_session_complete(output_dir, keep_data=True)
        return output_dir, service.run_full_analysis_as_dto.call_args.kwargs["window"], result

    def test_without_a_window_nothing_is_applied(self, tmp_path, monkeypatch):
        _out, window, result = self._run(tmp_path, monkeypatch, None)

        assert window is None
        assert result.validation_warnings == []

    def test_offline_window_on_the_capture_clock_is_applied(self, tmp_path, monkeypatch):
        from zebtrack.core.conditions import artifact_path, read_artifact

        raw = _frame_spec().model_dump(mode="json", by_alias=True)
        output_dir, window, _result = self._run(tmp_path, monkeypatch, raw, online_start=1)

        assert window is not None
        assert window.start is not None and window.stop is not None
        assert (window.start.frame, window.stop.frame) == (1, 2)
        # Ledger instants (0.5 s, 1.0 s), not the processing timestamps (0.0, 0.1).
        assert (window.start.t_s, window.stop.t_s) == pytest.approx((0.5, 1.0))
        assert not any("live session" in w for w in window.warnings)
        artifact = read_artifact(artifact_path(output_dir, "adhoc_exp"))
        assert artifact is not None and artifact.offline is not None
        assert artifact.offline.start is not None and artifact.offline.start.frame == 1
        assert artifact.online.start is not None and artifact.online.start.frame == 1
        assert artifact.clock == "capture_perf"

    def test_divergent_online_window_is_reported(self, tmp_path, monkeypatch):
        raw = _frame_spec().model_dump(mode="json", by_alias=True)

        _out, window, _result = self._run(tmp_path, monkeypatch, raw, online_start=9)

        assert window is not None and window.start is not None
        assert window.start.frame == 1
        assert any("frame 9" in w for w in window.warnings)

    def test_unreadable_rule_analyses_everything_and_says_so(self, tmp_path, monkeypatch):
        _out, window, result = self._run(
            tmp_path, monkeypatch, {"version": 1, "start": {"kind": "nope"}}
        )

        assert window is None
        assert any("analysis window" in w for w in result.validation_warnings)


class TestPublishPostAnalysisStatus:
    def test_without_event_bus_is_a_noop(self):
        host = DummyPostProcessor(project_data={}, polygon=None, analysis_params={})
        host.event_bus = None  # type: ignore[assignment]  # headless: no bus wired

        host._publish_post_analysis_status("gerando")  # must not raise

    def test_publishes_a_status_event(self):
        host = DummyPostProcessor(project_data={}, polygon=None, analysis_params={})
        host.event_bus = MagicMock()

        host._publish_post_analysis_status("gerando relatorios")

        host.event_bus.publish.assert_called_once()
        event = host.event_bus.publish.call_args[0][0]
        assert event.data.message == "gerando relatorios"

    def test_a_failing_bus_never_breaks_the_analysis(self):
        host = DummyPostProcessor(project_data={}, polygon=None, analysis_params={})
        host.event_bus = MagicMock()
        host.event_bus.publish.side_effect = RuntimeError("bus down")

        host._publish_post_analysis_status("gerando")  # swallowed by design


class _MultiHost(LiveAnalysisPostProcessorMixin):
    """Live-service stand-in for the multi-aquarium recording path."""

    def __init__(self, output_dir, recorder, detector):
        self.recorder = recorder
        self.current_output_dir = output_dir
        self.is_capturing_for_video = True
        self.camera = None
        self.preview_window = None
        self._experiment_id = "multi_exp"
        self._session_duration_s = 0.0
        self._multi_aq_detector = None
        self.project_manager = MagicMock()
        self.detector_service: Any = SimpleNamespace(detector=detector)
        self.recording_fps: float | None = None

    def _live_object_metadata(self) -> Any:
        return None

    def _live_recording_fps(self) -> float | None:
        return self.recording_fps


def _two_aquariums():
    from zebtrack.core.detection import AquariumData, MultiAquariumZoneData

    return MultiAquariumZoneData(
        aquariums=[
            AquariumData(
                id=aq_id,
                polygon=[[x0, 0], [x0 + 300, 0], [x0 + 300, 480], [x0, 480]],
                roi_polygons=[],
                roi_names=[],
                roi_colors=[],
                group="G",
                subject_id=f"S0{aq_id + 1}",
                day=1,
            )
            for aq_id, x0 in ((0, 0), (1, 320))
        ],
        video_width=640,
        video_height=480,
    )


class TestMultiAquariumLive:
    """Multi-aquarium live recording (#635): role map, rows, session MP4."""

    def test_role_map_reaches_the_multi_aquarium_detector(self, tmp_path, monkeypatch):
        import numpy as np

        role_map = object()
        detector = SimpleNamespace(
            plugin=object(),
            zone_scaler=object(),
            post_processor=object(),
            base_width=640,
            base_height=480,
            settings=None,
            class_role_map=role_map,
        )
        created = MagicMock()
        created.return_value.detect_partitioned_optimized.return_value = {}
        monkeypatch.setattr(
            "zebtrack.core.detection.multi_aquarium_detector.MultiAquariumDetector", created
        )
        host = _MultiHost(tmp_path, MagicMock(start_time=0.0), detector)

        host._run_multi_aquarium_detection(
            np.zeros((480, 640, 3), dtype=np.uint8), 5, SimpleNamespace(aquariums=[])
        )

        assert created.call_args.kwargs["class_role_map"] is role_map

    def test_capture_instant_reaches_the_multi_aquarium_tracker(self, tmp_path):
        """#654: every aquarium ages its lost tracks on the frame's capture clock."""
        import numpy as np

        fake = MagicMock()
        fake.detect_partitioned_optimized.return_value = {}
        host = _MultiHost(tmp_path, MagicMock(start_time=0.0), SimpleNamespace(plugin=object()))
        host._multi_aq_detector = fake
        host_any: Any = host
        host_any._tracker_frame_time_s = 512.25

        host._run_multi_aquarium_detection(
            np.zeros((480, 640, 3), dtype=np.uint8), 5, SimpleNamespace(aquariums=[])
        )

        names = [c[0] for c in fake.mock_calls]
        assert names.index("set_frame_time") < names.index("detect_partitioned_optimized")
        fake.set_frame_time.assert_called_once_with(512.25)

    def test_live_multi_aquarium_records_trajectory_rows(self, tmp_path, monkeypatch):
        """Was ``xfail(strict=True)``: 0 rows. Three defects stacked: the parent's
        ``start_time`` stayed 0, the partitioned write had invalid kwargs (the
        TypeError fell back to the single detector), and ``stop_recording()`` —
        the call ``stop_session`` makes — never reached the sub-recorders."""
        import numpy as np
        import pandas as pd

        from zebtrack.core.detection import AquariumData, MultiAquariumZoneData
        from zebtrack.io.recorder import Recorder

        zone_data = MultiAquariumZoneData(
            aquariums=[
                AquariumData(
                    id=aq_id,
                    polygon=[[x0, 0], [x0 + 300, 0], [x0 + 300, 480], [x0, 480]],
                    roi_polygons=[],
                    roi_names=[],
                    roi_colors=[],
                    group="G",
                    subject_id=f"S0{aq_id + 1}",
                    day=1,
                )
                for aq_id, x0 in ((0, 0), (1, 320))
            ],
            video_width=640,
            video_height=480,
        )
        recorder = Recorder(settings_obj=None)
        host = _MultiHost(tmp_path, recorder, SimpleNamespace())
        host_any: Any = host
        host_any._resolve_live_session_video_path = lambda _d: tmp_path / "multi_exp.mp4"
        host_any._resolve_live_multi_aquarium_zone_data = lambda _p: zone_data
        host._start_recording_after_arena()

        fake = MagicMock()
        fake.detect_partitioned_optimized.return_value = {
            0: [(10.0, 10.0, 20.0, 20.0, 0.9, 1, 1)],
            1: [(330.0, 10.0, 340.0, 20.0, 0.9, 1001, 1)],
        }
        host._multi_aq_detector = fake
        host._run_multi_aquarium_detection(np.zeros((480, 640, 3), dtype=np.uint8), 30, zone_data)
        recorder.stop_recording()  # what stop_session calls

        trajectories = sorted(tmp_path.rglob("3_CoordMovimento_*.parquet"))
        rows = {path.parent.name: len(pd.read_parquet(path)) for path in trajectories}
        assert rows == {"aquarium_1": 1, "aquarium_2": 1}
        assert sorted(pd.read_parquet(trajectories[1])["track_id"]) == [1001]
        # One session MP4, named like the single-aquarium one.
        assert (tmp_path / "multi_exp.mp4").exists()

    def test_session_aquariums_come_from_the_multi_zones_not_the_shim(self, tmp_path):
        """``get_zone_data()`` is the aquarium-0 shim: it can never say "multi"."""
        from zebtrack.core.detection import ZoneData

        zone_data = _two_aquariums()
        host = _MultiHost(tmp_path, MagicMock(), SimpleNamespace())
        host_any: Any = host
        pm: Any = host.project_manager
        pm.get_zone_data.return_value = ZoneData(polygon=[[0, 0], [1, 1]])
        host_any._resolve_live_multi_aquarium_zone_data = lambda _p: zone_data

        assert host._resolve_session_multi_zone_data() is zone_data
        assert host._live_multi_zone_data is zone_data

    def test_a_single_stored_aquarium_stays_on_the_single_path(self, tmp_path):
        """Same output layout as before for one-aquarium sessions."""
        from zebtrack.core.detection import MultiAquariumZoneData

        one = _two_aquariums()
        single = MultiAquariumZoneData(
            aquariums=one.aquariums[:1], video_width=640, video_height=480
        )
        host = _MultiHost(tmp_path, MagicMock(), SimpleNamespace())
        host_any: Any = host
        host_any._resolve_live_multi_aquarium_zone_data = lambda _p: single

        assert host._resolve_session_multi_zone_data() is None

    def test_zones_validated_up_front_still_record_per_aquarium(self, tmp_path):
        """The predefined-arena path (``start_session``) used ``start_recording``
        with aquarium 0's zones over the whole frame; it now shares the rule."""
        from zebtrack.core.detection import ZoneData

        recorder = MagicMock()
        host = _MultiHost(tmp_path, recorder, SimpleNamespace())
        host._live_multi_zone_data = _two_aquariums()

        assert host._start_live_recorder(ZoneData(), "sessao") is True

        recorder.start_recording.assert_not_called()
        kwargs = recorder.start_recording_multi_aquarium.call_args.kwargs
        assert sorted(kwargs["zones_by_aquarium"]) == [0, 1]
        assert kwargs["session_video"] is True
        assert kwargs["base_name"] == "sessao"

    def test_more_than_two_aquariums_are_refused(self, tmp_path):
        """The recorder supports two; a third would be silently lost."""
        import dataclasses

        from zebtrack.core.detection import MultiAquariumZoneData

        recorder = MagicMock()
        host = _MultiHost(tmp_path, recorder, SimpleNamespace())
        two = _two_aquariums()
        extra = dataclasses.replace(two.aquariums[1], id=2)
        host._live_multi_zone_data = MultiAquariumZoneData(
            aquariums=[*two.aquariums, extra], video_width=640, video_height=480
        )

        assert host._start_live_recorder(None, "sessao") is False
        recorder.start_recording_multi_aquarium.assert_not_called()
        recorder.start_recording.assert_not_called()

    def test_without_aquariums_the_single_recorder_starts(self, tmp_path):
        from zebtrack.core.detection import ZoneData

        recorder = MagicMock()
        host = _MultiHost(tmp_path, recorder, SimpleNamespace())
        host._live_multi_zone_data = None
        zones = ZoneData(polygon=[[0, 0], [1, 1]])

        host._start_live_recorder(zones, "sessao")

        recorder.start_recording_multi_aquarium.assert_not_called()
        assert recorder.start_recording.call_args.kwargs["zones"] is zones


class TestMultiAquariumPostAnalysis:
    """#635: the live post-analysis of a 2-aquarium session.

    It looked for ``3_CoordMovimento_*`` only at the top of the session folder,
    where a multi-aquarium session has none, and stopped at "no trajectory"
    before the per-aquarium analysis. Now each aquarium is re-timed on the
    session's single ledger and gets its own offline window (ADR-011).
    """

    def _session(self, tmp_path):
        import pandas as pd

        output_dir = tmp_path / "live_20261105_120000"
        output_dir.mkdir()
        (output_dir / "adhoc_exp.mp4").write_bytes(b"")  # the session MP4
        _write_ledger(output_dir)  # 6_FrameLedger_adhoc_exp, frames 1-2 at 0.5 s / 1.0 s
        for aq_id, x0 in ((0, 10.0), (1, 330.0)):
            folder = output_dir / f"aquarium_{aq_id + 1}"
            folder.mkdir()
            pd.DataFrame(
                {
                    "timestamp": [0.0, 0.1],
                    "frame": [1, 2],
                    "track_id": [aq_id * 1000 + 1] * 2,
                    "x1": [x0, x0 + 2],
                    "y1": [10.0, 12.0],
                    "x2": [x0 + 10, x0 + 12],
                    "y2": [20.0, 22.0],
                    "confidence": [0.9, 0.9],
                }
            ).to_parquet(folder / f"3_CoordMovimento_adhoc_exp_aquarium_{aq_id + 1}.parquet")
        return output_dir

    def _run(self, tmp_path, monkeypatch, raw_window=None):
        from unittest.mock import patch

        output_dir = self._session(tmp_path)
        host = PostAnalysisHost(
            output_dir,
            project_data={"calibration": {"pixelcm_x": 12.0, "pixelcm_y": 12.0}},
            analysis_params={},
        )
        host._analysis_window_raw = raw_window  # type: ignore[attr-defined]
        pm: Any = host.project_manager
        pm.get_multi_aquarium_zone_data.return_value = _two_aquariums()
        results = {0: SimpleNamespace(validation_warnings=[]), 1: None}
        service = MagicMock()
        service.collect_analysis_parameters.return_value = {
            "freezing_vel_threshold": 0.5,
            "freezing_min_duration": 1.0,
            "smoothing_window_length": 5,
            "smoothing_polyorder": 2,
            "behavioral_config": {},
        }
        service.run_multi_aquarium_analysis.return_value = results
        service.resolve_roi_rule.return_value = None
        host._build_post_analysis_service = lambda: service  # type: ignore[method-assign]
        monkeypatch.setattr(
            "zebtrack.core.recording.live_analysis_post_processor.threading.Thread",
            _ImmediateThread,
        )
        with patch("zebtrack.analysis.reporters.export_multi_aquarium_reports", return_value={}):
            host._on_session_complete(output_dir, keep_data=True)
        return service, results

    def test_per_aquarium_trajectories_reach_the_analysis(self, tmp_path, monkeypatch):
        service, _results = self._run(tmp_path, monkeypatch)

        service.run_multi_aquarium_analysis.assert_called_once()
        data_map = service.run_multi_aquarium_analysis.call_args.kwargs["aquarium_data_map"]
        assert sorted(data_map) == [0, 1]

    def test_every_aquarium_is_retimed_on_the_session_ledger(self, tmp_path, monkeypatch):
        service, results = self._run(tmp_path, monkeypatch)

        kwargs = service.run_multi_aquarium_analysis.call_args.kwargs
        for aq_id in (0, 1):
            df, _aquarium = kwargs["aquarium_data_map"][aq_id]
            assert list(df["timestamp"]) == pytest.approx([0.5, 1.0])
        assert kwargs["fps"] == pytest.approx(2.0)  # the recording's rate, not 30
        assert results[0].validation_warnings == []  # the ledger was found

    def test_one_offline_window_per_aquarium(self, tmp_path, monkeypatch):
        raw = _frame_spec().model_dump(mode="json", by_alias=True)
        service, _results = self._run(tmp_path, monkeypatch, raw)

        windows = service.run_multi_aquarium_analysis.call_args.kwargs["windows"]
        assert sorted(windows) == [0, 1]
        for window in windows.values():
            assert (window.start.frame, window.stop.frame) == (1, 2)
            assert (window.start.t_s, window.stop.t_s) == pytest.approx((0.5, 1.0))

    def test_without_a_window_none_is_applied(self, tmp_path, monkeypatch):
        service, _results = self._run(tmp_path, monkeypatch)

        windows = service.run_multi_aquarium_analysis.call_args.kwargs["windows"]
        assert windows == {0: None, 1: None}


class TestLiveMp4Rate:
    """#637: the live MP4 was written at the settings' 30 fps while the camera
    delivered 39-41: the video ran slow and re-processing it re-dated everything."""

    @staticmethod
    def _feed(recorder) -> None:
        import numpy as np

        for _ in range(3):
            recorder.write_video_frame(np.zeros((480, 640, 3), dtype=np.uint8))

    @staticmethod
    def _mp4_fps(path) -> float:
        import cv2

        capture = cv2.VideoCapture(str(path))
        try:
            return float(capture.get(cv2.CAP_PROP_FPS))
        finally:
            capture.release()

    def test_single_aquarium_mp4_runs_at_the_measured_rate(self, tmp_path):
        from zebtrack.core.detection import ZoneData
        from zebtrack.io.recorder import Recorder

        recorder = Recorder(settings_obj=None)
        host = _MultiHost(tmp_path, recorder, SimpleNamespace())
        host.recording_fps = 40.0

        assert host._start_live_recorder(ZoneData(), "sessao") is True
        self._feed(recorder)
        recorder.stop_recording()

        assert self._mp4_fps(tmp_path / "sessao.mp4") == pytest.approx(40.0, abs=0.01)

    def test_multi_aquarium_session_mp4_runs_at_the_measured_rate(self, tmp_path):
        from zebtrack.io.recorder import Recorder

        recorder = Recorder(settings_obj=None)
        host = _MultiHost(tmp_path, recorder, SimpleNamespace())
        host._live_multi_zone_data = _two_aquariums()
        host.recording_fps = 40.0

        assert host._start_live_recorder(None, "sessao") is True
        self._feed(recorder)
        recorder.stop_recording()

        assert self._mp4_fps(tmp_path / "sessao.mp4") == pytest.approx(40.0, abs=0.01)

    def test_unknown_rate_keeps_the_settings_value(self, tmp_path):
        from zebtrack.core.detection import ZoneData
        from zebtrack.io.recorder import Recorder

        recorder = Recorder(settings_obj=None)
        host = _MultiHost(tmp_path, recorder, SimpleNamespace())

        host._start_live_recorder(ZoneData(), "sessao")
        self._feed(recorder)
        recorder.stop_recording()

        assert self._mp4_fps(tmp_path / "sessao.mp4") == pytest.approx(30.0, abs=0.01)


class TestLiveRoiBuilder:
    """ROIs of the window/analysis built from the stored zone lists."""

    def test_names_and_colours_fall_back_per_index(self):
        square = [[0, 0], [10, 0], [10, 10], [0, 10]]
        rois, colors = LiveAnalysisPostProcessorMixin._build_live_rois(
            [square, square], ["Centro"], [(1, 2, 3)]
        )

        assert [roi.name for roi in rois] == ["Centro", "ROI_1"]
        assert colors == {"Centro": (1, 2, 3), "ROI_1": (255, 0, 0)}
        assert rois[0].geometry.area == 100.0

    def test_no_polygons_no_rois(self):
        assert LiveAnalysisPostProcessorMixin._build_live_rois(None, None, None) == ([], {})


class TestPostAnalysisEdges:
    def test_an_empty_trajectory_reports_no_detections(self, tmp_path, monkeypatch):
        import pandas as pd

        output_dir = tmp_path / "live_20261105_150000"
        output_dir.mkdir()
        pd.DataFrame(columns=["timestamp", "frame", "track_id"]).to_parquet(
            output_dir / "3_CoordMovimento_adhoc_exp.parquet"
        )
        host = PostAnalysisHost(output_dir, project_data={}, analysis_params={})
        root = MagicMock()
        host.root = root
        service = MagicMock()
        service.collect_analysis_parameters.return_value = {}
        host._build_post_analysis_service = lambda: service  # type: ignore[method-assign]
        monkeypatch.setattr(
            "zebtrack.core.recording.live_analysis_post_processor.threading.Thread",
            _ImmediateThread,
        )

        host._on_session_complete(output_dir, keep_data=True)

        service.run_full_analysis_as_dto.assert_not_called()
        args = root.after.call_args.args
        assert args[2:] == (output_dir, False, None, "no_detections")

    def test_an_unreadable_window_is_reported_per_aquarium(self, tmp_path, monkeypatch):
        harness = TestMultiAquariumPostAnalysis()
        _service, results = harness._run(tmp_path, monkeypatch, {"start": "not a condition"})

        assert any("analysis window" in w for w in results[0].validation_warnings)


class TestRecordingProblemsReachTheOperator:
    """Live paths that used to log an error and keep the preview running (A5-S-006, 007)."""

    @staticmethod
    def _host(tmp_path, detector=None):
        host = _MultiHost(tmp_path, MagicMock(start_time=0.0), detector)
        host_any: Any = host
        host_any.event_bus = MagicMock()
        host_any._session_duration_s = 30.0
        host_any._resolve_session_multi_zone_data = lambda: None
        host_any.timers = []
        host_any._setup_session_timer = lambda duration, folder: host_any.timers.append(duration)
        return host_any

    @staticmethod
    def _errors(host):
        from zebtrack.ui.event_bus_v2 import UIEvents

        events = [call.args[0] for call in host.event_bus.publish.call_args_list]
        return [event.data for event in events if event.type is UIEvents.SHOW_ERROR]

    # -- A5-S-007: the recorder does not start after the arena is defined --------

    def test_a_recorder_that_starts_runs_the_timer_and_reports_nothing(self, tmp_path):
        host = self._host(tmp_path)
        host._start_live_recorder = lambda zone_data, base_name: True

        host._start_recording_after_arena()

        assert host.timers == [30.0]
        assert self._errors(host) == []

    def test_a_recorder_that_refuses_to_start_is_shown_and_no_timer_runs(self, tmp_path):
        host = self._host(tmp_path)
        host._start_live_recorder = lambda zone_data, base_name: False

        host._start_recording_after_arena()

        assert host.timers == []
        (error,) = self._errors(host)
        assert error.title == "Recording did not start"
        assert "NOT being recorded" in error.message
        assert str(tmp_path) in error.message

    def test_a_recorder_that_raises_is_shown_with_its_cause(self, tmp_path):
        host = self._host(tmp_path)

        def _raise(zone_data, base_name):
            raise OSError("folder is read-only")

        host._start_live_recorder = _raise

        host._start_recording_after_arena()

        assert host.timers == []
        (error,) = self._errors(host)
        assert "folder is read-only" in error.message

    def test_a_start_failure_without_a_bus_still_returns(self, tmp_path):
        host = self._host(tmp_path)
        host.event_bus = None
        host._start_live_recorder = lambda zone_data, base_name: False

        host._start_recording_after_arena()

        assert host.timers == []

    # -- A5-S-006: multi-aquarium detection fails while the preview goes on ------

    @staticmethod
    def _failing_multi(host):
        fake = MagicMock()
        fake.detect_partitioned_optimized.side_effect = RuntimeError("tracker state broken")
        host._multi_aq_detector = fake
        return fake

    def _frame_host(self, tmp_path):
        import numpy as np

        detector = MagicMock()
        detector.detect.return_value = ([(1, 2, 3, 4, 0.9, 7, 1)], None)
        host = self._host(tmp_path, detector)
        self._failing_multi(host)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        return host, frame

    def test_a_failing_frame_still_feeds_the_preview_from_the_single_detector(self, tmp_path):
        host, frame = self._frame_host(tmp_path)

        detections = host._run_multi_aquarium_detection(frame, 5, SimpleNamespace(aquariums=[]))

        assert detections == [(1, 2, 3, 4, 0.9, 7, 1)]

    def test_the_operator_is_told_once_per_session_not_once_per_frame(self, tmp_path):
        host, frame = self._frame_host(tmp_path)

        for frame_number in range(5):
            host._run_multi_aquarium_detection(frame, frame_number, SimpleNamespace(aquariums=[]))

        (error,) = self._errors(host)
        assert error.title == "Detections are not being recorded"
        assert "tracker state broken" in error.message

    def test_a_new_session_folder_is_told_again(self, tmp_path):
        host, frame = self._frame_host(tmp_path)
        host._run_multi_aquarium_detection(frame, 1, SimpleNamespace(aquariums=[]))

        host.current_output_dir = tmp_path / "next_session"
        host._run_multi_aquarium_detection(frame, 1, SimpleNamespace(aquariums=[]))

        assert len(self._errors(host)) == 2

    def test_a_frame_that_succeeds_reports_nothing(self, tmp_path):
        host, frame = self._frame_host(tmp_path)
        host._multi_aq_detector.detect_partitioned_optimized.side_effect = None
        host._multi_aq_detector.detect_partitioned_optimized.return_value = {}

        host._run_multi_aquarium_detection(frame, 1, SimpleNamespace(aquariums=[]))

        assert self._errors(host) == []


# ---------------------------------------------------------------------------
# A4-02: the "tracks" figure of the completion dialog is the report's count of
# animals (count_subjects over the screened trajectory), not a raw nunique().
# ---------------------------------------------------------------------------


def _trajectory_rows(track_rows: dict[Any, list[float]], *, x0: float = 10.0):
    """Rows for each ``track_id`` at the given timestamps (frame = index + 1)."""
    import pandas as pd

    rows = []
    for track_id, stamps in track_rows.items():
        for t in stamps:
            rows.append(
                {
                    "timestamp": t,
                    "frame": round(t * 10) + 1,
                    "track_id": track_id,
                    "x1": x0,
                    "y1": 10.0,
                    "x2": x0 + 10,
                    "y2": 20.0,
                    "confidence": 0.9,
                }
            )
    return pd.DataFrame(rows)


_ONE_SECOND = [round(0.1 * i, 1) for i in range(10)]  # 10 rows over 0.9 s


def _analysis_service_double() -> MagicMock:
    service = MagicMock()
    service.collect_analysis_parameters.return_value = {
        "freezing_vel_threshold": 0.5,
        "freezing_min_duration": 1.0,
        "smoothing_window_length": 5,
        "smoothing_polyorder": 2,
        "behavioral_config": {},
    }
    service.run_full_analysis_as_dto.return_value = SimpleNamespace(validation_warnings=[])
    service.resolve_roi_rule.return_value = None
    return service


def _completion_args(host: Any) -> tuple:
    """``(output_dir, success, stats, reason)`` scheduled on the Tk root."""
    args = host.root.after.call_args.args
    assert args[0] == 0
    assert args[1] == host._show_completion_message
    return tuple(args[2:]) + (None,) * (6 - len(args))


class TestCompletionTrackCount:
    def _run_single(self, tmp_path, monkeypatch, df):
        from unittest.mock import patch

        output_dir = tmp_path / "live_20261116_090000"
        output_dir.mkdir()
        df.to_parquet(output_dir / "3_CoordMovimento_adhoc_exp.parquet")
        host = PostAnalysisHost(output_dir, project_data={}, analysis_params={})
        host.root = MagicMock()
        host._build_post_analysis_service = _analysis_service_double  # type: ignore[method-assign]
        monkeypatch.setattr(
            "zebtrack.core.recording.live_analysis_post_processor.threading.Thread",
            _ImmediateThread,
        )
        with (
            patch("zebtrack.analysis.reporters.ExcelReporter"),
            patch("zebtrack.analysis.reporters.WordReporter"),
            patch("zebtrack.analysis.reporters.ReporterContext"),
        ):
            host._on_session_complete(output_dir, keep_data=True)
        return host

    def test_a_one_row_glitch_is_not_counted_as_an_animal(self, tmp_path, monkeypatch):
        # Track 1 lasts a second; track 7 is a single row (0.1 s < 0.5 s).
        df = _trajectory_rows({1: _ONE_SECOND, 7: [0.4]})

        host = self._run_single(tmp_path, monkeypatch, df)

        _out, success, stats, _reason = _completion_args(host)[:4]
        assert success is True
        assert stats["tracks"] == 1
        # Frames and detections still describe the raw recording.
        assert stats["detections"] == 11

    def test_rows_without_any_id_are_one_subject(self, tmp_path, monkeypatch):
        df = _trajectory_rows({float("nan"): _ONE_SECOND})

        host = self._run_single(tmp_path, monkeypatch, df)

        assert _completion_args(host)[2]["tracks"] == 1

    def test_two_real_animals_are_two(self, tmp_path, monkeypatch):
        df = _trajectory_rows({1: _ONE_SECOND, 2: _ONE_SECOND})

        host = self._run_single(tmp_path, monkeypatch, df)

        assert _completion_args(host)[2]["tracks"] == 2

    def test_multi_aquarium_total_counts_animals_not_ids(self, tmp_path, monkeypatch):
        from unittest.mock import patch

        output_dir = tmp_path / "live_20261116_100000"
        output_dir.mkdir()
        (output_dir / "adhoc_exp.mp4").write_bytes(b"")
        tracks = {
            0: {1: _ONE_SECOND, 5: [0.3]},  # one fish + a one-row glitch
            1: {1001: _ONE_SECOND},
        }
        for aq_id, by_track in tracks.items():
            folder = output_dir / f"aquarium_{aq_id + 1}"
            folder.mkdir()
            _trajectory_rows(by_track).to_parquet(
                folder / f"3_CoordMovimento_adhoc_exp_aquarium_{aq_id + 1}.parquet"
            )
        host = PostAnalysisHost(
            output_dir,
            project_data={"calibration": {"pixelcm_x": 12.0, "pixelcm_y": 12.0}},
            analysis_params={},
        )
        host.root = MagicMock()
        pm: Any = host.project_manager
        pm.get_multi_aquarium_zone_data.return_value = _two_aquariums()
        service = _analysis_service_double()
        service.run_multi_aquarium_analysis.return_value = {
            0: SimpleNamespace(validation_warnings=[]),
            1: SimpleNamespace(validation_warnings=[]),
        }
        host._build_post_analysis_service = lambda: service  # type: ignore[method-assign]
        monkeypatch.setattr(
            "zebtrack.core.recording.live_analysis_post_processor.threading.Thread",
            _ImmediateThread,
        )
        reports = {0: {"summary_path": "a.xlsx", "report_path": "a.docx"}}
        with patch(
            "zebtrack.analysis.reporters.export_multi_aquarium_reports", return_value=reports
        ):
            host._on_session_complete(output_dir, keep_data=True)

        _out, success, stats, _reason = _completion_args(host)[:4]
        assert success is True
        assert stats == {"frames": 20, "detections": 21, "tracks": 2}


# ---------------------------------------------------------------------------
# Completion message, zone lookup, multi-aquarium registration edges.
# ---------------------------------------------------------------------------


class TestCompletionMessage:
    @staticmethod
    def _host(tmp_path) -> PostAnalysisHost:
        host = PostAnalysisHost(tmp_path, project_data={}, analysis_params={})
        host.event_bus = MagicMock()
        return host

    @staticmethod
    def _shown(host) -> Any:
        from zebtrack.ui.event_bus_v2 import UIEvents

        (call,) = host.event_bus.publish.call_args_list
        event = call.args[0]
        assert event.type == UIEvents.UI_SHOW_INFO
        return event.data

    def test_success_lists_stats_and_the_files_on_disk(self, tmp_path):
        (tmp_path / "3_CoordMovimento_exp.parquet").write_bytes(b"x")
        (tmp_path / "4_Relatorio_exp.docx").write_bytes(b"x")
        host = self._host(tmp_path)

        host._show_completion_message(
            tmp_path, True, {"frames": 120, "detections": 118, "tracks": 1}
        )

        data = self._shown(host)
        assert data.title == "Analysis Completed"
        assert "Frames processed: 120" in data.message
        assert "Total detections: 118" in data.message
        assert "Unique tracks: 1" in data.message
        assert "3_CoordMovimento_exp.parquet" in data.message
        assert "4_Relatorio_exp.docx" in data.message
        assert str(tmp_path) in data.message

    def test_no_detections_has_its_own_title(self, tmp_path):
        host = self._host(tmp_path)

        host._show_completion_message(tmp_path, False, None, "no_detections")

        data = self._shown(host)
        assert data.title == "Analysis Completed - No Detections"
        assert "no detection was found" in data.message

    def test_failure_points_at_the_raw_data(self, tmp_path):
        host = self._host(tmp_path)

        host._show_completion_message(tmp_path, False, None, "error")

        data = self._shown(host)
        assert data.title == "Recording Completed"
        assert "automatic analysis failed" in data.message
        # An empty folder lists no files at all.
        assert "Files generated" not in data.message

    def test_success_without_stats_is_reported_as_a_failure(self, tmp_path):
        host = self._host(tmp_path)

        host._show_completion_message(tmp_path, True, None)

        assert self._shown(host).title == "Recording Completed"

    def test_without_bus_nothing_is_published(self, tmp_path):
        host = PostAnalysisHost(tmp_path, project_data={}, analysis_params={})

        host._show_completion_message(tmp_path, True, {"frames": 1, "detections": 1, "tracks": 1})

    def test_unlistable_folder_still_produces_a_message(self, tmp_path, monkeypatch):
        import zebtrack.utils.report_files as report_files

        def _deny(_folder):
            raise PermissionError("share dropped")

        monkeypatch.setattr(report_files, "list_session_outputs", _deny)

        assert LiveAnalysisPostProcessorMixin._format_generated_files(tmp_path) == ""


class TestZoneLookup:
    def test_reference_frame_needs_a_project(self, tmp_path):
        host = PostAnalysisHost(tmp_path, project_data={}, analysis_params={})
        assert host._resolve_live_reference_frame_path() is None

        host.project_manager.project_path = str(tmp_path)
        assert host._resolve_live_reference_frame_path() == (
            tmp_path / "live_camera_reference_frame.png"
        )

        host.project_manager = None  # type: ignore[assignment]
        assert host._resolve_live_reference_frame_path() is None

    def test_multi_zones_fall_back_to_the_reference_frame_key(self, tmp_path):
        host = PostAnalysisHost(tmp_path, project_data={}, analysis_params={})
        host.project_manager.project_path = str(tmp_path)
        zones = _two_aquariums()
        reference = tmp_path / "live_camera_reference_frame.png"
        pm: Any = host.project_manager
        pm.get_multi_aquarium_zone_data.side_effect = lambda key: (
            zones if Path(key) == reference else None
        )

        assert host._resolve_live_multi_aquarium_zone_data(tmp_path / "v.mp4") is zones

    def test_multi_zones_without_project_are_none(self, tmp_path):
        host = PostAnalysisHost(tmp_path, project_data={}, analysis_params={})
        pm: Any = host.project_manager
        pm.get_multi_aquarium_zone_data.return_value = None

        assert host._resolve_live_multi_aquarium_zone_data(tmp_path / "v.mp4") is None
        host.project_manager = None  # type: ignore[assignment]
        assert host._resolve_live_multi_aquarium_zone_data(tmp_path / "v.mp4") is None

    def test_collect_skips_what_is_not_an_aquarium_trajectory(self, tmp_path):
        host = PostAnalysisHost(tmp_path, project_data={}, analysis_params={})
        assert host._collect_multi_aquarium_trajectory_outputs(tmp_path / "missing") == {}

        (tmp_path / "aquarium_x").mkdir()  # not numbered, even with a trajectory inside
        (tmp_path / "aquarium_x" / "3_CoordMovimento_s.parquet").write_bytes(b"x")
        (tmp_path / "aquarium_2").mkdir()  # numbered but empty
        (tmp_path / "aquarium_3").write_text("a file, not a folder", encoding="utf-8")
        (tmp_path / "aquarium_1").mkdir()
        trajectory = tmp_path / "aquarium_1" / "3_CoordMovimento_s_aquarium_1.parquet"
        trajectory.write_bytes(b"x")

        outputs = host._collect_multi_aquarium_trajectory_outputs(tmp_path)

        # Folder N holds aquarium id N - 1.
        assert outputs == {
            0: {"results_dir": tmp_path / "aquarium_1", "trajectory_path": trajectory}
        }

    def test_project_views_refresh_carries_the_reason(self, tmp_path):
        from zebtrack.ui.event_bus_v2 import UIEvents

        host = PostAnalysisHost(tmp_path, project_data={}, analysis_params={})
        host._publish_project_views_refresh("ignored without a bus")
        host.event_bus = MagicMock()

        host._publish_project_views_refresh("Live analysis complete")

        (call,) = host.event_bus.publish.call_args_list
        assert call.args[0].type == UIEvents.UI_REFRESH_PROJECT_VIEWS
        assert call.args[0].data.reason == "Live analysis complete"


class TestPostAnalysisFlow:
    """``_on_session_complete`` branches around the analysis itself."""

    def _host(self, tmp_path, monkeypatch, *, analysis_params=None):
        output_dir = tmp_path / "live_20261116_110000"
        output_dir.mkdir()
        host = PostAnalysisHost(output_dir, project_data={}, analysis_params=analysis_params or {})
        host.root = MagicMock()
        monkeypatch.setattr(
            "zebtrack.core.recording.live_analysis_post_processor.threading.Thread",
            _ImmediateThread,
        )
        return host, output_dir

    def test_second_completion_is_ignored(self, tmp_path, monkeypatch):
        host, output_dir = self._host(tmp_path, monkeypatch)
        host._analysis_completed = True

        host._on_session_complete(output_dir)

        assert host.stopped_with == []
        host.root.after.assert_not_called()

    def test_no_trajectory_reports_failure(self, tmp_path, monkeypatch):
        host, output_dir = self._host(tmp_path, monkeypatch)
        host._build_post_analysis_service = MagicMock()  # type: ignore[method-assign]

        host._on_session_complete(output_dir)

        host._build_post_analysis_service.assert_not_called()
        assert host.root.after.call_args.args[2:] == (output_dir, False)

    def test_an_analysis_crash_reports_error(self, tmp_path, monkeypatch):
        host, output_dir = self._host(tmp_path, monkeypatch)
        _write_trajectory(output_dir)

        def _boom():
            raise RuntimeError("analysis service unavailable")

        host._build_post_analysis_service = _boom  # type: ignore[method-assign]

        host._on_session_complete(output_dir)

        assert host.root.after.call_args.args[2:] == (output_dir, False, None, "error")

    def test_session_overrides_reach_the_analysis(self, tmp_path, monkeypatch):
        from unittest.mock import patch

        params = {
            "freezing_velocity_threshold": 0.8,
            "freezing_min_duration_s": 2.5,
            "smoothing_window_length": 9,
            "smoothing_polyorder": 3,
            "behavioral_analysis": {"thigmotaxis_margin_cm": 1.5},
            "group": "Controle",
            "day": 3,
            "subject_id": "S07",
        }
        host, output_dir = self._host(tmp_path, monkeypatch, analysis_params=params)
        _write_trajectory(output_dir)
        service = _analysis_service_double()
        host._build_post_analysis_service = lambda: service  # type: ignore[method-assign]

        with (
            patch("zebtrack.analysis.reporters.ExcelReporter"),
            patch("zebtrack.analysis.reporters.WordReporter"),
            patch("zebtrack.analysis.reporters.ReporterContext"),
        ):
            host._on_session_complete(output_dir)

        kwargs = service.run_full_analysis_as_dto.call_args.kwargs
        assert kwargs["freezing_vel_threshold"] == 0.8
        assert kwargs["freezing_min_duration"] == 2.5
        assert kwargs["smoothing_window_length"] == 9
        assert kwargs["smoothing_polyorder"] == 3
        assert kwargs["behavioral_config"] == {"thigmotaxis_margin_cm": 1.5}
        assert (kwargs["metadata"]["group"], kwargs["metadata"]["day"]) == ("Controle", 3)
        assert kwargs["metadata"]["subject_id"] == "S07"
        registered = host.project_manager.register_processing_outputs.call_args.kwargs
        assert registered["summary_excel"].endswith("4_Relatorio_adhoc_exp.xlsx")
        assert registered["report_path"].endswith("4_Relatorio_adhoc_exp.docx")
        assert registered["group"] == "Controle"


class TestMultiAquariumRegistrationEdges:
    """When the per-aquarium analysis cannot run, the outputs are still registered."""

    def _session(self, tmp_path, tracks):
        output_dir = tmp_path / "live_20261116_120000"
        output_dir.mkdir()
        (output_dir / "adhoc_exp.mp4").write_bytes(b"")
        for aq_id, by_track in tracks.items():
            folder = output_dir / f"aquarium_{aq_id + 1}"
            folder.mkdir()
            _trajectory_rows(by_track).to_parquet(
                folder / f"3_CoordMovimento_adhoc_exp_aquarium_{aq_id + 1}.parquet"
            )
        return output_dir

    def _run(self, tmp_path, monkeypatch, *, zones, tracks, reports=None, project=True):
        from unittest.mock import patch

        output_dir = self._session(tmp_path, tracks)
        host = PostAnalysisHost(output_dir, project_data={}, analysis_params={})
        host.root = MagicMock()
        host.event_bus = MagicMock()
        pm: Any = host.project_manager
        pm.project_path = str(tmp_path) if project else None
        pm.get_multi_aquarium_zone_data.return_value = zones
        service = _analysis_service_double()
        service.run_multi_aquarium_analysis.return_value = {0: None, 1: None}
        host._build_post_analysis_service = lambda: service  # type: ignore[method-assign]
        monkeypatch.setattr(
            "zebtrack.core.recording.live_analysis_post_processor.threading.Thread",
            _ImmediateThread,
        )
        with patch(
            "zebtrack.analysis.reporters.export_multi_aquarium_reports",
            return_value=reports or {},
        ):
            host._on_session_complete(output_dir, keep_data=True)
        return host, service, output_dir

    def test_missing_zones_register_raw_outputs_and_report_failure(self, tmp_path, monkeypatch):
        host, service, output_dir = self._run(
            tmp_path, monkeypatch, zones=None, tracks={0: {1: _ONE_SECOND}}
        )

        service.run_multi_aquarium_analysis.assert_not_called()
        registered = host.project_manager.register_multi_aquarium_outputs.call_args.kwargs
        entry = registered["outputs_by_aquarium"][0]
        assert entry["results_dir"] == str(output_dir / "aquarium_1")
        assert "group" not in entry  # no zones, no experimental metadata
        assert host.root.after.call_args.args[2:] == (output_dir, False, None, "error")

    def test_missing_zones_without_project_registers_nothing_multi(self, tmp_path, monkeypatch):
        host, _service, _out = self._run(
            tmp_path, monkeypatch, zones=None, tracks={0: {1: _ONE_SECOND}}, project=False
        )

        host.project_manager.register_multi_aquarium_outputs.assert_not_called()
        # The session itself is registered all the same (Reports tab).
        host.project_manager.register_processing_outputs.assert_called_once()

    def test_unconfigured_and_empty_aquariums_are_skipped(self, tmp_path, monkeypatch):
        import pandas as pd

        zones = _two_aquariums()
        zones.aquariums = zones.aquariums[:1]  # aquarium 1 has no configuration
        output_dir = self._session(tmp_path, {1: {1001: _ONE_SECOND}})
        folder = output_dir / "aquarium_1"
        folder.mkdir()
        pd.DataFrame(columns=["timestamp", "frame", "track_id"]).to_parquet(
            folder / "3_CoordMovimento_adhoc_exp_aquarium_1.parquet"
        )
        from unittest.mock import patch

        host = PostAnalysisHost(output_dir, project_data={}, analysis_params={})
        host.root = MagicMock()
        pm: Any = host.project_manager
        pm.project_path = str(tmp_path)
        pm.get_multi_aquarium_zone_data.return_value = zones
        service = _analysis_service_double()
        host._build_post_analysis_service = lambda: service  # type: ignore[method-assign]
        monkeypatch.setattr(
            "zebtrack.core.recording.live_analysis_post_processor.threading.Thread",
            _ImmediateThread,
        )
        with patch("zebtrack.analysis.reporters.export_multi_aquarium_reports"):
            host._on_session_complete(output_dir, keep_data=True)

        service.run_multi_aquarium_analysis.assert_not_called()
        registered = pm.register_multi_aquarium_outputs.call_args.kwargs["outputs_by_aquarium"]
        assert sorted(registered) == [0, 1]
        assert registered[0]["group"] == "G"  # configured aquarium keeps its metadata
        assert "group" not in registered[1]

    def test_no_reports_still_register_the_trajectories(self, tmp_path, monkeypatch):
        host, service, output_dir = self._run(
            tmp_path,
            monkeypatch,
            zones=_two_aquariums(),
            tracks={0: {1: _ONE_SECOND}, 1: {1001: _ONE_SECOND}},
        )

        service.run_multi_aquarium_analysis.assert_called_once()
        registered = host.project_manager.register_multi_aquarium_outputs.call_args.kwargs
        assert sorted(registered["outputs_by_aquarium"]) == [0, 1]
        assert host.root.after.call_args.args[2:] == (output_dir, False, None, "error")

    def test_reports_are_attached_per_aquarium(self, tmp_path, monkeypatch):
        reports = {
            0: {"summary_path": "aq1.xlsx", "report_path": "aq1.docx"},
            1: {"summary_path": "aq2.xlsx"},
        }
        host, _service, _out = self._run(
            tmp_path,
            monkeypatch,
            zones=_two_aquariums(),
            tracks={0: {1: _ONE_SECOND}, 1: {1001: _ONE_SECOND}},
            reports=reports,
        )

        outputs = host.project_manager.register_multi_aquarium_outputs.call_args.kwargs[
            "outputs_by_aquarium"
        ]
        assert outputs[0]["parquet_files"]["summary_excel"] == "aq1.xlsx"
        assert outputs[0]["parquet_files"]["report_docx"] == "aq1.docx"
        assert outputs[1]["parquet_files"]["summary_excel"] == "aq2.xlsx"
        assert "report_docx" not in outputs[1]["parquet_files"]
        assert outputs[1]["subject_id"] == "S02"
        refresh = [
            c.args[0].data.reason
            for c in host.event_bus.publish.call_args_list
            if getattr(c.args[0].data, "reason", None)
        ]
        assert "Live multi-aquarium analysis complete" in refresh


class TestArenaFallbackAndMultiDetection:
    def test_without_detections_the_arena_is_a_centred_third_of_the_frame(self):
        service = DummyPostProcessor(project_data={}, polygon=None, analysis_params={})
        service._actual_width = 600
        service._actual_height = 400
        service._detected_aquarium_bboxes = []
        service.detector_service = MagicMock()
        service.camera = SimpleNamespace(actual_width=600, actual_height=400)  # type: ignore[assignment]
        service._arena_defined_event = MagicMock()
        service._animals_per_aquarium = 2
        service.project_manager.project_path = "/p"

        service._define_arena_from_detections()

        pm: Any = service.project_manager
        (zone,) = pm.save_zone_data.call_args.args
        # side = sqrt(600 * 400 / 3) = 282.84..., centred on (300, 200).
        assert zone.polygon == [[158, 58], [441, 58], [441, 341], [158, 341]]
        assert pm.save_zone_data.call_args.kwargs["persist"] is True
        service.detector_service.configure_zones.assert_called_once_with(
            zone_data=zone, width=600, height=400
        )
        service.detector_service.detector.set_single_subject_mode.assert_called_once_with(False)
        assert service._aquarium_detection_phase is False

    def test_median_of_the_detected_boxes_is_the_arena(self):
        service = DummyPostProcessor(project_data={}, polygon=None, analysis_params={})
        service._actual_width = 640
        service._actual_height = 480
        service._detected_aquarium_bboxes = [
            (10, 20, 300, 400),
            (12, 18, 310, 390),
            (90, 90, 90, 90),
        ]
        service.detector_service = MagicMock()
        service.camera = None
        service._arena_defined_event = MagicMock()
        service._animals_per_aquarium = 1
        service.project_manager.project_path = None

        service._define_arena_from_detections()

        pm: Any = service.project_manager
        (zone,) = pm.save_zone_data.call_args.args
        assert zone.polygon == [[12, 20], [300, 20], [300, 390], [12, 390]]
        assert pm.save_zone_data.call_args.kwargs["persist"] is False

    def test_recorder_without_partitioned_writer_gets_flat_rows(self, tmp_path):
        import numpy as np

        detector = MagicMock()
        host = _MultiHost(tmp_path, recorder=None, detector=detector)
        recorder = SimpleNamespace(start_time=1.0, rows=[])
        recorder.write_detection_data = lambda ts, frame, dets: recorder.rows.append(  # type: ignore[attr-defined]
            (frame, list(dets))
        )
        host.recorder = recorder
        multi = MagicMock()
        multi.detect_partitioned_optimized.return_value = {0: ["a"], 1: ["b", "c"]}
        host._multi_aq_detector = multi

        flat = host._run_multi_aquarium_detection(
            np.zeros((4, 4, 3), dtype=np.uint8), 9, SimpleNamespace(aquariums=[])
        )

        assert flat == ["a", "b", "c"]
        assert recorder.rows == [(9, ["a", "b", "c"])]  # type: ignore[attr-defined]

    def test_without_detector_nothing_is_detected(self, tmp_path):
        import numpy as np

        host = _MultiHost(tmp_path, recorder=None, detector=None)

        assert host._run_multi_aquarium_detection(np.zeros((4, 4, 3)), 1, SimpleNamespace()) == []
