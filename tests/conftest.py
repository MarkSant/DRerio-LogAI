import sys
from unittest.mock import MagicMock

# Mock tkinter if it's not available (for headless environments)
try:
    import tkinter
except ImportError:
    sys.modules["tkinter"] = MagicMock()
    sys.modules["tkinter.filedialog"] = MagicMock()
    sys.modules["tkinter.messagebox"] = MagicMock()
    sys.modules["tkinter.simpledialog"] = MagicMock()
    sys.modules["tkinter.ttk"] = MagicMock()
