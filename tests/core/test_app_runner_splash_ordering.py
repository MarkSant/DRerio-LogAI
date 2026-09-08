"""The splash must appear before anything expensive is imported.

Measured in ``logs/analysis.log``, a first launch spent roughly four seconds
between the process starting and the splash being drawn. Two import costs sat in
front of it, both looking like ordinary ``import`` lines:

* ``from zebtrack.utils import set_seed`` -- ``zebtrack.utils`` imports torch at
  module level, about 1.1 s.
* the ``di_registrations`` block -- it eagerly builds the coordinator/service
  graph, pulling ultralytics, cv2 and matplotlib, about 3 s.

Under the desktop shortcut the app runs through ``pythonw.exe``, so there is no
console either: a double-click produced four seconds of nothing at all, which is
indistinguishable from a dead icon.

These tests pin the ordering rather than the duration. A timing assertion would
be flaky on a loaded machine and would not say *why* it regressed; the order of
the calls is the thing that must not drift back.
"""

from __future__ import annotations

from unittest.mock import MagicMock


def _run_until_container(monkeypatch, order: list[str]):
    """Drive ``run_app`` far enough to observe startup ordering, then stop."""
    import sys

    import zebtrack.core.app_runner as app_runner

    # run_app parses sys.argv; under pytest that is the pytest command line.
    monkeypatch.setattr(sys, "argv", ["zebtrack"])

    settings = MagicMock()
    settings.reproducibility.seed = 42
    settings.camera.index = 0
    settings.yolo_model.path = "model.pt"
    settings.openvino.auto_benchmark = False
    settings.ui.language = "en"

    monkeypatch.setattr("zebtrack.settings.load_settings", lambda: settings)
    monkeypatch.setattr(app_runner, "_setup_logging", lambda *a, **k: (lambda _s: None))
    monkeypatch.setattr(app_runner, "_select_language_on_first_run", lambda *a, **k: None)
    monkeypatch.setattr(app_runner, "_require_detector_weights", lambda *a, **k: None)
    monkeypatch.setattr(app_runner, "_set_windows_app_id", lambda *a, **k: None)
    monkeypatch.setattr(app_runner, "install_tk_exception_handler", lambda *a, **k: None)
    monkeypatch.setattr("zebtrack.i18n.install", lambda *a, **k: None)
    monkeypatch.setattr("zebtrack.ui.icon_utils.set_window_icon", lambda *a, **k: None)

    def make_splash(parent):
        order.append("splash")
        return MagicMock()

    def note_set_seed(seed):
        order.append("set_seed")

    def stop(context):
        order.append("build_container")
        raise RuntimeError("stop here")

    monkeypatch.setattr("zebtrack.ui.splash_screen.create_splash", make_splash)
    monkeypatch.setattr("zebtrack.utils.set_seed", note_set_seed)
    monkeypatch.setattr("zebtrack.core.di_registrations.build_container", stop)

    tk_module = MagicMock()
    messagebox_module = MagicMock()

    # run_app swallows the RuntimeError into its own fatal-error handler, so
    # the call returns normally; the recorded order is what we assert on.
    app_runner.run_app(
        tk_module=tk_module,
        messagebox_module=messagebox_module,
        configure_logging_fn=lambda: None,
    )
    return order


def test_splash_is_created_before_torch_is_imported(monkeypatch):
    """``set_seed`` is the first thing that pulls torch. The splash precedes it."""
    order = _run_until_container(monkeypatch, [])

    assert "splash" in order, "the splash was never created"
    assert "set_seed" in order, "the run stopped before the seed was set"
    assert order.index("splash") < order.index("set_seed")


def test_splash_is_created_before_the_container_is_built(monkeypatch):
    """The di_registrations import is the three-second cost. It comes after."""
    order = _run_until_container(monkeypatch, [])

    assert order.index("splash") < order.index("build_container")


def test_splash_module_stays_cheap_to_import():
    """The splash's own imports must not grow into the gap it exists to close.

    A heavy import added to ``ui/splash_screen.py`` would move the dead time
    back in front of the window without changing a single line of app_runner.
    """
    import inspect

    import zebtrack.ui.splash_screen

    source = inspect.getsource(zebtrack.ui.splash_screen)
    for forbidden in ("import torch", "import ultralytics", "import cv2", "import matplotlib"):
        assert forbidden not in source, f"splash_screen.py must not {forbidden}"
