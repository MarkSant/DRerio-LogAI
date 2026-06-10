"""Testes da pasta dedicada Zonas_Referencia e do reuso de zonas (bugs 1-2).

Cobre:
- ``resolve_results_directory`` desviando o frame de referência live para
  ``<projeto>/Zonas_Referencia`` (em vez de ``Grupo_Sem_Grupo/...``).
- ``copy_zone_parquet_files`` encontrando os parquets de uma fonte que o scan
  não enxerga (PNG), inclusive no caminho legado de projetos antigos, sem
  recriar a hierarquia-fantasma quando o alvo não tem grupo.
- ``import_zone_data_from_video_parquets`` carregando as zonas a partir dos
  parquets já existentes do próprio vídeo (gravações live).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from zebtrack.core.project.output_registration_manager import (
    LEGACY_NO_DAY_DIRNAME,
    LEGACY_NO_GROUP_DIRNAME,
    LEGACY_NO_SUBJECT_DIRNAME,
    LIVE_REFERENCE_FRAME_FILENAME,
    REFERENCE_ZONES_DIRNAME,
    OutputRegistrationManager,
)
from zebtrack.core.project.parquet_io_manager import ParquetIOManager


@pytest.fixture
def project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "projeto"
    project_dir.mkdir()
    return project_dir


@pytest.fixture
def orm() -> OutputRegistrationManager:
    return OutputRegistrationManager()


@pytest.fixture
def pio() -> ParquetIOManager:
    return ParquetIOManager()


def _resolve_fn(orm: OutputRegistrationManager, project: Path):
    def resolve(experiment_id, video_path=None, metadata=None):
        return orm.resolve_results_directory(
            experiment_id,
            project_path=project,
            video_path=video_path,
            metadata=metadata,
        )

    return resolve


class _FakeZoneData:
    def __init__(self) -> None:
        self.polygon = [[0, 0], [10, 0], [10, 10]]
        self.roi_polygons = [[[1, 1], [2, 1], [2, 2]]]
        self.roi_names = ["roi_a"]
        self.roi_colors = [(0, 128, 0)]


def _write_zone_parquets(directory: Path, stem: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"x": [0, 1], "y": [0, 1]}).to_parquet(
        directory / f"1_ProcessingArea_{stem}.parquet"
    )
    pd.DataFrame(
        {"roi_name": ["r1", "r1"], "point_index": [0, 1], "x": [1, 2], "y": [1, 2]}
    ).to_parquet(directory / f"2_AreasOfInterest_{stem}.parquet")


# ---------------------------------------------------------------------------
# Bug 1 — resolver
# ---------------------------------------------------------------------------


def test_resolver_reference_frame_goes_to_dedicated_folder(orm, project):
    ref_png = project / LIVE_REFERENCE_FRAME_FILENAME

    resolved = orm.resolve_results_directory(
        ref_png.stem, project_path=project, video_path=str(ref_png)
    )

    assert resolved == project / REFERENCE_ZONES_DIRNAME


def test_resolver_reference_frame_matches_by_experiment_id(orm, project):
    resolved = orm.resolve_results_directory(
        "live_camera_reference_frame", project_path=project, video_path=None
    )

    assert resolved == project / REFERENCE_ZONES_DIRNAME


def test_resolver_regular_video_keeps_hierarchical_fallback(orm, project):
    resolved = orm.resolve_results_directory(
        "video_x", project_path=project, video_path=str(project / "video_x.mp4")
    )

    assert LEGACY_NO_GROUP_DIRNAME in resolved.parts


def test_resolver_without_project_unchanged(orm, tmp_path):
    video = tmp_path / "avulso.mp4"

    resolved = orm.resolve_results_directory("avulso", project_path=None, video_path=str(video))

    assert resolved == tmp_path / "avulso_results"


def test_export_zones_for_reference_frame_writes_to_dedicated_folder(orm, pio, project):
    ref_png = project / LIVE_REFERENCE_FRAME_FILENAME
    ref_png.write_bytes(b"png")

    exported = pio.export_zones_to_parquet(
        str(ref_png),
        _FakeZoneData(),
        project_path=project,
        find_video_entry_fn=lambda **kw: None,
        resolve_results_directory_fn=_resolve_fn(orm, project),
    )

    assert Path(exported["arena"]).parent == project / REFERENCE_ZONES_DIRNAME
    assert Path(exported["rois"]).parent == project / REFERENCE_ZONES_DIRNAME


# ---------------------------------------------------------------------------
# Bug 2 — copy_zone_parquet_files com fonte não-vídeo
# ---------------------------------------------------------------------------


def _copy(pio, orm, project, source, target, find_video_entry_fn):
    return pio.copy_zone_parquet_files(
        str(source),
        str(target),
        project_data={},
        project_path=project,
        set_active_zone_video_fn=lambda p: None,
        scan_input_paths_fn=lambda paths: [],  # PNG: scan nunca retorna nada
        find_video_entry_fn=find_video_entry_fn,
        resolve_results_directory_fn=_resolve_fn(orm, project),
        save_project_fn=lambda: None,
        persist=False,
    )


def test_copy_from_reference_png_finds_parquets_in_dedicated_folder(orm, pio, project):
    ref_png = project / LIVE_REFERENCE_FRAME_FILENAME
    ref_png.write_bytes(b"png")
    _write_zone_parquets(project / REFERENCE_ZONES_DIRNAME, ref_png.stem)

    target = project / "sessao" / "sujeito1.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"mp4")
    entry = {"path": target.as_posix(), "metadata": {}}

    copied = _copy(
        pio,
        orm,
        project,
        ref_png,
        target,
        lambda **kw: entry if str(kw.get("path", "")).endswith("sujeito1.mp4") else None,
    )

    assert sorted(copied) == ["arena", "rois"]
    assert (target.parent / "1_ProcessingArea_sujeito1.parquet").exists()
    assert entry["has_arena"] and entry["has_rois"]


def test_copy_from_reference_png_falls_back_to_legacy_folder(orm, pio, project):
    """Projetos antigos guardam os parquets de referência no caminho legado."""
    ref_png = project / LIVE_REFERENCE_FRAME_FILENAME
    ref_png.write_bytes(b"png")
    legacy_dir = (
        project / LEGACY_NO_GROUP_DIRNAME / LEGACY_NO_DAY_DIRNAME / LEGACY_NO_SUBJECT_DIRNAME
    )
    _write_zone_parquets(legacy_dir, ref_png.stem)

    target = project / "sessao" / "sujeito2.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"mp4")

    copied = _copy(pio, orm, project, ref_png, target, lambda **kw: None)

    assert sorted(copied) == ["arena", "rois"]
    assert (target.parent / "1_ProcessingArea_sujeito2.parquet").exists()


def test_copy_does_not_recreate_phantom_no_group_hierarchy(orm, pio, project):
    """Alvo sem metadados de grupo não deve ganhar cópia em Grupo_Sem_Grupo."""
    ref_png = project / LIVE_REFERENCE_FRAME_FILENAME
    ref_png.write_bytes(b"png")
    _write_zone_parquets(project / REFERENCE_ZONES_DIRNAME, ref_png.stem)

    target = project / "sessao" / "sujeito3.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"mp4")

    copied = _copy(pio, orm, project, ref_png, target, lambda **kw: None)

    assert sorted(copied) == ["arena", "rois"]
    assert not (project / LEGACY_NO_GROUP_DIRNAME).exists()


def test_copy_without_any_source_parquets_returns_empty(orm, pio, project):
    ref_png = project / LIVE_REFERENCE_FRAME_FILENAME
    ref_png.write_bytes(b"png")

    target = project / "sessao" / "sujeito4.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"mp4")

    copied = _copy(pio, orm, project, ref_png, target, lambda **kw: None)

    assert copied == {}


# ---------------------------------------------------------------------------
# Bug 2 — import dos parquets do próprio vídeo
# ---------------------------------------------------------------------------


class _MutableZoneData:
    def __init__(self) -> None:
        self.polygon = None
        self.roi_polygons: list = []
        self.roi_names: list = []
        self.roi_colors: list = []


def test_import_zone_data_from_own_session_folder(orm, pio, project):
    session_dir = project / "Grupo_G01" / "Dia_01" / "Sujeito_01" / "live_x"
    video = session_dir / "sujeito1.mp4"
    _write_zone_parquets(session_dir, video.stem)
    video.write_bytes(b"mp4")

    entry: dict = {"path": video.as_posix(), "metadata": {}}
    zone_data = _MutableZoneData()
    saved: dict = {}

    imported = pio.import_zone_data_from_video_parquets(
        str(video),
        project_path=project,
        find_video_entry_fn=lambda **kw: entry,
        resolve_results_directory_fn=_resolve_fn(orm, project),
        get_zone_data_fn=lambda **kw: zone_data,
        save_zone_data_fn=lambda zd, vp, persist: saved.update({"video": vp, "persist": persist}),
    )

    assert imported is True
    assert zone_data.polygon == [[0, 0], [1, 1]]
    assert zone_data.roi_names == ["r1"]
    assert saved["video"] == str(video)
    assert entry["has_arena"] and entry["has_rois"]
    assert entry["parquet_files"]["arena"].endswith("1_ProcessingArea_sujeito1.parquet")


def test_import_zone_data_returns_false_without_parquets(orm, pio, project):
    video = project / "sessao" / "vazio.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"mp4")

    imported = pio.import_zone_data_from_video_parquets(
        str(video),
        project_path=project,
        find_video_entry_fn=lambda **kw: None,
        resolve_results_directory_fn=_resolve_fn(orm, project),
        get_zone_data_fn=lambda **kw: _MutableZoneData(),
        save_zone_data_fn=lambda zd, vp, persist: pytest.fail("não deveria salvar"),
    )

    assert imported is False
