"""Testes do ledger de frames da sessão ao vivo.

Cobre as duas camadas:

* ``FrameLedger`` — acumulação thread-safe, streaming de CSV, parquet + âncora,
  e a garantia de que ``record()`` não faz I/O síncrono (o flush é daemon).
* ``FrameProcessingMixin`` — as threads de captura e de vídeo produzindo, juntas,
  UMA linha por frame capturado, com o índice real do MP4 vindo do consumidor.

O teste central é o do ``queue.Full``: um frame descartado na thread de captura
não pode deslocar silenciosamente o ``video_frame_index`` dos frames seguintes.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, cast

import numpy as np
import pytest

from zebtrack.core.recording.frame_ledger import (
    LEDGER_COLUMNS,
    FrameLedger,
    index_by_pipeline_frame,
    load_anchor,
    load_ledger,
    perf_to_wall,
)
from zebtrack.core.recording.frame_processing_pipeline import FrameProcessingMixin

FRAME = np.zeros((4, 4, 3), dtype=np.uint8)


# --------------------------------------------------------------------------- #
# FrameLedger — unidade
# --------------------------------------------------------------------------- #


def _ledger(tmp_path, **kwargs) -> FrameLedger:
    ledger = FrameLedger(tmp_path, "exp", **kwargs)
    return ledger


def test_record_streams_csv_with_single_header(tmp_path):
    ledger = _ledger(tmp_path, flush_interval_s=0.01)
    ledger.record(1, 10.0, 1_700_000_000.0, "written", video_frame_index=0)
    ledger.record(2, 10.03, 1_700_000_000.03, "dropped_queue_full")
    _wait_for(lambda: (tmp_path / "6_FrameLedger_exp.csv").exists())
    ledger.finalize()

    lines = (tmp_path / "6_FrameLedger_exp.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0].split(",") == LEDGER_COLUMNS
    assert len([ln for ln in lines[1:] if ln]) == 2
    assert ledger.row_count == 2


def test_record_does_no_synchronous_io(tmp_path):
    """O caminho quente de captura não pode ganhar I/O: o flush é daemon."""
    ledger = _ledger(tmp_path, flush_interval_s=60.0)
    assert ledger._writer_thread.daemon is True  # Phase 7: worker = daemon

    # Congela a thread de flush e prova que ``record`` sozinho não escreve nada.
    ledger._stop.set()
    ledger._wake.set()
    ledger._writer_thread.join(timeout=2.0)

    for i in range(1, 51):
        ledger.record(i, float(i), 1_700_000_000.0 + i, "written", video_frame_index=i - 1)

    assert not (tmp_path / "6_FrameLedger_exp.csv").exists()
    assert ledger.row_count == 50
    ledger.finalize()  # o flush final recupera tudo
    assert len(load_ledger(tmp_path, "exp")) == 50


def test_concurrent_producers_lose_no_row(tmp_path):
    """Duas threads reais escrevendo: nada se perde, nada duplica."""
    ledger = _ledger(tmp_path, flush_interval_s=0.01)
    per_thread = 300

    def producer(offset: int, outcome: str) -> None:
        for i in range(per_thread):
            ledger.record(offset + i, float(i), 1_700_000_000.0 + i, outcome)

    threads = [
        threading.Thread(target=producer, args=(0, "written"), daemon=True),
        threading.Thread(target=producer, args=(10_000, "dropped_queue_full"), daemon=True),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert ledger.row_count == 2 * per_thread
    ledger.finalize()
    rows = load_ledger(tmp_path, "exp")
    assert len(rows) == 2 * per_thread
    frames = [r["pipeline_frame"] for r in rows]
    assert len(set(frames)) == 2 * per_thread  # sem duplicatas


def test_finalize_writes_parquet_and_anchor(tmp_path):
    pytest.importorskip("pandas")
    ledger = _ledger(tmp_path, flush_interval_s=0.01)
    ledger.set_anchor(recorder_start_time=1_700_000_000.0, fps_nominal=30.0)
    ledger.record(1, 100.0, 1_700_000_000.0, "not_recording")
    ledger.record(2, 101.0, 1_700_000_001.0, "written", video_frame_index=0)
    ledger.record(3, 102.0, 1_700_000_002.0, "written", video_frame_index=1)

    path = ledger.finalize()
    assert path is not None and path.exists()

    anchor = load_anchor(tmp_path, "exp")
    assert anchor["t0_perf"] == 100.0
    assert anchor["t0_wall"] == 1_700_000_000.0
    assert anchor["first_captured_index"] == 1
    assert anchor["first_video_index"] == 0
    assert anchor["first_video_pipeline_frame"] == 2
    assert anchor["fps_nominal"] == 30.0
    assert anchor["recorder_start_time"] == 1_700_000_000.0
    # 3 amostras em 2 s de perf_counter -> 1 fps real
    assert anchor["fps_real_medio"] == pytest.approx(1.0)


def test_unbound_ledger_buffers_until_bind(tmp_path):
    ledger = FrameLedger(flush_interval_s=0.01)
    ledger.record(1, 1.0, 1_700_000_000.0, "not_recording")
    assert ledger.is_bound is False
    assert ledger.csv_path is None

    ledger.bind(tmp_path, "late")
    ledger.record(2, 2.0, 1_700_000_001.0, "written", video_frame_index=0)
    ledger.finalize()

    rows = load_ledger(tmp_path, "late")
    assert [r["pipeline_frame"] for r in rows] == [1, 2]


def test_perf_to_wall_reconstructs_from_anchor():
    anchor = {"t0_perf": 500.0, "t0_wall": 1_700_000_000.0}
    assert perf_to_wall(512.5, anchor) == pytest.approx(1_700_000_012.5)
    assert perf_to_wall(512.5, {}) is None


# --------------------------------------------------------------------------- #
# Pipeline — captura + vídeo produzindo o ledger juntas
# --------------------------------------------------------------------------- #


class _FakeCamera:
    """Câmera que entrega ``n_frames`` e depois sinaliza o fim da sessão."""

    _camera_index = 0

    def __init__(self, n_frames: int, exit_event: threading.Event) -> None:
        self._n = n_frames
        self._served = 0
        self._exit = exit_event

    def get_frame(self):
        if self._served >= self._n:
            self._exit.set()
            return False, None
        self._served += 1
        return True, FRAME.copy()


class _FakeRecorder:
    """Recorder mínimo; ``fail_on_calls`` levanta ``OSError`` nas escritas dadas."""

    def __init__(self, output_folder, fail_on_calls: set[int] | None = None) -> None:
        self.output_folder = str(output_folder)
        self.base_name = "exp"
        self.is_recording = True
        self.video_writer = object()
        self.start_time = 1_700_000_000.0
        self._fps = 30.0
        self.calls = 0
        self._fail_on = fail_on_calls or set()
        self.written: list[Any] = []

    def write_video_frame(self, frame) -> None:
        self.calls += 1
        if self.calls in self._fail_on:
            raise OSError("disco cheio")
        self.written.append(frame)


class _DroppingQueue(queue.Queue):
    """``video_queue`` que simula ``queue.Full`` em frames específicos."""

    def __init__(self, drop_frames: set[int], maxsize: int = 0) -> None:
        super().__init__(maxsize=maxsize)
        self._drop_frames = drop_frames

    def put(self, item, block=True, timeout=None):  # type: ignore[override]
        if isinstance(item, tuple) and item and item[0] in self._drop_frames:
            raise queue.Full
        super().put(item, block=block, timeout=timeout)


class _PipelineHarness(FrameProcessingMixin):
    """Instância mínima do mixin para rodar os loops de captura e vídeo."""

    def __init__(
        self,
        tmp_path,
        n_frames: int = 12,
        analysis_interval_frames: int = 1,
        drop_frames: set[int] | None = None,
        fail_writes: set[int] | None = None,
        frame_queue_maxsize: int = 0,
        recording: bool = True,
    ) -> None:
        self.exit_event = threading.Event()
        self.frame_queue = queue.Queue(maxsize=frame_queue_maxsize)
        self.video_queue = _DroppingQueue(drop_frames or set())
        self.camera = cast(Any, _FakeCamera(n_frames, self.exit_event))
        self.settings = None
        self.recorder = cast(Any, _FakeRecorder(tmp_path, fail_writes))
        self.is_capturing_for_video = recording
        self.analysis_interval_frames = analysis_interval_frames
        self._video_frames_written = 0
        self._dropped_frames_video = 0
        self._dropped_frames_processing = 0
        self._last_captured_frame = 0
        self._last_valid_frame_time = None
        self._camera_disconnected = False
        self._current_base_name = "exp"
        self._actual_fps = 30.0
        self._frame_ledger = None

    # Ganchos do mixin que não interessam a estes testes.
    def _check_camera_disconnect(self) -> None:
        return None

    def _on_camera_reconnected(self) -> None:  # pragma: no cover - não exercitado
        return None

    def _publish_video_drop_status(self) -> None:
        return None


def _run_pipeline(harness: _PipelineHarness) -> list[dict[str, Any]]:
    """Roda captura + vídeo concorrentes até a câmera esgotar, e finaliza."""
    harness._reset_frame_ledger()
    threads = [
        threading.Thread(target=harness._capture_loop, name="cap", daemon=True),
        threading.Thread(target=harness._video_recording_loop, name="vid", daemon=True),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive()
    # A thread de vídeo pode terminar com itens ainda na fila (o exit_event é
    # global); drena o restante como o consumidor faria. Uma linha por frame
    # capturado é a condição exata de término.
    ledger = harness._frame_ledger
    assert ledger is not None
    expected_rows = harness._last_captured_frame
    if ledger.row_count < expected_rows:
        harness.exit_event.clear()
        drain = threading.Thread(target=harness._video_recording_loop, daemon=True)
        drain.start()
        _wait_for(lambda: ledger.row_count >= expected_rows, timeout=10.0)
        harness.exit_event.set()
        drain.join(timeout=5)
    harness._finalize_frame_ledger()
    return sorted(ledger.rows_snapshot(), key=lambda r: r["pipeline_frame"])


def test_one_row_per_captured_frame_monotonic_without_gaps(tmp_path):
    harness = _PipelineHarness(tmp_path, n_frames=12)
    rows = _run_pipeline(harness)

    assert [r["pipeline_frame"] for r in rows] == list(range(1, 13))
    assert {r["outcome"] for r in rows} == {"written"}
    assert [r["video_frame_index"] for r in rows] == list(range(12))
    assert all(r["t_capture_perf"] is not None for r in rows)
    assert all(r["t_capture_wall"] is not None for r in rows)


def test_queue_full_drop_does_not_slide_following_video_indices(tmp_path):
    """Teste central: o frame descartado é registrado e o mapa segue exato."""
    harness = _PipelineHarness(tmp_path, n_frames=10, drop_frames={3, 7})
    rows = _run_pipeline(harness)
    by_frame = index_by_pipeline_frame(rows)

    assert len(rows) == 10
    for dropped in (3, 7):
        assert by_frame[dropped]["outcome"] == "dropped_queue_full"
        assert by_frame[dropped]["video_frame_index"] == -1

    written = [r for r in rows if r["outcome"] == "written"]
    # O índice do MP4 vem do CONSUMIDOR: contíguo, sem buraco onde houve drop.
    assert [r["video_frame_index"] for r in written] == list(range(8))
    # E o mapeamento pós-drop é o real, não ``frame - 1``.
    assert by_frame[4]["video_frame_index"] == 2
    assert by_frame[10]["video_frame_index"] == 7
    assert harness._dropped_frames_video == 2


def test_write_failure_is_distinguishable_from_queue_drop(tmp_path):
    # 3ª escrita falha -> frame 3 sai da fila mas não entra no MP4.
    harness = _PipelineHarness(tmp_path, n_frames=6, fail_writes={3})
    rows = _run_pipeline(harness)
    by_frame = index_by_pipeline_frame(rows)

    assert by_frame[3]["outcome"] == "write_failed"
    assert by_frame[3]["video_frame_index"] == -1
    assert "dropped_queue_full" not in {r["outcome"] for r in rows}
    # O contador do MP4 não avançou no frame falhado.
    assert by_frame[2]["video_frame_index"] == 1
    assert by_frame[4]["video_frame_index"] == 2


def test_analysis_cadence_and_opportunistic_queueing(tmp_path):
    harness = _PipelineHarness(tmp_path, n_frames=12, analysis_interval_frames=10)
    rows = _run_pipeline(harness)

    analysis = [r["pipeline_frame"] for r in rows if r["is_analysis_frame"]]
    assert analysis == [10]  # cadência determinística
    # Enfileiramento oportunista: o parquet NÃO contém só múltiplos de 10.
    assert all(r["queued_for_analysis"] for r in rows)


def test_opportunistic_queueing_marked_false_when_queue_is_full(tmp_path):
    # Fila de análise minúscula e sem consumidor: só os 2 primeiros entram.
    harness = _PipelineHarness(
        tmp_path, n_frames=6, analysis_interval_frames=10, frame_queue_maxsize=2
    )
    rows = _run_pipeline(harness)

    queued = [r["pipeline_frame"] for r in rows if r["queued_for_analysis"]]
    assert queued == [1, 2]
    assert all(r["outcome"] == "written" for r in rows)  # o vídeo não é afetado


def test_ledger_written_without_arduino(tmp_path):
    """O ledger não depende do caminho closed-loop (que exige bindings + ACK)."""
    harness = _PipelineHarness(tmp_path, n_frames=5)
    _run_pipeline(harness)

    assert not (tmp_path / "5_ClosedLoop_exp.csv").exists()
    assert (tmp_path / "6_FrameLedger_exp.csv").exists()
    rows = load_ledger(tmp_path, "exp")
    assert len(rows) == 5
    anchor = load_anchor(tmp_path, "exp")
    assert anchor["t0_perf"] is not None and anchor["t0_wall"] is not None
    assert anchor["recorder_start_time"] == 1_700_000_000.0


def test_not_recording_frames_are_recorded_without_video_index(tmp_path):
    harness = _PipelineHarness(tmp_path, n_frames=4, recording=False)
    rows = _run_pipeline(harness)

    assert {r["outcome"] for r in rows} == {"not_recording"}
    assert {r["video_frame_index"] for r in rows} == {-1}


def test_video_queue_legacy_item_is_tolerated(tmp_path):
    """Itens sem metadados (formato antigo) não quebram a thread de vídeo."""
    harness = _PipelineHarness(tmp_path, n_frames=0)
    harness._reset_frame_ledger()
    harness.video_queue.put(FRAME.copy())
    thread = threading.Thread(target=harness._video_recording_loop, daemon=True)
    thread.start()
    _wait_for(lambda: harness._video_frames_written == 1)
    harness.exit_event.set()
    thread.join(timeout=5)

    assert harness._frame_ledger is not None
    assert harness._frame_ledger.row_count == 0  # nada a correlacionar
    harness._finalize_frame_ledger()


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #


def _wait_for(predicate, timeout: float = 5.0, tick: float = 0.01) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(tick)
    raise AssertionError("condição não atingida dentro do timeout")
