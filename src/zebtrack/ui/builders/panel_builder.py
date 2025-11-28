"""
Panel Builder for creating status and summary panels.

Extracted from WidgetFactory to separate concern of panel construction.
"""

import tkinter as tk
from tkinter import StringVar, ttk

# Status symbols used in UI
STATUS_SYMBOLS = {
    "arena": "\U0001f3df",  # 🏟
    "rois": "\U0001f3af",  # 🎯
    "trajectory": "\U0001f9ed",  # 🧭
    "summary": "\u03a3",  # Σ
}


class PanelBuilder:
    """
    Builder for creating status and info panels.
    """

    @staticmethod
    def build_model_status_panel(
        parent: tk.Widget, status_vars: dict[str, StringVar]
    ) -> ttk.LabelFrame:
        """
        Create the model status display.

        Args:
            parent: Parent widget
            status_vars: Dictionary containing StringVars for status display.
                        Expected keys: 'active_weight', 'openvino_status', 'hardware_status'

        Returns:
            The created LabelFrame
        """
        model_status_frame = ttk.LabelFrame(parent, text="Estado do Modelo de Detecção", padding=10)
        model_status_frame.pack(fill="x", pady=10, expand=True)

        ttk.Label(
            model_status_frame,
            textvariable=status_vars.get("active_weight"),
        ).pack(anchor="w")

        ttk.Label(
            model_status_frame,
            textvariable=status_vars.get("openvino_status"),
        ).pack(anchor="w", pady=(4, 0))

        ttk.Label(
            model_status_frame,
            textvariable=status_vars.get("hardware_status"),
            foreground="gray",
        ).pack(anchor="w", pady=(4, 0))

        return model_status_frame

    @staticmethod
    def create_zone_summary_cards(
        parent: tk.Widget, helper_text: str
    ) -> tuple[ttk.LabelFrame, dict[str, dict[str, StringVar]]]:
        """
        Create zone summary cards section.

        Args:
            parent: Parent widget to pack the frame into
            helper_text: Helper text to display at the bottom

        Returns:
            Tuple containing (created_frame, cards_data_dict)
            cards_data_dict maps keys (arena_missing, etc.) to dicts containing 'value' and 'detail' StringVars.
        """
        zone_summary_frame = ttk.LabelFrame(
            parent,
            text=f"{STATUS_SYMBOLS['summary']} Indicadores de Preparação",
            padding=10,
        )
        zone_summary_frame.pack(fill="x", pady=(0, 5))

        cards_container = ttk.Frame(zone_summary_frame)
        cards_container.pack(fill="x")

        card_specs = [
            ("arena_missing", f"{STATUS_SYMBOLS['arena']} Arenas pendentes"),
            ("rois_missing", f"{STATUS_SYMBOLS['rois']} ROIs pendentes"),
            (
                "ready_for_processing",
                f"{STATUS_SYMBOLS['summary']} Prontos para trajetórias",
            ),
        ]

        cards_data = {}

        for idx, (key, title) in enumerate(card_specs):
            card = ttk.Frame(cards_container, padding=10, relief="ridge", borderwidth=1)
            card.grid(row=0, column=idx, padx=5, pady=5, sticky="nsew")
            cards_container.columnconfigure(idx, weight=1)

            value_var = StringVar(value="0")
            detail_var = StringVar(value="Nenhum vídeo listado")

            ttk.Label(card, text=title, font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
            value_label = ttk.Label(
                card, textvariable=value_var, font=("TkDefaultFont", 20, "bold")
            )
            value_label.pack(anchor="w", pady=(5, 0))
            ttk.Label(card, textvariable=detail_var, font=("TkDefaultFont", 8)).pack(
                anchor="w", pady=(2, 0)
            )

            cards_data[key] = {
                "value": value_var,
                "detail": detail_var,
            }

        # Add helper text at bottom
        if helper_text:
            ttk.Label(
                zone_summary_frame,
                text=helper_text,
                font=("TkDefaultFont", 8),
                foreground="gray",
            ).pack(anchor="w", pady=(5, 0))

        return zone_summary_frame, cards_data
