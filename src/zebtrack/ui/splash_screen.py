"""Splash screen for ZebTrack-AI startup."""

import platform
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import structlog

from zebtrack.constants import SPLASH_HEIGHT, SPLASH_WIDTH

log = structlog.get_logger()

# Platform-specific font selection
FONT_FAMILY = "Segoe UI" if platform.system() == "Windows" else "Helvetica"

# Color scheme constants
BG_COLOR = "#1e1e2e"  # Dark elegant background
ACCENT_COLOR = "#4a9eff"  # Blue accent for highlights
TEXT_PRIMARY = "#ffffff"  # White for primary text
TEXT_SECONDARY = "#a0a0a0"  # Gray for secondary text
TEXT_MUTED = "#505050"  # Darker gray for footer text


class SplashScreen:
    """Professional splash screen with logo and loading indicator.

    Displays the DRerio LogAI logo with a progress bar and status text
    during application initialization.
    """

    def __init__(self, parent=None):
        """Create and display splash screen.

        Args:
            parent: Optional parent window (tk.Tk instance). If None, uses default root.
        """
        self.splash = tk.Toplevel(parent)
        self.splash.overrideredirect(True)  # Remove window decorations

        # Get screen dimensions for centering
        screen_width = self.splash.winfo_screenwidth()
        screen_height = self.splash.winfo_screenheight()

        # Splash dimensions
        splash_width = SPLASH_WIDTH
        splash_height = SPLASH_HEIGHT

        # Calculate position for center of screen
        x = (screen_width - splash_width) // 2
        y = (screen_height - splash_height) // 2

        self.splash.geometry(f"{splash_width}x{splash_height}+{x}+{y}")

        # Set background color
        self.splash.configure(bg=BG_COLOR)

        # Main container
        container = tk.Frame(self.splash, bg=BG_COLOR)
        container.pack(expand=True, fill=tk.BOTH, padx=40, pady=40)

        # Logo image (try PNG first, fallback to text)
        logo_frame = tk.Frame(container, bg=BG_COLOR)
        logo_frame.pack(pady=(0, 30))

        self._logo_label = self._create_logo(logo_frame)

        # Subtitle (title removed - already in logo)
        subtitle_label = tk.Label(
            container,
            text="Zebrafish Tracking & Analysis",
            font=(FONT_FAMILY, 11),
            bg=BG_COLOR,
            fg=TEXT_SECONDARY,
        )
        subtitle_label.pack(pady=(0, 40))

        # Loading indicator (indeterminate progress bar)
        progress_frame = tk.Frame(container, bg=BG_COLOR)
        progress_frame.pack(fill=tk.X, pady=(0, 15))

        self.progress_bar = ttk.Progressbar(progress_frame, mode="indeterminate", length=400)
        self.progress_bar.pack()
        self.progress_bar.start(10)  # Animate every 10ms

        # Status label
        self.status_var = tk.StringVar(value="Inicializando...")
        self.status_label = tk.Label(
            container,
            textvariable=self.status_var,
            font=(FONT_FAMILY, 10),
            bg=BG_COLOR,
            fg=TEXT_SECONDARY,
        )
        self.status_label.pack()

        # Version/info label (small footer)
        version_label = tk.Label(
            container,
            text="Powered by YOLO + ByteTrack",
            font=(FONT_FAMILY, 8),
            bg=BG_COLOR,
            fg=TEXT_MUTED,
        )
        version_label.pack(side=tk.BOTTOM)

        # Make splash stay on top
        self.splash.attributes("-topmost", True)

        # Update to show splash immediately
        self.splash.update()

        log.info("splash.created", width=splash_width, height=splash_height)

    def _create_logo(self, parent):
        """Try to load logo image, fallback to text if not found."""
        try:
            # Try to find logo PNG
            possible_paths = [
                Path(__file__).parent / "assets" / "logo_welcome.png",
                Path("src/zebtrack/ui/assets/logo_welcome.png"),
            ]

            logo_path = None
            for path in possible_paths:
                if path.exists():
                    logo_path = path
                    break

            if logo_path:
                # Load and display image
                from PIL import Image, ImageTk

                img = Image.open(logo_path)
                # Resize to reasonable splash size (keep aspect ratio)
                img.thumbnail((200, 200), Image.LANCZOS)  # type: ignore[attr-defined]
                photo = ImageTk.PhotoImage(img)

                label = tk.Label(parent, image=photo, bg=BG_COLOR)
                label.image = photo  # type: ignore[attr-defined]
                label.pack()

                log.info("splash.logo.loaded", path=str(logo_path))
                return label
            else:
                raise FileNotFoundError("Logo not found")

        except Exception as e:
            # Fallback to text logo
            log.info("splash.logo.fallback", reason=str(e))
            label = tk.Label(
                parent, text="🐟", font=(FONT_FAMILY, 72), bg=BG_COLOR, fg=ACCENT_COLOR
            )
            label.pack()
            return label

    def update_status(self, message: str) -> None:
        """Update status message.

        Args:
            message: Status text to display
        """
        self.status_var.set(message)
        self.splash.update()
        log.debug("splash.status.updated", message=message)

    def destroy(self) -> None:
        """Close and destroy splash screen."""
        try:
            self.progress_bar.stop()
            self.splash.destroy()
            log.info("splash.destroyed")
        except Exception as e:
            log.warning("splash.destroy.failed", error=str(e))


def create_splash(parent=None) -> SplashScreen:
    """Factory function to create splash screen.

    Args:
        parent: Optional parent window (tk.Tk instance)

    Returns:
        SplashScreen instance
    """
    return SplashScreen(parent)
