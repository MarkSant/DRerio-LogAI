import pytest
import tkinter as tk

@pytest.fixture
def wizard_dependencies(tkinter_root):
    """Minimal dependencies for wizard tests."""
    return {
        "root": tkinter_root,
    }
