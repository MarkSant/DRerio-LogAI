"""Extended unit tests for BlockDetailDialog in ui/dialogs/block_detail_dialog.py."""

from __future__ import annotations

from zebtrack.ui.dialogs.block_detail_dialog import _block_label


class TestBlockDetailDialogExtended:
    """Test block label formatting and helpers."""

    def test_block_label_formatting(self):
        label = _block_label(1, "Controle")
        assert "1" in label
        assert "Controle" in label

    def test_block_label_with_string_day(self):
        label = _block_label("Dia_2", "Tratamento")
        assert "2" in label
        assert "Tratamento" in label
