"""
Tests for ExperimentalDesignStep (Phase 0 - Critical Fix).

Tests validation, data collection, and UI state management for
experimental design configuration in live projects.
"""

from tkinter import IntVar

import pytest

from zebtrack.ui.wizard.experimental_design_step import ExperimentalDesignStep

pytestmark = pytest.mark.gui  # All tests in this file are GUI tests


@pytest.fixture
def wizard_data():
    """Create wizard data dict."""
    return {"project_type": "live"}


@pytest.fixture
def step(tkinter_root, wizard_data):
    """Create ExperimentalDesignStep instance."""
    step = ExperimentalDesignStep(tkinter_root, wizard_data)
    step.build_ui()
    return step


def test_experimental_design_step_defaults(step):
    """Test default values are sensible."""
    data = step.get_data()

    assert data["num_groups"] == 2
    assert data["experiment_days"] == 1
    assert data["subjects_per_group"] == 1
    assert len(data["group_names"]) == 2
    assert data["group_names"] == ["Controle", "Tratamento 1"]


def test_experimental_design_validates_empty_group_name(step):
    """Test validation rejects empty group names."""
    # Set first group name to empty
    step.group_name_vars[0].set("")

    valid, msg = step.validate()

    assert not valid
    assert "empty" in msg.lower()
    # Message says "Group names cannot be empty" without specifying which one


def test_experimental_design_validates_duplicate_names(step):
    """Test validation rejects duplicate group names."""
    # Set both groups to same name
    step.group_name_vars[0].set("Grupo A")
    step.group_name_vars[1].set("Grupo A")

    valid, msg = step.validate()

    assert not valid
    assert "unique" in msg.lower() or "duplicate" in msg.lower()


def test_experimental_design_valid_configuration(step):
    """Test validation passes with valid configuration."""
    step.group_name_vars[0].set("Controle")
    step.group_name_vars[1].set("Tratamento")

    valid, msg = step.validate()

    assert valid
    assert msg == ""


def test_experimental_design_get_data_trims_names(step):
    """Test get_data() trims whitespace from group names."""
    step.group_name_vars[0].set("  Controle  ")
    step.group_name_vars[1].set("Tratamento   ")

    data = step.get_data()

    assert data["group_names"] == ["Controle", "Tratamento"]


def test_experimental_design_adjusts_to_group_count(step):
    """Test that changing num_groups rebuilds name entries."""
    # Start with 2 groups
    assert len(step.group_name_vars) == 2

    # Change to 4 groups
    step.num_groups_var.set(4)
    step._on_num_groups_change()

    # Should now have 4 entry fields
    assert len(step.group_name_vars) == 4
    assert len(step.group_name_entries) == 4

    # Get data should return 4 names
    data = step.get_data()
    assert len(data["group_names"]) == 4


def test_experimental_design_set_data_restores_state(step):
    """Test set_data() restores UI state correctly."""
    restore_data = {
        "experiment_days": 7,
        "num_groups": 3,
        "subjects_per_group": 5,
        "group_names": ["Controle", "CBD 10mg", "CBD 20mg"],
    }

    step.set_data(restore_data)

    # Verify variables updated
    assert step.num_days_var.get() == 7
    assert step.num_groups_var.get() == 3
    assert step.subjects_per_group_var.get() == 5

    # Verify group names restored
    assert len(step.group_name_vars) == 3
    assert step.group_name_vars[0].get() == "Controle"
    assert step.group_name_vars[1].get() == "CBD 10mg"
    assert step.group_name_vars[2].get() == "CBD 20mg"


def test_experimental_design_summary_updates(step):
    """Test summary label updates when values change."""
    step.num_groups_var.set(2)
    step.num_days_var.set(5)
    step.subjects_per_group_var.set(3)
    step._update_summary()

    summary = step.summary_var.get()

    # Should calculate: 2 groups x 5 days x 3 subjects = 30 sessions
    assert "30" in summary  # Total sessions
    assert "6" in summary  # Total animals (2 x 3)
    assert "5" in summary  # Days


