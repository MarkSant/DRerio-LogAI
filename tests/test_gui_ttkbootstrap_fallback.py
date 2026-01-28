from types import SimpleNamespace


def test_ttkbootstrap_style_initialization(monkeypatch, caplog):
    """Verify that ttkbootstrap.Style is initialized correctly.

    It should try without master first. If that fails, it should try with master.
    """

    # Import inside test to pick up local modifications
    from zebtrack.ui.gui import ApplicationGUI

    # Minimal fake root
    fake_root = SimpleNamespace()

    def fake_configure(**kwargs):
        fake_root.configured = kwargs

    fake_root.configure = fake_configure

    # Create a dummy style object
    class DummyStyle:
        def __init__(self, theme=None, master=None):
            self.theme = theme
            self.master = master

        def theme_use(self):
            return "cosmo"

        def lookup(self, *args, **kwargs):
            return "#ffffff"

    # Scenario 1: Style(theme=...) succeeds (Modern behavior)
    def style_factory_success(*args, **kwargs):
        return DummyStyle(*args, **kwargs)

    fake_ttkb = SimpleNamespace(Style=style_factory_success, __version__="1.0.0")

    # Patch dependencies
    import importlib

    gui_mod = importlib.import_module("zebtrack.ui.gui")
    monkeypatch.setattr(gui_mod, "ttkb", fake_ttkb)

    # Create app instance
    app = ApplicationGUI.__new__(ApplicationGUI)
    app.root = fake_root
    app.settings = SimpleNamespace(ui_theme_name="cosmo")
    app._ttkbootstrap_style = None

    # Run initialization
    app._initialize_theme()

    # Verify success
    assert isinstance(app._ttkbootstrap_style, DummyStyle)
    assert app._ttkbootstrap_style.theme == "cosmo"

    # Scenario 2: Style(theme=...) fails, but Style(theme=..., master=...) succeeds
    # (Legacy fallback)
    def style_factory_legacy(*args, **kwargs):
        if "master" not in kwargs:
            raise TypeError("master argument required")
        return DummyStyle(*args, **kwargs)

    fake_ttkb_legacy = SimpleNamespace(Style=style_factory_legacy, __version__="0.5.0")
    monkeypatch.setattr(gui_mod, "ttkb", fake_ttkb_legacy)

    app._ttkbootstrap_style = None
    app._initialize_theme()

    # Verify fallback success
    assert isinstance(app._ttkbootstrap_style, DummyStyle)
    assert app._ttkbootstrap_style.master == fake_root
