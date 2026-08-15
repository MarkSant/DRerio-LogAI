"""Tests for closed-loop latency logging (ROI trigger -> serial ACK timing).

Covers three layers:
* ``ClosedLoopLatencyLog`` — metric math, CSV streaming, parquet finalize.
* ``ArduinoManager`` ACK correlation — enqueue_tracked / _consume_ack / flush.
* ``FrameProcessingMixin`` dispatch — tracked context is built and forwarded.
"""

from __future__ import annotations

import csv
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest

from zebtrack.core.recording.frame_processing_pipeline import FrameProcessingMixin
from zebtrack.core.services.closed_loop_latency import CSV_COLUMNS, ClosedLoopLatencyLog

# --------------------------------------------------------------------------- #
# ClosedLoopLatencyLog
# --------------------------------------------------------------------------- #


def _context(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "event_id": 1,
        "frame": 100,
        "roi": "A",
        "edge": "enter",
        "token": 1,
        "frame_t0": 10.0,
        "decision_perf": 10.020,  # +20 ms software pipeline
        "session_ts_s": 3.5,
        "trigger_wall_s": 1_700_000_000.0,
        "analysis_interval_frames": 10,
        "fps": 30.0,
    }
    base.update(overrides)
    return base


def test_metrics_computed_from_timestamps(tmp_path):
    log = ClosedLoopLatencyLog(tmp_path, "exp")
    # t_send at +25 ms, t_ack at +40 ms relative to frame_t0=10.0
    log.on_sample(_context(), t_send=10.025, t_ack=10.040, ack_text="Red LED 1 ON")

    rows = _read_csv(tmp_path / "5_ClosedLoop_exp.csv")
    assert len(rows) == 1
    row = rows[0]
    assert float(row["serial_act_ms"]) == pytest.approx(15.0, abs=1e-6)  # 40-25
    assert float(row["frame_to_ack_ms"]) == pytest.approx(40.0, abs=1e-6)  # 40-0
    assert float(row["capture_to_decision_ms"]) == pytest.approx(20.0, abs=1e-6)
    assert float(row["decision_to_send_ms"]) == pytest.approx(5.0, abs=1e-6)
    # sampling quantization upper bound = 10 / 30 * 1000
    assert float(row["sampling_interval_ms"]) == pytest.approx(333.333, abs=1e-2)
    assert row["roi"] == "A"
    assert row["edge"] == "enter"
    assert row["ack_text"] == "Red LED 1 ON"


def test_queue_wait_and_inference_split_the_software_pipeline(tmp_path):
    log = ClosedLoopLatencyLog(tmp_path, "exp")
    # frame_t0=10.0, dequeue em +12 ms, decisão em +20 ms.
    log.on_sample(
        _context(dequeue_perf=10.012),
        t_send=10.025,
        t_ack=10.040,
        ack_text="Red LED 1 ON",
    )

    row = _read_csv(tmp_path / "5_ClosedLoop_exp.csv")[0]
    assert float(row["queue_wait_ms"]) == pytest.approx(12.0, abs=1e-6)
    assert float(row["inference_ms"]) == pytest.approx(8.0, abs=1e-6)
    # A soma é exatamente o agregado antigo, preservado por compatibilidade.
    assert float(row["queue_wait_ms"]) + float(row["inference_ms"]) == pytest.approx(
        float(row["capture_to_decision_ms"]), abs=1e-9
    )


def test_queue_wait_and_inference_blank_without_dequeue_stamp(tmp_path):
    log = ClosedLoopLatencyLog(tmp_path, "exp")
    log.on_sample(_context(), t_send=10.025, t_ack=10.040, ack_text="ON")  # sem dequeue_perf

    row = _read_csv(tmp_path / "5_ClosedLoop_exp.csv")[0]
    assert row["queue_wait_ms"] == ""
    assert row["inference_ms"] == ""
    assert float(row["capture_to_decision_ms"]) == pytest.approx(20.0, abs=1e-6)


def test_canonical_columns_stay_first_and_new_ones_are_appended():
    # ``analise_latencia.py`` (externo) depende destes nomes e desta ordem.
    assert CSV_COLUMNS[1] == "serial_act_ms"
    assert CSV_COLUMNS[2] == "frame_to_ack_ms"
    legacy = [
        "event_id",
        "serial_act_ms",
        "frame_to_ack_ms",
        "capture_to_decision_ms",
        "decision_to_send_ms",
        "sampling_interval_ms",
        "roi",
        "edge",
        "token",
        "ack_text",
        "frame",
        "session_ts_s",
        "trigger_wall_s",
        "analysis_interval_frames",
        "fps",
        "frame_t0_perf",
        "decision_perf",
        "t_send_perf",
        "t_ack_perf",
    ]
    assert CSV_COLUMNS[: len(legacy)] == legacy  # append-only
    assert CSV_COLUMNS[len(legacy) :] == [
        "queue_wait_ms",
        "inference_ms",
        "dequeue_perf",
        "fps_configured",
        "sampling_interval_ms_configured",
    ]


