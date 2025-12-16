"""Unit tests for multi-aquarium data models.

Tests the new dataclasses (AquariumData, MultiAquariumZoneData) and
Pydantic models (AquariumConfig, MultiAquariumData) introduced for
multi-aquarium support.

Coverage target: 80%+
"""

import pytest
from pydantic import ValidationError

from zebtrack.core.detector import AquariumData, MultiAquariumZoneData, ZoneData
from zebtrack.ui.wizard.models import AquariumConfig, CalibrationData, MultiAquariumData


class TestAquariumData:
    """Tests for the AquariumData dataclass."""

    def test_creation_with_defaults(self):
        """Testa criação com valores padrão."""
        aquarium = AquariumData(id=0)

        assert aquarium.id == 0
        assert aquarium.polygon == []
        assert aquarium.roi_polygons == []
        assert aquarium.roi_names == []
        assert aquarium.roi_colors == []
        assert aquarium.group == ""
        assert aquarium.subject_id == ""
        assert aquarium.day == 0

    def test_creation_with_all_fields(self):
        """Testa criação com todos os campos."""
        polygon = [[0, 0], [100, 0], [100, 100], [0, 100]]
        roi_polygons = [[[10, 10], [50, 10], [50, 50], [10, 50]]]
        roi_names = ["ROI1"]
        roi_colors = [(255, 0, 0)]

        aquarium = AquariumData(
            id=1,
            polygon=polygon,
            roi_polygons=roi_polygons,
            roi_names=roi_names,
            roi_colors=roi_colors,
            group="Tratamento",
            subject_id="S01",
            day=3,
        )

        assert aquarium.id == 1
        assert aquarium.polygon == polygon
        assert aquarium.roi_polygons == roi_polygons
        assert aquarium.roi_names == roi_names
        assert aquarium.roi_colors == roi_colors
        assert aquarium.group == "Tratamento"
        assert aquarium.subject_id == "S01"
        assert aquarium.day == 3

    def test_to_zone_data_conversion(self):
        """Testa conversão para ZoneData."""
        polygon = [[0, 0], [100, 0], [100, 100], [0, 100]]
        roi_polygons = [[[10, 10], [50, 10], [50, 50], [10, 50]]]
        roi_names = ["ROI1"]
        roi_colors = [(255, 0, 0)]

        aquarium = AquariumData(
            id=0,
            polygon=polygon,
            roi_polygons=roi_polygons,
            roi_names=roi_names,
            roi_colors=roi_colors,
            group="Controle",
            subject_id="S02",
            day=1,
        )

        zone_data = aquarium.to_zone_data()

        assert isinstance(zone_data, ZoneData)
        assert zone_data.polygon == polygon
        assert zone_data.roi_polygons == roi_polygons
        assert zone_data.roi_names == roi_names
        assert zone_data.roi_colors == roi_colors

    def test_polygon_with_multiple_points(self):
        """Testa polígonos com múltiplos pontos (forma irregular)."""
        polygon = [
            [0, 0],
            [50, 0],
            [100, 50],
            [100, 100],
            [50, 100],
            [0, 50],
        ]

        aquarium = AquariumData(id=0, polygon=polygon)
        assert len(aquarium.polygon) == 6
        assert aquarium.polygon[0] == [0, 0]
        assert aquarium.polygon[-1] == [0, 50]


