"""Common widget builders for shared UI utilities."""

from __future__ import annotations

import hashlib
import tkinter as tk
from pathlib import Path
from tkinter import Frame, Label, Radiobutton, StringVar, Toplevel, ttk

import structlog

from zebtrack.settings import Settings

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

    def build_status_icon_legend_simple(self, *, include_summary: bool = False) -> str:
        """Compose a compact legend string for the status glyphs."""
        legend_parts = [
            f"{STATUS_SYMBOLS['arena']} \u2713 Arena",
            f"{STATUS_SYMBOLS['rois']} \u2713 ROIs",
            f"{STATUS_SYMBOLS['trajectory']} \u2713 Trajetória",
        ]
        if include_summary:
            legend_parts.append(f"{STATUS_SYMBOLS['summary']} \u2713 Sumário")
        legend_parts.append("\u2717 Ausente")
        return "Legenda: " + " | ".join(legend_parts)

    def get_zone_summary_helper_text(self) -> str:
        """Return helper text for zone summary section."""
        return (
            f"{STATUS_SYMBOLS['summary']} indica vídeos prontos para gerar "
            "trajetórias (arena e ROIs salvos). O valor mostra quantos ainda "
            "aguardam processamento."
        )

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
            candidate = str(base_value) if base_value is not None else "Sem Dia"
        candidate_str = str(candidate).strip()
        if not candidate_str:
            candidate_str = "Sem Dia"
        if candidate_str.lower() == "sem dia":
            return "Sem Dia"
        return f"Dia {candidate_str}"

    def build_processing_report_artifact_id(self, parent_id: str, artifact_path: str) -> str:
        """Create a stable item id for report artifacts while avoiding duplicates."""
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
        return ["Todos", *ordered]

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    def configure_styles(self) -> None:
        """Configure custom styles for ttk components used by the GUI."""
        style = ttk.Style(self.gui.root)
        self.gui._style = style

        try:
            style.theme_use()
        except tk.TclError:
            style.theme_use("default")

        base_background = (
            style.lookup("TNotebook", "background", None)
            or (
                self.gui._ttkbootstrap_style.lookup("TFrame", "background")
                if self.gui._ttkbootstrap_style is not None
                else None
            )
            or "#f6f7fb"
        )
        accent_background = (
            style.lookup("TNotebook.Tab", "background", None, ("selected",))
            or style.lookup("TFrame", "background", None)
            or "#ffffff"
        )
        tab_inactive = style.lookup("TNotebook.Tab", "background", None) or "#dce3ee"
        border_color = (
            style.lookup("TNotebook", "bordercolor", None)
            or style.lookup("TNotebook", "lightcolor", None)
            or "#c5ccd9"
        )
        text_active = style.lookup("TNotebook.Tab", "foreground", None, ("selected",)) or "#1d2733"
        text_inactive = style.lookup("TNotebook.Tab", "foreground", None) or "#4a5568"

        style.configure(
            "Zebtrack.TNotebook",
            background=base_background,
            borderwidth=0,
            tabmargins=(10, 6, 10, 0),
        )

        style.configure(
            "Zebtrack.TNotebook.Tab",
            background=tab_inactive,
            padding=(18, 10),
            font=("Segoe UI", 10, "bold"),
            foreground=text_inactive,
            bordercolor=border_color,
        )

        style.map(
            "Zebtrack.TNotebook.Tab",
            background=[("selected", accent_background), ("!selected", tab_inactive)],
            foreground=[("selected", text_active), ("!selected", text_inactive)],
            bordercolor=[("selected", "#4c6997"), ("!selected", border_color)],
        )

        style.configure(
            "Zebtrack.TNotebook.Tab",
            focuscolor="",
        )
        style.configure("Zebtrack.TNotebook", padding=(4, 4))

    def prompt_for_weight_type(self):
        """Prompt user to select weight type when it cannot be determined from filename."""
        dialog = Toplevel(self.gui.root)
        dialog.title("Tipo de Peso")
        dialog.geometry("300x150")
        dialog.resizable(False, False)
        dialog.transient(self.gui.root)
        dialog.grab_set()

        self.gui.root.update_idletasks()
        x = (self.gui.root.winfo_screenwidth() // 2) - (300 // 2)
        y = (self.gui.root.winfo_screenheight() // 2) - (150 // 2)
        dialog.geometry(f"+{x}+{y}")

        Label(dialog, text="Selecione o tipo de modelo:").pack(pady=10)

        weight_type_var = StringVar(value="seg")

        Radiobutton(
            dialog,
            text="Segmentação (para máscaras e bordas precisas)",
            variable=weight_type_var,
            value="seg",
        ).pack(anchor="w", padx=20)

        Radiobutton(
            dialog,
            text="Detecção (para caixas delimitadoras rápidas)",
            variable=weight_type_var,
            value="det",
        ).pack(anchor="w", padx=20)

        result: list[str | None] = [None]

        def on_ok():
            result[0] = weight_type_var.get()
            dialog.destroy()

        def on_cancel():
            result[0] = None
            dialog.destroy()

        button_frame = Frame(dialog)
        button_frame.pack(pady=20)

        ttk.Button(button_frame, text="OK", command=on_ok).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Cancelar", command=on_cancel).pack(side="left", padx=5)

        dialog.wait_window()
        return result[0]

    def update_roi_rule_ui(self, rule: str) -> None:
        """Handle ROI inclusion rule change and update UI accordingly."""
        if hasattr(self.gui, "radius_frame") and self.gui.radius_frame:
            self.gui.radius_frame.pack_forget()
        if hasattr(self.gui, "overlap_frame") and self.gui.overlap_frame:
            self.gui.overlap_frame.pack_forget()

        if rule == "centroid_in_on_buffered_roi":
            if hasattr(self.gui, "radius_frame") and self.gui.radius_frame:
                self.gui.radius_frame.pack(fill="x", pady=2)
        elif rule in ("bbox_intersects", "seg_overlap"):
            if hasattr(self.gui, "overlap_frame") and self.gui.overlap_frame:
                self.gui.overlap_frame.pack(fill="x", pady=2)

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
                    text="Bem-vindo ao DRerio LogAI",
                    font=("Helvetica", 16),
                ).pack(pady=(0, 15))
                log.warning("welcome.logo.not_found", attempted_path=str(logo_path))

        except (OSError, tk.TclError, ImportError) as e:
            import ttkbootstrap as ttk_bootstrap

            ttk_bootstrap.Label(
                self.gui.welcome_frame,
                text="Bem-vindo ao DRerio LogAI",
                font=("Helvetica", 16),
            ).pack(pady=(0, 15))
            log.warning("welcome.logo.load_error", error=str(e))
