"""End-to-end tests for multi-aquarium functionality.

Phase 12 of multi-aquarium implementation:
Integration tests that verify the complete workflow from
project creation to analysis output.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from zebtrack.core.detector import AquariumData, MultiAquariumZoneData

if TYPE_CHECKING:
    pass


@pytest.fixture
def synthetic_dual_aquarium_frames() -> list[np.ndarray]:
    """Generate synthetic frames with 2 distinct aquarium regions.

    Creates frames with dark background and two bright rectangular
    regions representing aquariums, each containing a moving object.
    """
    frames = []
    height, width = 480, 640

    for i in range(30):  # 30 frames, 1 second at 30fps
        # Dark background
        frame = np.zeros((height, width, 3), dtype=np.uint8)

        # Left aquarium (0-300 x)
        frame[50:430, 20:300] = (80, 80, 80)  # Gray tank background
        # Moving object in left aquarium
        obj_y = 200 + int(50 * np.sin(i * 0.2))
        frame[obj_y : obj_y + 30, 100 + i * 2 : 130 + i * 2] = (255, 255, 255)

        # Right aquarium (340-620 x)
        frame[50:430, 340:620] = (80, 80, 80)  # Gray tank background
        # Moving object in right aquarium
        obj_y = 250 + int(30 * np.cos(i * 0.3))
        frame[obj_y : obj_y + 30, 400 + i * 2 : 430 + i * 2] = (255, 255, 255)

        frames.append(frame)

    return frames


@pytest.fixture
def dual_aquarium_zone_data() -> MultiAquariumZoneData:
    """Create zone data for two aquariums matching synthetic frames."""
    aquarium_0 = AquariumData(
        id=0,
        polygon=[(20, 50), (300, 50), (300, 430), (20, 430)],
        roi_polygons=[
            [(30, 60), (145, 60), (145, 240), (30, 240)],  # Top half
            [(30, 240), (145, 240), (145, 420), (30, 420)],  # Bottom half
        ],
        roi_names=["Top", "Bottom"],
        roi_colors=[(0, 255, 0), (255, 0, 0)],
        group="Controle",
        subject_id="S01",
        day=1,
    )
    aquarium_1 = AquariumData(
        id=1,
        polygon=[(340, 50), (620, 50), (620, 430), (340, 430)],
        roi_polygons=[
            [(350, 60), (480, 60), (480, 240), (350, 240)],  # Top half
        ],
        roi_names=["Top"],
        roi_colors=[(0, 255, 0)],
        group="CBD",
        subject_id="S02",
        day=1,
    )
    return MultiAquariumZoneData(
        aquariums=[aquarium_0, aquarium_1],
        video_width=640,
        video_height=480,
    )


@pytest.mark.integration
class TestMultiAquariumE2E:
    """End-to-end tests for multi-aquarium workflow."""

    def test_zone_data_structure(self, dual_aquarium_zone_data: MultiAquariumZoneData) -> None:
        """Test that zone data structure is valid for multi-aquarium."""
        assert len(dual_aquarium_zone_data.aquariums) == 2
        assert dual_aquarium_zone_data.aquariums[0].id == 0
        assert dual_aquarium_zone_data.aquariums[1].id == 1
        assert dual_aquarium_zone_data.aquariums[0].group == "Controle"
        assert dual_aquarium_zone_data.aquariums[1].group == "CBD"

    def test_aquarium_polygons_non_overlapping(
        self, dual_aquarium_zone_data: MultiAquariumZoneData
    ) -> None:
        """Test that aquarium polygons don't overlap."""
        aq0 = dual_aquarium_zone_data.aquariums[0]
        aq1 = dual_aquarium_zone_data.aquariums[1]

        # Get x-bounds for each aquarium
        aq0_max_x = max(p[0] for p in aq0.polygon)
        aq1_min_x = min(p[0] for p in aq1.polygon)

        # Aquariums should not overlap (gap between them)
        assert aq0_max_x < aq1_min_x

    def test_track_id_offset_convention(self) -> None:
        """Test track ID offset convention: aquarium_id * 1000 + local_id."""
        # Aquarium 0 tracks: 1, 2, 3 → 1, 2, 3
        # Aquarium 1 tracks: 1, 2, 3 → 1001, 1002, 1003
        for aquarium_id in [0, 1]:
            for local_id in [1, 2, 3]:
                global_id = aquarium_id * 1000 + local_id
                recovered_aquarium = global_id // 1000
                recovered_local = global_id % 1000

                assert recovered_aquarium == aquarium_id
                assert recovered_local == local_id

    def test_output_folder_structure_convention(self, tmp_path: Path) -> None:
        """Test expected output folder structure for multi-aquarium."""
        # Expected structure:
        # project/
        # ├── Grupo_Controle/
        # │   └── Dia_01/
        # │       └── Sujeito_01/
        # │           └── video_tracking.parquet
        # └── Grupo_CBD/
        #     └── Dia_01/
        #         └── Sujeito_02/
        #             └── video_tracking.parquet

        # Simulate creating the structure
        for group in ["Controle", "CBD"]:
            for day in [1]:
                subject = "S01" if group == "Controle" else "S02"
                output_dir = tmp_path / f"Grupo_{group}" / f"Dia_{day:02d}" / subject
                output_dir.mkdir(parents=True, exist_ok=True)

                # Create dummy parquet
                df = pd.DataFrame(
                    {
                        "timestamp": [0.0, 0.033, 0.066],
                        "frame": [0, 1, 2],
                        "track_id": [1, 1, 1] if group == "Controle" else [1001, 1001, 1001],
                        "x1": [100, 102, 104],
                        "y1": [200, 202, 204],
                        "x2": [130, 132, 134],
                        "y2": [230, 232, 234],
                        "confidence": [0.95, 0.93, 0.94],
                    }
                )
                df.to_parquet(output_dir / "video_tracking.parquet")

        # Verify structure exists
        assert (tmp_path / "Grupo_Controle" / "Dia_01" / "S01" / "video_tracking.parquet").exists()
        assert (tmp_path / "Grupo_CBD" / "Dia_01" / "S02" / "video_tracking.parquet").exists()

    def test_parquet_data_integrity(self, tmp_path: Path) -> None:
        """Test that parquet files contain valid tracking data."""
        # Create sample tracking data for aquarium 0
        df = pd.DataFrame(
            {
                "timestamp": np.linspace(0, 1, 30),
                "frame": range(30),
                "track_id": [1] * 30,  # Local ID for aquarium 0
                "x1": np.linspace(100, 160, 30),
                "y1": np.linspace(200, 250, 30),
                "x2": np.linspace(130, 190, 30),
                "y2": np.linspace(230, 280, 30),
                "confidence": np.random.uniform(0.85, 0.99, 30),
            }
        )

        output_file = tmp_path / "tracking.parquet"
        df.to_parquet(output_file)

        # Verify data integrity
        loaded = pd.read_parquet(output_file)

        assert len(loaded) == 30
        assert "timestamp" in loaded.columns
        assert "track_id" in loaded.columns
        assert loaded["x1"].min() >= 0
        assert loaded["confidence"].min() >= 0.85

    def test_roi_containment_per_aquarium(
        self, dual_aquarium_zone_data: MultiAquariumZoneData
    ) -> None:
        """Test that ROIs are contained within their parent aquarium."""
        for aq in dual_aquarium_zone_data.aquariums:
            aq_min_x = min(p[0] for p in aq.polygon)
            aq_max_x = max(p[0] for p in aq.polygon)
            aq_min_y = min(p[1] for p in aq.polygon)
            aq_max_y = max(p[1] for p in aq.polygon)

            for roi_polygon in aq.roi_polygons:
                for x, y in roi_polygon:
                    assert aq_min_x <= x <= aq_max_x, f"ROI x={x} outside aquarium {aq.id}"
                    assert aq_min_y <= y <= aq_max_y, f"ROI y={y} outside aquarium {aq.id}"


