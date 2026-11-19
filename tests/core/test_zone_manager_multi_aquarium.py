"""Unit tests for ZoneManager multi-aquarium support.

Tests the new methods for storing and retrieving MultiAquariumZoneData
in project configurations.

Coverage target: 80%+
"""

import sys
from pathlib import Path

import pytest

from zebtrack.core.detection import AquariumData, MultiAquariumZoneData, ZoneData
from zebtrack.core.project.zone_manager import ZoneManager


class TestZoneManagerMultiAquariumSerialization:
    """Tests for multi-aquarium serialization/deserialization."""

    @pytest.fixture
    def zone_manager(self):
        """Create a ZoneManager instance."""
        return ZoneManager()

    @pytest.fixture
    def sample_multi_aquarium_data(self):
        """Create sample MultiAquariumZoneData for testing."""
        return MultiAquariumZoneData(
            aquariums=[
                AquariumData(
                    id=0,
                    polygon=[[0, 0], [300, 0], [300, 400], [0, 400]],
                    roi_polygons=[[[50, 50], [150, 50], [150, 150], [50, 150]]],
                    roi_names=["ROI_Left"],
                    roi_colors=[(255, 0, 0)],
                    group="Controle",
                    subject_id="S01",
                    day=1,
                    roi_mode="grid",
                    roi_data={"rows": 2, "cols": 2},
                ),
                AquariumData(
                    id=1,
                    polygon=[[350, 0], [650, 0], [650, 400], [350, 400]],
                    roi_polygons=[[[400, 50], [500, 50], [500, 150], [400, 150]]],
                    roi_names=["ROI_Right"],
                    roi_colors=[(0, 255, 0)],
                    group="Tratamento",
                    subject_id="S02",
                    day=1,
                ),
            ],
            video_width=1280,
            video_height=720,
        )

    def test_multi_aquarium_zone_data_to_dict(self, sample_multi_aquarium_data):
        """Testa serialização de MultiAquariumZoneData para dict."""
        result = ZoneManager.multi_aquarium_zone_data_to_dict(sample_multi_aquarium_data)

        assert isinstance(result, dict)
        assert "aquariums" in result
        assert "video_width" in result
        assert "video_height" in result

        assert len(result["aquariums"]) == 2
        assert result["video_width"] == 1280
        assert result["video_height"] == 720

        # Check first aquarium
        aq0 = result["aquariums"][0]
        assert aq0["id"] == 0
        assert aq0["group"] == "Controle"
        assert aq0["subject_id"] == "S01"
        assert aq0["day"] == 1
        assert aq0["roi_mode"] == "grid"
        assert aq0["roi_data"] == {"rows": 2, "cols": 2}
        assert len(aq0["polygon"]) == 4
        assert len(aq0["roi_polygons"]) == 1
        assert aq0["roi_names"] == ["ROI_Left"]

        # Check second aquarium
        aq1 = result["aquariums"][1]
        assert aq1["id"] == 1
        assert aq1["group"] == "Tratamento"
        assert aq1["subject_id"] == "S02"

    def test_multi_aquarium_zone_data_to_dict_empty(self):
        """Testa serialização de dados vazios."""
        result = ZoneManager.multi_aquarium_zone_data_to_dict(None)

        assert result == {
            "aquariums": [],
            "video_width": 0,
            "video_height": 0,
            "sequential_processing": False,
        }

    def test_multi_aquarium_zone_data_from_dict(self):
        """Testa deserialização de dict para MultiAquariumZoneData."""
        data = {
            "aquariums": [
                {
                    "id": 0,
                    "polygon": [[0, 0], [100, 0], [100, 100], [0, 100]],
                    "roi_polygons": [],
                    "roi_names": [],
                    "roi_colors": [],
                    "group": "Controle",
                    "subject_id": "S01",
                    "day": 2,
                    "roi_mode": "grid",
                    "roi_data": {"rows": 3, "cols": 4},
                },
                {
                    "id": 1,
                    "polygon": [[200, 0], [300, 0], [300, 100], [200, 100]],
                    "roi_polygons": [[[210, 10], [290, 10], [290, 90], [210, 90]]],
                    "roi_names": ["TestROI"],
                    "roi_colors": [[0, 0, 255]],
                    "group": "Tratamento",
                    "subject_id": "S02",
                    "day": 2,
                },
            ],
            "video_width": 640,
            "video_height": 480,
        }

        result = ZoneManager.multi_aquarium_zone_data_from_dict(data)

        assert isinstance(result, MultiAquariumZoneData)
        assert len(result.aquariums) == 2
        assert result.video_width == 640
        assert result.video_height == 480

        # Check first aquarium
        aq0 = result.aquariums[0]
        assert aq0.id == 0
        assert aq0.group == "Controle"
        assert aq0.subject_id == "S01"
        assert aq0.day == 2
        assert aq0.roi_mode == "grid"
        assert aq0.roi_data == {"rows": 3, "cols": 4}

        # Check second aquarium
        aq1 = result.aquariums[1]
        assert aq1.id == 1
        assert aq1.group == "Tratamento"
        assert len(aq1.roi_polygons) == 1
        assert aq1.roi_names == ["TestROI"]
        assert aq1.roi_colors == [(0, 0, 255)]

    def test_multi_aquarium_zone_data_from_dict_empty(self):
        """Testa deserialização de dados vazios."""
        result = ZoneManager.multi_aquarium_zone_data_from_dict(None)

        assert isinstance(result, MultiAquariumZoneData)
        assert result.aquariums == []
        assert result.video_width == 0
        assert result.video_height == 0

    def test_serialization_roundtrip(self, sample_multi_aquarium_data):
        """Testa que serialização + deserialização preserva dados."""
        serialized = ZoneManager.multi_aquarium_zone_data_to_dict(sample_multi_aquarium_data)
        deserialized = ZoneManager.multi_aquarium_zone_data_from_dict(serialized)

        assert len(deserialized.aquariums) == len(sample_multi_aquarium_data.aquariums)
        assert deserialized.video_width == sample_multi_aquarium_data.video_width
        assert deserialized.video_height == sample_multi_aquarium_data.video_height

        for i, (orig, restored) in enumerate(
            zip(sample_multi_aquarium_data.aquariums, deserialized.aquariums, strict=False)
        ):
            assert restored.id == orig.id
            assert restored.polygon == orig.polygon
            assert restored.roi_polygons == orig.roi_polygons
            assert restored.roi_names == orig.roi_names
            assert restored.roi_colors == orig.roi_colors
            assert restored.group == orig.group
            assert restored.subject_id == orig.subject_id
            assert restored.day == orig.day
            assert restored.roi_mode == orig.roi_mode
            assert restored.roi_data == orig.roi_data


