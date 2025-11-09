"""
Testes para Dialogs Batch 2 (Média Complexidade)

Testa 5 dialogs de média complexidade:
1. TemplateDialog
2. PendingVideosDialog
3. CenterPeripheryDialog
4. DiagnosticProgressDialog
5. MissingMetadataDialog
"""

from unittest.mock import Mock, patch

import pytest

from zebtrack.ui.dialogs import (
    CenterPeripheryDialog,
    DiagnosticProgressDialog,
    MissingMetadataDialog,
    PendingVideosDialog,
    TemplateDialog,
)


@pytest.mark.gui
class TestTemplateDialog:
    """Testes para TemplateDialog - criação de templates de ROI."""

    def test_init_with_defaults(self, tkinter_root):
        """Testa inicialização com valores padrão."""
        dialog = TemplateDialog(tkinter_root)
        dialog.withdraw()  # Não mostrar visualmente

        assert dialog.template_type.get() == "vertical"
        assert dialog.num_lanes.get() == "3"
        assert dialog.num_rows.get() == "2"
        assert dialog.num_cols.get() == "2"

        dialog.destroy()

    def test_body_creates_all_widgets(self, tkinter_root):
        """Testa que o body cria todos os widgets necessários."""
        dialog = TemplateDialog(tkinter_root)
        dialog.withdraw()

        # Verificar que variáveis foram criadas
        assert hasattr(dialog, 'template_type')
        assert hasattr(dialog, 'num_lanes')
        assert hasattr(dialog, 'num_rows')
        assert hasattr(dialog, 'num_cols')

        dialog.destroy()

    def test_apply_with_valid_vertical_input(self, tkinter_root):
        """Testa apply com entrada válida para faixas verticais."""
        dialog = TemplateDialog(tkinter_root)
        dialog.withdraw()

        dialog.template_type.set("vertical")
        dialog.num_lanes.set("5")
        dialog.num_rows.set("3")
        dialog.num_cols.set("4")

        dialog.apply()

        assert dialog.result == {
            "type": "vertical",
            "lanes": 5,
            "rows": 3,
            "cols": 4,
        }

        dialog.destroy()

    def test_apply_with_valid_horizontal_input(self, tkinter_root):
        """Testa apply com entrada válida para faixas horizontais."""
        dialog = TemplateDialog(tkinter_root)
        dialog.withdraw()

        dialog.template_type.set("horizontal")
        dialog.num_lanes.set("4")
        dialog.num_rows.set("2")
        dialog.num_cols.set("2")

        dialog.apply()

        assert dialog.result == {
            "type": "horizontal",
            "lanes": 4,
            "rows": 2,
            "cols": 2,
        }

        dialog.destroy()

    def test_apply_with_valid_grid_input(self, tkinter_root):
        """Testa apply com entrada válida para grade."""
        dialog = TemplateDialog(tkinter_root)
        dialog.withdraw()

        dialog.template_type.set("grid")
        dialog.num_lanes.set("6")
        dialog.num_rows.set("3")
        dialog.num_cols.set("3")

        dialog.apply()

        assert dialog.result == {
            "type": "grid",
            "lanes": 6,
            "rows": 3,
            "cols": 3,
        }

        dialog.destroy()

    def test_apply_with_invalid_numeric_input(self, tkinter_root):
        """Testa apply com entrada não-numérica (deve retornar None)."""
        dialog = TemplateDialog(tkinter_root)
        dialog.withdraw()

        dialog.template_type.set("vertical")
        dialog.num_lanes.set("abc")  # Inválido
        dialog.num_rows.set("2")
        dialog.num_cols.set("2")

        dialog.apply()

        assert dialog.result is None

        dialog.destroy()

    def test_apply_with_empty_input(self, tkinter_root):
        """Testa apply com entrada vazia (deve retornar None)."""
        dialog = TemplateDialog(tkinter_root)
        dialog.withdraw()

        dialog.template_type.set("grid")
        dialog.num_lanes.set("")  # Vazio
        dialog.num_rows.set("2")
        dialog.num_cols.set("2")

        dialog.apply()

        assert dialog.result is None

        dialog.destroy()


