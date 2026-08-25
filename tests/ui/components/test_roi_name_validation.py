"""O nome da ROI é chave de dado no relatório, não rótulo.

Ele vira a coluna ``in_<nome>_stable`` no DataFrame da análise e a chave dos
dicionários de métricas em ``analysis/roi.py``. Dois nomes iguais produzem a
mesma coluna e a mesma chave: a segunda ROI sobrescreve a primeira e uma das
duas **desaparece do relatório**, sem aviso — o polígono continua desenhado na
tela, então nada indica a perda até o relatório agregado.

Antes desta validação, o único filtro nos pontos de entrada era
``if not roi_name``, que deixa passar ``"   "`` (verdadeiro em Python) e não
olha duplicatas.
"""

from __future__ import annotations

import pytest

from zebtrack.ui.components.roi_name_validation import (
    RoiNameError,
    normalize_roi_name,
    validate_roi_name,
)


class TestNormalize:
    def test_trims_both_ends(self):
        assert normalize_roi_name("  Centro  ") == "Centro"

    def test_none_becomes_empty(self):
        assert normalize_roi_name(None) == ""

    def test_inner_spaces_are_preserved(self):
        """ "Zona A" é um nome legítimo; só as pontas são aparadas."""
        assert normalize_roi_name(" Zona A ") == "Zona A"


class TestEmptyNames:
    def test_empty_string_is_rejected(self):
        with pytest.raises(RoiNameError):
            validate_roi_name("", [])

    def test_whitespace_only_is_rejected(self):
        """``if not roi_name`` deixava este passar: "   " é verdadeiro."""
        with pytest.raises(RoiNameError):
            validate_roi_name("   ", [])

    def test_none_is_rejected(self):
        with pytest.raises(RoiNameError):
            validate_roi_name(None, [])


class TestDuplicates:
    def test_exact_duplicate_is_rejected(self):
        with pytest.raises(RoiNameError):
            validate_roi_name("Centro", ["Centro", "Periferia"])

    def test_duplicate_after_trimming_is_rejected(self):
        """ "  Centro " e "Centro" geram a MESMA coluna no DataFrame."""
        with pytest.raises(RoiNameError):
            validate_roi_name("  Centro ", ["Centro"])

    def test_existing_name_with_spaces_still_collides(self):
        with pytest.raises(RoiNameError):
            validate_roi_name("Centro", ["  Centro  "])

    def test_message_names_the_offending_roi(self):
        with pytest.raises(RoiNameError) as excinfo:
            validate_roi_name("Centro", ["Centro"])
        assert "Centro" in str(excinfo.value)

    def test_different_name_passes(self):
        assert validate_roi_name("Periferia", ["Centro"]) == "Periferia"

    def test_case_difference_is_allowed(self):
        """Não normalizamos maiúsculas: "centro" e "Centro" são colunas distintas.

        Fixado como decisão, não como omissão — o pandas trata as duas como
        colunas diferentes, então recusar aqui seria mais restritivo que o
        formato de saída.
        """
        assert validate_roi_name("centro", ["Centro"]) == "centro"


class TestRename:
    def test_keeping_its_own_name_is_not_a_collision(self):
        assert validate_roi_name("Centro", ["Centro", "Periferia"], current_name="Centro") == (
            "Centro"
        )

    def test_renaming_onto_another_roi_is_rejected(self):
        with pytest.raises(RoiNameError):
            validate_roi_name("Periferia", ["Centro", "Periferia"], current_name="Centro")

    def test_renaming_to_a_free_name_passes(self):
        assert validate_roi_name("Zona 3", ["Centro", "Periferia"], current_name="Centro") == (
            "Zona 3"
        )

    def test_current_name_is_compared_after_trimming(self):
        assert validate_roi_name("Centro", ["  Centro  "], current_name="Centro") == "Centro"


class TestReturnValue:
    def test_returns_the_normalized_name_to_be_stored(self):
        """O chamador precisa gravar o nome APARADO, não o texto cru."""
        assert validate_roi_name("  Zona 1  ", []) == "Zona 1"

    def test_error_is_a_value_error_subclass(self):
        """Call sites que já capturam ``ValueError`` continuam funcionando."""
        assert issubclass(RoiNameError, ValueError)