class TestMultiAquariumZoneData:
    """Tests for the MultiAquariumZoneData dataclass."""

    @pytest.fixture
    def two_aquariums(self):
        """Fixture com 2 aquários configurados."""
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

    def test_creation_with_defaults(self):
        """Testa criação com valores padrão."""
        zone_data = MultiAquariumZoneData()

        assert zone_data.aquariums == []
        assert zone_data.video_width == 0
        assert zone_data.video_height == 0

    def test_get_aquarium_existing(self, two_aquariums):
        """Testa busca de aquário existente."""
        aquarium_0 = two_aquariums.get_aquarium(0)
        aquarium_1 = two_aquariums.get_aquarium(1)

        assert aquarium_0 is not None
        assert aquarium_0.id == 0
        assert aquarium_0.group == "Controle"

        assert aquarium_1 is not None
        assert aquarium_1.id == 1
        assert aquarium_1.group == "Tratamento"

    def test_get_aquarium_not_found(self, two_aquariums):
        """Testa busca de aquário inexistente."""
        result = two_aquariums.get_aquarium(99)
        assert result is None

    def test_get_aquarium_empty_list(self):
        """Testa busca em lista vazia."""
        zone_data = MultiAquariumZoneData()
        result = zone_data.get_aquarium(0)
        assert result is None

    def test_to_zone_data_conversion(self, two_aquariums):
        """Testa conversão para ZoneData."""
        zone_data_0 = two_aquariums.to_zone_data(0)
        zone_data_1 = two_aquariums.to_zone_data(1)

        assert isinstance(zone_data_0, ZoneData)
        assert zone_data_0.polygon == [[0, 0], [300, 0], [300, 400], [0, 400]]

        assert isinstance(zone_data_1, ZoneData)
        assert zone_data_1.polygon == [[350, 0], [650, 0], [650, 400], [350, 400]]

    def test_to_zone_data_not_found_returns_empty(self, two_aquariums):
        """Testa que to_zone_data retorna ZoneData vazio se ID não existe."""
        zone_data = two_aquariums.to_zone_data(99)

        assert isinstance(zone_data, ZoneData)
        assert zone_data.polygon == []
        assert zone_data.roi_polygons == []

    def test_aquarium_count_property(self, two_aquariums):
        """Testa propriedade aquarium_count."""
        assert two_aquariums.aquarium_count == 2

        empty_data = MultiAquariumZoneData()
        assert empty_data.aquarium_count == 0

    def test_is_multi_aquarium_property(self, two_aquariums):
        """Testa propriedade is_multi_aquarium."""
        assert two_aquariums.is_multi_aquarium is True

        single_aquarium = MultiAquariumZoneData(
            aquariums=[AquariumData(id=0)],
            video_width=1280,
            video_height=720,
        )
        assert single_aquarium.is_multi_aquarium is False

        empty_data = MultiAquariumZoneData()
        assert empty_data.is_multi_aquarium is False

    def test_video_dimensions(self, two_aquariums):
        """Testa armazenamento de dimensões do vídeo."""
        assert two_aquariums.video_width == 1280
        assert two_aquariums.video_height == 720


class TestAquariumConfigPydantic:
    """Tests for the AquariumConfig Pydantic model."""

    def test_valid_config(self):
        """Testa configuração válida."""
        config = AquariumConfig(
            aquarium_id=0,
            group="Controle",
            subject_id="S01",
            day=1,
        )

        assert config.aquarium_id == 0
        assert config.group == "Controle"
        assert config.subject_id == "S01"
        assert config.day == 1

    def test_valid_config_minimal(self):
        """Testa configuração com campos mínimos."""
        config = AquariumConfig(aquarium_id=1, group="Tratamento")

        assert config.aquarium_id == 1
        assert config.group == "Tratamento"
        assert config.subject_id == ""
        assert config.day == 1  # default

    def test_invalid_aquarium_id_negative(self):
        """Testa ID de aquário negativo."""
        with pytest.raises(ValidationError) as exc_info:
            AquariumConfig(aquarium_id=-1, group="Controle")

        assert "aquarium_id" in str(exc_info.value)

    def test_invalid_aquarium_id_too_high(self):
        """Testa ID de aquário maior que 1."""
        with pytest.raises(ValidationError) as exc_info:
            AquariumConfig(aquarium_id=2, group="Controle")

        assert "aquarium_id" in str(exc_info.value)

    def test_invalid_empty_group(self):
        """Testa grupo vazio."""
        with pytest.raises(ValidationError) as exc_info:
            AquariumConfig(aquarium_id=0, group="")

        assert "group" in str(exc_info.value).lower()

    def test_invalid_whitespace_only_group(self):
        """Testa grupo com apenas espaços."""
        with pytest.raises(ValidationError) as exc_info:
            AquariumConfig(aquarium_id=0, group="   ")

        assert "grupo" in str(exc_info.value).lower() or "group" in str(exc_info.value).lower()

    def test_invalid_day_zero(self):
        """Testa dia zero."""
        with pytest.raises(ValidationError) as exc_info:
            AquariumConfig(aquarium_id=0, group="Controle", day=0)

        assert "day" in str(exc_info.value)

    def test_group_is_stripped(self):
        """Testa que grupo é trimmed."""
        config = AquariumConfig(aquarium_id=0, group="  Controle  ")
        assert config.group == "Controle"


