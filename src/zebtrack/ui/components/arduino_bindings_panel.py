"""Project-scoped editor for per-zone Arduino commands (live projects).

A point-and-click table mapping each ROI to the integer the application sends
to the Arduino when an animal **enters** and **leaves** that ROI. DRerio LogAI
only transports the number — what the firmware does with it (light an LED, fire
a relay, deliver a stimulus) lives entirely in the Arduino sketch.

The only typed value is the short integer token; ROI and edge are chosen from
controls. Persisted in ``project_data["arduino_bindings"]``.
"""

from __future__ import annotations

from tkinter import StringVar, ttk
from typing import Any, cast

import structlog
from pydantic import ValidationError

from zebtrack.core.services.arduino_bindings import (
    ArduinoBinding,
    ArduinoBindingConfig,
)

log = structlog.get_logger()

DISCLAIMER = (
    "O DRerio apenas ENVIA o número que você escolher quando o animal entra ou "
    "sai da ROI. O que o número faz (acender LED, choque, flash, etc.) é "
    "responsabilidade do SEU sketch Arduino — usar Arduino pressupõe que você "
    "saiba programá-lo. Ex. do sketch RGB de referência: 1=LED verm.1 ON, 2=OFF, "
    "3=azul ON, 4=OFF, 5=verde ON, 6=OFF, 7=verm.2 ON, 8=OFF."
)

NOTE_NO_ARDUINO = (
    "Arduino não está habilitado neste projeto. Ative 'Usar Arduino' ao criar o "
    "projeto (assistente, etapa de configuração ao vivo) para configurar comandos "
    "por zona."
)

TOKEN_MIN = 0
TOKEN_MAX = 255


