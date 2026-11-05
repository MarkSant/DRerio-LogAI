"""Unit tests for ``core/recording/live_analysis_post_processor.py``."""

from __future__ import annotations

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

    def stop_session(self, *, cancelled: bool = False, keep_data: bool = False) -> bool:
        self.stopped_with.append(keep_data)
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
