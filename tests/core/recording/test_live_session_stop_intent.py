"""Stop-intent matrix for a live session: discard vs keep.

Three intents reach ``stop_session``:

* **discard** (``cancelled=True``) — user pressed "Cancel": wipe the folder.
* **keep** (``keep_data=True``) — user pressed "Finish and Save", or the
  external trigger said stop: preserve and run the post-analysis.
* **unknown** (defaults) — timer expiry or an automatic stop: the 50 %
  heuristic decides.

The heuristic used to be the ONLY rule, so an intentional early stop was read
as an abandoned take and the recording was deleted.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from zebtrack.core.recording.live_session_manager import LiveSessionManagerMixin


class DummyLiveService(LiveSessionManagerMixin):
    def __init__(self, output_dir: Path, *, planned_s: float, elapsed_s: float):
        self.settings = MagicMock()
        self.project_manager = MagicMock()
        self.project_manager.project_path = None
        self.project_manager.project_data = {}
        self.state_manager = MagicMock()
        self.detector_service = MagicMock()
        self.recording_service = MagicMock()
        self.event_bus: Any = None
        self.root = None
        self.recorder = MagicMock()
        self.recorder.start_time = time.time() - elapsed_s
        self._session_duration_s = planned_s
        self.current_output_dir = output_dir
        self._analysis_params = {}
        self.completed_with: list[bool] = []

        # --- o que ``stop_session`` toca no caminho de parada ---
        self.timer_id = None
        self.exit_event = MagicMock()
        self.capture_thread = None
        self.processing_thread = None
        self.video_recording_thread = None
        self.preview_window = None
        self.camera = None
        self._saved_detector_context = None
        self._video_frames_written = 0
        self._preview_window_destroyed = False
        self.on_session_stopped = None
        self.cleared_queues = 0
        self.finalized_ledgers = 0

    def _clear_queues(self) -> None:
        self.cleared_queues += 1

    def _finalize_frame_ledger(self) -> None:
        self.finalized_ledgers += 1

    def _on_session_complete(self, output_dir: Path, *, keep_data: bool = False) -> None:
        self.completed_with.append(keep_data)


@pytest.fixture
def session_dir(tmp_path: Path) -> Path:
    output_dir = tmp_path / "live_20260822_100000"
    output_dir.mkdir()
    (output_dir / "live_20260822_100000.mp4").write_bytes(b"video")
    return output_dir


class TestCancellationIntent:
    def test_early_stop_without_intent_still_marks_cancelled(self, session_dir: Path):
        """Unchanged legacy behaviour: an automatic early stop is a cancellation."""
        service = DummyLiveService(session_dir, planned_s=300.0, elapsed_s=10.0)

        assert service._detect_and_mark_cancellation() is True
        assert (session_dir / ".cancelled").exists()

    def test_explicit_cancel_marks_even_near_the_end(self, session_dir: Path):
        service = DummyLiveService(session_dir, planned_s=300.0, elapsed_s=295.0)

        assert service._detect_and_mark_cancellation(force=True) is True
        assert (session_dir / ".cancelled").exists()

    def test_keep_beats_the_fifty_percent_heuristic(self, session_dir: Path):
        """ "Finish and Save" at 10 % elapsed must NOT be read as a cancellation."""
        service = DummyLiveService(session_dir, planned_s=300.0, elapsed_s=30.0)

        assert service._detect_and_mark_cancellation(keep=True) is False
        assert not (session_dir / ".cancelled").exists()

    def test_keep_wins_over_contradictory_force(self, session_dir: Path):
        service = DummyLiveService(session_dir, planned_s=300.0, elapsed_s=30.0)

        assert service._detect_and_mark_cancellation(force=True, keep=True) is False
        assert not (session_dir / ".cancelled").exists()


class TestFinishSessionEarly:
    def test_routes_through_session_complete_keeping_data(self, session_dir: Path):
        service = DummyLiveService(session_dir, planned_s=300.0, elapsed_s=30.0)

        assert service.finish_session_early() is True
        # Same entry point the duration timer uses, with the intent attached.
        assert service.completed_with == [True]

    def test_without_output_dir_falls_back_to_a_plain_keep_stop(self, tmp_path: Path):
        service = DummyLiveService(tmp_path, planned_s=300.0, elapsed_s=30.0)
        service.current_output_dir = None
        service.stop_session = MagicMock(return_value=True)  # type: ignore[method-assign]

        assert service.finish_session_early() is True
        service.stop_session.assert_called_once_with(keep_data=True)
        assert service.completed_with == []


class TestStopSessionOnDisk:
    """O que sobrevive em disco depois de cada intencao de parada."""

    def test_cancel_deletes_the_session_folder(self, session_dir: Path):
        service = DummyLiveService(session_dir, planned_s=300.0, elapsed_s=10.0)

        assert service.stop_session(cancelled=True) is True

        assert not session_dir.exists()
        assert service.current_output_dir is None

    def test_keep_data_preserves_the_folder_even_when_cancelled_is_set(self, session_dir: Path):
        """``keep_data`` vence: entre descartar e preservar, so preservar e reversivel."""
        service = DummyLiveService(session_dir, planned_s=300.0, elapsed_s=10.0)

        assert service.stop_session(cancelled=True, keep_data=True) is True

        assert session_dir.exists()
        assert (session_dir / "live_20260822_100000.mp4").exists()
        assert not (session_dir / ".cancelled").exists()
        assert service.current_output_dir == session_dir

    def test_early_stop_without_intent_keeps_files_but_marks_cancelled(self, session_dir: Path):
        """Comportamento historico do stop automatico precoce: marca, nao apaga."""
        service = DummyLiveService(session_dir, planned_s=300.0, elapsed_s=10.0)

        service.stop_session()

        assert session_dir.exists()
        assert (session_dir / ".cancelled").exists()

    def test_keep_data_stops_the_recorder_gracefully(self, session_dir: Path):
        """Parada preservando dado NAO pode usar o force_stop do descarte."""
        service = DummyLiveService(session_dir, planned_s=300.0, elapsed_s=10.0)

        service.stop_session(keep_data=True)

        service.recorder.stop_recording.assert_called_once_with()

    def test_cancel_forces_the_recorder_stop(self, session_dir: Path):
        service = DummyLiveService(session_dir, planned_s=300.0, elapsed_s=10.0)

        service.stop_session(cancelled=True)

        kwargs = service.recorder.stop_recording.call_args.kwargs
        assert kwargs["force_stop"] is True
        assert kwargs["reason"] == "user_cancelled"

    def test_ledger_is_finalized_before_the_folder_is_discarded(self, session_dir: Path):
        """O ledger e escrito DENTRO da pasta; finalizar depois do rmtree o perderia."""
        service = DummyLiveService(session_dir, planned_s=300.0, elapsed_s=10.0)

        service.stop_session(cancelled=True)

        assert service.finalized_ledgers == 1