def test_experimental_design_preserves_existing_names_on_rebuild(step, wizard_data):
    """Test that rebuilding entries preserves existing custom names."""
    # Set custom names
    step.group_name_vars[0].set("My Control")
    step.group_name_vars[1].set("My Treatment")

    # Store in wizard_data as would happen in real wizard
    wizard_data["group_names"] = ["My Control", "My Treatment"]

    # Rebuild (simulating group count change)
    step._rebuild_group_name_entries()

    # Names should be preserved
    assert step.group_name_vars[0].get() == "My Control"
    assert step.group_name_vars[1].get() == "My Treatment"


def test_experimental_design_validation_trims_before_checking(step):
    """Test that validation trims names before checking duplicates."""
    # Set names with whitespace that are the same after trimming
    step.group_name_vars[0].set("  Grupo A  ")
    step.group_name_vars[1].set("Grupo A")

    valid, msg = step.validate()

    # Should detect as duplicates after trimming
    assert not valid
    assert "unique" in msg.lower()

    # And should have trimmed the values
    assert step.group_name_vars[0].get() == "Grupo A"
    assert step.group_name_vars[1].get() == "Grupo A"


def test_experimental_design_only_validates_active_groups(step):
    """Test that validation only checks active group count."""
    # Set to 2 groups
    step.num_groups_var.set(2)
    step._rebuild_group_name_entries()

    # Set first 2 names to valid
    step.group_name_vars[0].set("Grupo 1")
    step.group_name_vars[1].set("Grupo 2")

    valid, _msg = step.validate()

    # Should be valid even though there might be more entries
    assert valid


def test_experimental_design_step_id_set_correctly(step):
    """Test that step_id is set to EXPERIMENTAL_DESIGN."""
    from zebtrack.ui.wizard.enums import WizardStepID

    assert step.step_id == WizardStepID.EXPERIMENTAL_DESIGN