def test_fps_is_measured_and_fps_configured_is_kept_separate_when_they_differ(tmp_path):
    """Câmera excede a taxa configurada: ``fps`` != ``fps_configured`` no CSV.

    Regressão do defeito depositado no P4: o logger gravava a taxa CONFIGURADA
    em ``fps`` como se fosse a alcançada. ``fps`` agora vem da taxa medida
    (contexto construído por ``FrameProcessingMixin`` a partir do
    ``FrameLedger``); ``fps_configured`` é o nominal, em coluna própria.
    """
    log = ClosedLoopLatencyLog(tmp_path, "exp")
    # Configurado: 30 fps -> 333.33 ms de intervalo de amostragem.
    # Medido: 41.2 fps (câmera excedeu o configurado) -> 242.7 ms.
    log.on_sample(
        _context(fps=41.2, fps_configured=30.0, analysis_interval_frames=10),
        t_send=10.025,
        t_ack=10.040,
        ack_text="Red LED 1 ON",
    )

    row = _read_csv(tmp_path / "5_ClosedLoop_exp.csv")[0]
    assert float(row["fps"]) == pytest.approx(41.2)
    assert float(row["fps_configured"]) == pytest.approx(30.0)
    assert float(row["sampling_interval_ms"]) == pytest.approx(242.7, abs=0.1)
    assert float(row["sampling_interval_ms_configured"]) == pytest.approx(333.333, abs=1e-2)
    # As duas taxas nunca podem coincidir por acidente de implementação neste teste.
    assert float(row["fps"]) != float(row["fps_configured"])


def test_fps_blank_when_measurement_not_yet_available(tmp_path):
    """Sem taxa medida ainda (início de sessão), ``fps`` fica em branco — nunca

    cai silenciosamente para o valor configurado, que reintroduziria o defeito
    original.
    """
    log = ClosedLoopLatencyLog(tmp_path, "exp")
    log.on_sample(
        _context(fps=None, fps_configured=30.0, analysis_interval_frames=10),
        t_send=10.025,
        t_ack=10.040,
        ack_text="Red LED 1 ON",
    )

    row = _read_csv(tmp_path / "5_ClosedLoop_exp.csv")[0]
    assert row["fps"] == ""
    assert row["sampling_interval_ms"] == ""
    assert float(row["fps_configured"]) == pytest.approx(30.0)
    assert float(row["sampling_interval_ms_configured"]) == pytest.approx(333.333, abs=1e-2)


def test_unmatched_trigger_leaves_serial_metrics_empty(tmp_path):
    log = ClosedLoopLatencyLog(tmp_path, "exp")
    # No ACK ever arrived: t_ack None -> serial/frame_to_ack blank, software ok.
    log.on_sample(_context(), t_send=10.025, t_ack=None, ack_text=None)

    row = _read_csv(tmp_path / "5_ClosedLoop_exp.csv")[0]
    assert row["serial_act_ms"] == ""
    assert row["frame_to_ack_ms"] == ""
    assert float(row["capture_to_decision_ms"]) == pytest.approx(20.0, abs=1e-6)


