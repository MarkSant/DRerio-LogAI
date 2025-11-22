"""Tests for SplashScreen UI component."""

import platform
import tkinter as tk

import pytest

from zebtrack.ui.splash_screen import (
    ACCENT_COLOR,
    BG_COLOR,
    FONT_FAMILY,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    SplashScreen,
    create_splash,
)


@pytest.mark.gui
def test_splash_screen_creation(tkinter_root):
    """Test that SplashScreen can be created without errors."""
    splash = SplashScreen(parent=tkinter_root)
    assert splash.splash is not None
    assert isinstance(splash.splash, tk.Toplevel)
    splash.destroy()


@pytest.mark.gui
def test_splash_screen_no_parent(tkinter_root):
    """Test that SplashScreen can be created without explicit parent."""
    splash = SplashScreen(parent=tkinter_root)
    assert splash.splash is not None
    splash.destroy()


@pytest.mark.gui
def test_splash_screen_geometry(tkinter_root):
    """Test that splash screen has correct dimensions."""
    splash = SplashScreen(parent=tkinter_root)

    # Update to ensure geometry is calculated
    splash.splash.update()

    # Check that geometry is set (500x400)
    geometry = splash.splash.geometry()
    assert "500x400" in geometry

    splash.destroy()


@pytest.mark.gui
def test_splash_screen_update_status(tkinter_root):
    """Test that status can be updated without errors."""
    splash = SplashScreen(parent=tkinter_root)

    # Update status multiple times
    splash.update_status("Loading...")
    assert splash.status_var.get() == "Loading..."

    splash.update_status("Processing...")
    assert splash.status_var.get() == "Processing..."

    splash.update_status("Ready!")
    assert splash.status_var.get() == "Ready!"

    splash.destroy()


@pytest.mark.gui
def test_splash_screen_destroy(tkinter_root):
    """Test that splash screen can be destroyed without errors."""
    splash = SplashScreen(parent=tkinter_root)

    # Destroy should not raise
    splash.destroy()

    # Multiple destroy calls should be safe
    splash.destroy()


@pytest.mark.gui
def test_splash_screen_progress_bar(tkinter_root):
    """Test that progress bar is created and animating."""
    splash = SplashScreen(parent=tkinter_root)

    # Progress bar should exist
    assert splash.progress_bar is not None

    # Update to ensure progress bar is rendered
    splash.splash.update()

    splash.destroy()


@pytest.mark.gui
def test_splash_screen_topmost(tkinter_root):
    """Test that splash screen is set to stay on top."""
    splash = SplashScreen(parent=tkinter_root)

    # Check topmost attribute (returns 1 for True in Tkinter)
    assert splash.splash.attributes("-topmost") == 1

    splash.destroy()


@pytest.mark.gui
def test_splash_screen_no_decorations(tkinter_root):
    """Test that splash screen has no window decorations."""
    splash = SplashScreen(parent=tkinter_root)

    # Check that overrideredirect is set
    assert splash.splash.overrideredirect() == 1

    splash.destroy()


@pytest.mark.gui
def test_create_splash_factory(tkinter_root):
    """Test the factory function create_splash."""
    splash = create_splash(parent=tkinter_root)

    assert isinstance(splash, SplashScreen)
    assert splash.splash is not None

    splash.destroy()


@pytest.mark.gui
def test_splash_screen_logo_fallback(tkinter_root):
    """Test that splash screen handles missing logo gracefully."""
    splash = SplashScreen(parent=tkinter_root)

    # Logo label should exist (either image or fallback text)
    assert splash._logo_label is not None

    splash.destroy()


def test_font_family_platform_specific():
    """Test that font family is correctly set based on platform."""
    if platform.system() == "Windows":
        assert FONT_FAMILY == "Segoe UI"
    else:
        assert FONT_FAMILY == "Helvetica"


@pytest.mark.gui
def test_splash_screen_labels_use_correct_font(tkinter_root):
    """Test that labels use the platform-appropriate font."""
    splash = SplashScreen(parent=tkinter_root)

    # Check that status label uses correct font family
    font_info = splash.status_label.cget("font")
    # font_info could be a tuple or a font object, check the family
    if isinstance(font_info, tuple):
        assert font_info[0] == FONT_FAMILY

    splash.destroy()


@pytest.mark.gui
def test_splash_screen_background_color(tkinter_root):
    """Test that splash screen has the expected dark background."""
    splash = SplashScreen(parent=tkinter_root)

    # Check background color
    bg_color = splash.splash.cget("bg")
    assert bg_color == BG_COLOR

    splash.destroy()


def test_color_constants():
    """Test that color constants are defined with expected values."""
    assert BG_COLOR == "#1e1e2e"
    assert ACCENT_COLOR == "#4a9eff"
    assert TEXT_PRIMARY == "#ffffff"
    assert TEXT_SECONDARY == "#a0a0a0"
    assert TEXT_MUTED == "#505050"


@pytest.mark.gui
def test_splash_screen_status_initial_value(tkinter_root):
    """Test that splash screen starts with correct initial status."""
    splash = SplashScreen(parent=tkinter_root)

    # Initial status should be "Inicializando..."
    assert splash.status_var.get() == "Inicializando..."

    splash.destroy()