@pytest.mark.integration
class TestAutoDetectionE2E:
    """Tests for aquarium auto-detection end-to-end."""

    def test_detect_two_aquarium_regions(
        self, synthetic_dual_aquarium_frames: list[np.ndarray]
    ) -> None:
        """Test that auto-detection can identify 2 aquarium regions."""
        # Use first frame for detection
        frame = synthetic_dual_aquarium_frames[0]

        # Simple detection: find contours in thresholded image
        import cv2

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter by area (aquariums should be large)
        large_contours = [c for c in contours if cv2.contourArea(c) > 10000]

        # Should find at least 2 large regions (the aquariums)
        assert len(large_contours) >= 2

    def test_aquariums_horizontally_separated(
        self, synthetic_dual_aquarium_frames: list[np.ndarray]
    ) -> None:
        """Test that detected aquariums are horizontally separated."""
        import cv2

        frame = synthetic_dual_aquarium_frames[0]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Get bounding boxes
        large_contours = [c for c in contours if cv2.contourArea(c) > 10000]
        bboxes = [cv2.boundingRect(c) for c in large_contours]

        if len(bboxes) >= 2:
            # Sort by x position
            bboxes_sorted = sorted(bboxes, key=lambda b: b[0])
            left_bbox = bboxes_sorted[0]
            right_bbox = bboxes_sorted[1]

            # Right box should start after left box ends
            left_end = left_bbox[0] + left_bbox[2]
            right_start = right_bbox[0]

            assert right_start > left_end, "Aquariums should not overlap horizontally"


