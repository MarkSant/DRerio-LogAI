"""Tests for MultiAquariumLivePreviewWindow (live preview for 2+ aquariums).

The clock is injected (the module's ``time`` is replaced by a fake whose ``time()``
a test advances by hand) and ``after`` is replaced by a recorder, so nothing here
depends on wall-clock time. ``update_recorded_count`` and ``update_aquarium_frame``
are not tested: the dead-code audit (A2-D-329, A2-D-330) found no caller for them.
"""

from __future__ import annotations

import time as real_time
import tkinter as tk
import types
from tkinter import ttk
from typing import Any, cast

import pytest
import structlog

from zebtrack.ui.dialogs import multi_aquarium_live_preview_window as window_module
from zebtrack.ui.dialogs.multi_aquarium_live_preview_window import (
    MultiAquariumLivePreviewWindow,
    format_mmss,
    grid_layout,
    progress_percent,
)

# 2026-11-15 13:45:09 local time, built from fields so the expected clock text is
# an input, not something recomputed with the code under test.
T0 = real_time.mktime((2026, 11, 15, 13, 45, 9, 0, 0, -1))


class _FakeClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def time(self) -> float:
        return self.now


class _AfterRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[int, Any]] = []

    def __call__(self, delay: int, func: Any = None, *args: Any) -> str:
        self.calls.append((delay, func))
        return f"after#{len(self.calls)}"


def _walk(widget: tk.Misc) -> list[tk.Misc]:
    found: list[tk.Misc] = []
    for child in widget.winfo_children():
        found.append(child)
        found.extend(_walk(child))
    return found


def _texts(preview: MultiAquariumLivePreviewWindow, kind: type) -> list[str]:
    return [str(w.cget("text")) for w in _walk(preview.window) if isinstance(w, kind)]


class TestGridLayout:
    @pytest.mark.parametrize(
        ("count", "expected"),
        [
            (1, (2, 1, 840, 500)),
            (2, (2, 1, 840, 500)),
            (3, (2, 2, 840, 850)),
            (4, (2, 2, 840, 850)),
            (5, (3, 2, 1240, 850)),
            (6, (3, 2, 1240, 850)),
            (7, (3, 3, 1240, 1200)),
        ],
    )
    def test_columns_rows_and_window_size(self, count, expected):
        # 2 columns up to 4 aquariums, 3 beyond; 400 px per column + 40 padding;
        # 350 px per row + 150 for the controls.
        assert grid_layout(count) == expected


class TestProgressPercent:
    @pytest.mark.parametrize(
        ("elapsed", "duration", "expected"),
        [(30, 120, 25.0), (0, 120, 0.0), (120, 120, 100.0), (150, 120, 100.0), (-5, 120, 0.0)],
    )
    def test_is_clamped_to_zero_and_one_hundred(self, elapsed, duration, expected):
        assert progress_percent(elapsed, duration) == expected


class TestFormatMmss:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [(0, "00:00"), (65.9, "01:05"), (299, "04:59"), (3599, "59:59"), (3725, "62:05")],
    )
    def test_minutes_are_not_wrapped_into_hours(self, seconds, expected):
        assert format_mmss(seconds) == expected


class TestFormatEta:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (0, "0s"),
            (59, "59s"),
            (59.9, "59s"),
            (60, "1m 00s"),
            (125, "2m 05s"),
            (3599, "59m 59s"),
            (3600, "1h 00m 00s"),
            (3725, "1h 02m 05s"),
            (-5, "0s"),
        ],
    )
    def test_renders_seconds_minutes_and_hours(self, seconds, expected):
        assert MultiAquariumLivePreviewWindow._format_eta(seconds) == expected


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    fake = _FakeClock(T0)
    monkeypatch.setattr(
        window_module,
        "time",
        types.SimpleNamespace(
            time=fake.time, strftime=real_time.strftime, localtime=real_time.localtime
        ),
    )
    return fake


def _build(
    root: tk.Misc,
    *,
    num_aquariums: int = 2,
    duration_s: float = 300.0,
    on_stop: Any = None,
    camera_index: int = 3,
) -> tuple[Any, _AfterRecorder]:
    preview = MultiAquariumLivePreviewWindow(
        parent=root,
        camera_index=camera_index,
        num_aquariums=num_aquariums,
        duration_s=duration_s,
        on_stop_callback=on_stop,
    )
    recorder = _AfterRecorder()
    preview.window.after = recorder  # type: ignore[method-assign, assignment]
    return preview, recorder