@pytest.mark.gui
class TestPendingVideosDialog:
    """Testes para PendingVideosDialog - revisão de vídeos pendentes."""

    def test_init_with_empty_lists(self, tkinter_root):
        """Testa inicialização com listas vazias."""
        mock_builder = Mock(return_value=[])

        dialog = PendingVideosDialog(
            tkinter_root,
            hierarchy_builder=mock_builder,
            ready_with_trajectory=[],
            ready_with_zones=[],
            arena_only=[],
            without_arena=[],
        )
        dialog.withdraw()

        assert dialog.ready_with_trajectory == []
        assert dialog.ready_with_zones == []
        assert dialog.arena_only == []
        assert dialog.without_arena == []
        assert dialog.result == {"confirmed": False, "include_arena_only": False}

        dialog.destroy()

    def test_init_with_videos(self, tkinter_root):
        """Testa inicialização com vídeos em diferentes estados."""
        mock_builder = Mock(return_value=[])

        ready_trajectory = [{"path": "/path/to/video1.mp4"}]
        ready_zones = [{"path": "/path/to/video2.mp4"}]
        arena = [{"path": "/path/to/video3.mp4"}]

        dialog = PendingVideosDialog(
            tkinter_root,
            hierarchy_builder=mock_builder,
            ready_with_trajectory=ready_trajectory,
            ready_with_zones=ready_zones,
            arena_only=arena,
            without_arena=[],
        )
        dialog.withdraw()

        assert len(dialog.ready_with_trajectory) == 1
        assert len(dialog.ready_with_zones) == 1
        assert len(dialog.arena_only) == 1

        dialog.destroy()

    def test_body_creates_treeview(self, tkinter_root):
        """Testa que o body cria a treeview corretamente."""
        mock_builder = Mock(return_value=[])

        dialog = PendingVideosDialog(
            tkinter_root,
            hierarchy_builder=mock_builder,
            ready_with_trajectory=[],
            ready_with_zones=[],
            arena_only=[],
            without_arena=[],
        )
        dialog.withdraw()

        assert hasattr(dialog, 'tree')
        assert dialog.tree.cget('columns') == ("status", "arquivo")

        dialog.destroy()

    def test_apply_sets_confirmed_true(self, tkinter_root):
        """Testa que apply seta confirmed=True."""
        mock_builder = Mock(return_value=[])

        dialog = PendingVideosDialog(
            tkinter_root,
            hierarchy_builder=mock_builder,
            ready_with_trajectory=[],
            ready_with_zones=[],
            arena_only=[],
            without_arena=[],
        )
        dialog.withdraw()

        dialog.apply()

        assert dialog.result["confirmed"] is True
        assert dialog.result["include_arena_only"] is False

        dialog.destroy()

    def test_apply_with_arena_only_checked(self, tkinter_root):
        """Testa apply com checkbox de arena_only marcado."""
        mock_builder = Mock(return_value=[])

        arena = [{"path": "/path/to/video.mp4"}]

        dialog = PendingVideosDialog(
            tkinter_root,
            hierarchy_builder=mock_builder,
            ready_with_trajectory=[],
            ready_with_zones=[],
            arena_only=arena,
            without_arena=[],
        )
        dialog.withdraw()

        dialog.include_arena_only_var.set(True)
        dialog.apply()

        assert dialog.result["confirmed"] is True
        assert dialog.result["include_arena_only"] is True

        dialog.destroy()

    def test_cancel_sets_confirmed_false(self, tkinter_root):
        """Testa que cancel seta confirmed=False."""
        mock_builder = Mock(return_value=[])

        dialog = PendingVideosDialog(
            tkinter_root,
            hierarchy_builder=mock_builder,
            ready_with_trajectory=[],
            ready_with_zones=[],
            arena_only=[],
            without_arena=[],
        )
        dialog.withdraw()

        # Simular cancel
        dialog.result = {"confirmed": True, "include_arena_only": True}
        dialog.cancel()

        assert dialog.result["confirmed"] is False
        assert dialog.result["include_arena_only"] is False

    def test_populate_tree_with_hierarchy(self, tkinter_root):
        """Testa população da tree com hierarquia."""
        hierarchy = [
            {
                "label": "Grupo A",
                "status_label": "3 vídeos",
                "filename_display": "",
                "children": [
                    {
                        "label": "Dia 1",
                        "status_label": "2 vídeos",
                        "children": [
                            {
                                "label": "Vídeo 1",
                                "status_label": "Pronto",
                                "filename": "video1.mp4",
                                "path": "/path/to/video1.mp4",
                            }
                        ],
                    }
                ],
            }
        ]

        mock_builder = Mock(return_value=hierarchy)
        ready_trajectory = [{"path": "/path/to/video1.mp4"}]

        dialog = PendingVideosDialog(
            tkinter_root,
            hierarchy_builder=mock_builder,
            ready_with_trajectory=ready_trajectory,
            ready_with_zones=[],
            arena_only=[],
            without_arena=[],
        )
        dialog.withdraw()

        # Verificar que a tree foi populada
        children = dialog.tree.get_children()
        assert len(children) > 0

        dialog.destroy()

    def test_tag_styles_configured(self, tkinter_root):
        """Testa que os estilos de tag foram configurados."""
        mock_builder = Mock(return_value=[])

        dialog = PendingVideosDialog(
            tkinter_root,
            hierarchy_builder=mock_builder,
            ready_with_trajectory=[],
            ready_with_zones=[],
            arena_only=[],
            without_arena=[],
        )
        dialog.withdraw()

        # Verificar que os estilos existem
        assert "ready_full" in PendingVideosDialog.TAG_STYLES
        assert "ready_partial" in PendingVideosDialog.TAG_STYLES
        assert "ready_missing" in PendingVideosDialog.TAG_STYLES

        dialog.destroy()


