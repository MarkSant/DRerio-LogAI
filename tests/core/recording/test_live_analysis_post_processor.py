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


class TestPostAnalysisWiring:
    """``_on_session_complete`` → ``_run_post_analysis`` → reports."""

    def _run(self, tmp_path, monkeypatch, *, project_data, analysis_params):
        from unittest.mock import patch

        output_dir = tmp_path / "live_20260822_120000"
        output_dir.mkdir()
        _write_trajectory(output_dir)

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