@pytest.mark.gui
class TestLayoutOnScreen:
    def test_two_aquariums_get_two_labelled_panels_and_one_canvas_each(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root, num_aquariums=2, camera_index=3)

        assert preview.window.title() == "Multi-Aquarium Live Analysis - Camera 3"
        assert sorted(preview.aquarium_canvases) == [0, 1]
        assert [t for t in _texts(preview, ttk.LabelFrame) if t.startswith("Aquarium")] == [
            "Aquarium 1",
            "Aquarium 2",
        ]
        assert sorted(preview.aquarium_labels) == [0, 1]
        assert all(
            str(label.cget("text")) == "Detections: 0" for label in preview.aquarium_labels.values()
        )
        assert "Camera: 3 | Aquariums: 2" in _texts(preview, ttk.Label)

    def test_five_aquariums_use_three_columns(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root, num_aquariums=5)

        cells = [cast(Any, c.master).grid_info() for c in preview.aquarium_canvases.values()]
        columns = {int(cell["column"]) for cell in cells}
        rows = {int(cell["row"]) for cell in cells}
        assert columns == {0, 1, 2}
        assert rows == {0, 1}

    def test_a_timed_session_shows_a_determinate_bar(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root, duration_s=300)

        assert str(preview.progress_bar.cget("mode")) == "determinate"

    def test_an_open_ended_session_shows_an_indeterminate_bar(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root, duration_s=0)

        assert str(preview.progress_bar.cget("mode")) == "indeterminate"

    def test_initial_footer_has_placeholder_clocks_and_is_english(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root)

        assert preview.status_label.cget("text") == "Status: Initializing..."
        assert preview.start_time_label.cget("text") == "Start: --:--:--"
        assert preview.stop_time_label.cget("text") == "End: --:--:--"
        assert preview.eta_label.cget("text") == "ETA: --"
        assert preview.recorded_frames_label.cget("text") == "Recorded frames: 0"


@pytest.mark.gui
class TestTimer:
    def test_start_timer_stamps_the_start_clock(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root)

        preview.start_timer()

        assert preview.start_time == T0
        assert preview.start_time_label.cget("text") == "Start: 13:45:09"

    def test_a_tick_shows_elapsed_and_remaining_eta_and_percent(self, tkinter_root, clock):
        preview, after = _build(tkinter_root, duration_s=300)
        preview.start_timer()
        clock.now = T0 + 65  # 1m05s elapsed, 3m55s left

        preview._update_timer()

        assert preview.timer_label.cget("text") == "Time: 01:05 / 03:55"
        assert preview.eta_label.cget("text") == "ETA: 3m 55s"
        assert float(preview.progress_bar.cget("value")) == pytest.approx(65 / 300 * 100)
        assert after.calls == [(1000, preview._update_timer)]
        assert preview.is_stopped is False

    def test_before_the_timer_starts_a_tick_only_reschedules(self, tkinter_root, clock):
        preview, after = _build(tkinter_root)
        label_before = preview.timer_label.cget("text")

        preview._update_timer()

        assert preview.timer_label.cget("text") == label_before == "Time: waiting..."
        assert after.calls == [(1000, preview._update_timer)]

    def test_time_running_out_stops_the_session_through_the_callback(self, tkinter_root, clock):
        stops: list[str] = []
        preview, after = _build(tkinter_root, duration_s=300, on_stop=lambda: stops.append("stop"))
        preview.start_timer()
        clock.now = T0 + 300

        preview._update_timer()

        assert stops == ["stop"]
        assert preview.is_stopped is True
        assert after.calls == [], "no tick may be scheduled after the auto-stop"
        assert preview.status_label.cget("text") == "Status: Stopping..."
        assert str(preview.stop_button.cget("state")) == "disabled"
        assert preview.stop_time_label.cget("text") == "End: 13:50:09"
        assert preview.eta_label.cget("text") == "ETA: --"

    def test_one_second_before_the_end_does_not_stop(self, tkinter_root, clock):
        stops: list[str] = []
        preview, after = _build(tkinter_root, duration_s=300, on_stop=lambda: stops.append("stop"))
        preview.start_timer()
        clock.now = T0 + 299

        preview._update_timer()

        assert stops == []
        assert preview.timer_label.cget("text") == "Time: 04:59 / 00:01"
        assert len(after.calls) == 1

    def test_without_a_stop_callback_time_running_out_does_not_stop(self, tkinter_root, clock):
        preview, after = _build(tkinter_root, duration_s=300, on_stop=None)
        preview.start_timer()
        clock.now = T0 + 400

        preview._update_timer()

        assert preview.is_stopped is False
        assert preview.timer_label.cget("text") == "Time: 06:40 / 00:00"
        assert len(after.calls) == 1

    def test_an_open_ended_session_never_auto_stops_and_shows_no_eta(self, tkinter_root, clock):
        stops: list[str] = []
        preview, after = _build(tkinter_root, duration_s=0, on_stop=lambda: stops.append("stop"))
        preview.start_timer()
        clock.now = T0 + 5000

        preview._update_timer()

        assert stops == []
        assert preview.eta_label.cget("text") == "ETA: --"
        assert len(after.calls) == 1

    def test_a_tick_after_stopping_does_nothing(self, tkinter_root, clock):
        preview, after = _build(tkinter_root, duration_s=300)
        preview.start_timer()
        preview.is_stopped = True
        clock.now = T0 + 10

        preview._update_timer()

        assert preview.timer_label.cget("text") == "Time: waiting..."
        assert after.calls == []


