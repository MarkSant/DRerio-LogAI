"""Ledger de frames da sessão ao vivo — correlaciona parquet, MP4 e relógio.

A sessão ao vivo mantém TRÊS numerações independentes:

* ``frame_count`` da thread de captura (1-based, só incrementa em captura
  bem-sucedida) — é o número gravado na coluna ``frame`` de
  ``3_CoordMovimento_<base>.parquet``;
* ``_video_frames_written`` da thread de vídeo — o índice real dentro do MP4;
* o relógio de parede/monotônico do instante de captura.

Sem um mapa persistido entre elas, um único frame perdido desloca todo o
alinhamento seguinte e não deixa rastro no disco. Este módulo grava esse mapa
como sidecar ``6_FrameLedger_<base>.parquet`` (+ CSV streamado, para sobreviver
a um crash de sessão), UMA LINHA POR FRAME CAPTURADO, com o desfecho de cada
frame:

``written``             — escrito no MP4 (``video_frame_index`` é o índice real);
``dropped_queue_full``  — a fila de vídeo encheu; o frame nunca chegou à thread
                          de vídeo (registrado pela thread de CAPTURA, a única
                          que sabe desse descarte);
``write_failed``        — o frame saiu da fila mas ``write_video_frame`` falhou
                          (``OSError``); o contador do MP4 NÃO avança;
``not_recording``       — a sessão não estava gravando vídeo nesse instante.

O schema de ``3_CoordMovimento`` é IMUTÁVEL por contrato (CLAUDE.md), então
nenhuma coluna é acrescentada lá: a correção da base de tempo é feita no
consumo, por join ``pipeline_frame == 3_CoordMovimento.frame``.

DOIS PRODUTORES, UM LEDGER: as threads de captura e de vídeo chamam ``record``
concorrentemente; tudo passa por um ``threading.Lock`` (mesmo padrão de
``ClosedLoopLatencyLog``). O flush em disco acontece numa thread daemon
dedicada — o caminho quente de captura nunca faz I/O síncrono.

LIMITE HONESTO: ``cv2.VideoWriter.write()`` devolve ``None`` e não reporta falha
do encoder. Uma linha ``written`` significa "o Python entregou o frame ao
writer sem exceção", não "o encoder confirmou o frame".
"""

from __future__ import annotations

import csv
import json
import threading
import time
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

# Ordem das colunas do CSV/parquet do ledger. Append-only: consumidores externos
# (reconstrução da linha do tempo) posicionam por nome, mas a ordem estável
# mantém os CSVs de sessões antigas legíveis lado a lado.
LEDGER_COLUMNS: list[str] = [
    "pipeline_frame",
    "video_frame_index",
    "t_capture_perf",
    "t_capture_wall",
    "outcome",
    "is_analysis_frame",
    "queued_for_analysis",
]

OUTCOME_WRITTEN = "written"
OUTCOME_DROPPED_QUEUE_FULL = "dropped_queue_full"
OUTCOME_WRITE_FAILED = "write_failed"
OUTCOME_NOT_RECORDING = "not_recording"

VALID_OUTCOMES: frozenset[str] = frozenset(
    {
        OUTCOME_WRITTEN,
        OUTCOME_DROPPED_QUEUE_FULL,
        OUTCOME_WRITE_FAILED,
        OUTCOME_NOT_RECORDING,
    }
)

# Índice usado quando o frame não corresponde a nenhum frame do MP4.
NO_VIDEO_INDEX = -1