class TestZoneManagerMultiAquariumStorage:
    """Tests for saving and retrieving multi-aquarium zone data."""

    @pytest.fixture
    def zone_manager(self):
        """Create a ZoneManager instance."""
        return ZoneManager()

    @pytest.fixture
    def empty_project_data(self):
        """Create empty project data dictionary."""
        return {}

    @pytest.fixture
    def sample_multi_aquarium_data(self):
        """Create sample MultiAquariumZoneData for testing."""
        return MultiAquariumZoneData(
            aquariums=[
                AquariumData(
                    id=0,
                    polygon=[[0, 0], [300, 0], [300, 400], [0, 400]],
                    group="Controle",
                    subject_id="S01",
                    day=1,
                ),
                AquariumData(
                    id=1,
                    polygon=[[350, 0], [650, 0], [650, 400], [350, 400]],
                    group="Tratamento",
                    subject_id="S02",
                    day=1,
                ),
            ],
            video_width=1280,
            video_height=720,
        )

    def test_save_multi_aquarium_zone_data(
        self, zone_manager, empty_project_data, sample_multi_aquarium_data
    ):
        """Testa salvamento de dados multi-aquário."""
        video_path = "/path/to/video.mp4"

        result = zone_manager.save_multi_aquarium_zone_data(
            empty_project_data, video_path, sample_multi_aquarium_data
        )

        assert result is True
        assert "multi_aquarium_zones" in empty_project_data
        assert len(empty_project_data["multi_aquarium_zones"]) == 1

        # Also check compatibility with zones_by_video
        assert "zones_by_video" in empty_project_data
        assert len(empty_project_data["zones_by_video"]) == 1

    def test_get_multi_aquarium_zone_data(
        self, zone_manager, empty_project_data, sample_multi_aquarium_data
    ):
        """Testa recuperação de dados multi-aquário."""
        video_path = "/path/to/video.mp4"

        # Save first
        zone_manager.save_multi_aquarium_zone_data(
            empty_project_data, video_path, sample_multi_aquarium_data
        )

        # Retrieve
        result = zone_manager.get_multi_aquarium_zone_data(empty_project_data, video_path)

        assert result is not None
        assert isinstance(result, MultiAquariumZoneData)
        assert len(result.aquariums) == 2
        assert result.video_width == 1280
        assert result.aquariums[0].group == "Controle"
        assert result.aquariums[1].group == "Tratamento"

    def test_get_multi_aquarium_zone_data_not_found(self, zone_manager, empty_project_data):
        """Testa recuperação de dados não existentes."""
        result = zone_manager.get_multi_aquarium_zone_data(
            empty_project_data, "/nonexistent/video.mp4"
        )
        assert result is None

    def test_get_aquarium_count_multi(
        self, zone_manager, empty_project_data, sample_multi_aquarium_data
    ):
        """Testa contagem de aquários em modo multi."""
        video_path = "/path/to/video.mp4"

        zone_manager.save_multi_aquarium_zone_data(
            empty_project_data, video_path, sample_multi_aquarium_data
        )

        count = zone_manager.get_aquarium_count(empty_project_data, video_path)
        assert count == 2

    def test_get_aquarium_count_single(self, zone_manager, empty_project_data):
        """Testa contagem de aquários em modo padrão (1 aquário)."""
        video_path = "/path/to/video.mp4"

        # Save standard zone data
        zone_data = ZoneData(polygon=[[0, 0], [100, 0], [100, 100], [0, 100]])
        zone_manager.save_zone_data(empty_project_data, zone_data, video_path)

        count = zone_manager.get_aquarium_count(empty_project_data, video_path)
        assert count == 1

    def test_get_aquarium_count_none(self, zone_manager, empty_project_data):
        """Testa contagem de aquários sem dados."""
        count = zone_manager.get_aquarium_count(empty_project_data, "/nonexistent/video.mp4")
        assert count == 0

    def test_is_multi_aquarium_video_true(
        self, zone_manager, empty_project_data, sample_multi_aquarium_data
    ):
        """Testa detecção de vídeo multi-aquário."""
        video_path = "/path/to/video.mp4"

        zone_manager.save_multi_aquarium_zone_data(
            empty_project_data, video_path, sample_multi_aquarium_data
        )

        assert zone_manager.is_multi_aquarium_video(empty_project_data, video_path) is True

    def test_is_multi_aquarium_video_false_single(self, zone_manager, empty_project_data):
        """Testa que vídeo com 1 aquário não é multi-aquário."""
        video_path = "/path/to/video.mp4"

        # Save single aquarium data
        single_data = MultiAquariumZoneData(
            aquariums=[AquariumData(id=0, polygon=[[0, 0], [100, 0], [100, 100], [0, 100]])],
            video_width=640,
            video_height=480,
        )
        zone_manager.save_multi_aquarium_zone_data(empty_project_data, video_path, single_data)

        assert zone_manager.is_multi_aquarium_video(empty_project_data, video_path) is False

    def test_is_multi_aquarium_video_false_none(self, zone_manager, empty_project_data):
        """Testa que vídeo sem dados não é multi-aquário."""
        assert (
            zone_manager.is_multi_aquarium_video(empty_project_data, "/nonexistent/video.mp4")
            is False
        )

    def test_clear_multi_aquarium_zone_data(
        self, zone_manager, empty_project_data, sample_multi_aquarium_data
    ):
        """Testa remoção de dados multi-aquário."""
        video_path = "/path/to/video.mp4"

        # Save first
        zone_manager.save_multi_aquarium_zone_data(
            empty_project_data, video_path, sample_multi_aquarium_data
        )

        # Verify saved
        assert zone_manager.get_multi_aquarium_zone_data(empty_project_data, video_path) is not None

        # Clear
        zone_manager.clear_multi_aquarium_zone_data(empty_project_data, video_path)

        # Verify cleared
        assert zone_manager.get_multi_aquarium_zone_data(empty_project_data, video_path) is None

    def test_persist_callback_called(
        self, zone_manager, empty_project_data, sample_multi_aquarium_data
    ):
        """Testa que callback de persistência é chamado."""
        video_path = "/path/to/video.mp4"
        callback_called = [False]

        def mock_callback():
            callback_called[0] = True

        zone_manager.save_multi_aquarium_zone_data(
            empty_project_data,
            video_path,
            sample_multi_aquarium_data,
            persist_callback=mock_callback,
        )

        assert callback_called[0] is True


