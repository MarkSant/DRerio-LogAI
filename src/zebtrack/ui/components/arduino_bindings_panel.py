"""Project-scoped editor for per-zone Arduino commands (live projects).

A point-and-click table mapping each ROI to the integer the application sends
to the Arduino when an animal **enters** and **leaves** that ROI. DRerio LogAI
only transports the number — what the firmware does with it (light an LED, fire
a relay, deliver a stimulus) lives entirely in the Arduino sketch.

The only typed value is the short integer token; ROI and edge are chosen from
controls. Persisted in ``project_data["arduino_bindings"]``.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from tkinter import StringVar, ttk
from typing import Any, cast

import structlog
from pydantic import ValidationError

from zebtrack.core.services.arduino_ack_semantics import edge_ack_is_inverted
from zebtrack.core.services.arduino_bindings import (
    ArduinoBinding,
    ArduinoBindingConfig,
)

log = structlog.get_logger()

DISCLAIMER = (
    "O DRerio apenas ENVIA o número que você escolher quando o animal entra ou "
    "sai da ROI. O que o número aciona (LED, choque, flash, bomba, qualquer "
    "módulo) é responsabilidade do SEU sketch Arduino — usar Arduino pressupõe "
    "que você saiba programá-lo. O sketch de referência usa pares consecutivos: "
    "1=canal 1 liga, 2=desliga, 3/4=canal 2, 5/6=canal 3, 7/8=canal 4. "
    "Use 'Dispositivo' para registrar o que está de fato ligado em cada canal."
)

NOTE_NO_ARDUINO = (
    "Arduino não está habilitado neste projeto. Ative 'Usar Arduino' ao criar o "
    "projeto (assistente, etapa de configuração ao vivo) para configurar comandos "
    "por zona."
)

CONFLICT_WARNING = (
    "⚠ Token ambíguo: o mesmo número está configurado como ENTRADA de uma ROI e "
    "SAÍDA de outra. O sketch não consegue ligar e desligar com o mesmo comando — "
    "a saída da ROI vai acender o dispositivo da outra zona, e o desligamento no "
    "fim da sessão não vai funcionar. Confira a numeração —"
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
        self.device_label = StringVar(master=self)

        self._tree: ttk.Treeview | None = None
        self._roi_combo: ttk.Combobox | None = None
        self._status: ttk.Label | None = None
        self._note: ttk.Label | None = None
        self._frame: ttk.LabelFrame | None = None
        self._conflict_label: ttk.Label | None = None
        self._test_button: ttk.Button | None = None
        self._test_output: ttk.Label | None = None

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

        cols = ("roi", "label", "enter", "exit")
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=4)
        tree.heading("roi", text="ROI")
        tree.heading("label", text="Dispositivo")
        tree.heading("enter", text="Ao Entrar")
        tree.heading("exit", text="Ao Sair")
        tree.column("roi", width=95, anchor="w")
        tree.column("label", width=115, anchor="w")
        tree.column("enter", width=70, anchor="center")
        tree.column("exit", width=70, anchor="center")
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

        label_row = ttk.Frame(frame)
        label_row.pack(fill="x", pady=(4, 0))
        ttk.Label(label_row, text="Dispositivo:").pack(side="left")
        ttk.Entry(label_row, textvariable=self.device_label, width=22).pack(
            side="left", padx=(2, 8)
        )
        ttk.Label(
            label_row,
            text="opcional — o que está ligado neste canal",
            foreground="gray",
        ).pack(side="left")

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text="Adicionar / Atualizar", command=self._add_or_update).pack(
            side="left"
        )
        ttk.Button(buttons, text="Remover", command=self._remove).pack(side="left", padx=4)
        ttk.Button(buttons, text="Limpar", command=self._clear).pack(side="left")
        ttk.Button(buttons, text="🔄 ROIs", command=self.refresh_roi_choices).pack(side="right")

        test_row = ttk.Frame(frame)
        test_row.pack(fill="x", pady=(6, 0))
        self._test_button = ttk.Button(
            test_row, text="🔌 Testar comandos", command=self.test_bindings
        )
        self._test_button.pack(side="left")
        ttk.Label(
            test_row,
            text="Envia cada token e mostra o que o firmware respondeu.",
            foreground="gray",
        ).pack(side="left", padx=(6, 0))

        self._test_output = ttk.Label(
            frame, text="", justify="left", wraplength=380, font=("TkFixedFont", 8)
        )

        self._status = ttk.Label(frame, text="", foreground="gray")
        self._status.pack(anchor="w", pady=(4, 0))

        # Packed on demand by _refresh_conflict_warning (hidden while clean).
        self._conflict_label = ttk.Label(
            frame, text="", foreground="red", wraplength=380, justify="left"
        )

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
        self._refresh_conflict_warning(cfg)
        for binding in cfg.bindings:
            self._tree.insert("", "end", iid=binding.roi, values=self._row_values(binding))

    @staticmethod
    def _row_values(binding: ArduinoBinding) -> tuple[str, str, str, str]:
        """Tree row for a binding — column order must match ``cols`` in _build."""
        return (
            binding.roi,
            binding.label or "",
            "" if binding.on_enter is None else str(binding.on_enter),
            "" if binding.on_exit is None else str(binding.on_exit),
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
        roi, label, enter, exit_ = cast(
            "tuple[Any, Any, Any, Any]", self._tree.item(selection[0], "values")
        )
        self.roi_choice.set(roi)
        self.device_label.set(str(label))
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
                label=self.device_label.get(),
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
            self._tree.item(roi, values=self._row_values(binding))
        elif self._tree is not None:
            self._tree.insert("", "end", iid=roi, values=self._row_values(binding))
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
        self._refresh_conflict_warning(cfg)

    # ------------------------------------------------------------------
    # Command test (pre-flight)
    # ------------------------------------------------------------------
    def test_bindings(self) -> None:
        """Send every configured token and report what the firmware answered.

        The application only transports integers, so a token bound to the wrong
        edge is invisible to it — the 2026-08-04 sessions lost two recordings to
        exactly that. The firmware's ACK line, however, says what the device did.
        Sending the tokens up front turns a post-mortem into a five-second check.

        Serial I/O runs on a worker thread; results are marshalled back with
        ``root.after(0, ...)`` (CLAUDE.md: Tk is touched only from its own thread).
        """
        manager = getattr(self.controller, "arduino_manager", None)
        if manager is None or not manager.is_connected():
            self._set_test_output("Arduino não conectado. Conecte antes de testar.", error=True)
            return

        probes = self._probe_plan()
        if not probes:
            self._set_test_output("Nenhum token configurado para testar.", error=True)
            return

        if self._test_button is not None:
            self._test_button.config(state="disabled")
        self._set_test_output("Testando… aguarde as respostas do firmware.")

        def _worker() -> None:
            try:
                answers = manager.probe_tokens([token for _roi, _edge, token in probes])
            # except Exception justified: serial/hardware boundary; the panel must
            # report the failure instead of dying on a worker thread.
            except Exception as exc:
                log.warning("arduino_bindings_panel.test_failed", error=str(exc))
                self._schedule_ui(self._finish_test, None, str(exc))
                return
            self._schedule_ui(self._finish_test, list(zip(probes, answers, strict=False)), None)

        threading.Thread(target=_worker, name="ArduinoBindingProbe", daemon=True).start()

    def _probe_plan(self) -> list[tuple[str, str, int]]:
        """Flatten the bindings into the ordered ``(display_name, edge, token)`` sends.

        ``display_name`` is a label for the result lines, **not** a ROI name: it
        becomes ``"Z1 (Choque)"`` when the operator named the device, and falls
        back to the bare ROI otherwise. Naming what is actually wired beats
        leaning on the firmware's ACK text, which names the channel from the
        sketch's point of view ("Red LED 1" even when the pin drives a relay).
        """
        cfg = ArduinoBindingConfig.from_project_data(self._project_data())
        plan: list[tuple[str, str, int]] = []
        for binding in cfg.bindings:
            display_name = f"{binding.roi} ({binding.label})" if binding.label else binding.roi
            if binding.on_enter is not None:
                plan.append((display_name, "enter", binding.on_enter))
            if binding.on_exit is not None:
                plan.append((display_name, "exit", binding.on_exit))
        return plan

    def _schedule_ui(self, func: Any, *args: Any) -> None:
        """Run ``func`` on the Tk main thread.

        The panel is itself a Tk widget, so ``self.after`` is always the right
        queue — no need to hunt for a root through the controller. There is
        deliberately **no** inline fallback: this is called from the probe worker
        thread, and running the callback here would touch widgets off the Tk
        thread (CLAUDE.md). If scheduling fails the widget is being torn down,
        so dropping the update is the correct outcome.
        """
        try:
            self.after(0, func, *args)
        # except Exception justified: ``after`` raises TclError once the widget
        # (or the interpreter) is gone — nothing left to update.
        except Exception:  # pragma: no cover - defensive
            log.debug("arduino_bindings_panel.schedule_ui.after_failed")

    def _finish_test(
        self,
        results: Sequence[tuple[tuple[str, str, int], tuple[int, str | None]]] | None,
        error: str | None,
    ) -> None:
        """Render the probe results (Tk thread).

        ``results`` pairs each :meth:`_probe_plan` entry with the manager's
        ``(token, ack_text)`` answer for it.
        """
        if self._test_button is not None:
            self._test_button.config(state="normal")
        if results is None:
            self._set_test_output(f"Falha ao testar: {error}", error=True)
            return

        lines: list[str] = []
        problems = 0
        for (display_name, edge, token), (_sent, ack) in results:
            edge_pt = "entrar" if edge == "enter" else "sair"
            if not ack:
                lines.append(f"{display_name} {edge_pt} → {token} → (sem resposta)")
                problems += 1
                continue
            if edge_ack_is_inverted(edge, ack):
                lines.append(f"⚠ {display_name} {edge_pt} → {token} → {ack}")
                problems += 1
            else:
                lines.append(f"✓ {display_name} {edge_pt} → {token} → {ack}")

        if problems:
            lines.append("")
            lines.append(
                f"{problems} problema(s): uma ENTRADA deve ligar e uma SAÍDA "
                "desligar. O sketch de referência pareia 1/2, 3/4, 5/6, 7/8."
            )
        self._set_test_output("\n".join(lines), error=bool(problems))

    def _set_test_output(self, message: str, *, error: bool = False) -> None:
        if self._test_output is None:
            return
        self._test_output.config(text=message, foreground="red" if error else "green")
        if not self._test_output.winfo_manager():
            self._test_output.pack(anchor="w", fill="x", pady=(4, 0))

    def _refresh_conflict_warning(self, cfg: ArduinoBindingConfig | None = None) -> None:
        """Show/hide the ambiguous-token warning for the current bindings.

        A token used as one ROI's "enter" and another's "exit" cannot mean the
        same thing to the firmware, and it makes the session-end sweep turn a
        device **on** instead of off. The panel cannot know what the sketch does
        with each integer, so it warns rather than rejecting the value.
        """
        if self._conflict_label is None:
            return
        if cfg is None:
            cfg = ArduinoBindingConfig.from_project_data(self._project_data())
        conflicts = cfg.token_conflicts()
        if not conflicts:
            self._conflict_label.pack_forget()
            return
        detail = "; ".join(c.describe() for c in conflicts)
        self._conflict_label.config(text=f"{CONFLICT_WARNING} {detail}.")
        self._conflict_label.pack(anchor="w", fill="x", pady=(4, 0))

    def _collect_from_tree(self) -> ArduinoBindingConfig:
        bindings: list[ArduinoBinding] = []
        if self._tree is not None:
            for iid in self._tree.get_children():
                roi, label, enter, exit_ = cast(
                    "tuple[Any, Any, Any, Any]", self._tree.item(iid, "values")
                )
                bindings.append(
                    ArduinoBinding(
                        roi=str(roi),
                        on_enter=self._parse_token(enter),
                        on_exit=self._parse_token(exit_),
                        label=str(label),
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
