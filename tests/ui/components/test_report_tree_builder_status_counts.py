"""Testes de get_project_status_counts (bug 4 — contadores zerados).

Sessões live são persistidas com status "recorded"/"processed" e nunca
chegam a "complete"; os cards derivam agora o status efetivo dos dados:
Pendentes = sem dados; Com Dados = trajetória sem relatório; Concluídos =
com sumário/relatório. "failed"/"complete" explícitos são preservados.
"""

from __future__ import annotations

from zebtrack.ui.components.project_views.report_tree_builder import ReportTreeBuilder


class _FakeProjectManager:
    """ProjectManager mínimo: flags por vídeo vindas do próprio dict."""

    def __init__(self, videos: list[dict]) -> None:
        self._videos = videos
        self._by_path = {v["path"]: v for v in videos}

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


def _builder(videos: list[dict]) -> ReportTreeBuilder:
    pm = _FakeProjectManager(videos)
    return ReportTreeBuilder(project_manager_getter=lambda: pm)


def test_live_recorded_video_with_reports_counts_as_complete():
    """Sessão live com sumário: status cru "recorded" vira Concluído."""
    videos = [
        {
            "path": "p/s1.mp4",
            "status": "recorded",
            "has_arena": True,
            "has_rois": True,
            "has_trajectory": True,
            "has_summary": True,
        }
    ]

    counts = _builder(videos).get_project_status_counts()

    assert counts["total"] == 1
    assert counts["complete"] == 1
    assert counts["pending"] == 0
    assert counts["processed"] == 0
    assert counts["summary"] == 1


def test_recorded_without_any_data_counts_as_pending():
    """ "recorded" sem dados não some mais da contagem: vira Pendente."""
    videos = [{"path": "p/s2.mp4", "status": "recorded"}]

    counts = _builder(videos).get_project_status_counts()

    assert counts["pending"] == 1
    assert counts["complete"] == 0
    assert counts["processed"] == 0


def test_trajectory_without_summary_counts_as_processed():
    videos = [
        {
            "path": "p/s3.mp4",
            "status": "recorded",
            "has_trajectory": True,
        }
    ]

    counts = _builder(videos).get_project_status_counts()

    assert counts["processed"] == 1
    assert counts["pending"] == 0
    assert counts["complete"] == 0


def test_explicit_failed_and_complete_are_preserved():
    """Status explícitos vencem a derivação por flags."""
    videos: list[dict] = [
        {"path": "p/f.mp4", "status": "failed", "has_summary": True},
        {"path": "p/c.mp4", "status": "complete"},
    ]

    counts = _builder(videos).get_project_status_counts()

    assert counts["failed"] == 1
    assert counts["complete"] == 1
    assert counts["pending"] == 0


def test_processing_status_kept_when_no_data_yet():
    videos = [{"path": "p/w.mp4", "status": "processing"}]

    counts = _builder(videos).get_project_status_counts()

    assert counts["processing"] == 1
    assert counts["pending"] == 0


def test_mixed_project_matches_user_expectation():
    """Cenário do relato: N gravados com relatórios + 1 pendente.

    Esperado: Total=3, Concluídos=2, Pendentes=1 (total menos com dados),
    nada zerado indevidamente.
    """
    done: dict = {
        "status": "recorded",
        "has_arena": True,
        "has_rois": True,
        "has_trajectory": True,
        "has_summary": True,
    }
    videos: list[dict] = [
        {"path": "p/a.mp4", **done},
        {"path": "p/b.mp4", **done},
        {"path": "p/c.mp4", "status": "pending"},
    ]

    counts = _builder(videos).get_project_status_counts()

    assert counts["total"] == 3
    assert counts["complete"] == 2
    assert counts["pending"] == 1
    assert counts["failed"] == 0