class TestZoneManagerMultiAquariumProjectFile:
    """Tests for multi-aquarium data in project file structure."""

    @pytest.fixture
    def zone_manager(self):
        """Create a ZoneManager instance."""
        return ZoneManager()

    def test_project_data_structure(self, zone_manager):
        """Testa estrutura correta do project_data com multi-aquário."""
        project_data: dict[str, object] = {}
        video_path = "/path/to/video.mp4"

        multi_data = MultiAquariumZoneData(
            aquariums=[
                AquariumData(id=0, polygon=[[0, 0], [100, 0], [100, 100], [0, 100]]),
                AquariumData(id=1, polygon=[[200, 0], [300, 0], [300, 100], [200, 100]]),
            ],
            video_width=640,
            video_height=480,
        )

        zone_manager.save_multi_aquarium_zone_data(project_data, video_path, multi_data)

        # Verify structure matches expected JSON format
        assert "multi_aquarium_zones" in project_data
        assert "zones_by_video" in project_data
        assert "detection_zones" in project_data

        # multi_aquarium_zones should have the full data
        multi_zones = project_data["multi_aquarium_zones"]
        assert isinstance(multi_zones, dict)
        assert len(multi_zones) == 1

        # zones_by_video should have first aquarium for compatibility
        zones_by_video = project_data["zones_by_video"]
        assert isinstance(zones_by_video, dict)
        assert len(zones_by_video) == 1

    def test_compatibility_with_standard_zone_data(self, zone_manager):
        """Testa que dados multi-aquário são compatíveis com fluxo padrão."""
        project_data: dict[str, object] = {}
        video_path = "/path/to/video.mp4"

        multi_data = MultiAquariumZoneData(
            aquariums=[
                AquariumData(
                    id=0,
                    polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
                    roi_polygons=[[[10, 10], [50, 10], [50, 50], [10, 50]]],
                    roi_names=["ROI1"],
                    roi_colors=[(255, 0, 0)],
                ),
                AquariumData(id=1, polygon=[[200, 0], [300, 0], [300, 100], [200, 100]]),
            ],
            video_width=640,
            video_height=480,
        )

        zone_manager.save_multi_aquarium_zone_data(project_data, video_path, multi_data)

        # Standard get_zone_data should return first aquarium
        zone_data = zone_manager.get_zone_data(project_data, video_path)

        assert isinstance(zone_data, ZoneData)
        assert zone_data.polygon == [[0, 0], [100, 0], [100, 100], [0, 100]]
        assert len(zone_data.roi_polygons) == 1
        assert zone_data.roi_names == ["ROI1"]
        assert zone_data.metadata["source_video_width"] == 640
        assert zone_data.metadata["source_video_height"] == 480

    def test_zone_data_roundtrip_preserves_metadata(self, zone_manager):
        """Testa que zone_data serializa/deserializa metadata sem perda."""
        zone_data = ZoneData(
            polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            metadata={"source_video_width": 864, "source_video_height": 480},
        )

        serialized = zone_manager.zone_data_to_dict(zone_data)
        restored = zone_manager.zone_data_from_dict(serialized)

        assert restored.metadata["source_video_width"] == 864
        assert restored.metadata["source_video_height"] == 480


