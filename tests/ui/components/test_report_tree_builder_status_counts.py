"""Testes de get_project_status_counts (bug 4 — contadores zerados).

Semântica dos cards (derivada dos dados em disco, não do status cru):
- Concluídos = com sumário/relatório (ou status explícito "complete").
- Com Dados = com trajetória/dados — CUMULATIVO (inclui concluídos), para
  que "Pendentes = Total - Com Dados" feche.
- Pendentes = unidades planejadas sem dados; em projetos live o total é o
  desenho experimental (dias x grupos x sujeitos), não só as gravadas.
"""

from __future__ import annotations

from zebtrack.ui.components.project_views.report_tree_builder import ReportTreeBuilder


class _FakeProjectManager:
    """ProjectManager mínimo: flags por vídeo vindas do próprio dict."""

    def __init__(
        self,
        videos: list[dict],
        *,
        project_type: str = "prerecorded",
        project_data: dict | None = None,
    ) -> None:
        self._videos = videos
        self._by_path = {v["path"]: v for v in videos}
        self._project_type = project_type
        self.project_data = project_data or {}

    def get_project_type(self) -> str:
        return self._project_type

    def get_all_videos(self) -> list[dict]:
        return self._videos

    def _flag(self, path: str, key: str) -> bool:
        return bool(self._by_path.get(path, {}).get(key, False))

    def has_arena_data(self, path: str) -> bool:
        return self._flag(path, "has_arena")

    def has_roi_data(self, path: str) -> bool:
        return self._flag(path, "has_rois")

    def has_trajectory_data(self, path: str) -> bool:
        return self._flag(path, "has_trajectory")

    def has_summary_data(self, path: str) -> bool:
        return self._flag(path, "has_summary")


def _builder(videos: list[dict], **pm_kwargs) -> ReportTreeBuilder:
    pm = _FakeProjectManager(videos, **pm_kwargs)
    return ReportTreeBuilder(project_manager_getter=lambda: pm)


_DONE: dict = {
    "status": "recorded",
    "has_arena": True,
    "has_rois": True,
    "has_trajectory": True,
    "has_summary": True,
}


def test_live_recorded_video_with_reports_counts_complete_and_processed():
    """Sessão live com sumário conta como Concluído E Com Dados (cumulativo)."""
    videos: list[dict] = [{"path": "p/s1.mp4", **_DONE}]

    counts = _builder(videos).get_project_status_counts()

    assert counts["total"] == 1
    assert counts["complete"] == 1
    assert counts["processed"] == 1
    assert counts["pending"] == 0
    assert counts["summary"] == 1


def test_recorded_without_any_data_counts_as_pending():
    """ "recorded" sem dados não some mais da contagem: vira Pendente."""
    videos: list[dict] = [{"path": "p/s2.mp4", "status": "recorded"}]

    counts = _builder(videos).get_project_status_counts()

    assert counts["pending"] == 1
    assert counts["complete"] == 0
    assert counts["processed"] == 0


def test_trajectory_without_summary_counts_as_processed_only():
    videos: list[dict] = [{"path": "p/s3.mp4", "status": "recorded", "has_trajectory": True}]

    counts = _builder(videos).get_project_status_counts()

    assert counts["processed"] == 1
    assert counts["complete"] == 0
    assert counts["pending"] == 0


def test_explicit_failed_and_complete_are_preserved():
    """Status explícitos vencem a derivação por flags; falha não conta em dados."""
    videos: list[dict] = [
        {"path": "p/f.mp4", "status": "failed", "has_summary": True},
        {"path": "p/c.mp4", "status": "complete"},
    ]

    counts = _builder(videos).get_project_status_counts()

    assert counts["failed"] == 1
    assert counts["complete"] == 1
    assert counts["processed"] == 1  # complete explícito conta como com dados
    assert counts["pending"] == 0


def test_processing_status_without_data_counts_as_pending():
    """O card "Processando" é ao vivo (UI_UPDATE_PROCESSING_COUNT), não derivado
    do disco. Um status de disco "processing" sem trajetória conta como PENDENTE
    e a chave "processing" NÃO é emitida (para não sobrescrever o valor ao vivo).
    """
    videos: list[dict] = [{"path": "p/w.mp4", "status": "processing"}]

    counts = _builder(videos).get_project_status_counts()

    assert "processing" not in counts
    assert counts["pending"] == 1
    assert counts["processed"] == 0


def test_live_project_pending_uses_experimental_design():
    """Cenário real (Live_T7): 6 gravadas com relatórios de 12 planejadas.

    Total = 3 dias x 2 grupos x 2 sujeitos = 12; Pendentes = 12 - 6 = 6
    ("total menos os com dados"); Com Dados = 6; Concluídos = 6.
    """
    videos: list[dict] = [{"path": f"p/s{i}.mp4", **_DONE} for i in range(6)]

    counts = _builder(
        videos,
        project_type="live",
        project_data={
            "experiment_days": 3,
            "groups": ["Controle", "Tratamento 1"],
            "subjects_per_group": 2,
        },
    ).get_project_status_counts()

    assert counts["total"] == 12
    assert counts["processed"] == 6
    assert counts["complete"] == 6
    assert counts["pending"] == 6
    assert counts["failed"] == 0


def test_live_project_without_design_falls_back_to_video_count():
    videos: list[dict] = [{"path": "p/a.mp4", **_DONE}]

    counts = _builder(videos, project_type="live", project_data={}).get_project_status_counts()

    assert counts["total"] == 1
    assert counts["pending"] == 0


def test_prerecorded_mixed_project():
    """Pré-gravado: total = vídeos registrados; pendente = sem dados."""
    videos: list[dict] = [
        {"path": "p/a.mp4", **_DONE},
        {"path": "p/b.mp4", **_DONE},
        {"path": "p/c.mp4", "status": "pending"},
    ]

    counts = _builder(videos).get_project_status_counts()

    assert counts["total"] == 3
    assert counts["complete"] == 2
    assert counts["processed"] == 2
    assert counts["pending"] == 1
    assert counts["failed"] == 0


def test_project_overview_summary_uses_shared_counts():
    """A "Visão Geral do Projeto" (Controle Principal) usa a MESMA contagem.

    Antes havia uma derivação local duplicada no VideoSelectorTreeManager
    (sem desenho experimental em projetos live, "Com Dados" exclusivo) e os
    cards das duas abas divergiam.
    """
    from unittest.mock import Mock

    from zebtrack.ui.components.project_views.report_tree_builder import (
        compute_project_status_counts,
    )
    from zebtrack.ui.components.project_views.video_selector_tree_manager import (
        VideoSelectorTreeManager,
    )

    videos: list[dict] = [{"path": f"p/s{i}.mp4", **_DONE} for i in range(6)]
    pm = _FakeProjectManager(
        videos,
        project_type="live",
        project_data={
            "experiment_days": 3,
            "groups": ["Controle", "Tratamento 1"],
            "subjects_per_group": 2,
        },
    )

    manager = VideoSelectorTreeManager.__new__(VideoSelectorTreeManager)
    manager.gui = Mock()
    manager.gui.controller.project_manager = pm

    manager._update_project_overview_summary()

    expected = compute_project_status_counts(pm)
    manager.gui.project_overview_widget.update_summary.assert_called_once_with(expected)
    assert expected["total"] == 12
    assert expected["pending"] == 6