def test_csv_header_written_once_and_rows_appended(tmp_path):
    log = ClosedLoopLatencyLog(tmp_path, "exp")
    log.on_sample(_context(event_id=1), t_send=10.02, t_ack=10.03, ack_text="ON")
    log.on_sample(_context(event_id=2, edge="exit"), t_send=11.02, t_ack=11.03, ack_text="OFF")

    with (tmp_path / "5_ClosedLoop_exp.csv").open(encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    assert lines[0].split(",") == CSV_COLUMNS  # single header
    assert len([ln for ln in lines[1:] if ln]) == 2
    assert log.row_count == 2


def test_header_written_when_prior_file_is_empty(tmp_path):
    # A 0-byte file left by a crashed prior attempt must be treated as new so
    # the first streamed row is preceded by a header (valid CSV).
    csv_path = tmp_path / "5_ClosedLoop_exp.csv"
    csv_path.touch()  # empty file exists before any row is written
    log = ClosedLoopLatencyLog(tmp_path, "exp")
    log.on_sample(_context(), t_send=10.02, t_ack=10.03, ack_text="ON")

    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert lines[0].split(",") == CSV_COLUMNS
    assert len([ln for ln in lines[1:] if ln]) == 1


def test_finalize_writes_parquet(tmp_path):
    pd = pytest.importorskip("pandas")
    log = ClosedLoopLatencyLog(tmp_path, "exp")
    log.on_sample(_context(), t_send=10.025, t_ack=10.040, ack_text="ON")

    path = log.finalize()
    assert path is not None and path.exists()
    frame = pd.read_parquet(path)
    assert list(frame.columns) == CSV_COLUMNS
    assert frame.loc[0, "serial_act_ms"] == pytest.approx(15.0, abs=1e-6)


def _read_csv(path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# --------------------------------------------------------------------------- #
# ArduinoManager ACK correlation
# --------------------------------------------------------------------------- #

from zebtrack.io.arduino_manager import ArduinoManager  # noqa: E402


def _connected_manager() -> ArduinoManager:
    mgr = ArduinoManager(controller=SimpleNamespace())
    # Pretend connected without opening a real port.
    mgr.arduino = cast(Any, SimpleNamespace(ser=SimpleNamespace(is_open=True)))
    return mgr


def test_consume_ack_matches_oldest_pending_fifo():
    mgr = _connected_manager()
    calls: list[tuple] = []
    mgr.set_latency_sink(lambda ctx, ts, ta, txt: calls.append((ctx["event_id"], ts, ta, txt)))

    # Two tracked sends stamped in order.
    with mgr._latency_lock:
        mgr._pending_acks.append((100.0, {"event_id": 1}))
        mgr._pending_acks.append((100.5, {"event_id": 2}))

    assert mgr._consume_ack("Red LED 1 ON", 100.2) is True
    assert mgr._consume_ack("Red LED 1 OFF", 100.7) is True
    assert [c[0] for c in calls] == [1, 2]  # FIFO order
    assert calls[0][1:] == (100.0, 100.2, "Red LED 1 ON")


def test_consume_ack_noop_without_pending():
    mgr = _connected_manager()
    mgr.set_latency_sink(lambda *a: None)
    assert mgr._consume_ack("stray text", 1.0) is False  # nothing to match -> logged normally


def test_flush_pending_emits_unmatched_with_none_ack():
    mgr = _connected_manager()
    seen: list[tuple] = []
    mgr.set_latency_sink(lambda ctx, ts, ta, txt: seen.append((ctx["event_id"], ta)))
    with mgr._latency_lock:
        mgr._pending_acks.append((5.0, {"event_id": 7}))

    mgr.flush_pending_acks()
    assert seen == [(7, None)]
    with mgr._latency_lock:
        assert not mgr._pending_acks


def test_enqueue_tracked_queues_context_when_sink_set():
    mgr = _connected_manager()
    mgr.set_latency_sink(lambda *a: None)
    assert mgr.enqueue_tracked(1, {"event_id": 42}) is True
    token, context = mgr._write_queue.get_nowait()
    assert token == 1
    assert context == {"event_id": 42}


def test_enqueue_tracked_drops_context_without_sink():
    mgr = _connected_manager()  # no sink registered
    assert mgr.enqueue_tracked(1, {"event_id": 42}) is True
    token, context = mgr._write_queue.get_nowait()
    assert token == 1
    assert context is None  # untracked fallback


# --------------------------------------------------------------------------- #
# FrameProcessingMixin dispatch integration
# --------------------------------------------------------------------------- #

SQUARE_A = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.int32)


class TrackingManager:
    """Fake ArduinoManager exposing the tracked path + a manual ACK pump."""

    def __init__(self) -> None:
        self.sink = None
        self.tracked: list[tuple[int, dict]] = []
        self.plain: list[int] = []

    def is_connected(self) -> bool:
        return True

    def set_latency_sink(self, sink) -> None:
        self.sink = sink

    def flush_pending_acks(self) -> None:  # pragma: no cover - not exercised here
        pass

    def enqueue_tracked(self, token: int, context: dict) -> bool:
        self.tracked.append((token, context))
        return True

    def enqueue(self, token: int) -> bool:
        self.plain.append(token)
        return True


class FakeDetector:
    def __init__(self, names, polygons) -> None:
        self.roi_names = names
        self.scaled_roi_polygons = polygons


class FakeFrameLedger:
    """Stand-in for ``FrameLedger`` exposing only ``current_fps_measured``."""

    def __init__(self, fps_measured: float | None) -> None:
        self._fps_measured = fps_measured

    def current_fps_measured(self) -> float | None:
        return self._fps_measured


class _Harness(FrameProcessingMixin):
    def __init__(self, project_data, manager, detector, recorder, frame_ledger=None) -> None:
        self.controller = cast(Any, SimpleNamespace(arduino_manager=manager))
        self.project_manager = cast(Any, SimpleNamespace(project_data=project_data))
        self.detector_service = cast(Any, SimpleNamespace(detector=detector))
        self.recorder = recorder
        self.analysis_interval_frames = 10
        self._actual_fps = 30.0
        self._frame_ledger = frame_ledger


PROJECT = {
    "use_arduino": True,
    "arduino_bindings": [{"roi": "A", "on_enter": 1, "on_exit": 2}],
}


def _bbox_at(cx, cy, half=2):
    return (cx - half, cy - half, cx + half, cy + half, 0.9, 1, 0)


def test_dispatch_builds_tracked_context_and_writes_log(tmp_path):
    manager = TrackingManager()
    detector = FakeDetector(["A"], [SQUARE_A])
    recorder = SimpleNamespace(output_folder=str(tmp_path), base_name="exp", start_time=1000.0)
    h = _Harness(PROJECT, manager, detector, recorder)
    h._reset_arduino_zone_state()
    assert h._arduino_zone_enabled is True

    # Animal enters A on an analyzed frame with a capture timestamp present.
    h._dispatch_arduino_zone_commands(
        [_bbox_at(5, 5)], frame_number=100, capture_ts=500.0, dequeue_ts=500.010
    )

    # Tracked path used, context carries ROI/edge/frame_t0.
    assert len(manager.tracked) == 1
    token, ctx = manager.tracked[0]
    assert token == 1
    assert ctx["roi"] == "A" and ctx["edge"] == "enter"
    assert ctx["frame_t0"] == 500.0
    assert ctx["dequeue_perf"] == 500.010
    assert ctx["analysis_interval_frames"] == 10
    # No frame ledger attached in this harness -> no measurement available yet.
    assert ctx["fps"] is None
    assert ctx["fps_configured"] == 30.0

    # A sink was registered; simulate the ACK and finalize.
    assert manager.sink is not None
    manager.sink(ctx, 500.030, 500.045, "Red LED 1 ON")
    h._finalize_closed_loop_log()

    rows = _read_csv(tmp_path / "5_ClosedLoop_exp.csv")
    assert rows[0]["roi"] == "A"
    assert float(rows[0]["serial_act_ms"]) == pytest.approx(15.0, abs=1e-6)


def test_dispatch_uses_measured_fps_from_frame_ledger_not_configured(tmp_path):
    """A câmera excedeu o configurado: o contexto deve carregar a taxa MEDIDA.

    Regressão do defeito depositado no P4 (``fps`` = configurado gravado como
    se fosse alcançado). Aqui o ledger fake simula uma câmera entregando 41.2
    fps medidos enquanto as settings configuram 30.
    """
    manager = TrackingManager()
    detector = FakeDetector(["A"], [SQUARE_A])
    recorder = SimpleNamespace(output_folder=str(tmp_path), base_name="exp", start_time=1000.0)
    ledger = FakeFrameLedger(fps_measured=41.2)
    h = _Harness(PROJECT, manager, detector, recorder, frame_ledger=ledger)
    h._reset_arduino_zone_state()

    h._dispatch_arduino_zone_commands(
        [_bbox_at(5, 5)], frame_number=100, capture_ts=500.0, dequeue_ts=500.010
    )

    token, ctx = manager.tracked[0]
    assert ctx["fps"] == pytest.approx(41.2)
    assert ctx["fps_configured"] == pytest.approx(30.0)
    assert ctx["fps"] != ctx["fps_configured"]

    assert manager.sink is not None
    manager.sink(ctx, 500.030, 500.045, "Red LED 1 ON")
    h._finalize_closed_loop_log()

    row = _read_csv(tmp_path / "5_ClosedLoop_exp.csv")[0]
    assert float(row["fps"]) == pytest.approx(41.2)
    assert float(row["fps_configured"]) == pytest.approx(30.0)
    assert float(row["sampling_interval_ms"]) == pytest.approx(242.7, abs=0.1)
    assert float(row["sampling_interval_ms_configured"]) == pytest.approx(333.333, abs=1e-2)


def test_dispatch_without_capture_ts_uses_plain_enqueue(tmp_path):
    manager = TrackingManager()
    detector = FakeDetector(["A"], [SQUARE_A])
    recorder = SimpleNamespace(output_folder=str(tmp_path), base_name="exp", start_time=1000.0)
    h = _Harness(PROJECT, manager, detector, recorder)
    h._reset_arduino_zone_state()

    # No capture timestamp -> latency cannot be measured -> plain enqueue.
    h._dispatch_arduino_zone_commands([_bbox_at(5, 5)], frame_number=100, capture_ts=None)
    assert manager.plain == [1]
    assert manager.tracked == []
    assert h._closed_loop_log is None