class TestMultiAquariumDataPydantic:
    """Tests for the MultiAquariumData Pydantic model."""

    def test_disabled_by_default(self):
        """Testa que modo está desabilitado por padrão."""
        data = MultiAquariumData()

        assert data.enabled is False
        assert data.aquarium_configs == []
        assert data.regex_pattern == ""

    def test_valid_enabled_with_two_configs(self):
        """Testa configuração válida habilitada."""
        data = MultiAquariumData(
            enabled=True,
            aquarium_configs=[
                AquariumConfig(aquarium_id=0, group="Controle"),
                AquariumConfig(aquarium_id=1, group="Tratamento"),
            ],
        )

        assert data.enabled is True
        assert len(data.aquarium_configs) == 2

    def test_invalid_enabled_without_configs(self):
        """Testa que enabled=True requer 2 configurações."""
        with pytest.raises(ValidationError) as exc_info:
            MultiAquariumData(enabled=True, aquarium_configs=[])

        assert "2" in str(exc_info.value)

    def test_invalid_enabled_with_one_config(self):
        """Testa que enabled=True requer exatamente 2 configurações."""
        with pytest.raises(ValidationError) as exc_info:
            MultiAquariumData(
                enabled=True,
                aquarium_configs=[AquariumConfig(aquarium_id=0, group="Controle")],
            )

        assert "2" in str(exc_info.value)

    def test_invalid_more_than_two_configs(self):
        """Testa que não aceita mais de 2 configurações."""
        with pytest.raises(ValidationError) as exc_info:
            MultiAquariumData(
                enabled=True,
                aquarium_configs=[
                    AquariumConfig(aquarium_id=0, group="A"),
                    AquariumConfig(aquarium_id=1, group="B"),
                    AquariumConfig(aquarium_id=0, group="C"),  # extra
                ],
            )

        assert "2" in str(exc_info.value) or "máximo" in str(exc_info.value).lower()

    def test_valid_regex_pattern(self):
        """Testa padrão regex válido."""
        data = MultiAquariumData(regex_pattern=r"(?P<group>\w+)_(?P<subject>S\d+)_D(?P<day>\d+)")

        assert data.regex_pattern == r"(?P<group>\w+)_(?P<subject>S\d+)_D(?P<day>\d+)"

    def test_invalid_regex_pattern(self):
        """Testa padrão regex inválido."""
        with pytest.raises(ValidationError) as exc_info:
            MultiAquariumData(regex_pattern=r"[invalid(regex")

        assert "regex" in str(exc_info.value).lower()

    def test_regex_extraction_success(self):
        """Testa extração de metadados via regex."""
        data = MultiAquariumData(
            regex_pattern=r"(?P<group>\w+)_(?P<subject>S\d+)_D(?P<day>\d+)",
            regex_group_field="group",
            regex_subject_field="subject",
            regex_day_field="day",
        )

        result = data.extract_metadata("Controle_S01_D3.mp4")

        assert result["group"] == "Controle"
        assert result["subject"] == "S01"
        assert result["day"] == "3"

    def test_regex_extraction_no_match(self):
        """Testa extração quando regex não faz match."""
        data = MultiAquariumData(regex_pattern=r"(?P<group>\w+)_(?P<subject>S\d+)_D(?P<day>\d+)")

        result = data.extract_metadata("video_sem_padrao.mp4")

        assert result["group"] == ""
        assert result["subject"] == ""
        assert result["day"] == ""

    def test_regex_extraction_no_pattern(self):
        """Testa extração sem padrão definido."""
        data = MultiAquariumData()

        result = data.extract_metadata("qualquer_arquivo.mp4")

        assert result["group"] == ""
        assert result["subject"] == ""
        assert result["day"] == ""

    def test_regex_extraction_partial_match(self):
        """Testa extração com match parcial."""
        data = MultiAquariumData(
            regex_pattern=r"(?P<group>\w+)_(?P<subject>S\d+)?",
            regex_group_field="group",
            regex_subject_field="subject",
            regex_day_field="day",
        )

        result = data.extract_metadata("Tratamento_video.mp4")

        assert result["group"] == "Tratamento"
        assert result["subject"] == ""  # Não capturado
        assert result["day"] == ""


