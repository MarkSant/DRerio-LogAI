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
def test_splash_screen_creation():
    """Test that SplashScreen can be created without errors."""
    root = tk.Tk()
    root.withdraw()

    try:
        splash = SplashScreen(parent=root)
        assert splash.splash is not None
        assert isinstance(splash.splash, tk.Toplevel)
        splash.destroy()
    finally:
        root.destroy()


@pytest.mark.gui
def test_splash_screen_no_parent():
    """Test that SplashScreen can be created without explicit parent."""
    # Create implicit root
    root = tk.Tk()
    root.withdraw()

    try:
        splash = SplashScreen()
        assert splash.splash is not None
        splash.destroy()
    finally:
        root.destroy()


@pytest.mark.gui
def test_splash_screen_geometry():
    """Test that splash screen has correct dimensions."""
    root = tk.Tk()
    root.withdraw()

    try:
        splash = SplashScreen(parent=root)

        # Update to ensure geometry is calculated
        splash.splash.update()

        # Check that geometry is set (500x400)
        geometry = splash.splash.geometry()
        assert "500x400" in geometry

        splash.destroy()
    finally:
        root.destroy()


@pytest.mark.gui
def test_splash_screen_update_status():
    """Test that status can be updated without errors."""
    root = tk.Tk()
    root.withdraw()

    try:
        splash = SplashScreen(parent=root)

        # Update status multiple times
        splash.update_status("Loading...")
        assert splash.status_var.get() == "Loading..."

        splash.update_status("Processing...")
        assert splash.status_var.get() == "Processing..."

        splash.update_status("Ready!")
        assert splash.status_var.get() == "Ready!"

        splash.destroy()
    finally:
        root.destroy()


@pytest.mark.gui
def test_splash_screen_destroy():
    """Test that splash screen can be destroyed without errors."""
    root = tk.Tk()
    root.withdraw()

    try:
        splash = SplashScreen(parent=root)

        # Destroy should not raise
        splash.destroy()

        # Multiple destroy calls should be safe
        splash.destroy()
    finally:
        root.destroy()


@pytest.mark.gui
def test_splash_screen_progress_bar():
    """Test that progress bar is created and animating."""
    root = tk.Tk()
    root.withdraw()

    try:
        splash = SplashScreen(parent=root)

        # Progress bar should exist
        assert splash.progress_bar is not None

        # Update to ensure progress bar is rendered
        splash.splash.update()

        splash.destroy()
    finally:
        root.destroy()


@pytest.mark.gui
def test_splash_screen_topmost():
    """Test that splash screen is set to stay on top."""
    root = tk.Tk()
    root.withdraw()

    try:
        splash = SplashScreen(parent=root)

        # Check topmost attribute
        assert splash.splash.attributes("-topmost") is True

        splash.destroy()
    finally:
        root.destroy()


@pytest.mark.gui
def test_splash_screen_no_decorations():
    """Test that splash screen has no window decorations."""
    root = tk.Tk()
    root.withdraw()

    try:
        splash = SplashScreen(parent=root)

        # Check that overrideredirect is set
        assert splash.splash.overrideredirect() == 1

        splash.destroy()
    finally:
        root.destroy()


@pytest.mark.gui
def test_create_splash_factory():
    """Test the factory function create_splash."""
    root = tk.Tk()
    root.withdraw()

    try:
        splash = create_splash(parent=root)

        assert isinstance(splash, SplashScreen)
        assert splash.splash is not None

        splash.destroy()
    finally:
        root.destroy()


@pytest.mark.gui
def test_splash_screen_logo_fallback():
    """Test that splash screen handles missing logo gracefully."""
    root = tk.Tk()
    root.withdraw()

    try:
        splash = SplashScreen(parent=root)

        # Logo label should exist (either image or fallback text)
        assert splash._logo_label is not None

        splash.destroy()
    finally:
        root.destroy()


def test_font_family_platform_specific():
    """Test that font family is correctly set based on platform."""
    if platform.system() == "Windows":
        assert FONT_FAMILY == "Segoe UI"
    else:
        assert FONT_FAMILY == "Helvetica"


@pytest.mark.gui
def test_splash_screen_labels_use_correct_font():
    """Test that labels use the platform-appropriate font."""
    root = tk.Tk()
    root.withdraw()

    try:
        splash = SplashScreen(parent=root)

        # Check that status label uses correct font family
        font_info = splash.status_label.cget("font")
        # font_info could be a tuple or a font object, check the family
        if isinstance(font_info, tuple):
            assert font_info[0] == FONT_FAMILY

        splash.destroy()
    finally:
        root.destroy()


@pytest.mark.gui
def test_splash_screen_background_color():
    """Test that splash screen has the expected dark background."""
    root = tk.Tk()
    root.withdraw()

    try:
        splash = SplashScreen(parent=root)

        # Check background color
        bg_color = splash.splash.cget("bg")
        assert bg_color == BG_COLOR

        splash.destroy()
    finally:
        root.destroy()


def test_color_constants():
    """Test that color constants are defined with expected values."""
    assert BG_COLOR == "#1e1e2e"
    assert ACCENT_COLOR == "#4a9eff"
    assert TEXT_PRIMARY == "#ffffff"
    assert TEXT_SECONDARY == "#a0a0a0"
    assert TEXT_MUTED == "#505050"


@pytest.mark.gui
def test_splash_screen_status_initial_value():
    """Test that splash screen starts with correct initial status."""
    root = tk.Tk()
    root.withdraw()

    try:
        splash = SplashScreen(parent=root)

        # Initial status should be "Inicializando..."
        assert splash.status_var.get() == "Inicializando..."

        splash.destroy()
    finally:
        root.destroy()
