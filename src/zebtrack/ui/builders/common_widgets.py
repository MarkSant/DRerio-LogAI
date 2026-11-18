"""Common widget builders for shared UI utilities."""

from __future__ import annotations

import hashlib
import tkinter as tk
from pathlib import Path

import structlog

from zebtrack.i18n import _
from zebtrack.settings import Settings
from zebtrack.ui.sentinels import all_tracks_label, day_prefix, no_day_label

log = structlog.get_logger()


# Status symbols used in UI
STATUS_SYMBOLS = {
    "arena": "\U0001f3df",  # \U0001f3df
    "rois": "\U0001f3af",  # \U0001f3af
    "trajectory": "\U0001f9ed",  # \U0001f9ed
    "summary": "\u03a3",  # \u03a3
}


class CommonWidgetsBuilder:
    """Shared widget builder utilities and config-related UI handlers."""

    def __init__(self, gui, settings_obj: Settings | None, dialog_manager=None) -> None:
        self.gui = gui
        self._settings = settings_obj
        self._dialog_manager = dialog_manager

    @property
    def dialog_manager(self):
        return self._dialog_manager or self.gui.dialog_manager

    # ------------------------------------------------------------------
    # Simple utilities
    # ------------------------------------------------------------------

    def build_day_title(self, day_value, metadata: dict | None = None) -> str:
        """Build formatted day title for display."""
        metadata = metadata or {}
        candidate = metadata.get("day_label") or ""
        if not candidate and metadata.get("day") is not None:
            candidate = self.gui.validation_manager._format_day_display(metadata.get("day"))
        if not candidate:
            candidate = self.gui.validation_manager._format_day_display(day_value)
        if not candidate:
            base_value = day_value if day_value not in (None, "") else None
            candidate = str(base_value) if base_value is not None else no_day_label()
        candidate_str = str(candidate).strip()
        if not candidate_str:
            candidate_str = no_day_label()
        # "sem dia" is what existing metadata contains; both spellings map to
        # the localized label.
        if candidate_str.lower() in ("sem dia", no_day_label().lower()):  # i18n: not-ui
            return no_day_label()
        return f"{day_prefix()} {candidate_str}"

    def build_processing_report_artifact_id(self, parent_id: str, artifact_path: Path | str) -> str:
        """Create a stable item id for report artifacts while avoiding duplicates.

        Normalizing through Path also makes the id independent of separator
        style, so a caller passing ``"a/b.docx"`` and one passing
        ``Path("a\\b.docx")`` no longer produce two tree entries for one file.
        """
        artifact_path = Path(artifact_path) if isinstance(artifact_path, str) else artifact_path
        digest_source = f"{parent_id}|{artifact_path}".encode("utf-8", "ignore")
        digest = hashlib.blake2b(digest_source, digest_size=8).hexdigest()
        return f"file_{digest}"

    def build_track_options(self, detections: list[tuple]) -> list[str]:
        """Build list of track IDs from detections for selector."""
        observed: set[str] = set()
        for det in detections:
            if len(det) < 6:
                continue
            track_id = det[5]
            if track_id is None:
                continue
            text = str(track_id).strip()
            if text:
                observed.add(text)

        ordered = sorted(observed, key=str)
        return [all_tracks_label(), *ordered]

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    def display_welcome_logo(self) -> None:
        """Display the DRerio LogAI logo in the welcome frame."""
        try:
            logo_path = Path(__file__).parent.parent / "assets" / "logo_welcome.png"

            if not logo_path.exists():
                logo_path = Path("src/zebtrack/ui/assets/logo_welcome.png")

            if logo_path.exists():
                from PIL import Image, ImageTk

                logo_pil = Image.open(logo_path)
                self.gui._welcome_logo_image = ImageTk.PhotoImage(logo_pil)

                import ttkbootstrap as ttk_bootstrap

                logo_label = ttk_bootstrap.Label(
                    self.gui.welcome_frame,
                    image=self.gui._welcome_logo_image,
                )
                logo_label.pack(pady=(10, 20))

                log.debug("welcome.logo.displayed", path=str(logo_path))
            else:
                import ttkbootstrap as ttk_bootstrap

                ttk_bootstrap.Label(
                    self.gui.welcome_frame,
                    text=_("Welcome to DRerio LogAI"),
                    font=("Helvetica", 16),
                ).pack(pady=(0, 15))
                log.warning("welcome.logo.not_found", attempted_path=str(logo_path))

        except (OSError, tk.TclError, ImportError) as e:
            import ttkbootstrap as ttk_bootstrap

            ttk_bootstrap.Label(
                self.gui.welcome_frame,
                text=_("Welcome to DRerio LogAI"),
                font=("Helvetica", 16),
            ).pack(pady=(0, 15))
            log.warning("welcome.logo.load_error", error=str(e))