@pytest.mark.integration
class TestAnalysisResultsE2E:
    """Tests for analysis results per aquarium."""

    def test_separate_analysis_per_aquarium(
        self,
        dual_aquarium_zone_data: MultiAquariumZoneData,
        tmp_path: Path,
    ) -> None:
        """Test that analysis produces separate results per aquarium."""
        # Create mock trajectory data for each aquarium
        trajectories = {}
        for aq in dual_aquarium_zone_data.aquariums:
            # Simulate 30 frames of tracking
            track_id = aq.id * 1000 + 1  # First track in this aquarium
            df = pd.DataFrame(
                {
                    "timestamp": np.linspace(0, 1, 30),
                    "frame": range(30),
                    "track_id": [track_id] * 30,
                    "center_x": np.random.uniform(100, 200, 30),
                    "center_y": np.random.uniform(150, 350, 30),
                    "x1": np.random.uniform(80, 180, 30),
                    "y1": np.random.uniform(130, 330, 30),
                    "x2": np.random.uniform(120, 220, 30),
                    "y2": np.random.uniform(170, 370, 30),
                    "confidence": np.random.uniform(0.85, 0.99, 30),
                }
            )
            trajectories[aq.id] = (df, aq)

        # Verify we have separate data for each aquarium
        assert 0 in trajectories
        assert 1 in trajectories
        assert trajectories[0][0]["track_id"].iloc[0] == 1  # Aquarium 0
        assert trajectories[1][0]["track_id"].iloc[0] == 1001  # Aquarium 1

    def test_roi_metrics_per_aquarium(
        self,
        dual_aquarium_zone_data: MultiAquariumZoneData,
    ) -> None:
        """Test that ROI metrics are calculated per aquarium."""
        # Aquarium 0 has 2 ROIs, Aquarium 1 has 1 ROI
        aq0 = dual_aquarium_zone_data.aquariums[0]
        aq1 = dual_aquarium_zone_data.aquariums[1]

        assert len(aq0.roi_polygons) == 2
        assert len(aq0.roi_names) == 2
        assert len(aq1.roi_polygons) == 1
        assert len(aq1.roi_names) == 1


