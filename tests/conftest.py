import importlib.util
import sys
from unittest.mock import MagicMock


def _mock_tkinter_modules() -> None:
    mock_module = MagicMock()
    sys.modules["tkinter"] = mock_module
    sys.modules["tkinter.filedialog"] = MagicMock()
    sys.modules["tkinter.messagebox"] = MagicMock()
    sys.modules["tkinter.simpledialog"] = MagicMock()
    sys.modules["tkinter.ttk"] = MagicMock()


tkinter_spec = importlib.util.find_spec("tkinter")
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
