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

import threading
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
        # Preenchido so pelos casos que plantam uma thread travada.
        self.halt_the_stuck_thread = threading.Event()

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


class TestThreadHangIsNotACancellation:
    """Uma trava de thread e problema de MAQUINA; cancelar e intencao do OPERADOR.

    As duas dividiam a mesma variavel: ao estourar o teto de join,
    ``stop_session`` fazia ``cancelled_session = True`` -- com a intencao
    legitima de promover o encerramento do recorder a ``force_stop`` -- e essa
    mesma variavel viajava para ``on_session_stopped``. O coordinator lia
    "cancelada", pulava ``_register_batch_session()`` e o projeto nunca ficava
    sabendo da gravacao.

    O que tornava a perda invisivel: a pasta NAO e apagada nesse caminho (o
    ``rmtree`` obedece ao parametro ``cancelled``, nao a essa variavel). MP4,
    parquets e ledger no disco, projeto sem entrada nenhuma, nenhum erro para o
    operador -- so a UI dizendo "sessao interrompida".
    """

    @pytest.fixture(autouse=True)
    def _release_stuck_threads(self):
        """Destrava, no teardown, toda thread que um caso deixou parada.

        Sao daemons, entao nao seguram o pytest -- mas ficam vivas ate o fim da
        sessao, e uma suite que acumula threads paradas transforma qualquer
        diagnostico de vazamento de thread em ruido.
        """
        self._halts: list[threading.Event] = []
        yield
        for halt in self._halts:
            halt.set()

    def _service_with_a_stuck_thread(self, session_dir: Path) -> DummyLiveService:
        service = DummyLiveService(session_dir, planned_s=300.0, elapsed_s=300.0)
        # Encurta o teto: o caso sob teste e "o orcamento estourou", nao o valor
        # do orcamento -- esse continua guardado por
        # ``test_stop_session_bounded_total_join_budget``.
        service._max_join_wait_s = 0.2
        halt = threading.Event()
        stuck = threading.Thread(target=halt.wait, daemon=True)
        stuck.start()
        service.processing_thread = stuck
        # Guardado para o caso que precisa MATAR a thread no meio do
        # encerramento. ``threads_to_join`` e uma lista LOCAL que segura o
        # objeto Thread, entao zerar ``service.processing_thread`` nao muda o
        # que o codigo velho consultava -- so a thread morrer de fato muda.
        service.halt_the_stuck_thread = halt
        self._halts.append(halt)
        return service

    def test_a_hung_thread_does_not_report_the_session_as_cancelled(self, session_dir: Path):
        """O defeito reportado: sessao completa virava sessao nao registrada."""
        service = self._service_with_a_stuck_thread(session_dir)
        verdicts: list[bool] = []
        service.on_session_stopped = verdicts.append

        service.stop_session()

        assert verdicts == [False], (
            "a trava de thread voltou a ser relatada como cancelamento; o "
            "coordinator pula _register_batch_session() e a gravacao fica no "
            "disco sem entrada no projeto"
        )

    def test_the_hung_session_keeps_its_files(self, session_dir: Path):
        """A pasta sobrevive -- e por isso que a perda so aparece no relatorio."""
        service = self._service_with_a_stuck_thread(session_dir)

        service.stop_session()

        assert session_dir.exists()
        assert (session_dir / "live_20260822_100000.mp4").exists()

    def test_a_hung_thread_still_forces_the_recorder_stop(self, session_dir: Path):
        """A promocao a ``force_stop`` era o proposito legitimo -- ela permanece.

        Sem ela o recorder libera o ``video_writer`` enquanto uma thread viva
        ainda pode escrever, que e a corrida da assercao do FFmpeg.
        """
        service = self._service_with_a_stuck_thread(session_dir)

        service.stop_session()

        kwargs = service.recorder.stop_recording.call_args.kwargs
        assert kwargs["force_stop"] is True
        assert kwargs["reason"] == "thread_hang"

    def test_a_cancelled_session_that_also_hangs_stays_cancelled(self, session_dir: Path):
        """Separar as variaveis nao pode ressuscitar uma sessao descartada."""
        service = self._service_with_a_stuck_thread(session_dir)
        verdicts: list[bool] = []
        service.on_session_stopped = verdicts.append

        service.stop_session(cancelled=True)

        assert verdicts == [True]
        assert not session_dir.exists()

    def test_the_reason_survives_a_thread_that_dies_after_the_timeout(self, session_dir: Path):
        """``reason`` vem do laco, nao de um segundo ``is_alive()``.

        Ele era derivado depois da finalizacao do ledger; uma thread que
        morresse nesse intervalo transformava uma trava genuina em
        ``user_cancelled`` -- corrompendo justamente o campo que se le para
        explicar o ocorrido.
        """
        service = self._service_with_a_stuck_thread(session_dir)
        stuck = service.processing_thread
        assert stuck is not None

        def _let_the_thread_die_between_the_break_and_the_reason() -> None:
            # A thread destrava e SAI de verdade: e o unico jeito de o
            # ``is_alive()`` tardio mudar de resposta.
            service.halt_the_stuck_thread.set()
            stuck.join(timeout=2.0)
            assert not stuck.is_alive()
            service.finalized_ledgers += 1

        service._finalize_frame_ledger = _let_the_thread_die_between_the_break_and_the_reason  # type: ignore[method-assign]

        service.stop_session()

        assert service.recorder.stop_recording.call_args.kwargs["reason"] == "thread_hang"


class TestHungThreadStacks:
    """Sem a pilha, o log diz QUAIS threads travaram, nunca ONDE."""

    def test_a_live_thread_contributes_its_stack(self):
        halt = threading.Event()
        stuck = threading.Thread(target=halt.wait, daemon=True)
        stuck.start()
        try:
            stacks = LiveSessionManagerMixin._hung_thread_stacks([("processing_thread", stuck)])
        finally:
            halt.set()

        assert "processing_thread" in stacks
        # A pilha real de uma thread parada em ``Event.wait`` passa por
        # ``threading.py``; o conteudo importa mais que o formato.
        assert "wait" in stacks["processing_thread"]

    def test_dead_and_missing_threads_are_skipped(self):
        finished = threading.Thread(target=lambda: None, daemon=True)
        finished.start()
        finished.join()

        stacks = LiveSessionManagerMixin._hung_thread_stacks(
            [("capture_thread", None), ("video_recording_thread", finished)]
        )

        assert stacks == {}
