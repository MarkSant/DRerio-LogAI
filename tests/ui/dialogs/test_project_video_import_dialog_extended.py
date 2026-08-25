"""Extended unit tests for ui/dialogs/project_video_import_dialog.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.dialogs.project_video_import_dialog import (
    SubjectEntriesDialog,
    VideoMetadataDialog,
    _parse_day,
)


class TestProjectVideoImportDialogExtended:
    def test_coerce_day(self):
        assert SubjectEntriesDialog._coerce_day(5, fallback=1) == 5
        assert SubjectEntriesDialog._coerce_day("3", fallback=1) == 3
        assert SubjectEntriesDialog._coerce_day(0, fallback=2) == 2
        assert SubjectEntriesDialog._coerce_day(-1, fallback=2) == 2
        assert SubjectEntriesDialog._coerce_day("invalid", fallback=1) == 1
        assert SubjectEntriesDialog._coerce_day(None, fallback=4) == 4

    def test_subject_entries_dialog_apply(self):
        dialog = object.__new__(SubjectEntriesDialog)
        mock_g1 = MagicMock()
        mock_g1.get.return_value = "Control"
        mock_d1 = MagicMock()
        mock_d1.get.return_value = 1
        mock_s1 = MagicMock()
        mock_s1.get.return_value = "Animal_1"

        dialog._rows = [(mock_g1, mock_d1, mock_s1)]
        dialog.apply()

        assert dialog.result is not None
        assert len(dialog.result) == 1
        assert dialog.result[0] == {
            "group": "Control",
            "day": 1,
            "subject": "Animal_1",
        }

    def test_video_metadata_dialog_apply_single(self):
        dialog = object.__new__(VideoMetadataDialog)
        dialog.group_var = MagicMock()
        dialog.group_var.get.return_value = "Treated"
        dialog.day_var = MagicMock()
        dialog.day_var.get.return_value = 2
        dialog.subject_var = MagicMock()
        dialog.subject_var.get.return_value = "Sub_A"
        dialog.subject_entries = []

        dialog.apply()
        assert dialog.result is not None
        assert dialog.result["group"] == "Treated"
        assert dialog.result["day"] == 2
        assert dialog.result["subject"] == "Sub_A"

    def test_video_metadata_dialog_apply_multiple_entries(self):
        dialog = object.__new__(VideoMetadataDialog)
        dialog.group_var = MagicMock()
        dialog.group_var.get.return_value = "Treated"
        dialog.day_var = MagicMock()
        dialog.day_var.get.return_value = 2
        dialog.subject_entries = [
            {"group": "Treated", "day": 2, "subject": "Sub_1"},
            {"group": "Treated", "day": 2, "subject": "Sub_2"},
        ]

        dialog.apply()
        assert dialog.result is not None
        assert "subject_entries" in dialog.result
        assert len(dialog.result["subject_entries"]) == 2


class TestProjectVideoImportDialogExtended6:
    def test_coerce_day_valid_positive_integer(self):
        assert SubjectEntriesDialog._coerce_day(5, fallback=1) == 5
        assert SubjectEntriesDialog._coerce_day("10", fallback=1) == 10

    def test_coerce_day_zero_or_negative(self):
        assert SubjectEntriesDialog._coerce_day(0, fallback=3) == 3
        assert SubjectEntriesDialog._coerce_day(-5, fallback=2) == 2

    def test_coerce_day_invalid_types(self):
        assert SubjectEntriesDialog._coerce_day(None, fallback=1) == 1
        assert SubjectEntriesDialog._coerce_day("invalid", fallback=4) == 4
        assert SubjectEntriesDialog._coerce_day([], fallback=2) == 2

    def test_coerce_day_large_value(self):
        assert SubjectEntriesDialog._coerce_day("365", fallback=1) == 365


class TestProjectVideoImportDialogExtended7:
    def test_coerce_day_float_string(self):
        # int("12.5") raises ValueError, should return fallback
        assert SubjectEntriesDialog._coerce_day("12.5", fallback=5) == 5

    def test_coerce_day_whitespace_string(self):
        assert SubjectEntriesDialog._coerce_day("  ", fallback=1) == 1

    def test_coerce_day_string_with_leading_zeros(self):
        assert SubjectEntriesDialog._coerce_day("007", fallback=1) == 7


class TestParseDay:
    """``_parse_day`` é a única leitura do campo "Dia" deste módulo.

    Os cinco campos de dia são ``ttk.Spinbox`` editáveis. Presos a um
    ``IntVar``, ``get()`` levantava ``TclError`` sobre texto — e ``TclError``
    não é ``ValueError``, então os ``except (TypeError, ValueError)`` de todos
    os ``validate()`` daqui passavam direto. O operador recebia "Erro
    Inesperado" no lugar de "Informe um dia válido".
    """

    def test_accepts_positive_integers(self):
        assert _parse_day("5") == 5
        assert _parse_day(5) == 5
        assert _parse_day("  12  ") == 12

    def test_rejects_non_numeric_text(self):
        assert _parse_day("x") is None
        assert _parse_day("dois") is None
        assert _parse_day("1.5") is None

    def test_rejects_floats_instead_of_truncating(self):
        """``int(5.9)`` daria 5 em silêncio; o dia 5.9 não existe, é erro.

        É por isto que o parser converte via ``str(value)``: um float chega
        aqui quando algo a montante já corrompeu o dado, e truncar esconderia
        essa corrupção atrás de um número plausível.
        """
        assert _parse_day(5.9) is None
        assert _parse_day(0.5) is None

    def test_rejects_empty_and_none(self):
        assert _parse_day("") is None
        assert _parse_day("   ") is None
        assert _parse_day(None) is None

    def test_rejects_zero_and_negative(self):
        """Dia 0 e dia negativo não existem no domínio — ``Dia_0`` não é pasta."""
        assert _parse_day("0") is None
        assert _parse_day("-3") is None

    def test_never_raises_for_any_input(self):
        """A garantia central: falha vira valor de retorno, nunca exceção."""
        for value in ("", "x", None, "0", "-1", [], {}, object(), "1e3", "٣"):
            assert _parse_day(value) is None or isinstance(_parse_day(value), int)


class TestDayFieldsAreTextNotInt:
    """As variáveis de dia precisam ser ``StringVar``, não ``IntVar``.

    Não é preferência de estilo: ``IntVar.get()`` sobre um ``Spinbox`` editável
    levanta ``TclError``, e é isso que os guardas deste arquivo não capturam.
    Este teste falha se alguém reverter o tipo.
    """

    def test_subject_entries_rows_hold_string_vars(self, tkinter_root):
        from tkinter import StringVar

        dialog = object.__new__(SubjectEntriesDialog)
        dialog.available_groups = ["G01"]
        dialog.subject_entry_count = 2
        dialog.initial_entries = []
        dialog.default_group = "G01"
        dialog.default_day = 1
        dialog._rows = []

        dialog.body(tkinter_root)

        assert dialog._rows, "body() precisa criar as linhas"
        for _group_var, day_var, _subject_var in dialog._rows:
            assert isinstance(day_var, StringVar), (
                "campo Dia voltou a ser IntVar: TclError escapa dos validate()"
            )


class TestValidateRejectsUnreadableDay:
    """``validate()`` precisa recusar com a mensagem própria, sem levantar."""

    @staticmethod
    def _subject_dialog(day_text):
        from tkinter import StringVar

        dialog = object.__new__(SubjectEntriesDialog)
        group = StringVar(value="G01")
        day = StringVar(value=day_text)
        subject = StringVar(value="S01")
        dialog._rows = [(group, day, subject)]
        return dialog

    def test_text_in_day_is_rejected_not_raised(self, tkinter_root, monkeypatch):
        shown: list[tuple] = []
        monkeypatch.setattr(
            "zebtrack.ui.dialogs.project_video_import_dialog.messagebox.showerror",
            lambda *args, **kwargs: shown.append(args),
        )
        dialog = self._subject_dialog("nao-e-numero")

        result = dialog.validate()

        assert result == 0
        assert shown, "precisa mostrar a mensagem específica de dia inválido"

    def test_empty_day_is_rejected(self, tkinter_root, monkeypatch):
        shown: list[tuple] = []
        monkeypatch.setattr(
            "zebtrack.ui.dialogs.project_video_import_dialog.messagebox.showerror",
            lambda *args, **kwargs: shown.append(args),
        )
        dialog = self._subject_dialog("")

        assert dialog.validate() == 0
        assert shown

    def test_valid_day_passes(self, tkinter_root):
        dialog = self._subject_dialog("3")

        assert dialog.validate() == 1

    def test_apply_after_valid_validate_yields_the_typed_day(self, tkinter_root):
        dialog = self._subject_dialog("3")
        dialog.validate()
        dialog.apply()

        assert dialog.result == [{"group": "G01", "day": 3, "subject": "S01"}]


class TestLateValidationDialogs:
    """Validação precisa morar em ``validate()``, não em ``apply()``.

    ``Dialog.ok()`` do Tkinter chama ``apply()`` DEPOIS do ``withdraw()`` e
    sempre dentro de ``try/finally: self.cancel()``. Uma checagem em ``apply()``
    mostra a mensagem e a janela fecha assim mesmo. Só ``validate()`` mantém o
    diálogo aberto.
    """

    def test_template_dialog_rejects_text_instead_of_closing(self, tkinter_root, monkeypatch):
        from tkinter import StringVar

        from zebtrack.ui.dialogs.template_dialog import TemplateDialog

        shown: list = []
        monkeypatch.setattr(
            "zebtrack.ui.dialogs.template_dialog.messagebox.showerror",
            lambda *a, **k: shown.append(a),
        )

        dialog = object.__new__(TemplateDialog)
        dialog.template_type = StringVar(master=tkinter_root, value="vertical")
        dialog.num_lanes = StringVar(master=tkinter_root, value="três")
        dialog.num_rows = StringVar(master=tkinter_root, value="2")
        dialog.num_cols = StringVar(master=tkinter_root, value="2")

        assert dialog.validate() is False
        assert shown, "entrada inválida precisa avisar, não virar cancelamento mudo"

    def test_template_dialog_rejects_zero_lanes(self, tkinter_root, monkeypatch):
        """Zero convertia, ``range(0)`` não iterava, e nada era criado."""
        from tkinter import StringVar

        from zebtrack.ui.dialogs.template_dialog import TemplateDialog

        monkeypatch.setattr(
            "zebtrack.ui.dialogs.template_dialog.messagebox.showerror",
            lambda *a, **k: None,
        )
        dialog = object.__new__(TemplateDialog)
        dialog.template_type = StringVar(master=tkinter_root, value="vertical")
        dialog.num_lanes = StringVar(master=tkinter_root, value="0")
        dialog.num_rows = StringVar(master=tkinter_root, value="2")
        dialog.num_cols = StringVar(master=tkinter_root, value="2")

        assert dialog.validate() is False

    def test_template_dialog_ignores_fields_irrelevant_to_the_type(self, tkinter_root):
        """Criar faixas verticais não pode exigir "linhas" preenchido."""
        from tkinter import StringVar

        from zebtrack.ui.dialogs.template_dialog import TemplateDialog

        dialog = object.__new__(TemplateDialog)
        dialog.template_type = StringVar(master=tkinter_root, value="vertical")
        dialog.num_lanes = StringVar(master=tkinter_root, value="4")
        dialog.num_rows = StringVar(master=tkinter_root, value="")
        dialog.num_cols = StringVar(master=tkinter_root, value="lixo")

        assert dialog.validate() is True

        dialog.apply()
        result = dialog.result
        assert result is not None
        assert result["lanes"] == 4
        assert result["rows"] == 2, "campo irrelevante cai no padrão, não estoura"

    def test_template_dialog_grid_checks_rows_and_cols(self, tkinter_root, monkeypatch):
        from tkinter import StringVar

        from zebtrack.ui.dialogs.template_dialog import TemplateDialog

        monkeypatch.setattr(
            "zebtrack.ui.dialogs.template_dialog.messagebox.showerror",
            lambda *a, **k: None,
        )
        dialog = object.__new__(TemplateDialog)
        dialog.template_type = StringVar(master=tkinter_root, value="grid")
        dialog.num_lanes = StringVar(master=tkinter_root, value="lixo")
        dialog.num_rows = StringVar(master=tkinter_root, value="0")
        dialog.num_cols = StringVar(master=tkinter_root, value="2")

        assert dialog.validate() is False

    def test_center_periphery_rejects_text(self, tkinter_root, monkeypatch):
        from tkinter import StringVar

        from zebtrack.ui.dialogs.center_periphery_dialog import CenterPeripheryDialog

        shown: list = []
        monkeypatch.setattr(
            "zebtrack.ui.dialogs.center_periphery_dialog.messagebox.showerror",
            lambda *a, **k: shown.append(a),
        )
        dialog = object.__new__(CenterPeripheryDialog)
        dialog.method = StringVar(master=tkinter_root, value="distance")
        dialog.value = StringVar(master=tkinter_root, value="cinco")

        assert dialog.validate() is False
        assert shown

    def test_center_periphery_rejects_zero(self, tkinter_root, monkeypatch):
        from tkinter import StringVar

        from zebtrack.ui.dialogs.center_periphery_dialog import CenterPeripheryDialog

        monkeypatch.setattr(
            "zebtrack.ui.dialogs.center_periphery_dialog.messagebox.showerror",
            lambda *a, **k: None,
        )
        dialog = object.__new__(CenterPeripheryDialog)
        dialog.method = StringVar(master=tkinter_root, value="distance")
        dialog.value = StringVar(master=tkinter_root, value="0")

        assert dialog.validate() is False

    def test_center_periphery_valid_value_passes_and_applies(self, tkinter_root):
        from tkinter import StringVar

        from zebtrack.ui.dialogs.center_periphery_dialog import CenterPeripheryDialog

        dialog = object.__new__(CenterPeripheryDialog)
        dialog.method = StringVar(master=tkinter_root, value="distance")
        dialog.value = StringVar(master=tkinter_root, value="5.0")

        assert dialog.validate() is True
        dialog.apply()
        assert dialog.result == {"method": "distance", "value": 5.0}

    def test_design_editor_blocks_close_via_validate_not_apply(self, tkinter_root, monkeypatch):
        """Sem grupos, ``validate()`` precisa devolver False — ``apply()`` não barra."""
        from zebtrack.ui.wizard.design_editor_dialog import DesignEditorDialog

        monkeypatch.setattr(
            "zebtrack.ui.wizard.design_editor_dialog.messagebox.showerror",
            lambda *a, **k: None,
        )
        dialog = object.__new__(DesignEditorDialog)
        dialog.groups = []

        assert dialog.validate() is False

    def test_design_editor_allows_close_with_groups(self, tkinter_root):
        from zebtrack.ui.wizard.design_editor_dialog import DesignEditorDialog

        dialog = object.__new__(DesignEditorDialog)
        dialog.groups = ["G01"]

        assert dialog.validate() is True
