"""Unit tests for ZoneManager multi-aquarium support.

Tests the new methods for storing and retrieving MultiAquariumZoneData
in project configurations.

Coverage target: 80%+
"""

import pytest

from zebtrack.core.detector import AquariumData, MultiAquariumZoneData, ZoneData
from zebtrack.core.zone_manager import ZoneManager


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
        project_data = {}
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
        assert len(multi_zones) == 1

        # zones_by_video should have first aquarium for compatibility
        zones_by_video = project_data["zones_by_video"]
        assert len(zones_by_video) == 1

    def test_compatibility_with_standard_zone_data(self, zone_manager):
        """Testa que dados multi-aquário são compatíveis com fluxo padrão."""
        project_data = {}
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