class TestNumericFieldEditing:
    """Editar um campo numérico não pode gerar erro nem gravar outro número.

    Os três campos usam ``NumberInput``. Enquanto o ``Entry`` estava ligado
    direto ao ``IntVar``, apagar o conteúdo para digitar outro valor:

    1. levantava ``TclError`` dentro dos traces do passo (que rodam ANTES do
       validador do widget, porque o Tcl dispara traces em ordem inversa de
       criação), abrindo um diálogo "Erro Inesperado" no meio da digitação; e
    2. repunha o mínimo no campo com o cursor em 0, de modo que a próxima tecla
       era ANEXADA — quem queria 5 dias terminava com 51, limitado a 30.

    Nenhum teste cobria a edição do campo; todos partiam de ``var.set(n)``.
    """

    @staticmethod
    def _errors_from(widget):
        """Coleta o que iria para o diálogo "Erro Inesperado" da rede do Tk.

        O gancho precisa ser instalado em ``_root()``, a instância ``Tk``, e não
        no ``Toplevel`` que a fixture entrega: ``CallWrapper`` resolve
        ``report_callback_exception`` sempre pela raiz. Instalado no Toplevel ele
        nunca é consultado, e o teste vira uma tautologia que passa mesmo com o
        bug presente — foi o que aconteceu na primeira versão deste arquivo.
        """
        captured: list[str] = []
        root = widget._root()
        original = getattr(root, "report_callback_exception", None)
        root.report_callback_exception = lambda exc_type, exc, tb: captured.append(
            exc_type.__name__
        )
        # Devolvido junto para o teste poder restaurar; a raiz é de sessão e
        # deixar o gancho instalado vazaria para os testes seguintes.
        return captured, root, original

    def test_clearing_the_field_raises_nothing(self, step, tkinter_root):
        errors, root, original = self._errors_from(step.days_input)
        try:
            step.days_input.entry.delete(0, "end")
            tkinter_root.update_idletasks()
        finally:
            root.report_callback_exception = original

        assert errors == [], f"apagar o campo disparou {errors}"

    def test_typing_letters_raises_nothing(self, step, tkinter_root):
        errors, root, original = self._errors_from(step.groups_input)
        try:
            step.groups_input.entry.delete(0, "end")
            step.groups_input.entry.insert(0, "ab")
            tkinter_root.update_idletasks()
        finally:
            root.report_callback_exception = original

        assert errors == [], f"digitar letras disparou {errors}"

    def test_the_error_hook_is_actually_installed(self, step):
        """Guarda contra a tautologia: o gancho precisa mesmo disparar.

        Sem isto, instalar ``report_callback_exception`` no widget errado faz
        os dois testes acima passarem sempre, com bug ou sem bug.
        """
        errors, root, original = self._errors_from(step.days_input)
        try:
            probe = IntVar(master=step.days_input, value=1)
            probe.trace_add("write", lambda *_: probe.get())
            # ``IntVar.set`` é tipado como int; escrever texto é exatamente o
            # que o Tk permite ao usuário e o que precisamos simular aqui.
            probe.set("nao numerico")  # type: ignore[arg-type]
            step.days_input.update_idletasks()
        finally:
            root.report_callback_exception = original

        assert errors, "o gancho de exceção do Tk não foi instalado onde é lido"

    def test_replacing_one_by_five_stores_five_not_thirty(self, step, tkinter_root):
        """A regressão exata: 1 -> (apagar) -> 5 precisa virar 5."""
        assert step.num_days_var.get() == 1

        step.days_input.entry.delete(0, "end")
        assert step.days_input.entry.get() == "", (
            "o campo não pode se re-preencher sozinho no meio da digitação"
        )

        step.days_input.entry.insert(0, "5")
        step.days_input.commit()

        assert step.num_days_var.get() == 5
        assert step.get_data()["experiment_days"] == 5

    def test_unreadable_text_keeps_the_last_valid_value(self, step):
        step.num_days_var.set(7)

        step.days_input.entry.delete(0, "end")
        step.days_input.entry.insert(0, "sete")
        step.days_input.commit()

        assert step.num_days_var.get() == 7, "texto ilegível não pode alterar o valor"
        assert step.days_input.entry.get() == "7", "o campo volta a exibir o valor válido"

    def test_value_above_maximum_is_clamped_on_commit(self, step):
        step.days_input.entry.delete(0, "end")
        step.days_input.entry.insert(0, "999")
        step.days_input.commit()

        assert step.num_days_var.get() == 30

    def test_value_below_minimum_is_clamped_on_commit(self, step):
        step.groups_input.entry.delete(0, "end")
        step.groups_input.entry.insert(0, "0")
        step.groups_input.commit()

        assert step.num_groups_var.get() == 1

    def test_get_data_commits_pending_text_without_focus_out(self, step):
        """ "Avançar" pode não disparar ``<FocusOut>``; o valor não pode se perder."""
        step.subjects_input.entry.delete(0, "end")
        step.subjects_input.entry.insert(0, "12")

        assert step.get_data()["subjects_per_group"] == 12

    def test_validate_commits_pending_text(self, step):
        step.days_input.entry.delete(0, "end")
        step.days_input.entry.insert(0, "9")

        step.validate()

        assert step.num_days_var.get() == 9

    def test_programmatic_set_still_updates_the_entry(self, step):
        """``set_data``/``on_show`` escrevem no IntVar; o campo precisa seguir."""
        step.set_data({"experiment_days": 4, "num_groups": 3, "subjects_per_group": 2})

        assert step.days_input.entry.get() == "4"
        assert step.groups_input.entry.get() == "3"
        assert step.subjects_input.entry.get() == "2"

    def test_plus_button_commits_typed_text_before_stepping(self, step):
        """Digitar 10 e clicar em + precisa dar 11, não 2."""
        step.days_input.entry.delete(0, "end")
        step.days_input.entry.insert(0, "10")

        step.days_input._increase()

        assert step.num_days_var.get() == 11

    def test_minus_button_stops_at_the_minimum(self, step):
        step.num_groups_var.set(1)

        step.groups_input._decrease()

        assert step.num_groups_var.get() == 1