class TestRoiNamesInProject:
    """``ZoneManager.roi_names_in_project`` — every ROI the project defines (#650)."""

    def test_reads_global_per_video_and_per_aquarium_rois_in_order(self):
        project_data = {
            "detection_zones": {"roi_names": ["center"]},
            "zones_by_video": {
                "C:/v/a.mp4": {"roi_names": ["toca", "center"]},
                "C:/v/b.mp4": {"roi_names": ["edge"]},
            },
            "multi_aquarium_zones": {
                "C:/v/c.mp4": {
                    "aquariums": [
                        {"id": 0, "roi_names": ["top"]},
                        {"id": 1, "roi_names": ["toca"]},
                    ]
                }
            },
        }

        assert ZoneManager.roi_names_in_project(project_data) == ["center", "toca", "edge", "top"]

    def test_empty_project_has_no_roi(self):
        assert ZoneManager.roi_names_in_project({}) == []

    def test_malformed_entries_are_skipped_not_raised(self):
        project_data = {
            "detection_zones": None,
            "zones_by_video": {
                "a": "not a dict",
                "b": {"roi_names": None},
                "c": {"roi_names": [3]},
            },
            "multi_aquarium_zones": {"d": {"aquariums": [None, {"roi_names": ["  ", "ok"]}]}},
        }

        assert ZoneManager.roi_names_in_project(project_data) == ["3", "ok"]

    def test_does_not_create_missing_structures(self):
        project_data: dict = {}

        ZoneManager.roi_names_in_project(project_data)

        assert project_data == {}


# ---------------------------------------------------------------------------
# Single-zone registry: path identity, the global mirror, flags and parquets
# (TASK-087). Every expected value below is derived from the inputs.
# ---------------------------------------------------------------------------

ARENA = [[10, 10], [110, 10], [110, 90], [10, 90]]
OTHER_ARENA = [[0, 0], [50, 0], [50, 50]]
ROI = [[20, 20], [40, 20], [40, 40]]


def _norm(path) -> str:
    return ZoneManager.normalize_video_path(path)  # type: ignore[return-value]


def _zone(polygon=ARENA, rois=(), names=(), colors=()) -> ZoneData:
    return ZoneData(
        polygon=[list(p) for p in polygon],
        roi_polygons=[list(map(list, r)) for r in rois],
        roi_names=list(names),
        roi_colors=list(colors),
    )


def _batch_project(project_type, *paths) -> dict:
    return {
        "project_type": project_type,
        "batches": [{"videos": [{"path": str(p)} for p in paths]}],
    }


class TestResolveZoneEntry:
    def test_no_video_resolves_to_nothing(self):
        assert ZoneManager().resolve_zone_entry({}, None) == (None, None)
        assert ZoneManager().resolve_zone_entry({}, "") == (None, None)

    def test_normalized_key_is_returned_with_its_entry(self, tmp_path):
        video = tmp_path / "Dia_1" / "a.mp4"
        stored = {"polygon": ARENA}
        project = {"zones_by_video": {_norm(video): stored}}

        assert ZoneManager().resolve_zone_entry(project, video) == (_norm(video), stored)

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="backslash and case equivalence of paths only holds on Windows",
    )
    def test_raw_key_spelled_differently_is_found_by_normalized_comparison(self, tmp_path):
        video = tmp_path / "Dia_1" / "A.mp4"
        raw_key = str(video).replace("/", "\\").upper()
        stored = {"polygon": ARENA}
        project = {"zones_by_video": {raw_key: stored}}

        key, entry = ZoneManager().resolve_zone_entry(project, str(video))

        assert key == raw_key
        assert entry is stored

    def test_exact_string_key_wins_when_normalization_differs(self, tmp_path):
        relative = "relative/video.mp4"
        stored = {"polygon": OTHER_ARENA}
        project = {"zones_by_video": {str(Path(relative)): stored}}

        key, entry = ZoneManager().resolve_zone_entry(project, relative)

        assert key == str(Path(relative))
        assert entry is stored

    def test_unknown_video_returns_its_normalized_key_and_no_entry(self, tmp_path):
        video = tmp_path / "missing.mp4"
        project = {"zones_by_video": {_norm(tmp_path / "other.mp4"): {}}}  # type: ignore[var-annotated]

        assert ZoneManager().resolve_zone_entry(project, video) == (_norm(video), None)


class TestDeduplicateZoneKeys:
    def test_other_spellings_of_the_preferred_path_are_removed(self, tmp_path):
        video = tmp_path / "a.mp4"
        sibling = tmp_path / "b.mp4"
        preferred = _norm(video)
        zones = {
            preferred: {"keep": 1},
            str(video).upper(): {"drop": 1},
            _norm(sibling): {"sibling": 1},
        }
        project = {"zones_by_video": zones}

        ZoneManager.deduplicate_zone_keys(project, preferred)

        assert zones == {preferred: {"keep": 1}, _norm(sibling): {"sibling": 1}}

    def test_without_a_preferred_key_nothing_is_touched(self, tmp_path):
        zones = {"x": {}, "X": {}}  # type: ignore[var-annotated]
        project = {"zones_by_video": zones}

        ZoneManager.deduplicate_zone_keys(project, None)

        assert zones == {"x": {}, "X": {}}


