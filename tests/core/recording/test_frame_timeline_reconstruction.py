"""Reconstrução da linha do tempo de uma sessão ao vivo — teste de objetivo.

Dado um diretório de sessão completo (``3_CoordMovimento``, ``5_ClosedLoop`` e
``6_FrameLedger`` + âncora), a pergunta que este PR precisa responder é:

    "a detecção do frame N do parquet ocorreu em que instante real e
     corresponde a que frame do MP4?"

A fórmula é:

    ``3_CoordMovimento.frame`` == ``6_FrameLedger.pipeline_frame``
        -> ``t_capture_perf``            (monotônico, instante de captura)
        -> ``t0_wall + (t_capture_perf - t0_perf)``   (relógio de parede)
        -> ``video_frame_index``         (índice real no MP4; -1 = não existe)

Os cenários exercitados incluem um ``dropped_queue_full`` e um ``write_failed``
ANTES das detecções, que são exatamente os pontos onde a correspondência
ingênua (``índice = frame - 1``) passa a mentir.
"""

from __future__ import annotations

import pytest

from zebtrack.core.recording.frame_ledger import (
    FrameLedger,
    index_by_pipeline_frame,
    load_anchor,
    load_ledger,
    perf_to_wall,
)
from zebtrack.core.services.closed_loop_latency import ClosedLoopLatencyLog

BASE = "sessao"
T0_PERF = 1_000.0
T0_WALL = 1_700_000_000.0
RECORDER_START = T0_WALL + 0.5  # a gravação começa depois da captura
PERIOD_S = 0.0333  # ~30 fps

# Frames 1..10; 3 descartado pela fila de vídeo, 6 falhou na escrita.
DROPPED = 3
WRITE_FAILED = 6
N_FRAMES = 10
ANALYSIS_INTERVAL = 2


def _capture_perf(frame: int) -> float:
    return T0_PERF + (frame - 1) * PERIOD_S


def _build_session(tmp_path):
    """Fabrica ledger + âncora, o parquet da trajetória e o log closed-loop."""
    ledger = FrameLedger(tmp_path, BASE, flush_interval_s=0.01)
    ledger.set_anchor(
        recorder_start_time=RECORDER_START,
        fps_nominal=30.0,
        analysis_interval_frames=ANALYSIS_INTERVAL,
    )
    video_index = 0
    for frame in range(1, N_FRAMES + 1):
        perf = _capture_perf(frame)
        wall = T0_WALL + (perf - T0_PERF)
        is_analysis = (frame % ANALYSIS_INTERVAL) == 0
        if frame == DROPPED:
            ledger.record(frame, perf, wall, "dropped_queue_full", is_analysis_frame=is_analysis)
            continue
        if frame == WRITE_FAILED:
            ledger.record(frame, perf, wall, "write_failed", is_analysis_frame=is_analysis)
            continue
        ledger.record(
            frame,
            perf,
            wall,
            "written",
            video_frame_index=video_index,
            is_analysis_frame=is_analysis,
            queued_for_analysis=True,
        )
        video_index += 1
    ledger.finalize()
    return ledger


def _write_trajectory(tmp_path, frames: list[int]):
    """``3_CoordMovimento`` com ``timestamp`` de PROCESSAMENTO (atrasado)."""
    pd = pytest.importorskip("pandas")
    # 80 ms de espera de fila + inferência somados ao instante real do evento —
    # é exatamente por isso que ``timestamp`` não serve para datar a detecção.
    processing_lag_s = 0.080
    rows = []
    for frame in frames:
        wall = T0_WALL + (_capture_perf(frame) - T0_PERF)
        rows.append(
            {
                "timestamp": (wall + processing_lag_s) - RECORDER_START,
                "frame": frame,
                "track_id": 1,
                "x1": 10.0,
                "y1": 10.0,
                "x2": 20.0,
                "y2": 20.0,
                "confidence": 0.9,
            }
        )
    path = tmp_path / f"3_CoordMovimento_{BASE}.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def _write_closed_loop(tmp_path, frame: int):
    """Uma linha de gatilho ROI para o frame dado, com a decomposição da latência."""
    log = ClosedLoopLatencyLog(tmp_path, BASE)
    frame_t0 = _capture_perf(frame)
    dequeue = frame_t0 + 0.040  # 40 ms de espera de fila
    decision = dequeue + 0.030  # 30 ms de inferência
    log.on_sample(
        {
            "event_id": 1,
            "frame": frame,
            "roi": "A",
            "edge": "enter",
            "token": 1,
            "frame_t0": frame_t0,
            "dequeue_perf": dequeue,
            "decision_perf": decision,
            "session_ts_s": (T0_WALL + (frame_t0 - T0_PERF)) - RECORDER_START,
            "trigger_wall_s": T0_WALL + (decision - T0_PERF),
            "analysis_interval_frames": ANALYSIS_INTERVAL,
            "fps": 30.0,
        },
        t_send=decision + 0.002,
        t_ack=decision + 0.014,
        ack_text="Red LED 1 ON",
    )
    log.finalize()