class TestCalibrationDataWithMultiAquarium:
    """Tests for CalibrationData with multi_aquarium field."""

    def test_default_multi_aquarium(self):
        """Testa que CalibrationData tem multi_aquarium por padrão."""
        calibration = CalibrationData(
            num_aquariums=1,
            animals_per_aquarium=1,
            aquarium_width_cm=10.0,
            aquarium_height_cm=5.0,
        )

        assert isinstance(calibration.multi_aquarium, MultiAquariumData)
        assert calibration.multi_aquarium.enabled is False

    def test_with_multi_aquarium_enabled(self):
        """Testa CalibrationData com multi_aquarium habilitado."""
        calibration = CalibrationData(
            num_aquariums=2,
            animals_per_aquarium=1,
            aquarium_width_cm=10.0,
            aquarium_height_cm=5.0,
            multi_aquarium=MultiAquariumData(
                enabled=True,
                aquarium_configs=[
                    AquariumConfig(aquarium_id=0, group="Controle"),
                    AquariumConfig(aquarium_id=1, group="Tratamento"),
                ],
            ),
        )

        assert calibration.multi_aquarium.enabled is True
        assert len(calibration.multi_aquarium.aquarium_configs) == 2

    def test_serialization_with_multi_aquarium(self):
        """Testa serialização para dict com multi_aquarium."""
        calibration = CalibrationData(
            num_aquariums=2,
            animals_per_aquarium=1,
            aquarium_width_cm=10.0,
            aquarium_height_cm=5.0,
            multi_aquarium=MultiAquariumData(
                enabled=True,
                aquarium_configs=[
                    AquariumConfig(aquarium_id=0, group="Controle", day=1),
                    AquariumConfig(aquarium_id=1, group="Tratamento", day=2),
                ],
                regex_pattern=r"(?P<group>\w+)",
            ),
        )

        data_dict = calibration.model_dump()

        assert "multi_aquarium" in data_dict
        assert data_dict["multi_aquarium"]["enabled"] is True
        assert len(data_dict["multi_aquarium"]["aquarium_configs"]) == 2
        assert data_dict["multi_aquarium"]["regex_pattern"] == r"(?P<group>\w+)"

    def test_deserialization_from_dict(self):
        """Testa deserialização de dict."""
        data = {
            "num_aquariums": 2,
            "animals_per_aquarium": 1,
            "aquarium_width_cm": 10.0,
            "aquarium_height_cm": 5.0,
            "multi_aquarium": {
                "enabled": True,
                "aquarium_configs": [
                    {"aquarium_id": 0, "group": "Controle", "subject_id": "S01", "day": 1},
                    {"aquarium_id": 1, "group": "Tratamento", "subject_id": "S02", "day": 1},
                ],
            },
        }

        calibration = CalibrationData.model_validate(data)

        assert calibration.multi_aquarium.enabled is True
        assert calibration.multi_aquarium.aquarium_configs[0].group == "Controle"
        assert calibration.multi_aquarium.aquarium_configs[1].group == "Tratamento"
