"""Tests for TemplateDialog apply logic."""

from typing import Any, cast

from zebtrack.ui.dialogs.template_dialog import TemplateDialog


class _DummyVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


def _build_dialog(template_type="grid", lanes="3", rows="2", cols="4"):
    dialog = cast(Any, TemplateDialog.__new__(TemplateDialog))
    dialog.template_type = _DummyVar(template_type)
    dialog.num_lanes = _DummyVar(lanes)
    dialog.num_rows = _DummyVar(rows)
    dialog.num_cols = _DummyVar(cols)
    dialog.result = None
    return cast(TemplateDialog, dialog)


def test_apply_sets_result_for_valid_values():
    dialog = _build_dialog(template_type="horizontal", lanes="5", rows="3", cols="4")

    dialog.apply()

    assert dialog.result == {
        "type": "horizontal",
        "lanes": 5,
        "rows": 3,
        "cols": 4,
    }


def test_invalid_values_are_rejected_by_validate_not_swallowed_by_apply():
    """Entrada inválida precisa AVISAR, não virar um cancelamento mudo.

    ``apply()`` fazia ``self.result = None`` no ``except``. Quem chama testa
    ``if not dialog.result: return`` — a mesma condição de "o usuário
    cancelou" — então digitar "invalid" fechava o diálogo e não criava ROI
    nenhuma, sem mensagem. A checagem foi para ``validate()``, o único método
    que o Tkinter respeita para manter a janela aberta.
    """
    from unittest.mock import patch

    dialog = _build_dialog(template_type="vertical", lanes="invalid")

    with patch("zebtrack.ui.dialogs.template_dialog.messagebox.showerror") as showerror:
        assert dialog.validate() is False
        showerror.assert_called_once()


def test_validate_only_checks_the_fields_the_chosen_type_uses():
    """Criar faixas verticais não pode exigir "linhas"/"colunas" preenchidos."""
    from unittest.mock import patch

    dialog = _build_dialog(template_type="vertical", lanes="4", rows="", cols="lixo")

    with patch("zebtrack.ui.dialogs.template_dialog.messagebox.showerror") as showerror:
        assert dialog.validate() is True
        showerror.assert_not_called()

    dialog.apply()
    assert dialog.result["lanes"] == 4
    assert dialog.result["rows"] == 2, "campo irrelevante cai no padrão em vez de estourar"


def test_grid_type_checks_rows_and_columns():
    from unittest.mock import patch

    dialog = _build_dialog(template_type="grid", lanes="lixo", rows="0", cols="4")

    with patch("zebtrack.ui.dialogs.template_dialog.messagebox.showerror") as showerror:
        assert dialog.validate() is False
        showerror.assert_called_once()