@pytest.mark.gui
class TestStopping:
    def test_the_stop_button_calls_back_once(self, tkinter_root, clock):
        stops: list[str] = []
        preview, _after = _build(tkinter_root, on_stop=lambda: stops.append("stop"))

        preview.stop_button.invoke()

        assert stops == ["stop"]
        assert str(preview.stop_button.cget("state")) == "disabled"

    def test_a_second_stop_is_ignored(self, tkinter_root, clock):
        stops: list[str] = []
        preview, _after = _build(tkinter_root, on_stop=lambda: stops.append("stop"))

        preview._on_stop_clicked()
        preview._on_stop_clicked()

        assert stops == ["stop"]

    def test_stopping_without_a_callback_still_freezes_the_window(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root, on_stop=None)

        preview._on_stop_clicked()

        assert preview.is_stopped is True
        assert preview.status_label.cget("text") == "Status: Stopping..."

    def test_an_indeterminate_bar_is_halted_at_stop(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root, duration_s=0)
        calls: list[str] = []
        preview.progress_bar.stop = lambda: calls.append("stop")  # type: ignore[method-assign]

        preview._on_stop_clicked()

        assert calls == ["stop"]

    def test_closing_a_running_window_is_a_stop_not_a_destroy(self, tkinter_root, clock):
        stops: list[str] = []
        preview, _after = _build(tkinter_root, on_stop=lambda: stops.append("stop"))

        preview.window.tk.call(preview.window.protocol("WM_DELETE_WINDOW"))

        assert stops == ["stop"]
        assert preview.window.winfo_exists()

    def test_closing_an_already_stopped_window_destroys_it(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root)
        preview._on_stop_clicked()

        preview.window.tk.call(preview.window.protocol("WM_DELETE_WINDOW"))

        assert not preview.window.winfo_exists()


@pytest.mark.gui
class TestStatusAndDestroy:
    def test_status_text_carries_the_colour(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root)

        preview.update_status_text("● Recording", color="red")

        assert preview.status_label.cget("text") == "Status: ● Recording"
        assert str(preview.status_label.cget("foreground")) == "red"

    def test_destroy_closes_the_window(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root)

        preview.destroy()

        assert not preview.window.winfo_exists()

    def test_destroying_twice_logs_and_does_not_raise(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root)
        preview.destroy()
        preview.window.destroy = lambda: (_ for _ in ()).throw(  # type: ignore[method-assign]
            tk.TclError("bad window path name")
        )

        with structlog.testing.capture_logs() as logs:
            preview.destroy()

        assert [e["event"] for e in logs] == ["multi_aquarium_preview.destroy_failed"]


@pytest.mark.gui
class TestPipelineContract:
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "F2-UI-002: FrameProcessingPipeline calls preview_window.update_frame("
            "frame, detections, recorded_count) on whatever window "
            "camera_connection_handler built; the multi-aquarium window has no "
            "update_frame (its update_aquarium_frame has no caller), so a two-aquarium "
            "live session raises AttributeError per displayed frame and draws no video."
        ),
    )
    def test_the_window_offers_the_update_frame_the_pipeline_calls(self):
        assert callable(getattr(MultiAquariumLivePreviewWindow, "update_frame", None))
