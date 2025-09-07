import importlib.util
import sys
from unittest.mock import MagicMock

# Mock tkinter if it's not available (for headless environments)
tkinter_spec = importlib.util.find_spec("tkinter")
if tkinter_spec is None:
    sys.modules["tkinter"] = MagicMock()
    sys.modules["tkinter.filedialog"] = MagicMock()
    sys.modules["tkinter.messagebox"] = MagicMock()
    sys.modules["tkinter.simpledialog"] = MagicMock()
    sys.modules["tkinter.ttk"] = MagicMock()