class ArduinoBindingsPanel(ttk.Frame):
    """Editor table for ROI → enter/exit Arduino tokens."""

    def __init__(self, parent: Any, controller: Any) -> None:
        super().__init__(parent)
        self.controller = controller
        self.project_manager = controller.project_manager

        self.roi_choice = StringVar(master=self)
        self.enter_token = StringVar(master=self)
        self.exit_token = StringVar(master=self)

        self._tree: ttk.Treeview | None = None
        self._roi_combo: ttk.Combobox | None = None
        self._status: ttk.Label | None = None
        self._note: ttk.Label | None = None
        self._frame: ttk.LabelFrame | None = None

        self._build()
        self.refresh()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self._note = ttk.Label(
            self, text=NOTE_NO_ARDUINO, foreground="gray", wraplength=380, justify="left"
        )

        frame = ttk.LabelFrame(self, text="Comandos Arduino por Zona (Opcional)", padding=8)
        self._frame = frame

        ttk.Label(frame, text=DISCLAIMER, foreground="gray", wraplength=380, justify="left").pack(
            anchor="w", pady=(0, 6)
        )

        cols = ("roi", "enter", "exit")
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=4)
        tree.heading("roi", text="ROI")
        tree.heading("enter", text="Ao Entrar")
        tree.heading("exit", text="Ao Sair")
        tree.column("roi", width=150, anchor="w")
        tree.column("enter", width=80, anchor="center")
        tree.column("exit", width=80, anchor="center")
        tree.pack(fill="x")
        tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree = tree

        editor = ttk.Frame(frame)
        editor.pack(fill="x", pady=(6, 0))
        ttk.Label(editor, text="ROI:").pack(side="left")
        self._roi_combo = ttk.Combobox(
            editor, textvariable=self.roi_choice, state="readonly", width=14
        )
        self._roi_combo.pack(side="left", padx=(2, 8))
        ttk.Label(editor, text="Entrar:").pack(side="left")
        ttk.Spinbox(
            editor, from_=TOKEN_MIN, to=TOKEN_MAX, textvariable=self.enter_token, width=5
        ).pack(side="left", padx=(2, 8))
        ttk.Label(editor, text="Sair:").pack(side="left")
        ttk.Spinbox(
            editor, from_=TOKEN_MIN, to=TOKEN_MAX, textvariable=self.exit_token, width=5
        ).pack(side="left", padx=(2, 8))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text="Adicionar / Atualizar", command=self._add_or_update).pack(
            side="left"
        )
        ttk.Button(buttons, text="Remover", command=self._remove).pack(side="left", padx=4)
        ttk.Button(buttons, text="Limpar", command=self._clear).pack(side="left")
        ttk.Button(buttons, text="🔄 ROIs", command=self.refresh_roi_choices).pack(side="right")

        self._status = ttk.Label(frame, text="", foreground="gray")
        self._status.pack(anchor="w", pady=(4, 0))

    # ------------------------------------------------------------------
    # Public refresh
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-evaluate visibility and reload ROIs/bindings from the project."""
        project_type = None
        if hasattr(self.project_manager, "get_project_type"):
            project_type = self.project_manager.get_project_type()
        use_arduino = bool(self._project_data().get("use_arduino"))

        # Only meaningful for live projects (per-zone commands run live).
        if project_type not in (None, "live"):
            self._hide_all()
            return

        if not use_arduino:
            if self._frame:
                self._frame.pack_forget()
            if self._note:
                self._note.pack(anchor="w", fill="x")
            return

        if self._note:
            self._note.pack_forget()
        if self._frame:
            self._frame.pack(fill="both", expand=True)
        self.refresh_roi_choices()
        self.load_bindings()

    def _hide_all(self) -> None:
        if self._frame:
            self._frame.pack_forget()
        if self._note:
            self._note.pack_forget()

    def refresh_roi_choices(self) -> None:
        """Reload the ROI dropdown from the project's current zone data."""
        names = self._project_roi_names()
        if self._roi_combo is not None:
            self._roi_combo["values"] = names
            if not self.roi_choice.get() and names:
                self.roi_choice.set(names[0])
        if self._status is not None:
            self._status.config(
                text=(f"{len(names)} ROI(s) disponível(is)." if names else "Defina ROIs primeiro."),
                foreground="gray",
            )

    def load_bindings(self) -> None:
        """Populate the table from ``project_data["arduino_bindings"]``."""
        if self._tree is None:
            return
        self._tree.delete(*self._tree.get_children())
        cfg = ArduinoBindingConfig.from_project_data(self._project_data())
        for binding in cfg.bindings:
            self._tree.insert(
                "",
                "end",
                iid=binding.roi,
                values=(
                    binding.roi,
                    "" if binding.on_enter is None else binding.on_enter,
                    "" if binding.on_exit is None else binding.on_exit,
                ),
            )

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------
    def _on_select(self, _event: Any = None) -> None:
        if self._tree is None:
            return
        selection = self._tree.selection()
        if not selection:
            return
        roi, enter, exit_ = cast("tuple[Any, Any, Any]", self._tree.item(selection[0], "values"))
        self.roi_choice.set(roi)
        self.enter_token.set(str(enter))
        self.exit_token.set(str(exit_))

    def _add_or_update(self) -> None:
        roi = self.roi_choice.get().strip()
        if not roi:
            self._set_status("Selecione uma ROI.", error=True)
            return
        try:
            binding = ArduinoBinding(
                roi=roi,
                on_enter=self._parse_token(self.enter_token.get()),
                on_exit=self._parse_token(self.exit_token.get()),
            )
        # ValidationError (Pydantic) subclasses ValueError, but catch it
        # explicitly so a model-level constraint never escapes to crash the UI.
        except (ValidationError, ValueError) as exc:
            self._set_status(str(exc), error=True)
            return
        if binding.on_enter is None and binding.on_exit is None:
            self._set_status("Informe ao menos um token (Entrar ou Sair).", error=True)
            return

        if self._tree is not None and self._tree.exists(roi):
            self._tree.item(
                roi,
                values=(
                    roi,
                    "" if binding.on_enter is None else binding.on_enter,
                    "" if binding.on_exit is None else binding.on_exit,
                ),
            )
        elif self._tree is not None:
            self._tree.insert(
                "",
                "end",
                iid=roi,
                values=(
                    roi,
                    "" if binding.on_enter is None else binding.on_enter,
                    "" if binding.on_exit is None else binding.on_exit,
                ),
            )
        self._save()

    def _remove(self) -> None:
        if self._tree is None:
            return
        for iid in self._tree.selection():
            self._tree.delete(iid)
        self._save()

    def _clear(self) -> None:
        if self._tree is None:
            return
        self._tree.delete(*self._tree.get_children())
        self._save()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _save(self) -> None:
        cfg = self._collect_from_tree()
        project_data = self._project_data()
        project_data["arduino_bindings"] = cfg.to_storage()
        try:
            if getattr(self.project_manager, "project_path", None):
                self.project_manager.save_project()
                self._set_status("Configuração salva.", error=False)
            else:
                self._set_status("Configuração aplicada (projeto sem caminho em disco).")
        # except Exception justified: disk/serialization errors must not crash the UI.
        except Exception as exc:
            log.error("arduino_bindings_panel.save_failed", error=str(exc), exc_info=True)
            self._set_status(f"Erro ao salvar: {exc}", error=True)

    def _collect_from_tree(self) -> ArduinoBindingConfig:
        bindings: list[ArduinoBinding] = []
        if self._tree is not None:
            for iid in self._tree.get_children():
                roi, enter, exit_ = cast("tuple[Any, Any, Any]", self._tree.item(iid, "values"))
                bindings.append(
                    ArduinoBinding(
                        roi=str(roi),
                        on_enter=self._parse_token(enter),
                        on_exit=self._parse_token(exit_),
                    )
                )
        return ArduinoBindingConfig(bindings=bindings)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _project_data(self) -> dict[str, Any]:
        return getattr(self.project_manager, "project_data", {}) or {}

    def _project_roi_names(self) -> list[str]:
        try:
            zone_data = self.project_manager.get_zone_data()
        # except Exception justified: zone data may be unavailable early on.
        except Exception:
            return []
        names = list(getattr(zone_data, "roi_names", []) or [])
        return [str(n) for n in names if str(n).strip()]

    @staticmethod
    def _parse_token(value: Any) -> int | None:
        """Parse a token string into an int in ``[TOKEN_MIN, TOKEN_MAX]``.

        Returns None for empty input. Raises ``ValueError`` (surfaced by the
        caller as a friendly status message) for non-numeric or out-of-range
        values — a Spinbox accepts free text, so the bound is enforced here
        rather than relying on the widget or a later Pydantic error.
        """
        text = str(value).strip()
        if not text:
            return None
        try:
            token = int(text)
        except ValueError:
            raise ValueError(f"Token inválido: '{text}'. Use um número inteiro.") from None
        if not (TOKEN_MIN <= token <= TOKEN_MAX):
            raise ValueError(f"Token fora do intervalo [{TOKEN_MIN}, {TOKEN_MAX}]: {token}.")
        return token

    def _set_status(self, message: str, *, error: bool = False) -> None:
        if self._status is not None:
            self._status.config(text=message, foreground="red" if error else "green")