class TestUpdateVideoZoneFlags:
    def test_root_videos_dict_entry_gets_flags_and_is_reopened(self, tmp_path):
        video = tmp_path / "v.mp4"
        entry = {"path": str(video), "zones_finalized": True}
        project = {"videos": {"id1": {"path": ""}, "id2": entry}}

        ZoneManager.update_video_zone_flags(project, video, _zone(rois=[ROI], names=["r"]))

        assert entry == {
            "path": str(video),
            "has_arena": True,
            "has_rois": True,
            "zones_finalized": False,
        }

    def test_batch_entry_is_matched_by_path_and_others_untouched(self, tmp_path):
        target = tmp_path / "Dia_2" / "CECT_4" / "CECT_4.mp4"
        homonym = tmp_path / "Dia_1" / "CECT_4" / "CECT_4.mp4"
        project = _batch_project("pre-recorded", homonym, target)

        ZoneManager.update_video_zone_flags(project, target, _zone())

        day1, day2 = project["batches"][0]["videos"]
        assert day1 == {"path": str(homonym)}
        assert day2 == {
            "path": str(target),
            "has_arena": True,
            "has_rois": False,
            "zones_finalized": False,
        }

    def test_multi_aquarium_flags_come_from_any_aquarium(self, tmp_path):
        video = tmp_path / "v.mp4"
        project = _batch_project("pre-recorded", video)
        data = MultiAquariumZoneData(
            aquariums=[
                AquariumData(id=0, polygon=ARENA),
                AquariumData(id=1, roi_polygons=[ROI]),
            ]
        )

        ZoneManager.update_video_zone_flags(project, video, data)

        entry = project["batches"][0]["videos"][0]
        assert (entry["has_arena"], entry["has_rois"]) == (True, True)

    def test_live_project_without_entry_stores_flags_at_the_root(self, tmp_path):
        project = {"project_type": "live", "batches": []}

        ZoneManager.update_video_zone_flags(
            project, tmp_path / "live_camera_reference_frame.png", _zone(polygon=[])
        )

        assert (project["has_arena"], project["has_rois"]) == (False, False)

    def test_unregistered_video_in_a_pre_recorded_project_changes_nothing(self, tmp_path):
        known = tmp_path / "known.mp4"
        project = _batch_project("pre-recorded", known)

        ZoneManager.update_video_zone_flags(project, tmp_path / "stranger.mp4", _zone())

        assert project == _batch_project("pre-recorded", known)

    def test_clearing_flags_with_none_zone_data(self, tmp_path):
        video = tmp_path / "v.mp4"
        project = _batch_project("pre-recorded", video)
        project["batches"][0]["videos"][0].update(has_arena=True, has_rois=True)

        ZoneManager.update_video_zone_flags(project, video, None)

        entry = project["batches"][0]["videos"][0]
        assert (entry["has_arena"], entry["has_rois"]) == (False, False)


class TestShouldMirrorToGlobal:
    @pytest.mark.parametrize(
        ("project_type", "target", "expected"),
        [
            ("pre-recorded", None, True),
            ("pre-recorded", "", True),
            (None, "v.mp4", True),
            ("   ", "v.mp4", True),
            (3, "v.mp4", True),
            ("live", "v.mp4", True),
            ("  LIVE ", "v.mp4", True),
            ("pre-recorded", "v.mp4", False),
            ("batch", "v.mp4", False),
        ],
    )
    def test_only_a_declared_non_live_project_with_a_target_skips_the_mirror(
        self, project_type, target, expected
    ):
        project = {} if project_type is None else {"project_type": project_type}

        assert ZoneManager.should_mirror_to_global(project, target) is expected


