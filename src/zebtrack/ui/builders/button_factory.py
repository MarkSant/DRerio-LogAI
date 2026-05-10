"""
Button Factory for creating action buttons and controls.

Extracted from WidgetFactory to separate concern of button creation.
"""

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk


class ButtonFactory:
    """
    Factory for creating application buttons and action controls.
    """

    @staticmethod
    def create_project_action_buttons(
        parent: tk.Widget, commands: dict[str, Callable[[], None]]
    ) -> ttk.LabelFrame:
        """
        Create the project actions controls frame.

        Args:
            parent: Parent widget
            commands: Dictionary mapping action names to callback functions.
                     Expected keys: 'model_configuration', 'diagnostics',
                     'single_analysis', 'live_camera', 'create_project',
                     'open_project'

        Returns:
            The created LabelFrame containing the buttons
        """
        project_actions_frame = ttk.LabelFrame(parent, text="Ações do Projeto", padding=10)
        project_actions_frame.pack(fill="x", pady=10, expand=True)

        ttk.Button(
            project_actions_frame,
            text="Configuração Global de Modelos...",
            command=commands["model_configuration"],
        ).pack(fill="x", padx=10, pady=5)

        ttk.Button(
            project_actions_frame,
            text="Diagnóstico Global...",
            command=commands["diagnostics"],
        ).pack(fill="x", padx=10, pady=5)

        ttk.Button(
            project_actions_frame,
            text="Analisar Vídeo Único",
            command=commands["single_analysis"],
        ).pack(fill="x", padx=10, pady=5)

        ttk.Button(
            project_actions_frame,
            text="Analisar Câmera ao Vivo",
            command=commands["live_camera"],
        ).pack(fill="x", padx=10, pady=5)

        ttk.Button(
            project_actions_frame,
            text="Criar Novo Projeto",
            command=commands["create_project"],
        ).pack(fill="x", padx=10, pady=5)

        ttk.Button(
            project_actions_frame,
            text="Abrir Projeto Existente",
            command=commands["open_project"],
        ).pack(fill="x", padx=10, pady=5)

        return project_actions_frame

    @staticmethod
    def create_floating_drawing_buttons(
        parent: tk.Widget, commands: dict[str, Callable[[], None]]
    ) -> ttk.Frame:
        """
        Create floating undo/redo buttons frame.

        Args:
            parent: Parent widget (usually the visualization frame)
            commands: Dictionary mapping action names to callback functions.
                     Expected keys: 'undo', 'redo'

        Returns:
            The created Frame (caller responsible for placing it)
        """
        drawing_buttons_frame = ttk.Frame(parent, relief="raised", borderwidth=2)

        # Undo button
        undo_btn = ttk.Button(
            drawing_buttons_frame,
            text="↶ Desfazer (Ctrl+Z)",
            command=commands["undo"],
            width=20,
        )
        undo_btn.pack(side="left", padx=2)

        # Redo button
        redo_btn = ttk.Button(
            drawing_buttons_frame,
            text="↷ Refazer (Ctrl+Y)",
            command=commands["redo"],
            width=20,
        )
        redo_btn.pack(side="left", padx=2)

        return drawing_buttons_frame
