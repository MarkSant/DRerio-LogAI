"""Unit tests for LiveCameraService helpers."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.recording import camera_connection_handler as camera_conn_module
from zebtrack.core.recording.live_camera_service import LiveCameraService


@pytest.fixture
def live_camera_service():
    """Create LiveCameraService with mocked dependencies."""
    return LiveCameraService(
        controller=None,
        state_manager=Mock(),
        project_manager=Mock(),
        recording_service=Mock(),
        detector_service=Mock(),
        settings_obj=Mock(),
        recorder=Mock(),
        event_bus=Mock(),
        root=None,
    )


def test_resolve_calibration_perspective_returns_top_down(live_camera_service):
    """When project_data carries calibration.behavioral_analysis.aquarium_perspective,
    the helper must surface it so live can pick the correct 4-slot default.
    """
    pm = Mock()
    pm.project_data = {"calibration": {"behavioral_analysis": {"aquarium_perspective": "top_down"}}}
    live_camera_service.project_manager = pm

    assert live_camera_service._resolve_calibration_perspective() == "top_down"


def test_resolve_calibration_perspective_returns_lateral(live_camera_service):
    """Lateral perspective must round-trip unchanged."""
    pm = Mock()
    pm.project_data = {"calibration": {"behavioral_analysis": {"aquarium_perspective": "lateral"}}}
    live_camera_service.project_manager = pm

    assert live_camera_service._resolve_calibration_perspective() == "lateral"


def test_resolve_calibration_perspective_returns_none_when_missing(live_camera_service):
    """Without calibration data the helper returns None (perspective-agnostic
    fallback path inside WeightManager)."""
    pm = Mock()
    pm.project_data = {}
    live_camera_service.project_manager = pm

    assert live_camera_service._resolve_calibration_perspective() is None


def test_resolve_calibration_perspective_returns_none_when_no_project_manager(
    live_camera_service,
):
    """No project loaded → perspective is None and live falls back gracefully."""
    live_camera_service.project_manager = None

    assert live_camera_service._resolve_calibration_perspective() is None


def test_resolve_live_multi_aquarium_zone_data_falls_back_to_reference_frame(
    live_camera_service, tmp_path, multi_aquarium_zone_data
):
    project_manager = Mock()
    project_manager.project_path = tmp_path
    project_manager.get_multi_aquarium_zone_data.side_effect = [None, multi_aquarium_zone_data]
    live_camera_service.project_manager = project_manager

    video_path = tmp_path / "session" / "live_recording.mp4"
    result = live_camera_service._resolve_live_multi_aquarium_zone_data(video_path)

    assert result is multi_aquarium_zone_data
    assert project_manager.get_multi_aquarium_zone_data.call_args_list[0].args[0] == video_path
    assert project_manager.get_multi_aquarium_zone_data.call_args_list[1].args[0] == (
        tmp_path / "live_camera_reference_frame.png"
    )


def test_collect_multi_aquarium_trajectory_outputs_detects_subfolders(
    live_camera_service,
    tmp_path,
):
    output_dir = tmp_path / "live_session"
    aq0_dir = output_dir / "aquarium_1"
    aq1_dir = output_dir / "aquarium_2"
    aq0_dir.mkdir(parents=True)
    aq1_dir.mkdir()
    aq0_path = aq0_dir / "3_CoordMovimento_exp_aquarium_1.parquet"
    aq1_path = aq1_dir / "3_CoordMovimento_exp_aquarium_2.parquet"
    aq0_path.touch()
    aq1_path.touch()

    outputs = live_camera_service._collect_multi_aquarium_trajectory_outputs(output_dir)

    assert outputs[0]["results_dir"] == aq0_dir
    assert outputs[0]["trajectory_path"] == aq0_path
    assert outputs[1]["results_dir"] == aq1_dir
    assert outputs[1]["trajectory_path"] == aq1_path


def test_start_recording_after_arena_uses_multi_aquarium_zone_data(
    live_camera_service, tmp_path, multi_aquarium_zone_data
):
    output_dir = tmp_path / "live_session"
    output_dir.mkdir()

    project_manager = Mock()
    project_manager.project_path = tmp_path
    project_manager.get_multi_aquarium_zone_data.side_effect = [None, multi_aquarium_zone_data]
    project_manager.get_zone_data.return_value = ZoneData()

    recorder = Mock()
    recorder.start_recording_multi_aquarium.return_value = True
    recorder.start_recording.return_value = True

    live_camera_service.project_manager = project_manager
    live_camera_service.recorder = recorder
    live_camera_service.current_output_dir = output_dir
    live_camera_service._session_duration_s = 0
    live_camera_service._experiment_id = "live_exp"
    live_camera_service.is_capturing_for_video = True
    live_camera_service.camera = SimpleNamespace(actual_width=1280, actual_height=720)
    live_camera_service.preview_window = None

    live_camera_service._start_recording_after_arena()

    recorder.start_recording_multi_aquarium.assert_called_once()
    recorder.start_recording.assert_not_called()


def test_start_session_clears_stale_exit_event(live_camera_service, monkeypatch):
    """``start_session`` deve limpar o ``exit_event`` logo no início.

    Regressão: na 2ª sessão em diante o ``exit_event`` ainda estava setado
    pelo ``__exit__``/``stop_session`` da sessão anterior. O loop de countdown
    detectava ``exit_event.is_set()`` e abortava imediatamente
    (``countdown.aborted``), fazendo a gravação falhar silenciosamente e o
    ``block_detail_dialog`` exibir "Falha ao iniciar sessão". O ``clear()`` em
    ``_start_threads`` rodava tarde demais (após o countdown).
    """
    svc = live_camera_service
    # Simula o estado deixado por uma sessão anterior.
    svc.exit_event.set()
    assert svc.exit_event.is_set()

    # Curto-circuito logo após o bloco que limpa o exit_event: a câmera "falha"
    # ao abrir, então start_session retorna False sem tocar hardware/threads.
    monkeypatch.setattr(svc, "_setup_camera", lambda *a, **k: False)

    result = svc.start_session(
        camera_index=0,
        duration_s=1.0,
        experiment_id="exp",
        use_countdown=True,
        countdown_duration_s=3,
    )

    assert result is False, "deve sair no setup de câmera mockado"
    assert not svc.exit_event.is_set(), "start_session deve limpar o exit_event antes do countdown"


def test_start_session_resets_live_detected_frames(live_camera_service, monkeypatch):
    """``start_session`` zera ``_live_detected_frames`` para a nova sessão.

    Regressão: o contador de frames detectados era um atributo de instância
    nunca reiniciado, então a 2ª gravação live somava sobre a contagem da 1ª na
    aba "Análise". O reset ocorre antes do setup de câmera, então mockamos
    ``_setup_camera`` para retornar False e sair cedo sem tocar hardware.
    """
    svc = live_camera_service
    # Simula contagem deixada por uma sessão anterior.
    svc._live_detected_frames = 42

    monkeypatch.setattr(svc, "_setup_camera", lambda *a, **k: False)

    result = svc.start_session(camera_index=0, duration_s=1.0, experiment_id="exp")

    assert result is False, "deve sair no setup de câmera mockado"
    assert svc._live_detected_frames == 0, "start_session deve zerar o contador de detectados"


def test_detect_and_mark_cancellation_force_overrides_50pct(live_camera_service, tmp_path):
    """``force=True`` marca como cancelado mesmo após 50% da duração.

    A heurística dos 50% só vale para o stop automático precoce; o cancelamento
    manual (``force=True``) sempre descarta.
    """
    svc = live_camera_service
    svc.current_output_dir = tmp_path
    svc._session_duration_s = 100.0
    # Decorrido 99s de 100s planejados → muito além do limiar de 50%.
    svc.recorder = Mock()
    svc.recorder.start_time = time.time() - 99.0

    # Sem force: passou de 50% → NÃO é tratado como cancelado.
    assert svc._detect_and_mark_cancellation(force=False) is False
    # Com force: descarta mesmo assim.
    assert svc._detect_and_mark_cancellation(force=True) is True


def test_stop_session_cancelled_deletes_output_dir(live_camera_service, tmp_path):
    """``stop_session(cancelled=True)`` apaga a subpasta da sessão do disco.

    Regressão: cancelar uma gravação perto do fim deixava MP4/parquet parciais
    e registrava a sessão como concluída. Agora o cancelamento manual descarta
    tudo.
    """
    svc = live_camera_service
    session_dir = tmp_path / "live_20260607_180447"
    session_dir.mkdir()
    (session_dir / "partial.mp4").write_bytes(b"x")
    svc.current_output_dir = session_dir

    # Sem threads ativas e recorder mockado: stop_session percorre o caminho
    # completo sem hardware real.
    svc.capture_thread = None
    svc.processing_thread = None
    svc.video_recording_thread = None
    svc.camera = None
    svc.preview_window = None
    svc.recorder = Mock()

    result = svc.stop_session(cancelled=True)

    assert result is True
    assert not session_dir.exists(), "a pasta da sessão cancelada deve ser apagada"
    assert svc.current_output_dir is None


def test_stop_session_not_cancelled_keeps_output_dir(live_camera_service, tmp_path):
    """Stop normal (``cancelled=False``) NÃO apaga a pasta da sessão."""
    svc = live_camera_service
    session_dir = tmp_path / "live_20260607_181000"
    session_dir.mkdir()
    (session_dir / "trajectory.parquet").write_bytes(b"x")
    svc.current_output_dir = session_dir
    svc._session_duration_s = 0.0  # evita a heurística de stop precoce

    svc.capture_thread = None
    svc.processing_thread = None
    svc.video_recording_thread = None
    svc.camera = None
    svc.preview_window = None
    svc.recorder = Mock()
    svc.recorder.start_time = time.time()

    result = svc.stop_session(cancelled=False)

    assert result is True
    assert session_dir.exists(), "stop normal deve preservar os arquivos da sessão"


def test_is_session_active_false_when_no_threads(live_camera_service):
    """Fresh service (no threads spawned) is not active."""
    live_camera_service.capture_thread = None
    live_camera_service.processing_thread = None
    live_camera_service.video_recording_thread = None

    assert live_camera_service.is_session_active() is False


def test_is_session_active_true_when_capture_thread_alive(live_camera_service):
    """Active capture thread → session is active."""
    alive_thread = Mock()
    alive_thread.is_alive.return_value = True
    live_camera_service.capture_thread = alive_thread
    live_camera_service.processing_thread = None
    live_camera_service.video_recording_thread = None

    assert live_camera_service.is_session_active() is True


def test_is_session_active_false_when_threads_finished(live_camera_service):
    """Threads exist but already exited → session is not active."""
    dead_thread = Mock()
    dead_thread.is_alive.return_value = False
    live_camera_service.capture_thread = dead_thread
    live_camera_service.processing_thread = dead_thread
    live_camera_service.video_recording_thread = dead_thread

    assert live_camera_service.is_session_active() is False


def test_cleanup_existing_session_folders_no_base(live_camera_service, tmp_path):
    """Return early when output base does not exist."""
    missing_dir = tmp_path / "missing"

    live_camera_service._cleanup_existing_session_folders(missing_dir, "exp1")

    assert not missing_dir.exists()


def test_cleanup_existing_session_folders_removes_matching(live_camera_service, tmp_path):
    """Remove all experiment folders matching pattern."""
    base_dir = tmp_path / "sessions"
    base_dir.mkdir()

    exp1_a = base_dir / "exp1_20240101_010101"
    exp1_b = base_dir / "exp1_20240101_020202"
    exp2 = base_dir / "exp2_20240101_010101"

    exp1_a.mkdir()
    exp1_b.mkdir()
    exp2.mkdir()

    live_camera_service._cleanup_existing_session_folders(base_dir, "exp1")

    assert not exp1_a.exists()
    assert not exp1_b.exists()
    assert exp2.exists()


def test_threadsafe_properties_round_trip(live_camera_service):
    """Verify thread-safe getters/setters."""
    camera = Mock()
    preview = Mock()

    live_camera_service.camera = camera
    live_camera_service.preview_window = preview
    live_camera_service.is_capturing_for_video = True
    live_camera_service.timer_id = "timer-1"

    assert live_camera_service.camera is camera
    assert live_camera_service.preview_window is preview
    assert live_camera_service.is_capturing_for_video is True
    assert live_camera_service.timer_id == "timer-1"


def test_on_disconnect_user_action_sets_state(live_camera_service):
    live_camera_service._camera_disconnected = True

    live_camera_service._on_disconnect_user_action({"action": "resume", "experiment_id": "exp1"})

    assert live_camera_service._user_disconnect_action == "resume"


def test_on_disconnect_user_action_stop_calls_stop_session(live_camera_service):
    live_camera_service.stop_session = Mock()

    live_camera_service._on_disconnect_user_action({"action": "stop", "experiment_id": "exp1"})

    assert live_camera_service._user_disconnect_action == "stop"
    live_camera_service.stop_session.assert_called_once()


def test_adjust_fps_dynamically_increases_skip(live_camera_service):
    live_camera_service._fps_adjustment_interval = 1
    live_camera_service._target_fps = 30.0
    live_camera_service._frame_skip_count = 0
    live_camera_service._processing_times = [0.1] * 9

    should_process = live_camera_service._adjust_fps_dynamically(10, 0.1)

    assert should_process is True
    assert live_camera_service._frame_skip_count == 1


def test_adjust_fps_dynamically_decreases_skip(live_camera_service):
    live_camera_service._fps_adjustment_interval = 1
    live_camera_service._target_fps = 30.0
    live_camera_service._frame_skip_count = 2
    live_camera_service._processing_times = [0.01] * 9

    should_process = live_camera_service._adjust_fps_dynamically(10, 0.01)

    assert should_process is True
    assert live_camera_service._frame_skip_count == 1


def test_adjust_fps_dynamically_skips_frames(live_camera_service):
    live_camera_service._frame_skip_count = 1

    assert live_camera_service._adjust_fps_dynamically(1, 0.05) is False
    assert live_camera_service._adjust_fps_dynamically(2, 0.05) is True


def test_clear_queues_drains_all_items(live_camera_service):
    live_camera_service.frame_queue.put_nowait((1, "frame"))
    live_camera_service.video_queue.put_nowait((1, "video"))

    live_camera_service._clear_queues()

    assert live_camera_service.frame_queue.empty()
    assert live_camera_service.video_queue.empty()


def test_check_camera_disconnect_publishes_and_pauses(live_camera_service, monkeypatch):
    live_camera_service._last_valid_frame_time = 10.0
    live_camera_service._camera_disconnect_threshold_s = 2.0
    live_camera_service._analysis_params = {"experiment_id": "exp-1"}

    live_camera_service.recorder.pause_recording = Mock()

    monkeypatch.setattr(camera_conn_module.time, "time", lambda: 13.0)

    live_camera_service._check_camera_disconnect()

    assert live_camera_service._camera_disconnected is True
    assert live_camera_service._recording_paused is True
    assert live_camera_service._disconnect_gaps[-1] == (10.0, None)
    live_camera_service.recorder.pause_recording.assert_called_once()
    live_camera_service.event_bus.publish.assert_called_once()


def test_check_camera_disconnect_no_last_frame_noop(live_camera_service):
    live_camera_service._last_valid_frame_time = None

    live_camera_service._check_camera_disconnect()

    live_camera_service.event_bus.publish.assert_not_called()


def test_on_camera_reconnected_resumes_and_publishes(live_camera_service, monkeypatch):
    live_camera_service._camera_disconnected = True
    live_camera_service._recording_paused = True
    live_camera_service._disconnect_gaps = [(10.0, None)]
    live_camera_service.recorder.resume_recording = Mock()

    monkeypatch.setattr(camera_conn_module.time, "time", lambda: 15.0)

    live_camera_service._on_camera_reconnected()

    assert live_camera_service._camera_disconnected is False
    assert live_camera_service._recording_paused is False
    assert live_camera_service._disconnect_gaps[-1] == (10.0, 15.0)
    live_camera_service.recorder.resume_recording.assert_called_once()
    live_camera_service.event_bus.publish.assert_called_once()


def test_release_preview_camera_releases_hardware_vm_camera(live_camera_service):
    """At session start the project-level preview Camera (held by hardware_vm)
    must be released, otherwise its physical device stays powered on alongside
    the session camera — which is exactly what users observe with per-session
    overrides (two cameras lit at once)."""
    preview_camera = Mock()
    hardware_vm = Mock()
    hardware_vm.camera = preview_camera
    hardware_vm.active_frame_source = preview_camera
    controller = Mock()
    controller.hardware_vm = hardware_vm
    live_camera_service.controller = controller

    live_camera_service._release_preview_camera_if_any()

    preview_camera.release.assert_called_once()
    assert hardware_vm.camera is None
    assert hardware_vm.active_frame_source is None


def test_release_preview_camera_no_hardware_vm_is_noop(live_camera_service):
    """When there is no controller / hardware_vm (tests, headless), the helper
    must silently no-op — never crash the session start path."""
    live_camera_service.controller = None
    # Must not raise.
    live_camera_service._release_preview_camera_if_any()


def test_release_preview_camera_swallows_release_exception(live_camera_service):
    """A failure inside Camera.release must not abort the session — log and
    proceed (the device will be reclaimed when the process exits anyway)."""
    preview_camera = Mock()
    preview_camera.release.side_effect = RuntimeError("cv2 hiccup")
    hardware_vm = Mock()
    hardware_vm.camera = preview_camera
    hardware_vm.active_frame_source = preview_camera
    controller = Mock()
    controller.hardware_vm = hardware_vm
    live_camera_service.controller = controller

    live_camera_service._release_preview_camera_if_any()

    preview_camera.release.assert_called_once()
    assert hardware_vm.camera is None
