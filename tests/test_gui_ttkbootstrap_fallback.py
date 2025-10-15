from types import SimpleNamespace


def test_ttktbootstrap_style_master_fallback(monkeypatch, caplog):
    """Simulate ttkbootstrap.Style raising TypeError when called with
    master kwarg and ensure ApplicationGUI falls back and logs a warning.
    """

    # Import inside test to pick up local modifications
    from zebtrack.ui.gui import ApplicationGUI

    # Minimal fake root object with .configure and .after methods used by GUI
    fake_root = SimpleNamespace()

    def fake_configure(**kwargs):
        fake_root.configured = kwargs

    fake_root.configure = fake_configure

    # Create a dummy style object with theme_use and lookup
    class DummyStyle:
        def __init__(self, *args, **kwargs):
            pass

        def theme_use(self):
            return "cosmo"

        def lookup(self, *args, **kwargs):
            return "#ffffff"

    # Create a factory that raises TypeError when called with master kwarg
    def style_factory_raise_master(*args, **kwargs):
        if "master" in kwargs:
            raise TypeError("unexpected keyword argument 'master'")
        return DummyStyle()

    # Prepare ApplicationGUI instance with minimal attributes used in the method
    app = ApplicationGUI.__new__(ApplicationGUI)
    app.root = fake_root
    app._ttkbootstrap_style = None
    app._ttkbootstrap_theme = None

    # Monkeypatch the ttkbootstrap module used in gui to provide our factory
    import importlib

    gui_mod = importlib.import_module("zebtrack.ui.gui")
    # Create a fake module-like object with Style attribute and __version__
    fake_ttkb = SimpleNamespace(Style=style_factory_raise_master, __version__="9.9.9")
    monkeypatch.setattr(gui_mod, "ttkb", fake_ttkb)

    # Patch the module logger to capture calls to warning()
    captured = {}

    def fake_warning(*args, **kwargs):
        # store the last warning call args for assertions
        captured['args'] = args
        captured['kwargs'] = kwargs

    def fake_debug(*args, **kwargs):
        # no-op debug to avoid raising AttributeError in _initialize_theme
        captured.setdefault('debug_calls', []).append((args, kwargs))

    monkeypatch.setattr(gui_mod, 'log', SimpleNamespace(warning=fake_warning, debug=fake_debug))

    # Call the method under test
    app._initialize_theme()

    # Ensure style was set by the fallback path
    assert isinstance(app._ttkbootstrap_style, DummyStyle)

    # Ensure our fake logger was called and includes the theme and version
    assert 'args' in captured, "Expected log.warning to be called"
    # First positional arg is the event key string
    assert captured['args'][0] == "ui.theme.bootstrap_master_removed"
    # kwargs should include ttkbootstrap_version and theme (version may come
    # from importlib.metadata in the environment, so don't assert exact value)
    assert 'ttkbootstrap_version' in captured['kwargs']
    assert captured['kwargs'].get('theme') == "cosmo"
