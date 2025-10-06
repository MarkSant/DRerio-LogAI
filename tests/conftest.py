import os
import sys
from importlib import util
from unittest.mock import MagicMock

os.environ.setdefault("ZEBTRACK_SUPPRESS_POST_CREATION_GUIDE", "1")
os.environ.setdefault("ZEBTRACK_SUPPRESS_WIZARD_DIALOGS", "1")


def _mock_tkinter_modules() -> None:
    mock_module = MagicMock()
    sys.modules["tkinter"] = mock_module
    sys.modules["tkinter.filedialog"] = MagicMock()
    sys.modules["tkinter.messagebox"] = MagicMock()
    sys.modules["tkinter.simpledialog"] = MagicMock()
    sys.modules["tkinter.ttk"] = MagicMock()


tkinter_spec = util.find_spec("tkinter")
if tkinter_spec is None:
    _mock_tkinter_modules()
else:
    try:
        import tkinter  # runtime import for capability check

        try:
            root = tkinter.Tk()
            root.withdraw()
            root.destroy()
        except Exception:  # noqa: BLE001 - fallback to mock when Tk init fails
            _mock_tkinter_modules()
    except Exception:  # noqa: BLE001
        _mock_tkinter_modules()
