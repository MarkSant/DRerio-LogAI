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
from pathlib import Path
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


def test_failed_flush_retries_the_same_rows(tmp_path, monkeypatch):
    """Uma falha de I/O não pode consumir as linhas pendentes.

    Se o flush descartasse o lote ao falhar, as linhas existiriam só em memória
    e um crash antes do ``finalize`` as perderia no disco — o CSV streamado
    deixaria de ser resiliente a crash.
    """
    ledger = _ledger(tmp_path, flush_interval_s=60.0)
    ledger._stop.set()
    ledger._wake.set()
    ledger._writer_thread.join(timeout=2.0)

    ledger.record(1, 1.0, 1_700_000_000.0, "written", video_frame_index=0)
    ledger.record(2, 2.0, 1_700_000_001.0, "written", video_frame_index=1)

    original_open = Path.open
    calls = {"n": 0}

    def flaky_open(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("disco indisponível")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", flaky_open)

    ledger._flush()  # falha: as linhas voltam para a fila
    assert not (tmp_path / "6_FrameLedger_exp.csv").exists()
    assert len(ledger._unflushed) == 2

    ledger._flush()  # segunda tentativa grava tudo, na ordem original
    rows = load_ledger(tmp_path, "exp")
    assert [r["pipeline_frame"] for r in rows] == [1, 2]
    assert not ledger._unflushed
    ledger.finalize()


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


def test_current_fps_measured_matches_anchor_formula(tmp_path):
    """``current_fps_measured`` usa a mesma fórmula de ``fps_real_medio``.

    Utilizável DURANTE a sessão (não só no ``finalize``) — é a fonte que o
    logger closed-loop consulta para não gravar a taxa configurada como se
    fosse a alcançada.
    """
    ledger = _ledger(tmp_path, flush_interval_s=60.0)
    assert ledger.current_fps_measured() is None  # sem amostras ainda

    ledger.record(1, 100.0, 1_700_000_000.0, "not_recording")
    assert ledger.current_fps_measured() is None  # 1 amostra não basta

    ledger.record(2, 101.0, 1_700_000_001.0, "written", video_frame_index=0)
    ledger.record(3, 102.0, 1_700_000_002.0, "written", video_frame_index=1)
    # 3 amostras em 2 s de perf_counter -> 1 fps real (mesmo cálculo do anchor).
    assert ledger.current_fps_measured() == pytest.approx(1.0)
    ledger.finalize()


def test_current_fps_measured_reflects_camera_exceeding_configured_rate(tmp_path):
    """Câmera entregando mais que o configurado: a taxa medida reflete isso.

    Regressão do defeito depositado no P4: sessões com 30 fps configurados
    entregaram 41.2/39.1 fps reais. O ledger precisa medir isso corretamente
    a partir dos timestamps de captura, não repetir o valor configurado.
    """
    ledger = _ledger(tmp_path, flush_interval_s=60.0)
    # 41.2 fps configurado-excedente -> intervalo entre frames ~= 1/41.2 s.
    interval = 1.0 / 41.2
    for i in range(1, 11):
        ledger.record(
            i, 100.0 + (i - 1) * interval, 1_700_000_000.0, "written", video_frame_index=i - 1
        )
    assert ledger.current_fps_measured() == pytest.approx(41.2, abs=0.05)
    ledger.finalize()


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


def test_multi_aquarium_session_frames_are_written_to_the_session_mp4(tmp_path):
    """#635: the parent of a multi-aquarium session never has ``is_recording``.

    The video thread tested ``is_recording and video_writer``, so every frame
    of such a session was logged ``not_recording`` and no MP4 existed; the
    ledger did not even bind, the parent having no ``output_folder``.
    """
    from zebtrack.core.detection import ZoneData
    from zebtrack.io.recorder import Recorder

    recorder = Recorder()
    assert recorder.start_recording_multi_aquarium(
        output_folder=str(tmp_path),
        width=4,
        height=4,
        zones_by_aquarium={
            0: ZoneData(polygon=[(0, 0), (2, 0), (2, 4), (0, 4)]),
            1: ZoneData(polygon=[(2, 0), (4, 0), (4, 4), (2, 4)]),
        },
        base_name="exp",
        session_video=True,
    )
    harness = _PipelineHarness(tmp_path, n_frames=6)
    harness.recorder = cast(Any, recorder)

    rows = _run_pipeline(harness)
    recorder.stop_recording()

    assert {r["outcome"] for r in rows} == {"written"}
    assert [r["video_frame_index"] for r in rows] == list(range(6))
    assert load_ledger(tmp_path, "exp"), "the ledger must bind to the session folder"


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


# ---------------------------------------------------------------------------
# Pinned origin (v8 F5): the live analysis window and retime_from_ledger share t0
# ---------------------------------------------------------------------------


def test_pinned_origin_wins_over_row_order(tmp_path):
    """Frame 1 is pinned by the capture thread; a racing row cannot move t0."""
    ledger = _ledger(tmp_path, flush_interval_s=0.01)
    ledger.pin_origin(100.0, 1_700_000_000.0)
    ledger.record(2, 100.5, 1_700_000_000.5, "dropped_queue_full")  # appended first
    ledger.record(1, 100.0, 1_700_000_000.0, "written", video_frame_index=0)

    assert ledger.origin_perf == 100.0
    anchor = ledger.build_anchor()
    assert anchor["t0_perf"] == 100.0
    assert anchor["t0_wall"] == 1_700_000_000.0
    ledger.finalize()


def test_origin_is_pinned_once(tmp_path):
    ledger = _ledger(tmp_path, flush_interval_s=0.01)
    ledger.pin_origin(100.0, 1.0)
    ledger.pin_origin(200.0, 2.0)
    assert ledger.origin_perf == 100.0
    assert ledger.build_anchor()["t0_wall"] == 1.0
    ledger.finalize()


def test_origin_without_pin_is_the_first_timed_row(tmp_path):
    ledger = _ledger(tmp_path, flush_interval_s=0.01)
    assert ledger.origin_perf is None
    ledger.record(1, None, None, "not_recording")
    ledger.record(2, 50.0, 7.0, "not_recording")
    assert ledger.origin_perf == 50.0
    assert ledger.build_anchor()["t0_perf"] == 50.0
    ledger.finalize()


# --------------------------------------------------------------------------- #
# Stop: the tail of the session (#636)
# --------------------------------------------------------------------------- #


class _SlowRecorder(_FakeRecorder):
    """Writer that takes ``delay_s`` per frame, so the video queue backs up."""

    def __init__(self, output_folder, delay_s: float) -> None:
        super().__init__(output_folder)
        self._delay_s = delay_s

    def write_video_frame(self, frame) -> None:
        time.sleep(self._delay_s)
        super().write_video_frame(frame)


def _stop_like_stop_session(harness: _PipelineHarness, run_s: float, drain_s: float):
    """Run capture + video for ``run_s``, then stop in ``stop_session``'s order."""
    harness._reset_frame_ledger()
    harness._capture_stop_event = threading.Event()
    harness.capture_thread = threading.Thread(target=harness._capture_loop, daemon=True)
    harness.video_recording_thread = threading.Thread(
        target=harness._video_recording_loop, daemon=True
    )
    harness.capture_thread.start()
    harness.video_recording_thread.start()
    time.sleep(run_s)

    left = harness._drain_video_queue_for_stop(drain_s)
    harness.exit_event.set()
    harness._clear_queues()
    harness.capture_thread.join(timeout=5)
    harness.video_recording_thread.join(timeout=5)
    ledger = harness._frame_ledger
    assert ledger is not None
    rows = sorted(ledger.rows_snapshot(), key=lambda r: r["pipeline_frame"])
    harness._finalize_frame_ledger()
    return rows, left


def test_stop_writes_the_queued_tail_before_emptying_the_queues(tmp_path):
    """The video thread drains the queue: every captured frame reaches the MP4."""
    harness = _PipelineHarness(tmp_path, n_frames=10**9)
    harness.recorder = cast(Any, _SlowRecorder(tmp_path, delay_s=0.03))

    rows, left = _stop_like_stop_session(harness, run_s=0.4, drain_s=5.0)

    assert left == 0
    assert len(rows) == harness._last_captured_frame
    assert {r["outcome"] for r in rows} == {"written"}
    assert [r["video_frame_index"] for r in rows] == list(range(len(rows)))


def test_frames_left_after_the_deadline_are_logged_dropped_on_stop(tmp_path):
    """One ledger row per captured frame, to the very end of the session."""
    harness = _PipelineHarness(tmp_path, n_frames=10**9)
    harness.recorder = cast(Any, _SlowRecorder(tmp_path, delay_s=0.2))

    rows, left = _stop_like_stop_session(harness, run_s=0.5, drain_s=0.1)

    assert left > 0
    assert [r["pipeline_frame"] for r in rows] == list(range(1, harness._last_captured_frame + 1))
    by_outcome: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_outcome.setdefault(row["outcome"], []).append(row)
    assert set(by_outcome) == {"written", "dropped_on_stop"}
    assert len(by_outcome["dropped_on_stop"]) == left
    assert all(r["video_frame_index"] == -1 for r in by_outcome["dropped_on_stop"])
    # The tail is what was dropped: every dropped frame comes after every written one.
    assert max(r["pipeline_frame"] for r in by_outcome["written"]) < min(
        r["pipeline_frame"] for r in by_outcome["dropped_on_stop"]
    )


def test_capture_stops_before_the_drain(tmp_path):
    """No new frame is captured once the drain starts."""
    harness = _PipelineHarness(tmp_path, n_frames=10**9)
    harness.recorder = cast(Any, _SlowRecorder(tmp_path, delay_s=0.01))

    rows, _left = _stop_like_stop_session(harness, run_s=0.3, drain_s=1.0)
    captured_at_stop = harness._last_captured_frame
    time.sleep(0.1)

    assert harness._last_captured_frame == captured_at_stop
    assert len(rows) == captured_at_stop


def test_a_new_session_captures_again_after_a_stop(tmp_path):
    """The capture-only stop of the previous session must not leak into the next."""
    harness = _PipelineHarness(tmp_path)
    harness._capture_stop_event = threading.Event()
    harness._capture_stop_event.set()  # what the previous stop left behind
    for loop in ("_capture_loop", "_processing_loop", "_video_recording_loop"):
        setattr(harness, loop, lambda: None)

    assert harness._start_threads() is True

    assert harness._capture_stop_requested() is False
