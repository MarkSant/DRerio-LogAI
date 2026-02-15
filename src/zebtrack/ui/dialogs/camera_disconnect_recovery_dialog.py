"""Camera disconnect recovery dialog.

Presents options to user when camera disconnects during live session:
- Wait and retry (30s timeout)
- Stop session and save data
- Resume manually after reconnect

Version: 2.2.0
Author: ZebTrack-AI Team
Date: January 2026
"""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Literal

import structlog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

RecoveryAction = Literal["wait", "stop", "resume"]


class CameraDisconnectRecoveryDialog(tk.Toplevel):
    """Dialog shown when camera disconnects during live capture.

    Provides user with options:
    1. Wait 30s for automatic reconnection
    2. Stop session and save current data
    3. Manual resume after user reconnects camera

    Non-blocking: Uses after() for countdown and returns immediately.
    Callback invoked when user makes a choice or timeout expires.
    """

    def __init__(
        self,
        parent: tk.Misc,
        gap_duration_s: float,
        experiment_id: str,
        on_action_callback: Callable[[RecoveryAction], None],
    ):
        """Initialize recovery dialog.

        Args:
            parent: Parent Tkinter widget
            gap_duration_s: Duration of camera gap before detection
            experiment_id: Current experiment identifier
            on_action_callback: Callback invoked with user's chosen action
        """
        super().__init__(parent)

        self.gap_duration = gap_duration_s
        self.experiment_id = experiment_id
        self.on_action_callback = on_action_callback
        self.action_taken = False
        self.countdown_remaining = 30  # 30 second countdown
        self.countdown_active = False

        self.title("Câmera Desconectada")
        self.geometry("500x300")
        self.resizable(False, False)

        # Make modal
        self.transient(parent.winfo_toplevel())
        self.grab_set()

        self._create_widgets()
        self._start_countdown()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

        logger.info(
            "camera_disconnect_dialog.created",
            experiment_id=experiment_id,
            gap_duration_s=gap_duration_s,
        )

    def _create_widgets(self) -> None:
        """Create dialog widgets."""
        # Main frame
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Icon and title
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 15))

        icon_label = ttk.Label(
            title_frame,
            text="⚠️",
            font=("Arial", 32),
        )
        icon_label.pack(side=tk.LEFT, padx=(0, 15))

        title_label = ttk.Label(
            title_frame,
            text="Câmera Desconectada",
            font=("Arial", 14, "bold"),
        )
        title_label.pack(side=tk.LEFT, anchor=tk.W)

        # Description
        desc_text = (
            f"A câmera foi desconectada durante a sessão '{self.experiment_id}'.\n\n"
            f"Gap detectado após {self.gap_duration:.1f}s sem frames válidos.\n"
            f"A gravação foi pausada automaticamente para evitar dados inválidos."
        )
        desc_label = ttk.Label(
            main_frame,
            text=desc_text,
            wraplength=450,
            justify=tk.LEFT,
        )
        desc_label.pack(fill=tk.X, pady=(0, 15))

        # Countdown label
        self.countdown_label = ttk.Label(
            main_frame,
            text=f"Tentando reconectar automaticamente em {self.countdown_remaining}s...",
            font=("Arial", 10, "italic"),
            foreground="blue",
        )
        self.countdown_label.pack(fill=tk.X, pady=(0, 15))

        # Progress bar
        self.progress = ttk.Progressbar(
            main_frame,
            mode="determinate",
            maximum=30,
            value=30,
        )
        self.progress.pack(fill=tk.X, pady=(0, 15))

        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)

        # Wait button (auto-enabled)
        self.wait_btn = ttk.Button(
            button_frame,
            text="⏱️ Aguardar Reconexão (30s)",
            command=self._on_wait,
            state=tk.DISABLED,  # Countdown is automatic
        )
        self.wait_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        # Resume button
        resume_btn = ttk.Button(
            button_frame,
            text="🔌 Retomar Manualmente",
            command=self._on_resume,
        )
        resume_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        # Stop button
        stop_btn = ttk.Button(
            button_frame,
            text="⏹️ Parar Sessão",
            command=self._on_stop,
        )
        stop_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        # Instructions
        instructions_text = (
            "\nOpções:\n"
            "• Aguardar: Tenta reconectar automaticamente (30s)\n"
            "• Retomar: Continue gravação após reconectar câmera manualmente\n"
            "• Parar: Finaliza sessão e salva dados coletados até agora"
        )
        instructions_label = ttk.Label(
            main_frame,
            text=instructions_text,
            wraplength=450,
            justify=tk.LEFT,
            font=("Arial", 9),
            foreground="gray",
        )
        instructions_label.pack(fill=tk.X, pady=(15, 0))

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_stop)

    def _start_countdown(self) -> None:
        """Start automatic countdown timer."""
        self.countdown_active = True
        self._update_countdown()

    def _update_countdown(self) -> None:
        """Update countdown display (called via after())."""
        if not self.countdown_active:
            return

        if self.countdown_remaining <= 0:
            # Timeout - attempt automatic reconnection
            self._on_wait()
            return

        # Update UI
        self.countdown_label.config(
            text=f"Tentando reconectar automaticamente em {self.countdown_remaining}s..."
        )
        self.progress.config(value=self.countdown_remaining)

        # Decrement and schedule next update
        self.countdown_remaining -= 1
        self.after(1000, self._update_countdown)

    def _on_wait(self) -> None:
        """Handle wait/auto-reconnect action."""
        if self.action_taken:
            return

        self.action_taken = True
        self.countdown_active = False

        logger.info(
            "camera_disconnect_dialog.action_wait",
            experiment_id=self.experiment_id,
        )

        self.countdown_label.config(
            text="Aguardando reconexão da câmera...",
            foreground="orange",
        )

        # Invoke callback in background thread to avoid blocking UI
        threading.Thread(
            target=lambda: self.on_action_callback("wait"),
            daemon=True,
        ).start()

        # Keep dialog open to show status
        # Callback should close it when camera reconnects or timeout expires

    def _on_resume(self) -> None:
        """Handle manual resume action."""
        if self.action_taken:
            return

        self.action_taken = True
        self.countdown_active = False

        logger.info(
            "camera_disconnect_dialog.action_resume",
            experiment_id=self.experiment_id,
        )

        self.on_action_callback("resume")
        self.destroy()

    def _on_stop(self) -> None:
        """Handle stop session action."""
        if self.action_taken:
            return

        self.action_taken = True
        self.countdown_active = False

        logger.info(
            "camera_disconnect_dialog.action_stop",
            experiment_id=self.experiment_id,
        )

        self.on_action_callback("stop")
        self.destroy()

    def close_dialog(self) -> None:
        """Programmatically close dialog (called by controller)."""
        self.countdown_active = False
        try:
            self.destroy()
        except tk.TclError:
            pass  # Already destroyed