class TestSaveZoneDataMirror:
    def test_pre_recorded_save_keeps_the_previous_global_and_stores_per_video(self, tmp_path):
        video = tmp_path / "Dia_1" / "a.mp4"
        project = _batch_project("pre-recorded", video)
        previous_global = ZoneManager.zone_data_to_dict(_zone(polygon=OTHER_ARENA))
        project["detection_zones"] = previous_global
        calls: list[str] = []

        ZoneManager().save_zone_data(
            project, _zone(), video, persist_callback=lambda: calls.append("saved")
        )

        assert project["detection_zones"] == previous_global
        assert project["zones_by_video"] == {_norm(video): ZoneManager.zone_data_to_dict(_zone())}
        assert project["batches"][0]["videos"][0]["has_arena"] is True
        assert calls == ["saved"]

    def test_pre_recorded_arena_of_one_video_does_not_become_another_videos_arena(self, tmp_path):
        day1 = tmp_path / "Dia_1" / "CECT_4" / "CECT_4.mp4"
        day2 = tmp_path / "Dia_2" / "CECT_4" / "CECT_4.mp4"
        project = _batch_project("pre-recorded", day1, day2)
        manager = ZoneManager()

        manager.save_zone_data(project, _zone(), day2)

        assert manager.get_zone_data(project, day2).polygon == ARENA
        assert manager.get_zone_data(project, day1).polygon == []
        assert manager.get_zone_data(project, day1, fallback_to_global=False).polygon == []

    def test_live_save_mirrors_the_video_zones_into_the_global(self, tmp_path):
        reference = tmp_path / "live_camera_reference_frame.png"
        project = {"project_type": "live"}

        ZoneManager().save_zone_data(project, _zone(rois=[ROI], names=["toca"]), reference)

        expected = ZoneManager.zone_data_to_dict(_zone(rois=[ROI], names=["toca"]))
        assert project["detection_zones"] == expected
        assert project["zones_by_video"][_norm(reference)] == expected  # type: ignore[index]
        assert (project["has_arena"], project["has_rois"]) == (True, True)

    def test_without_project_type_the_legacy_mirror_is_kept(self, tmp_path):
        video = tmp_path / "single.mp4"
        project: dict = {}

        ZoneManager().save_zone_data(project, _zone(), video)

        assert project["detection_zones"]["polygon"] == ARENA
        assert project["zones_by_video"][_norm(video)]["polygon"] == ARENA

    def test_save_without_any_target_writes_only_the_global(self):
        project = {"project_type": "pre-recorded"}

        ZoneManager().save_zone_data(project, _zone())

        assert project["detection_zones"]["polygon"] == ARENA  # type: ignore[index]
        assert project["zones_by_video"] == {}

    def test_save_uses_the_active_video_when_none_is_given(self, tmp_path):
        video = tmp_path / "active.mp4"
        project = {"project_type": "pre-recorded"}
        manager = ZoneManager()
        manager.set_active_zone_video(project, video)

        manager.save_zone_data(project, _zone(polygon=OTHER_ARENA))

        assert project["zones_by_video"][_norm(video)]["polygon"] == OTHER_ARENA  # type: ignore[index]
        assert manager.get_last_zone_video(project) == _norm(video)

    def test_multi_aquarium_save_goes_to_its_registry_and_never_to_the_global(self, tmp_path):
        video = tmp_path / "two_tanks.mp4"
        project: dict = {"project_type": "live"}
        calls: list[int] = []
        data = MultiAquariumZoneData(
            aquariums=[AquariumData(id=0, polygon=ARENA), AquariumData(id=1, polygon=OTHER_ARENA)]
        )

        ZoneManager().save_zone_data(project, data, video, persist_callback=lambda: calls.append(1))  # type: ignore[arg-type]

        assert project["detection_zones"] == {}
        assert [
            a["polygon"] for a in project["multi_aquarium_zones"][_norm(video)]["aquariums"]
        ] == [
            ARENA,
            OTHER_ARENA,
        ]
        assert calls == [1]


class TestGetZoneDataAndClone:
    def test_aquarium_zero_shim_versus_the_full_multi_aquarium_data(self, tmp_path):
        video = tmp_path / "two_tanks.mp4"
        project: dict = {}
        manager = ZoneManager()
        data = MultiAquariumZoneData(
            aquariums=[AquariumData(id=0, polygon=ARENA), AquariumData(id=1, polygon=OTHER_ARENA)]
        )
        manager.save_multi_aquarium_zone_data(project, video, data)

        assert manager.get_zone_data(project, video).polygon == ARENA
        multi = manager.get_multi_aquarium_zone_data(project, video)
        assert [aq.polygon for aq in multi.aquariums] == [ARENA, OTHER_ARENA]  # type: ignore[union-attr]

    def test_no_target_and_no_active_video_serves_the_global(self):
        project = {"detection_zones": ZoneManager.zone_data_to_dict(_zone(polygon=OTHER_ARENA))}

        assert ZoneManager().get_zone_data(project).polygon == OTHER_ARENA

    def test_clone_is_a_deep_copy(self, tmp_path):
        video = tmp_path / "v.mp4"
        project: dict = {}
        manager = ZoneManager()
        manager.save_zone_data(project, _zone(), video)

        clone = manager.clone_zone_data_from_video(project, video)
        clone.polygon[0][0] = 999  # type: ignore[index]

        assert clone.polygon[1:] == ARENA[1:]
        assert project["zones_by_video"][_norm(video)]["polygon"][0] == ARENA[0]

    def test_has_zone_data_is_false_for_an_empty_stored_entry(self, tmp_path):
        video = tmp_path / "v.mp4"
        project = {"zones_by_video": {_norm(video): ZoneManager.zone_data_to_dict(ZoneData())}}
        manager = ZoneManager()

        assert manager.has_zone_data(project, video) is False
        assert manager.has_zone_data(project, None) is False
        project["zones_by_video"][_norm(video)]["roi_polygons"] = [ROI]
        assert manager.has_zone_data(project, str(video)) is True