class FrameLedger:
    """Acumulador thread-safe do mapa frame-de-pipeline ↔ frame-de-vídeo ↔ tempo.

    Uma instância vive por sessão ao vivo. Pode ser criada ANTES de a pasta de
    saída existir (a gravação só começa depois da fase de detecção de aquário):
    as linhas ficam em memória até ``bind`` informar o destino.
    """

    def __init__(
        self,
        output_dir: str | Path | None = None,
        base_name: str = "session",
        flush_interval_s: float = 0.25,
    ) -> None:
        self._lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._rows: list[dict[str, Any]] = []
        self._unflushed: list[dict[str, Any]] = []
        self._dir: Path | None = Path(output_dir) if output_dir else None
        self._base: str = base_name or "session"
        self._csv_header_written = False
        self._anchor: dict[str, Any] = {}
        self._flush_interval_s = flush_interval_s
        self._wake = threading.Event()
        self._stop = threading.Event()
        # daemon=True: threads worker não-daemon travam o shutdown do pytest
        # (docs/archive/PHASES.md, Phase 7).
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="FrameLedgerWriterThread",
            daemon=True,
        )
        self._writer_thread.start()

    # ------------------------------------------------------------------
    # Destino em disco
    # ------------------------------------------------------------------
    @property
    def is_bound(self) -> bool:
        """True quando a pasta de saída já é conhecida (o flush pode ocorrer)."""
        with self._lock:
            return self._dir is not None

    def bind(self, output_dir: str | Path, base_name: str | None = None) -> None:
        """Define (uma única vez) a pasta e o nome-base dos arquivos do ledger.

        Chamado quando o recorder abre a sessão. Linhas já acumuladas em memória
        são drenadas para o CSV no próximo flush.
        """
        with self._lock:
            if self._dir is not None:
                return
            self._dir = Path(output_dir)
            if base_name:
                self._base = base_name
        log.info(
            "frame_ledger.bound",
            output_dir=str(output_dir),
            base_name=self._base,
            buffered_rows=self.row_count,
        )
        self._wake.set()

    @property
    def csv_path(self) -> Path | None:
        """Caminho do CSV streamado, ou None enquanto não houver ``bind``."""
        with self._lock:
            return None if self._dir is None else self._dir / f"6_FrameLedger_{self._base}.csv"

    @property
    def parquet_path(self) -> Path | None:
        """Caminho do parquet final, ou None enquanto não houver ``bind``."""
        with self._lock:
            return None if self._dir is None else self._dir / f"6_FrameLedger_{self._base}.parquet"

    @property
    def anchor_path(self) -> Path | None:
        """Caminho do JSON de âncora da sessão, ou None sem ``bind``."""
        with self._lock:
            if self._dir is None:
                return None
            return self._dir / f"6_FrameLedger_{self._base}_anchor.json"

    # ------------------------------------------------------------------
    # Produtores (threads de captura e de vídeo)
    # ------------------------------------------------------------------
    def record(
        self,
        pipeline_frame: int,
        t_capture_perf: float | None,
        t_capture_wall: float | None,
        outcome: str,
        *,
        video_frame_index: int = NO_VIDEO_INDEX,
        is_analysis_frame: bool = False,
        queued_for_analysis: bool = False,
    ) -> None:
        """Registra o desfecho de UM frame capturado. Sem I/O — apenas memória.

        Args:
            pipeline_frame: ``frame_count`` da thread de captura (o mesmo número
                gravado na coluna ``frame`` de ``3_CoordMovimento``).
            t_capture_perf: ``perf_counter`` do instante de captura (monotônico).
            t_capture_wall: ``time()`` do MESMO instante — o par âncora que
                permite datar o evento em relógio de parede.
            outcome: um de ``VALID_OUTCOMES``.
            video_frame_index: índice real no MP4 (0-based), fornecido pela
                thread CONSUMIDORA. ``-1`` quando o frame não foi escrito.
            is_analysis_frame: respeitou a cadência determinística
                (``frame % analysis_interval_frames == 0``).
            queued_for_analysis: foi de fato enfileirado para detecção — inclui
                o enfileiramento oportunista de frames fora da cadência.
        """
        row = {
            "pipeline_frame": int(pipeline_frame),
            "video_frame_index": int(video_frame_index),
            "t_capture_perf": None if t_capture_perf is None else float(t_capture_perf),
            "t_capture_wall": None if t_capture_wall is None else float(t_capture_wall),
            "outcome": str(outcome),
            "is_analysis_frame": bool(is_analysis_frame),
            "queued_for_analysis": bool(queued_for_analysis),
        }
        with self._lock:
            self._rows.append(row)
            self._unflushed.append(row)
        self._wake.set()

    def set_anchor(self, **fields: Any) -> None:
        """Acrescenta campos à âncora da sessão (fps nominal, t0 do recorder…)."""
        with self._lock:
            self._anchor.update({k: v for k, v in fields.items() if v is not None})

    # ------------------------------------------------------------------
    # Thread de flush (daemon)
    # ------------------------------------------------------------------
    def _writer_loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self._flush_interval_s)
            self._wake.clear()
            self._flush()

    def _flush(self) -> None:
        """Escreve no CSV as linhas ainda não persistidas (best-effort)."""
        with self._lock:
            if self._dir is None or not self._unflushed:
                return
            pending = self._unflushed
            self._unflushed = []
            directory = self._dir
            csv_path = directory / f"6_FrameLedger_{self._base}.csv"
        with self._io_lock:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                # Cabeçalho quando ainda não foi escrito E o arquivo está ausente
                # ou vazio (uma tentativa anterior pode ter criado 0 bytes).
                new_file = not self._csv_header_written and (
                    not csv_path.exists() or csv_path.stat().st_size == 0
                )
                with csv_path.open("a", newline="", encoding="utf-8") as fh:
                    writer = csv.DictWriter(fh, fieldnames=LEDGER_COLUMNS)
                    if new_file:
                        writer.writeheader()
                    for row in pending:
                        writer.writerow({col: row.get(col) for col in LEDGER_COLUMNS})
                self._csv_header_written = True
            # except Exception justified: I/O best-effort numa thread daemon —
            # uma falha de disco não pode derrubar a captura.
            except Exception:
                # As linhas voltam para a FRENTE da fila de pendentes: sem isso
                # elas só existiriam em memória e um crash antes do ``finalize``
                # as perderia no disco — exatamente a promessa de resiliência a
                # crash que o CSV streamado existe para cumprir.
                with self._lock:
                    self._unflushed[:0] = pending
                log.warning("frame_ledger.csv_stream_failed", path=str(csv_path))

    # ------------------------------------------------------------------
    # Fim da sessão
    # ------------------------------------------------------------------
    def finalize(self) -> Path | None:
        """Encerra a thread de flush, escreve parquet + âncora e devolve o parquet.

        Best-effort: sem pandas/pyarrow o CSV já é o artefato durável.
        """
        self._stop.set()
        self._wake.set()
        if self._writer_thread.is_alive():
            self._writer_thread.join(timeout=2.0)
        self._flush()
        self._write_anchor()

        with self._lock:
            rows = list(self._rows)
            directory = self._dir
            base = self._base
        if directory is None:
            log.warning("frame_ledger.finalize.unbound", rows=len(rows))
            return None
        if not rows:
            log.info("frame_ledger.finalize.no_rows", base=base)
            return None
        parquet_path = directory / f"6_FrameLedger_{base}.parquet"
        try:
            import pandas as pd

            directory.mkdir(parents=True, exist_ok=True)
            frame = pd.DataFrame(rows, columns=LEDGER_COLUMNS)
            frame.to_parquet(parquet_path, index=False)
            log.info(
                "frame_ledger.finalize.parquet_written",
                path=str(parquet_path),
                rows=len(rows),
            )
            return parquet_path
        # except Exception justified: pandas/pyarrow são opcionais nesta camada;
        # o CSV é o artefato durável, o parquet é conveniência.
        except Exception:
            log.warning(
                "frame_ledger.finalize.parquet_failed",
                path=str(parquet_path),
                rows=len(rows),
            )
            return None

    def build_anchor(self) -> dict[str, Any]:
        """Monta a âncora da sessão a partir das linhas + campos informados.

        ``perf_counter`` é monotônico e SEM época: sem o par ``t0_perf`` /
        ``t0_wall`` não há como cruzar o ledger com o parquet da trajetória
        (relógio de parede) nem com ``5_ClosedLoop_*``. Por isso a âncora é
        obrigatória, não opcional.
        """
        with self._lock:
            rows = list(self._rows)
            anchor = dict(self._anchor)
            base = self._base

        timed = [r for r in rows if r["t_capture_perf"] is not None]
        first = timed[0] if timed else None
        video_rows = [r for r in rows if r["video_frame_index"] >= 0]

        fps_real_medio: float | None = None
        if len(timed) >= 2:
            span = float(timed[-1]["t_capture_perf"]) - float(timed[0]["t_capture_perf"])
            if span > 0:
                fps_real_medio = (len(timed) - 1) / span

        anchor.setdefault("base_name", base)
        anchor["t0_perf"] = None if first is None else first["t_capture_perf"]
        anchor["t0_wall"] = None if first is None else first["t_capture_wall"]
        anchor["fps_real_medio"] = fps_real_medio
        anchor["first_captured_index"] = None if not rows else rows[0]["pipeline_frame"]
        anchor["first_video_index"] = None if not video_rows else video_rows[0]["video_frame_index"]
        anchor["first_video_pipeline_frame"] = (
            None if not video_rows else video_rows[0]["pipeline_frame"]
        )
        anchor["rows"] = len(rows)
        anchor.setdefault("recorder_start_time", None)
        anchor.setdefault("fps_nominal", None)
        anchor.setdefault("analysis_interval_frames", None)
        anchor["generated_wall_s"] = time.time()
        return anchor

    def _write_anchor(self) -> None:
        anchor_path = self.anchor_path
        if anchor_path is None:
            return
        try:
            anchor_path.parent.mkdir(parents=True, exist_ok=True)
            anchor_path.write_text(
                json.dumps(self.build_anchor(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log.info("frame_ledger.anchor_written", path=str(anchor_path))
        # except Exception justified: artefato de análise opcional; o encerramento
        # da sessão nunca pode falhar por causa dele.
        except Exception:
            log.warning("frame_ledger.anchor_write_failed", path=str(anchor_path))

    # ------------------------------------------------------------------
    # Introspecção
    # ------------------------------------------------------------------
    @property
    def row_count(self) -> int:
        """Número de linhas acumuladas até agora (thread-safe)."""
        with self._lock:
            return len(self._rows)

    def rows_snapshot(self) -> list[dict[str, Any]]:
        """Cópia rasa das linhas acumuladas (para testes e inspeção)."""
        with self._lock:
            return [dict(r) for r in self._rows]


# ----------------------------------------------------------------------
# Leitura / reconstrução da linha do tempo (consumo pós-sessão)
# ----------------------------------------------------------------------
def _coerce_row(raw: dict[str, Any]) -> dict[str, Any]:
    """Normaliza uma linha vinda do CSV (tudo string) para os tipos do ledger."""

    def _num(value: Any) -> float | None:
        if value is None or value == "":
            return None
        return float(value)

    def _flag(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"true", "1"}

    return {
        "pipeline_frame": int(float(raw["pipeline_frame"])),
        "video_frame_index": int(float(raw["video_frame_index"])),
        "t_capture_perf": _num(raw.get("t_capture_perf")),
        "t_capture_wall": _num(raw.get("t_capture_wall")),
        "outcome": str(raw.get("outcome") or ""),
        "is_analysis_frame": _flag(raw.get("is_analysis_frame")),
        "queued_for_analysis": _flag(raw.get("queued_for_analysis")),
    }


def load_ledger(session_dir: str | Path, base_name: str) -> list[dict[str, Any]]:
    """Carrega as linhas do ledger de uma sessão (parquet, com fallback no CSV).

    O CSV é o artefato resiliente a crash: se a sessão morreu antes do
    ``finalize`` não existe parquet, mas as linhas até o último flush estão lá.
    """
    directory = Path(session_dir)
    parquet_path = directory / f"6_FrameLedger_{base_name}.parquet"
    if parquet_path.exists():
        try:
            import pandas as pd

            frame = pd.read_parquet(parquet_path)
            return [_coerce_row(dict(r)) for r in frame.to_dict("records")]
        # except Exception justified: pandas/pyarrow são opcionais aqui; o CSV
        # cobre o mesmo conteúdo.
        except Exception:
            log.warning("frame_ledger.load.parquet_failed", path=str(parquet_path))
    csv_path = directory / f"6_FrameLedger_{base_name}.csv"
    if not csv_path.exists():
        return []
    with csv_path.open(encoding="utf-8", newline="") as fh:
        return [_coerce_row(row) for row in csv.DictReader(fh)]


def load_anchor(session_dir: str | Path, base_name: str) -> dict[str, Any]:
    """Carrega a âncora da sessão (``{}`` quando ausente ou ilegível)."""
    path = Path(session_dir) / f"6_FrameLedger_{base_name}_anchor.json"
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    # except Exception justified: artefato externo; leitura tolerante.
    except Exception:
        log.warning("frame_ledger.load.anchor_failed", path=str(path))
        return {}
    return loaded if isinstance(loaded, dict) else {}


def perf_to_wall(t_perf: float, anchor: dict[str, Any]) -> float | None:
    """Converte um ``perf_counter`` da sessão em relógio de parede.

    ``perf_counter`` é monotônico e SEM época — só o par ``t0_perf``/``t0_wall``
    da âncora permite datar o evento (``wall = t0_wall + (t_perf - t0_perf)``).
    """
    t0_perf = anchor.get("t0_perf")
    t0_wall = anchor.get("t0_wall")
    if t0_perf is None or t0_wall is None:
        return None
    return float(t0_wall) + (float(t_perf) - float(t0_perf))


def index_by_pipeline_frame(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Indexa as linhas do ledger por ``pipeline_frame``.

    ``pipeline_frame`` é o mesmo número da coluna ``frame`` de
    ``3_CoordMovimento_<base>.parquet``, então este índice é o join que
    responde, para cada detecção: em que instante foi capturada e a que frame do
    MP4 corresponde (``video_frame_index``; ``-1`` = não existe no MP4).
    """
    return {int(row["pipeline_frame"]): row for row in rows}