def test_detection_frame_maps_to_capture_instant_and_video_frame(tmp_path):
    pd = pytest.importorskip("pandas")
    _build_session(tmp_path)
    detections_at = [2, 4, 8, 10]
    _write_trajectory(tmp_path, detections_at)

    rows = load_ledger(tmp_path, BASE)
    anchor = load_anchor(tmp_path, BASE)
    by_frame = index_by_pipeline_frame(rows)
    trajectory = pd.read_parquet(tmp_path / f"3_CoordMovimento_{BASE}.parquet")

    # Índices reais no MP4: frame 3 (drop) e 6 (write_failed) não existem lá, de
    # modo que a partir deles ``índice = frame - 1`` estaria errado — e o ledger
    # é a única fonte que sabe disso.
    esperado_video_index = {2: 1, 4: 2, 8: 5, 10: 7}

    for frame in trajectory["frame"]:
        ledger_row = by_frame[int(frame)]
        instante_real = perf_to_wall(ledger_row["t_capture_perf"], anchor)
        assert instante_real == pytest.approx(
            T0_WALL + (_capture_perf(int(frame)) - T0_PERF), abs=1e-6
        )
        assert ledger_row["video_frame_index"] == esperado_video_index[int(frame)]

    # O ``timestamp`` do parquet é o relógio de PROCESSAMENTO: chega ~80 ms
    # depois do instante real. Serve para ordenar, não para datar.
    linha = trajectory[trajectory["frame"] == 4].iloc[0]
    instante_processamento = RECORDER_START + float(linha["timestamp"])
    instante_captura = perf_to_wall(by_frame[4]["t_capture_perf"], anchor)
    assert instante_captura is not None
    assert instante_processamento - instante_captura == pytest.approx(0.080, abs=1e-6)


def test_lost_frames_are_explained_not_silent(tmp_path):
    _build_session(tmp_path)
    by_frame = index_by_pipeline_frame(load_ledger(tmp_path, BASE))

    assert by_frame[DROPPED]["outcome"] == "dropped_queue_full"
    assert by_frame[WRITE_FAILED]["outcome"] == "write_failed"
    assert by_frame[DROPPED]["video_frame_index"] == -1
    assert by_frame[WRITE_FAILED]["video_frame_index"] == -1
    # Nenhum buraco na numeração do pipeline: 1..10, um por frame capturado.
    assert sorted(by_frame) == list(range(1, N_FRAMES + 1))
    # O MP4 tem 8 frames, não 10 — e o ledger diz exatamente quais.
    written = [r for r in by_frame.values() if r["outcome"] == "written"]
    assert sorted(r["video_frame_index"] for r in written) == list(range(8))


def test_anchor_reconstructs_wall_clock_for_any_perf_stamp(tmp_path):
    _build_session(tmp_path)
    anchor = load_anchor(tmp_path, BASE)

    assert anchor["t0_perf"] == pytest.approx(T0_PERF)
    assert anchor["t0_wall"] == pytest.approx(T0_WALL)
    assert anchor["recorder_start_time"] == pytest.approx(RECORDER_START)
    assert anchor["analysis_interval_frames"] == ANALYSIS_INTERVAL
    assert anchor["fps_real_medio"] == pytest.approx(1 / PERIOD_S, rel=1e-6)

    for frame in range(1, N_FRAMES + 1):
        perf = _capture_perf(frame)
        assert perf_to_wall(perf, anchor) == pytest.approx(T0_WALL + (perf - T0_PERF), abs=1e-6)


def test_closed_loop_row_joins_the_ledger_on_the_same_capture_instant(tmp_path):
    pd = pytest.importorskip("pandas")
    _build_session(tmp_path)
    _write_closed_loop(tmp_path, frame=4)

    by_frame = index_by_pipeline_frame(load_ledger(tmp_path, BASE))
    closed_loop = pd.read_parquet(tmp_path / f"5_ClosedLoop_{BASE}.parquet")
    linha = closed_loop.iloc[0]

    # As três fontes concordam sobre o mesmo instante de captura.
    assert float(linha["frame_t0_perf"]) == pytest.approx(by_frame[4]["t_capture_perf"])
    assert by_frame[int(linha["frame"])]["video_frame_index"] == 2

    # Espera de fila e inferência somam o agregado antigo — e agora dá para
    # afirmar qual dos dois domina.
    assert float(linha["queue_wait_ms"]) == pytest.approx(40.0, abs=1e-3)
    assert float(linha["inference_ms"]) == pytest.approx(30.0, abs=1e-3)
    assert float(linha["queue_wait_ms"]) + float(linha["inference_ms"]) == pytest.approx(
        float(linha["capture_to_decision_ms"]), abs=1e-6
    )