class TestActiveVideoAndLastSource:
    def test_activating_rekeys_a_raw_entry_and_loads_it_as_the_global(self, tmp_path):
        video = tmp_path / "v.mp4"
        raw_key = str(video).upper()
        stored = ZoneManager.zone_data_to_dict(_zone(polygon=OTHER_ARENA))
        project = {"zones_by_video": {raw_key: stored}}
        manager = ZoneManager()

        manager.set_active_zone_video(project, str(video))

        assert project["zones_by_video"] == {_norm(video): stored}
        assert project["detection_zones"] == stored
        assert project["detection_zones"] is not stored
        assert manager.get_active_zone_video() == _norm(video)
        assert manager.get_last_zone_video(project) == _norm(video)

    def test_activating_a_video_without_zones_empties_the_global(self, tmp_path):
        project = {"detection_zones": ZoneManager.zone_data_to_dict(_zone())}
        manager = ZoneManager()

        manager.set_active_zone_video(project, tmp_path / "new.mp4")

        assert project["detection_zones"] == ZoneManager.zone_data_to_dict(None)
        assert manager.get_active_zone_video() == _norm(tmp_path / "new.mp4")

    def test_none_clears_the_active_video(self, tmp_path):
        manager = ZoneManager()
        manager.set_active_zone_video({}, tmp_path / "v.mp4")

        manager.set_active_zone_video({}, None)

        assert manager.get_active_zone_video() is None

    def test_reset_active_context_forgets_both_pointers(self, tmp_path):
        project: dict = {}
        manager = ZoneManager()
        manager.save_zone_data(project, _zone(), tmp_path / "v.mp4")
        manager.set_active_zone_video(project, tmp_path / "v.mp4")

        manager.reset_active_context()

        assert manager.get_active_zone_video() is None
        assert manager._last_zone_source_video is None

    def test_last_zone_video_skips_the_excluded_one(self, tmp_path):
        first, second = tmp_path / "a.mp4", tmp_path / "b.mp4"
        project: dict = {}
        manager = ZoneManager()
        manager.save_zone_data(project, _zone(), first)
        manager.save_zone_data(project, _zone(), second)

        assert manager.get_last_zone_video(project) == _norm(second)
        assert manager.get_last_zone_video(project, exclude=str(second)) == _norm(first)
        assert manager.get_last_zone_video({"zones_by_video": {}}) is None

    def test_refresh_after_removal_falls_back_to_the_newest_remaining(self, tmp_path):
        first, second, third = (tmp_path / f"{n}.mp4" for n in "abc")
        project: dict = {}
        manager = ZoneManager()
        for video in (first, second, third):
            manager.save_zone_data(project, _zone(), video)
        del project["zones_by_video"][_norm(third)]

        manager.refresh_last_zone_source(project, removed_path=str(third))

        assert manager._last_zone_source_video == _norm(second)

    def test_refresh_keeps_a_last_source_that_still_exists(self, tmp_path):
        first, second = tmp_path / "a.mp4", tmp_path / "b.mp4"
        project: dict = {}
        manager = ZoneManager()
        manager.save_zone_data(project, _zone(), first)
        manager.save_zone_data(project, _zone(), second)
        manager._last_zone_source_video = _norm(first)

        manager.refresh_last_zone_source(project, removed_path=tmp_path / "other.mp4")

        assert manager._last_zone_source_video == _norm(first)

    def test_refresh_with_no_zones_left_clears_the_pointer(self, tmp_path):
        manager = ZoneManager()
        manager._last_zone_source_video = "gone"

        manager.refresh_last_zone_source({"zones_by_video": {}})

        assert manager._last_zone_source_video is None


class TestClearZoneDataForVideo:
    def test_clearing_the_active_video_resets_global_flags_and_persists(self, tmp_path):
        video = tmp_path / "v.mp4"
        keep = tmp_path / "keep.mp4"
        project = _batch_project("live", video, keep)
        manager = ZoneManager()
        manager.save_zone_data(project, _zone(), keep)
        manager.save_zone_data(project, _zone(), video)
        manager.set_active_zone_video(project, video)
        calls: list[int] = []

        manager.clear_zone_data_for_video(
            project, str(video), persist_callback=lambda: calls.append(1)
        )

        assert list(project["zones_by_video"]) == [_norm(keep)]
        assert project["detection_zones"] == ZoneManager.zone_data_to_dict(None)
        assert project["batches"][0]["videos"][0]["has_arena"] is False
        assert manager.get_last_zone_video(project) == _norm(keep)
        assert calls == [1]

    def test_clearing_an_inactive_video_keeps_the_global(self, tmp_path):
        video, active = tmp_path / "v.mp4", tmp_path / "active.mp4"
        project: dict = {}
        manager = ZoneManager()
        manager.save_zone_data(project, _zone(), video)
        manager.set_active_zone_video(project, active)
        manager.save_zone_data(project, _zone(polygon=OTHER_ARENA))

        manager.clear_zone_data_for_video(project, video)

        assert project["detection_zones"]["polygon"] == OTHER_ARENA


class TestUpdateMainPolygon:
    def test_empty_project_data_raises(self):
        with pytest.raises(ValueError):
            ZoneManager().update_main_polygon({}, ARENA)

    def test_polygon_replaces_the_active_video_arena_and_keeps_rois(self, tmp_path):
        video = tmp_path / "v.mp4"
        project = {"project_type": "pre-recorded"}
        manager = ZoneManager()
        manager.save_zone_data(project, _zone(rois=[ROI], names=["r"]), video)
        manager.set_active_zone_video(project, video)
        calls: list[int] = []

        manager.update_main_polygon(project, OTHER_ARENA, persist_callback=lambda: calls.append(1))

        stored = manager.get_zone_data(project, video)
        assert stored.polygon == OTHER_ARENA
        assert stored.roi_polygons == [ROI]
        assert calls == [1]