@pytest.mark.gui
class TestCenterPeripheryDialog:
    """Testes para CenterPeripheryDialog - configuração de análise center-periphery."""

    def test_init_with_defaults(self, tkinter_root):
        """Testa inicialização com valores padrão."""
        dialog = CenterPeripheryDialog(tkinter_root)
        dialog.withdraw()

        assert dialog.method.get() == "distance"
        assert dialog.value.get() == "5.0"

        dialog.destroy()

    def test_body_creates_widgets(self, tkinter_root):
        """Testa que o body cria todos os widgets."""
        dialog = CenterPeripheryDialog(tkinter_root)
        dialog.withdraw()

        assert hasattr(dialog, 'method')
        assert hasattr(dialog, 'value')

        dialog.destroy()

    def test_apply_with_distance_method(self, tkinter_root):
        """Testa apply com método distance."""
        dialog = CenterPeripheryDialog(tkinter_root)
        dialog.withdraw()

        dialog.method.set("distance")
        dialog.value.set("10.5")

        dialog.apply()

        assert dialog.result == {
            "method": "distance",
            "value": 10.5,
        }

        dialog.destroy()

    def test_apply_with_area_ratio_method(self, tkinter_root):
        """Testa apply com método area_ratio."""
        dialog = CenterPeripheryDialog(tkinter_root)
        dialog.withdraw()

        dialog.method.set("area_ratio")
        dialog.value.set("0.75")

        dialog.apply()

        assert dialog.result == {
            "method": "area_ratio",
            "value": 0.75,
        }

        dialog.destroy()

    def test_apply_with_invalid_value(self, tkinter_root):
        """Testa apply com valor inválido (deve retornar None)."""
        dialog = CenterPeripheryDialog(tkinter_root)
        dialog.withdraw()

        dialog.method.set("distance")
        dialog.value.set("abc")  # Inválido

        dialog.apply()

        assert dialog.result is None

        dialog.destroy()

    def test_apply_with_empty_value(self, tkinter_root):
        """Testa apply com valor vazio (deve retornar None)."""
        dialog = CenterPeripheryDialog(tkinter_root)
        dialog.withdraw()

        dialog.method.set("area_ratio")
        dialog.value.set("")  # Vazio

        dialog.apply()

        assert dialog.result is None

        dialog.destroy()

    def test_apply_with_negative_value(self, tkinter_root):
        """Testa apply com valor negativo (aceita, mas pode ser validado externamente)."""
        dialog = CenterPeripheryDialog(tkinter_root)
        dialog.withdraw()

        dialog.method.set("distance")
        dialog.value.set("-5.0")

        dialog.apply()

        # Dialog aceita valores negativos, validação é responsabilidade do chamador
        assert dialog.result == {
            "method": "distance",
            "value": -5.0,
        }

        dialog.destroy()