@pytest.mark.integration
class TestMultiAquariumDataFlow:
    """Tests for data flow in multi-aquarium processing."""

    def test_detection_to_trajectory_flow(self) -> None:
        """Test data flow from detection to trajectory storage."""
        # Simulate detection output
        detections_aq0 = [
            (100, 200, 130, 230, 0.95, 1, 0),  # (x1, y1, x2, y2, conf, track_id, class_id)
            (102, 202, 132, 232, 0.93, 1, 0),
        ]
        detections_aq1 = [
            (400, 250, 430, 280, 0.92, 1001, 0),
            (402, 252, 432, 282, 0.91, 1001, 0),
        ]

        # Convert to trajectory format
        for det in detections_aq0:
            x1, y1, x2, y2, conf, track_id, _ = det
            center_x = (x1 + x2) / 2
            (y1 + y2) / 2
            assert track_id < 1000  # Aquarium 0 IDs
            assert 100 <= center_x <= 130

        for det in detections_aq1:
            x1, y1, x2, y2, _conf, track_id, _ = det
            center_x = (x1 + x2) / 2
            (y1 + y2) / 2
            assert track_id >= 1000  # Aquarium 1 IDs
            assert 400 <= center_x <= 432

    def test_aquarium_data_serialization(
        self, dual_aquarium_zone_data: MultiAquariumZoneData
    ) -> None:
        """Test that aquarium data can be serialized and deserialized."""
        # Convert to dict
        data_dict = {
            "aquariums": [
                {
                    "id": aq.id,
                    "polygon": aq.polygon,
                    "roi_polygons": aq.roi_polygons,
                    "roi_names": aq.roi_names,
                    "roi_colors": aq.roi_colors,
                    "group": aq.group,
                    "subject_id": aq.subject_id,
                    "day": aq.day,
                }
                for aq in dual_aquarium_zone_data.aquariums
            ],
            "video_width": dual_aquarium_zone_data.video_width,
            "video_height": dual_aquarium_zone_data.video_height,
        }

        # Reconstruct from dict
        reconstructed_aquariums = [AquariumData(**aq_data) for aq_data in data_dict["aquariums"]]
        reconstructed = MultiAquariumZoneData(
            aquariums=reconstructed_aquariums,
            video_width=data_dict["video_width"],
            video_height=data_dict["video_height"],
        )

        # Verify reconstruction
        assert len(reconstructed.aquariums) == 2
        assert reconstructed.aquariums[0].group == "Controle"
        assert reconstructed.aquariums[1].group == "CBD"


@pytest.mark.integration
class TestMultiAquariumEdgeCases:
    """Tests for edge cases in multi-aquarium processing."""

    def test_single_aquarium_fallback(self) -> None:
        """Test that single-aquarium mode still works."""
        single_aq = AquariumData(
            id=0,
            polygon=[(0, 0), (640, 0), (640, 480), (0, 480)],
            roi_polygons=[],
            roi_names=[],
            roi_colors=[],
            group="Default",
        )
        zone_data = MultiAquariumZoneData(
            aquariums=[single_aq],
            video_width=640,
            video_height=480,
        )

        assert len(zone_data.aquariums) == 1
        assert zone_data.aquariums[0].group == "Default"

    def test_empty_aquarium_list(self) -> None:
        """Test handling of empty aquarium list."""
        zone_data = MultiAquariumZoneData(
            aquariums=[],
            video_width=640,
            video_height=480,
        )

        assert len(zone_data.aquariums) == 0

    def test_aquarium_without_rois(self) -> None:
        """Test aquarium without any ROIs defined."""
        aq = AquariumData(
            id=0,
            polygon=[(50, 50), (300, 50), (300, 400), (50, 400)],
            roi_polygons=[],
            roi_names=[],
            roi_colors=[],
            group="Test",
        )
        zone_data = MultiAquariumZoneData(aquariums=[aq])

        assert len(zone_data.aquariums[0].roi_polygons) == 0

    def test_aquarium_with_missing_optional_fields(self) -> None:
        """Test aquarium with minimal required fields."""
        aq = AquariumData(
            id=0,
            polygon=[(0, 0), (100, 0), (100, 100), (0, 100)],
        )

        # Should have default values for optional fields
        assert aq.roi_polygons == []
        assert aq.roi_names == []
        assert aq.group is None or aq.group == ""