class TestLoadZonesFromParquet:
    @staticmethod
    def _write(path, rows):
        import pandas as pd

        pd.DataFrame(rows).to_parquet(path)
        return str(path)

    def test_arena_and_rois_are_rebuilt_in_point_order_with_cycled_colors(self, tmp_path):
        arena = self._write(tmp_path / "1.parquet", {"x": [1, 2, 3], "y": [4, 5, 6]})
        names = [f"r{i}" for i in range(7)]
        rows = {"roi_name": [], "point_index": [], "x": [], "y": []}  # type: ignore[var-annotated]
        for i, name in enumerate(names):
            for idx in (2, 0, 1):
                rows["roi_name"].append(name)
                rows["point_index"].append(idx)
                rows["x"].append(i * 10 + idx)
                rows["y"].append(idx)
        rois = self._write(tmp_path / "2.parquet", rows)

        zone = ZoneManager.load_zones_from_parquet(
            {"parquet_files": {"arena": arena, "rois": rois}}
        )

        assert zone.polygon == [[1, 4], [2, 5], [3, 6]]  # type: ignore[union-attr]
        assert zone.roi_names == names  # type: ignore[union-attr]
        assert zone.roi_polygons[3] == [[30, 0], [31, 1], [32, 2]]  # type: ignore[union-attr]
        assert zone.roi_colors[0] == zone.roi_colors[6] == (0, 128, 0)  # type: ignore[union-attr]
        assert zone.roi_colors[1:6] == [  # type: ignore[union-attr]
            (255, 0, 0),
            (0, 0, 255),
            (0, 204, 204),
            (255, 0, 255),
            (0, 255, 255),
        ]

    def test_files_with_the_wrong_columns_load_as_empty_zones(self, tmp_path):
        arena = self._write(tmp_path / "1.parquet", {"a": [1], "b": [2]})
        rois = self._write(tmp_path / "2.parquet", {"roi_name": ["r"], "x": [1]})

        zone = ZoneManager.load_zones_from_parquet(
            {"parquet_files": {"arena": arena, "rois": rois}}
        )

        assert (zone.polygon, zone.roi_polygons, zone.roi_names) == ([], [], [])  # type: ignore[union-attr]

    def test_empty_rois_file_and_missing_arena_file(self, tmp_path):
        import pandas as pd

        rois = tmp_path / "2.parquet"
        pd.DataFrame({"roi_name": [], "point_index": [], "x": [], "y": []}).to_parquet(rois)

        zone = ZoneManager.load_zones_from_parquet(
            {"parquet_files": {"arena": str(tmp_path / "absent.parquet"), "rois": str(rois)}}
        )

        assert zone == ZoneData()

    def test_no_zone_files_returns_none(self):
        assert ZoneManager.load_zones_from_parquet({"path": "v.mp4", "parquet_files": {}}) is None
        assert ZoneManager.load_zones_from_parquet({}) is None

    def test_corrupt_parquet_returns_none(self, tmp_path):
        broken = tmp_path / "1.parquet"
        broken.write_bytes(b"not a parquet file")

        assert (
            ZoneManager.load_zones_from_parquet({"parquet_files": {"arena": str(broken)}}) is None
        )


class TestMultiAquariumRegistryEdges:
    def test_failed_serialization_reports_false_and_stores_nothing(self, tmp_path):
        project: dict = {}
        broken = MultiAquariumZoneData(aquariums=[object()])  # type: ignore[list-item]

        assert (
            ZoneManager().save_multi_aquarium_zone_data(project, tmp_path / "v.mp4", broken)
            is False
        )
        assert project["multi_aquarium_zones"] == {}

    def test_saving_without_aquariums_leaves_the_single_zone_shim_alone(self, tmp_path):
        video = tmp_path / "v.mp4"
        project: dict = {}

        assert ZoneManager().save_multi_aquarium_zone_data(project, video, MultiAquariumZoneData())
        assert project["zones_by_video"] == {}
        assert project["multi_aquarium_zones"][_norm(video)]["aquariums"] == []

    def test_lookup_and_clear_reach_raw_and_differently_spelled_keys(self, tmp_path):
        video = tmp_path / "v.mp4"
        serialized = ZoneManager.multi_aquarium_zone_data_to_dict(
            MultiAquariumZoneData(aquariums=[AquariumData(id=0, polygon=ARENA)])
        )
        manager = ZoneManager()
        for key in (str(Path("rel/v.mp4")), str(video).upper()):
            lookup = "rel/v.mp4" if key.startswith("rel") else str(video)
            project = {"multi_aquarium_zones": {key: dict(serialized)}}

            assert (
                manager.get_multi_aquarium_zone_data(project, lookup).aquariums[0].polygon == ARENA  # type: ignore[union-attr]
            )

            manager.clear_multi_aquarium_zone_data(project, lookup)
            assert project["multi_aquarium_zones"] == {}

    def test_unknown_video_with_registry_present_returns_none(self, tmp_path):
        project = {"multi_aquarium_zones": {_norm(tmp_path / "a.mp4"): {"aquariums": []}}}  # type: ignore[var-annotated]

        assert ZoneManager().get_multi_aquarium_zone_data(project, tmp_path / "b.mp4") is None

    def test_clear_of_an_unknown_video_still_persists(self, tmp_path):
        project = {"multi_aquarium_zones": {"x": {}}}  # type: ignore[var-annotated]
        calls: list[int] = []

        ZoneManager().clear_multi_aquarium_zone_data(
            project, tmp_path / "b.mp4", persist_callback=lambda: calls.append(1)
        )

        assert project["multi_aquarium_zones"] == {"x": {}}
        assert calls == [1]