@pytest.mark.gui
class TestDiagnosticProgressDialog:
    """Testes para DiagnosticProgressDialog - progresso de diagnóstico."""

    def test_init_with_parent(self, tkinter_root):
        """Testa inicialização com parent."""
        dialog = DiagnosticProgressDialog(tkinter_root)

        assert dialog.user_cancelled is False
        assert dialog.progress_var.get() == "Iniciando..."
        assert dialog.status_var.get() == "Aguarde..."

        dialog.destroy()

    def test_init_with_custom_title(self, tkinter_root):
        """Testa inicialização com título customizado."""
        custom_title = "Teste de Diagnóstico"
        dialog = DiagnosticProgressDialog(tkinter_root, title=custom_title)

        assert dialog.title() == custom_title

        dialog.destroy()

    def test_update_progress_with_message_only(self, tkinter_root):
        """Testa update_progress com apenas mensagem."""
        dialog = DiagnosticProgressDialog(tkinter_root)

        dialog.update_progress("Processando frames...")

        assert dialog.progress_var.get() == "Processando frames..."
        assert dialog.status_var.get() == "Processando..."

        dialog.destroy()

    def test_update_progress_with_frame_count(self, tkinter_root):
        """Testa update_progress com contagem de frames."""
        dialog = DiagnosticProgressDialog(tkinter_root)

        dialog.update_progress("Detectando objetos", current=50, total=100)

        assert dialog.progress_var.get() == "Detectando objetos"
        assert "50/100" in dialog.status_var.get()
        assert "50%" in dialog.status_var.get()
        assert dialog.progress_bar["value"] == 50

        dialog.destroy()

    def test_update_progress_with_zero_total(self, tkinter_root):
        """Testa update_progress com total=0 (evita divisão por zero)."""
        dialog = DiagnosticProgressDialog(tkinter_root)

        dialog.update_progress("Iniciando", current=0, total=0)

        assert dialog.progress_var.get() == "Iniciando"
        assert dialog.status_var.get() == "Processando..."

        dialog.destroy()

    def test_update_progress_percentage_calculation(self, tkinter_root):
        """Testa cálculo de porcentagem em update_progress."""
        dialog = DiagnosticProgressDialog(tkinter_root)

        dialog.update_progress("Análise", current=33, total=100)

        assert dialog.progress_bar["value"] == 33

        dialog.destroy()

    def test_update_status(self, tkinter_root):
        """Testa update_status."""
        dialog = DiagnosticProgressDialog(tkinter_root)

        dialog.update_status("Carregando modelo...")

        assert dialog.status_var.get() == "Carregando modelo..."

        dialog.destroy()

    def test_cancel_sets_user_cancelled(self, tkinter_root):
        """Testa que cancel seta user_cancelled=True."""
        dialog = DiagnosticProgressDialog(tkinter_root)

        dialog.cancel()

        assert dialog.user_cancelled is True
        assert dialog.progress_var.get() == "Cancelando..."

        dialog.destroy()

    def test_cancel_with_event(self, tkinter_root):
        """Testa cancel com evento (Escape key)."""
        dialog = DiagnosticProgressDialog(tkinter_root)

        mock_event = Mock()
        dialog.cancel(event=mock_event)

        assert dialog.user_cancelled is True

        dialog.destroy()

    def test_finish_destroys_dialog(self, tkinter_root):
        """Testa que finish destrói o dialog."""
        dialog = DiagnosticProgressDialog(tkinter_root)

        # Não podemos testar destroy diretamente, mas podemos chamar finish
        # e verificar que não causa erros
        dialog.finish()

        # Dialog foi destruído, não podemos mais acessar suas propriedades


