"""Closed-loop latency logging for the live per-zone Arduino command path.

Software-only characterization (no photodiode / logic analyzer): reuses the
textual ACK the firmware echoes for every serial command (e.g. ``"Red LED 1
ON"``) to timestamp, per ROI enter/exit trigger, three moments captured with
``time.perf_counter()`` (monotonic):

* ``frame_t0``  — when the analyzed frame was read from the camera.
* ``t_send``    — immediately before the byte is written to the serial port.
* ``t_ack``     — immediately after the firmware's ACK line is received.

Derived per-trigger metrics (milliseconds):

* ``serial_act_ms``          = t_ack - t_send    (serial TX @9600 baud + firmware
                                                  actuation of the LED)
* ``frame_to_ack_ms``        = t_ack - frame_t0  (end-to-end: analyzed-frame
                                                  capture -> inference -> ROI
                                                  state machine -> serialization
                                                  -> LED ACK)
* ``capture_to_decision_ms`` = decision - frame_t0 (software pipeline before the
                                                    token is queued)
* ``decision_to_send_ms``    = t_send - decision (writer-thread queue latency)
* ``sampling_interval_ms``   = analysis_interval_frames / fps * 1000 (UPPER bound
                                of the extra quantization latency from analyzing
                                only 1 in N frames; NOT part of frame_to_ack_ms,
                                which starts at the *analyzed* frame's capture)

Rows stream to ``5_ClosedLoop_<base>.csv`` (flushed per trigger for crash
resilience) and are also written to ``5_ClosedLoop_<base>.parquet`` at session
end, alongside ``3_CoordMovimento_<base>.parquet``. The two canonical columns
(``serial_act_ms``, ``frame_to_ack_ms``) keep the exact names used by the
standalone ``analise_latencia.py`` pipeline so it runs unchanged.
"""

from __future__ import annotations

import csv
import threading
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

# Column order for the CSV/parquet. The first two are the canonical metrics
# consumed by the external ``analise_latencia.py`` — do not rename them.
CSV_COLUMNS: list[str] = [
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


def _ms(start: float | None, end: float | None) -> float | None:
    """Return ``(end - start)`` in milliseconds, or ``None`` if either is missing."""
    if start is None or end is None:
        return None
    return (end - start) * 1000.0


class ClosedLoopLatencyLog:
    """Thread-safe accumulator + writer for per-trigger closed-loop latencies.

    A single instance lives for one live session. ``on_sample`` is invoked from
    the ``ArduinoManager`` reader thread (ACK received) and, for unmatched
    triggers, from the session-end flush — both funnel through the same lock, so
    the in-memory rows and the streamed CSV stay consistent.
    """

    def __init__(self, output_dir: str | Path, base_name: str) -> None:
        self._dir = Path(output_dir)
        self._base = base_name or "session"
        self._rows: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._csv_path = self._dir / f"5_ClosedLoop_{self._base}.csv"
        self._parquet_path = self._dir / f"5_ClosedLoop_{self._base}.parquet"
        self._csv_header_written = False

    # ------------------------------------------------------------------
    # Sink entry point (called from the ArduinoManager reader/flush threads)
    # ------------------------------------------------------------------
    def on_sample(
        self,
        context: dict[str, Any],
        t_send: float | None,
        t_ack: float | None,
        ack_text: str | None,
    ) -> None:
        """Build one row from a trigger's context + serial timestamps and store it.

        Args:
            context: The per-trigger context dict built at dispatch time (ROI,
                edge, token, frame_t0, decision_perf, session_ts_s, etc.).
            t_send: ``perf_counter`` right before the serial write (may be None
                if the token never reached the wire).
            t_ack: ``perf_counter`` right after the firmware ACK (None when the
                ACK never arrived — unmatched trigger flushed at session end).
            ack_text: The raw ACK line, for auditing (None when unmatched).
        """
        row = self._build_row(context, t_send, t_ack, ack_text)
        with self._lock:
            self._rows.append(row)
            self._stream_csv_row(row)

    def _build_row(
        self,
        context: dict[str, Any],
        t_send: float | None,
        t_ack: float | None,
        ack_text: str | None,
    ) -> dict[str, Any]:
        frame_t0 = context.get("frame_t0")
        decision = context.get("decision_perf")
        fps = context.get("fps")
        interval = context.get("analysis_interval_frames")
        sampling_interval_ms: float | None = None
        if fps and interval:
            try:
                sampling_interval_ms = float(interval) / float(fps) * 1000.0
            except (TypeError, ZeroDivisionError, ValueError):
                sampling_interval_ms = None

        return {
            "event_id": context.get("event_id"),
            "serial_act_ms": _ms(t_send, t_ack),
            "frame_to_ack_ms": _ms(frame_t0, t_ack),
            "capture_to_decision_ms": _ms(frame_t0, decision),
            "decision_to_send_ms": _ms(decision, t_send),
            "sampling_interval_ms": sampling_interval_ms,
            "roi": context.get("roi"),
            "edge": context.get("edge"),
            "token": context.get("token"),
            "ack_text": ack_text,
            "frame": context.get("frame"),
            "session_ts_s": context.get("session_ts_s"),
            "trigger_wall_s": context.get("trigger_wall_s"),
            "analysis_interval_frames": interval,
            "fps": fps,
            "frame_t0_perf": frame_t0,
            "decision_perf": decision,
            "t_send_perf": t_send,
            "t_ack_perf": t_ack,
        }

    def _stream_csv_row(self, row: dict[str, Any]) -> None:
        """Append one row to the CSV, writing the header first (best-effort).

        Called under ``self._lock``. Opens/closes per row: the trigger rate is
        low (one line per ROI enter/exit), so the flush cost is negligible and a
        mid-session crash still leaves a complete CSV up to the last trigger.
        """
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            new_file = not self._csv_header_written and not self._csv_path.exists()
            with self._csv_path.open("a", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
                if new_file:
                    writer.writeheader()
                writer.writerow({col: row.get(col) for col in CSV_COLUMNS})
            self._csv_header_written = True
        # except Exception justified: best-effort disk I/O from a worker thread;
        # a failed stream must never crash serial reading. Rows stay in memory
        # for the parquet flush at session end.
        except Exception:
            log.warning("closed_loop_latency.csv_stream_failed", path=str(self._csv_path))

    # ------------------------------------------------------------------
    # Session end
    # ------------------------------------------------------------------
    def finalize(self) -> Path | None:
        """Write the parquet snapshot of all rows. Returns its path (or None).

        Best-effort: if pandas/pyarrow are unavailable the CSV already holds the
        data, so we log and return None rather than raising.
        """
        with self._lock:
            rows = list(self._rows)
        if not rows:
            log.info("closed_loop_latency.finalize.no_rows", base=self._base)
            return None
        try:
            import pandas as pd

            self._dir.mkdir(parents=True, exist_ok=True)
            frame = pd.DataFrame(rows, columns=CSV_COLUMNS)
            frame.to_parquet(self._parquet_path, index=False)
            log.info(
                "closed_loop_latency.finalize.parquet_written",
                path=str(self._parquet_path),
                rows=len(rows),
            )
            return self._parquet_path
        # except Exception justified: pandas/pyarrow optional at this layer; the
        # CSV is the durable artifact, parquet is a convenience.
        except Exception:
            log.warning(
                "closed_loop_latency.finalize.parquet_failed",
                path=str(self._parquet_path),
                rows=len(rows),
            )
            return None

    @property
    def row_count(self) -> int:
        """Number of rows accumulated so far (thread-safe)."""
        with self._lock:
            return len(self._rows)
