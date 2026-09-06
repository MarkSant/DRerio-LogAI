"""Uma sessão ao vivo AVULSA tem de aparecer na aba de Relatórios.

O defeito
---------
Sessão real de 2026-09-06: a gravação rodou, a análise concluiu, o aviso de
sucesso apareceu, o `.xlsx` e o `.docx` foram escritos em disco — e a aba de
Relatórios ficou vazia. Sem item na lista, não havia como abrir os resultados
pela interface.

A causa estava em ``live_analysis_post_processor``::

    # Register outputs in project if active
    if self.project_manager.project_path:
        self.project_manager.register_processing_outputs(...)
        self._publish_project_views_refresh(...)

A guarda não protegia nada. ``register_processing_outputs`` já trata a ausência
de projeto sozinho: popula ``project_data["videos"]`` em memória e condiciona
apenas o ``save_project()`` final, que é o único passo que precisa de arquivo em
disco. O que a guarda fazia era pular o registro inteiro no fluxo sem projeto —
e a aba de Relatórios monta a lista a partir de ``get_all_videos()``.

O fluxo de vídeo único PRÉ-GRAVADO registra sem guarda nenhuma
(``analysis_control_view_model``), e é exatamente por isso que ele aparece. A
assimetria estava só no lado ao vivo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from zebtrack.core.project.project_manager import ProjectManager


@pytest.fixture
def manager_without_project(tmp_path: Path) -> ProjectManager:
    """Um ``ProjectManager`` no estado do fluxo ad-hoc: sem projeto aberto."""
    settings = MagicMock()
    manager = ProjectManager(settings_obj=settings)
    assert manager.project_path is None, "o fixture precisa representar o fluxo SEM projeto"
    return manager


def _register(manager: ProjectManager, results_dir: Path) -> Any:
    """Registra as saídas de uma sessão ao vivo, como o pós-processamento faz."""
    return manager.register_processing_outputs(
        video_path=str(results_dir / "test4.mp4"),
        results_dir=str(results_dir),
        trajectory_path=str(results_dir / "3_CoordMovimento_test4.parquet"),
        summary_excel=str(results_dir / "4_Relatorio_test4.xlsx"),
        report_path=str(results_dir / "4_Relatorio_test4.docx"),
        experiment_id="test4",
    )


def test_registration_works_without_a_project(
    manager_without_project: ProjectManager, tmp_path: Path
) -> None:
    """A premissa que derruba a guarda.

    Se isto falhasse, a guarda ``if project_path`` estaria certa e o conserto
    teria de ser outro. Ele passa: o registro sem projeto é suportado.
    """
    assert _register(manager_without_project, tmp_path) is True


def test_the_session_becomes_visible_to_the_reports_tab(
    manager_without_project: ProjectManager, tmp_path: Path
) -> None:
    """``get_all_videos()`` é a fonte da árvore de Relatórios.

    Este é o teste que reproduz o sintoma: sem a entrada aqui, a aba fica vazia
    por mais que os arquivos existam em disco.
    """
    _register(manager_without_project, tmp_path)

    videos = manager_without_project.get_all_videos()

    assert len(videos) == 1, "a sessão ao vivo não chegou à lista que a aba lê"
    assert videos[0]["status"] == "processed"
    assert Path(videos[0]["results_dir"]).name == tmp_path.name


def test_registration_does_not_need_to_save_a_project_file(
    manager_without_project: ProjectManager, tmp_path: Path
) -> None:
    """Nada é escrito em disco quando não há projeto.

    É o motivo de a guarda ter parecido necessária. A condição correta está
    DENTRO de ``register_processing_outputs``, em volta do ``save_project()``
    apenas — não em volta do registro inteiro.
    """
    _register(manager_without_project, tmp_path)

    assert manager_without_project.project_path is None
    assert not list(tmp_path.glob("*.json")), "não deveria ter gravado arquivo de projeto"


def test_the_post_processor_no_longer_gates_registration_on_a_project() -> None:
    """A guarda não pode voltar.

    Uma varredura no fonte, e não uma execução: reproduzir o pós-processamento
    inteiro exigiria câmera, detector e thread de análise, e o que importa aqui
    é uma propriedade estática — que a chamada de registro não esteja aninhada
    sob um teste de ``project_path``.
    """
    import inspect

    from zebtrack.core.recording import live_analysis_post_processor as module

    source = inspect.getsource(module)

    for marker in ("register_processing_outputs(", "_publish_project_views_refresh("):
        assert marker in source, f"{marker} sumiu do pós-processamento"

    # Nenhuma das duas chamadas pode aparecer logo depois de uma guarda de
    # projeto. Procuramos o padrão exato que causou o defeito.
    offending = "if self.project_manager.project_path:"
    for index, line in enumerate(source.splitlines()):
        if offending in line:
            following = "\n".join(source.splitlines()[index : index + 6])
            assert "register_processing_outputs(" not in following, (
                "o registro das saídas voltou a depender de haver projeto aberto; "
                "sem projeto a sessão ao vivo some da aba de Relatórios"
            )