@pytest.mark.gui
class TestMissingMetadataDialog:
    """Testes para MissingMetadataDialog - entrada de metadados manualmente."""

    def test_init_with_experiment_id(self, tkinter_root):
        """Testa inicialização com experiment_id."""
        experiment_id = "EXP123"

        dialog = MissingMetadataDialog(tkinter_root, experiment_id)
        dialog.withdraw()

        assert dialog.experiment_id == experiment_id
        assert dialog.result is None

        dialog.destroy()

    def test_body_creates_form_fields(self, tkinter_root):
        """Testa que o body cria todos os campos do formulário."""
        dialog = MissingMetadataDialog(tkinter_root, "EXP123")
        dialog.withdraw()

        assert hasattr(dialog, 'day_var')
        assert hasattr(dialog, 'group_var')
        assert hasattr(dialog, 'cobaia_var')

        dialog.destroy()

    def test_validate_with_valid_input(self, tkinter_root):
        """Testa validação com entrada válida."""
        dialog = MissingMetadataDialog(tkinter_root, "EXP123")
        dialog.withdraw()

        dialog.day_var.set("5")
        dialog.group_var.set("Control")
        dialog.cobaia_var.set("42")

        result = dialog.validate()

        assert result == 1  # Validação bem-sucedida

        dialog.destroy()

    def test_validate_with_invalid_day(self, tkinter_root):
        """Testa validação com dia inválido (não-numérico)."""
        with patch("tkinter.messagebox.showerror"):
            dialog = MissingMetadataDialog(tkinter_root, "EXP123")
            dialog.withdraw()

            dialog.day_var.set("abc")  # Inválido
            dialog.group_var.set("Control")
            dialog.cobaia_var.set("42")

            result = dialog.validate()

            assert result == 0  # Validação falhou

            dialog.destroy()

    def test_validate_with_invalid_cobaia(self, tkinter_root):
        """Testa validação com cobaia inválida (não-numérica)."""
        with patch("tkinter.messagebox.showerror"):
            dialog = MissingMetadataDialog(tkinter_root, "EXP123")
            dialog.withdraw()

            dialog.day_var.set("5")
            dialog.group_var.set("Control")
            dialog.cobaia_var.set("xyz")  # Inválido

            result = dialog.validate()

            assert result == 0  # Validação falhou

            dialog.destroy()

    def test_validate_with_empty_group(self, tkinter_root):
        """Testa validação com grupo vazio."""
        with patch("tkinter.messagebox.showerror"):
            dialog = MissingMetadataDialog(tkinter_root, "EXP123")
            dialog.withdraw()

            dialog.day_var.set("5")
            dialog.group_var.set("   ")  # Apenas espaços
            dialog.cobaia_var.set("42")

            result = dialog.validate()

            assert result == 0  # Validação falhou

            dialog.destroy()

    def test_apply_with_valid_data(self, tkinter_root):
        """Testa apply com dados válidos."""
        dialog = MissingMetadataDialog(tkinter_root, "EXP123")
        dialog.withdraw()

        dialog.day_var.set("7")
        dialog.group_var.set("Treatment A")
        dialog.cobaia_var.set("99")

        dialog.apply()

        assert dialog.result == {
            "day": 7,
            "group": "Treatment A",
            "cobaia": 99,
        }

        dialog.destroy()

    def test_apply_strips_group_whitespace(self, tkinter_root):
        """Testa que apply remove espaços em branco do grupo."""
        dialog = MissingMetadataDialog(tkinter_root, "EXP123")
        dialog.withdraw()

        dialog.day_var.set("3")
        dialog.group_var.set("  Control Group  ")
        dialog.cobaia_var.set("15")

        dialog.apply()

        assert dialog.result["group"] == "Control Group"  # Espaços removidos

        dialog.destroy()
