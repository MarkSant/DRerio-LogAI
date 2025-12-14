"""Tests for multi-aquarium recording functionality (Phase 7).

These tests cover:
- Starting multi-aquarium recording with separate folders
- Writing partitioned detection data
- Parquet schema including aquarium_id
- Stopping all recorders
- Video output per aquarium
"""

import pytest
import numpy as np
from pathlib import Path
import pyarrow.parquet as pq

from zebtrack.io.recorder import Recorder
from zebtrack.core.detector import ZoneData


class TestStartRecordingMultiAquarium:
    """Tests for start_recording_multi_aquarium method."""

    def test_creates_aquarium_folders(self, tmp_path):
        """Test that separate folders are created for each aquarium."""
        recorder = Recorder()

        zones_by_aquarium = {
            0: ZoneData(polygon=[(0, 0), (100, 0), (100, 100), (0, 100)]),
            1: ZoneData(polygon=[(200, 0), (300, 0), (300, 100), (200, 100)]),
        }

        success = recorder.start_recording_multi_aquarium(
            output_folder=str(tmp_path / "results"),
            width=640,
            height=480,
            zones_by_aquarium=zones_by_aquarium,
            write_video=False,
        )

        assert success
        assert (tmp_path / "results" / "aquarium_0").exists()
        assert (tmp_path / "results" / "aquarium_1").exists()

        recorder.stop_recording_multi_aquarium()

    def test_creates_recorders_per_aquarium(self, tmp_path):
        """Test that a separate recorder is created for each aquarium."""
        recorder = Recorder()

        zones_by_aquarium = {
            0: ZoneData(polygon=[(0, 0), (100, 0), (100, 100), (0, 100)]),
            1: ZoneData(polygon=[(200, 0), (300, 0), (300, 100), (200, 100)]),
        }

        success = recorder.start_recording_multi_aquarium(
            output_folder=str(tmp_path),
            width=640,
            height=480,
            zones_by_aquarium=zones_by_aquarium,
            write_video=False,
        )

        assert success
        assert recorder.is_multi_aquarium_mode()
        recorders = recorder.get_aquarium_recorders()
        assert len(recorders) == 2
        assert 0 in recorders
        assert 1 in recorders

        # Verify each sub-recorder has correct aquarium_id
        assert recorders[0]._aquarium_id == 0
        assert recorders[1]._aquarium_id == 1

        recorder.stop_recording_multi_aquarium()

    def test_rejects_already_recording(self, tmp_path):
        """Test that multi-aquarium cannot start if already recording."""
        recorder = Recorder()

        zones = {0: ZoneData(polygon=[(0, 0), (100, 0), (100, 100), (0, 100)])}

        # Start first recording
        success1 = recorder.start_recording_multi_aquarium(
            output_folder=str(tmp_path / "first"),
            width=640,
            height=480,
            zones_by_aquarium=zones,
            write_video=False,
        )
        assert success1

        # Try to start second recording
        success2 = recorder.start_recording_multi_aquarium(
            output_folder=str(tmp_path / "second"),
            width=640,
            height=480,
            zones_by_aquarium=zones,
            write_video=False,
        )
        assert not success2

        recorder.stop_recording_multi_aquarium()

    def test_rejects_more_than_two_aquariums(self, tmp_path):
        """Test that more than 2 aquariums is rejected."""
        recorder = Recorder()

        zones_by_aquarium = {
            0: ZoneData(polygon=[(0, 0), (100, 0), (100, 100), (0, 100)]),
            1: ZoneData(polygon=[(200, 0), (300, 0), (300, 100), (200, 100)]),
            2: ZoneData(polygon=[(400, 0), (500, 0), (500, 100), (400, 100)]),
        }

        success = recorder.start_recording_multi_aquarium(
            output_folder=str(tmp_path),
            width=640,
            height=480,
            zones_by_aquarium=zones_by_aquarium,
            write_video=False,
        )

        assert not success
        assert not recorder.is_multi_aquarium_mode()

    def test_single_aquarium_allowed(self, tmp_path):
        """Test that single aquarium mode is allowed."""
        recorder = Recorder()

        zones = {0: ZoneData(polygon=[(0, 0), (100, 0), (100, 100), (0, 100)])}

        success = recorder.start_recording_multi_aquarium(
            output_folder=str(tmp_path),
            width=640,
            height=480,
            zones_by_aquarium=zones,
            write_video=False,
        )

        assert success
        assert recorder.is_multi_aquarium_mode()
        assert len(recorder.get_aquarium_recorders()) == 1

        recorder.stop_recording_multi_aquarium()


class TestWritePartitionedDetectionData:
    """Tests for write_partitioned_detection_data method."""

    def test_writes_to_correct_recorders(self, tmp_path):
        """Test that data is written to the correct aquarium recorder."""
        recorder = Recorder()

        zones = {
            0: ZoneData(polygon=[(0, 0), (100, 0), (100, 100), (0, 100)]),
            1: ZoneData(polygon=[(200, 0), (300, 0), (300, 100), (200, 100)]),
        }

        recorder.start_recording_multi_aquarium(
            output_folder=str(tmp_path),
            width=640,
            height=480,
            zones_by_aquarium=zones,
            write_video=False,
        )

        # Write partitioned data
        partitioned = {
            0: [(10, 10, 30, 30, 0.9, 1001, 1)],
            1: [(210, 10, 230, 30, 0.85, 2001, 1)],
        }

        recorder.write_partitioned_detection_data(
            timestamp=0.5,
            frame_number=15,
            partitioned_detections=partitioned,
        )

        # Check each recorder has data
        recorders = recorder.get_aquarium_recorders()
        assert len(recorders[0].detection_data) == 1
        assert len(recorders[1].detection_data) == 1

        recorder.stop_recording_multi_aquarium()

    def test_raises_error_when_not_in_multi_mode(self):
        """Test that writing partitioned data fails when not in multi-aquarium mode."""
        recorder = Recorder()

        with pytest.raises(RuntimeError, match="not in multi-aquarium mode"):
            recorder.write_partitioned_detection_data(
                timestamp=0.5,
                frame_number=15,
                partitioned_detections={0: []},
            )

    def test_ignores_unknown_aquarium_ids(self, tmp_path):
        """Test that unknown aquarium IDs are logged but don't cause errors."""
        recorder = Recorder()

        zones = {0: ZoneData(polygon=[(0, 0), (100, 0), (100, 100), (0, 100)])}

        recorder.start_recording_multi_aquarium(
            output_folder=str(tmp_path),
            width=640,
            height=480,
            zones_by_aquarium=zones,
            write_video=False,
        )

        # Write data for unknown aquarium ID (should be ignored)
        partitioned = {
            0: [(10, 10, 30, 30, 0.9, 1001, 1)],
            5: [(500, 10, 530, 30, 0.7, 5001, 1)],  # Unknown ID
        }

        # Should not raise
        recorder.write_partitioned_detection_data(
            timestamp=0.5,
            frame_number=15,
            partitioned_detections=partitioned,
        )

        recorders = recorder.get_aquarium_recorders()
        assert len(recorders[0].detection_data) == 1
        assert 5 not in recorders

        recorder.stop_recording_multi_aquarium()


class TestParquetSchemaWithAquariumId:
    """Tests for Parquet schema including aquarium_id column."""

    def test_schema_includes_aquarium_id(self, tmp_path):
        """Test that Parquet schema includes aquarium_id column."""
        recorder = Recorder()

        zones = {
            0: ZoneData(polygon=[(0, 0), (100, 0), (100, 100), (0, 100)]),
            1: ZoneData(polygon=[(200, 0), (300, 0), (300, 100), (200, 100)]),
        }

        recorder.start_recording_multi_aquarium(
            output_folder=str(tmp_path),
            width=640,
            height=480,
            zones_by_aquarium=zones,
            write_video=False,
        )

        # Write data
        for frame in range(10):
            partitioned = {
                0: [(10 + frame, 10, 30, 30, 0.9, 1001, 1)],
                1: [(210 + frame, 10, 230, 30, 0.85, 2001, 1)],
            }
            recorder.write_partitioned_detection_data(
                timestamp=frame * 0.033,
                frame_number=frame,
                partitioned_detections=partitioned,
            )

        recorder.stop_recording_multi_aquarium()

        # Check Parquet files
        parquet_0 = tmp_path / "aquarium_0" / "3_CoordMovimento_aquarium_0.parquet"
        parquet_1 = tmp_path / "aquarium_1" / "3_CoordMovimento_aquarium_1.parquet"

        assert parquet_0.exists()
        assert parquet_1.exists()

        # Read and verify schema includes aquarium_id
        table_0 = pq.read_table(parquet_0)
        table_1 = pq.read_table(parquet_1)

        assert "aquarium_id" in table_0.column_names
        assert "aquarium_id" in table_1.column_names

        # Verify aquarium_id values are correct
        df_0 = table_0.to_pandas()
        df_1 = table_1.to_pandas()

        assert (df_0["aquarium_id"] == 0).all()
        assert (df_1["aquarium_id"] == 1).all()

    def test_standard_recorder_has_no_aquarium_id(self, tmp_path):
        """Test that standard (non-multi) recording doesn't include aquarium_id."""
        recorder = Recorder()

        zones = ZoneData(polygon=[(0, 0), (100, 0), (100, 100), (0, 100)])

        recorder.start_recording(
            output_folder=str(tmp_path),
            frame_width=640,
            frame_height=480,
            zones=zones,
            is_video_file=True,
        )

        # Write some data
        for frame in range(10):
            recorder.write_detection_data(
                timestamp=frame * 0.033,
                frame_number=frame,
                detections=[(10 + frame, 10, 30, 30, 0.9, 1001, 1)],
            )

        recorder.stop_recording()

        # Check Parquet file
        parquet_files = list(tmp_path.glob("*.parquet"))
        coord_file = [f for f in parquet_files if "CoordMovimento" in f.name][0]

        table = pq.read_table(coord_file)

        # Standard recording should NOT have aquarium_id
        assert "aquarium_id" not in table.column_names


class TestStopRecordingMultiAquarium:
    """Tests for stop_recording_multi_aquarium method."""

    def test_stops_all_recorders(self, tmp_path):
        """Test that all aquarium recorders are stopped."""
        recorder = Recorder()

        zones = {
            0: ZoneData(polygon=[(0, 0), (100, 0), (100, 100), (0, 100)]),
            1: ZoneData(polygon=[(200, 0), (300, 0), (300, 100), (200, 100)]),
        }

        recorder.start_recording_multi_aquarium(
            output_folder=str(tmp_path),
            width=640,
            height=480,
            zones_by_aquarium=zones,
            write_video=False,
        )

        # Write some data
        recorder.write_partitioned_detection_data(
            timestamp=0.5,
            frame_number=15,
            partitioned_detections={
                0: [(10, 10, 30, 30, 0.9, 1001, 1)],
                1: [(210, 10, 230, 30, 0.85, 2001, 1)],
            },
        )

        assert recorder.is_multi_aquarium_mode()

        recorder.stop_recording_multi_aquarium()

        assert not recorder.is_multi_aquarium_mode()
        assert len(recorder.get_aquarium_recorders()) == 0

    def test_creates_output_files(self, tmp_path):
        """Test that all output files are created on stop."""
        recorder = Recorder()

        zones = {
            0: ZoneData(
                polygon=[(0, 0), (100, 0), (100, 100), (0, 100)],
                roi_polygons=[[(10, 10), (20, 10), (20, 20), (10, 20)]],
                roi_names=["ROI_1"],
            ),
            1: ZoneData(
                polygon=[(200, 0), (300, 0), (300, 100), (200, 100)],
                roi_polygons=[[(210, 10), (220, 10), (220, 20), (210, 20)]],
                roi_names=["ROI_1"],
            ),
        }

        recorder.start_recording_multi_aquarium(
            output_folder=str(tmp_path),
            width=640,
            height=480,
            zones_by_aquarium=zones,
            write_video=False,
        )

        # Write data for both aquariums
        for frame in range(5):
            recorder.write_partitioned_detection_data(
                timestamp=frame * 0.033,
                frame_number=frame,
                partitioned_detections={
                    0: [(10 + frame, 10, 30, 30, 0.9, 1001, 1)],
                    1: [(210 + frame, 10, 230, 30, 0.85, 2001, 1)],
                },
            )

        recorder.stop_recording_multi_aquarium()

        # Verify files for aquarium 0
        aq0_folder = tmp_path / "aquarium_0"
        assert (aq0_folder / "1_ProcessingArea_aquarium_0.parquet").exists()
        assert (aq0_folder / "2_AreasOfInterest_aquarium_0.parquet").exists()
        assert (aq0_folder / "3_CoordMovimento_aquarium_0.parquet").exists()

        # Verify files for aquarium 1
        aq1_folder = tmp_path / "aquarium_1"
        assert (aq1_folder / "1_ProcessingArea_aquarium_1.parquet").exists()
        assert (aq1_folder / "2_AreasOfInterest_aquarium_1.parquet").exists()
        assert (aq1_folder / "3_CoordMovimento_aquarium_1.parquet").exists()

    def test_no_error_when_not_in_multi_mode(self):
        """Test that stopping when not in multi-mode doesn't error."""
        recorder = Recorder()

        # Should not raise
        recorder.stop_recording_multi_aquarium()


class TestWriteVideoFrameMultiAquarium:
    """Tests for video frame writing per aquarium."""

    def test_writes_frame_to_correct_recorder(self, tmp_path):
        """Test that frames are written to correct aquarium recorder."""
        recorder = Recorder()

        zones = {
            0: ZoneData(polygon=[(0, 0), (100, 0), (100, 100), (0, 100)]),
            1: ZoneData(polygon=[(200, 0), (300, 0), (300, 100), (200, 100)]),
        }

        recorder.start_recording_multi_aquarium(
            output_folder=str(tmp_path),
            width=640,
            height=480,
            zones_by_aquarium=zones,
            write_video=True,  # Enable video writing
        )

        # Create test frames
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Write frames for each aquarium
        recorder.write_video_frame_multi_aquarium(0, frame)
        recorder.write_video_frame_multi_aquarium(1, frame)

        recorder.stop_recording_multi_aquarium()

        # Verify video files exist
        assert (tmp_path / "aquarium_0" / "aquarium_0.mp4").exists()
        assert (tmp_path / "aquarium_1" / "aquarium_1.mp4").exists()


class TestDetermineParquetColumns:
    """Tests for _determine_parquet_columns method."""

    def test_standard_columns_no_calibration(self):
        """Test columns without calibration."""
        recorder = Recorder()
        columns = recorder._determine_parquet_columns()

        expected = [
            "timestamp", "frame", "track_id",
            "x1", "y1", "x2", "y2", "confidence",
            "x_center_px", "y_center_px"
        ]
        assert columns == expected

    def test_columns_with_calibration(self):
        """Test columns with pixel_per_cm_ratio set."""
        recorder = Recorder()
        recorder.pixel_per_cm_ratio = (10.0, 10.0)
        columns = recorder._determine_parquet_columns()

        expected = [
            "timestamp", "frame", "track_id",
            "x1", "y1", "x2", "y2", "confidence",
            "x_center_px", "y_center_px",
            "x_cm", "y_cm"
        ]
        assert columns == expected

    def test_columns_with_aquarium_id_explicit(self):
        """Test columns with explicit include_aquarium_id."""
        recorder = Recorder()
        columns = recorder._determine_parquet_columns(include_aquarium_id=True)

        expected = [
            "timestamp", "frame", "track_id", "aquarium_id",
            "x1", "y1", "x2", "y2", "confidence",
            "x_center_px", "y_center_px"
        ]
        assert columns == expected

    def test_columns_with_aquarium_id_implicit(self):
        """Test columns when _aquarium_id is set."""
        recorder = Recorder()
        recorder._aquarium_id = 0
        columns = recorder._determine_parquet_columns()

        expected = [
            "timestamp", "frame", "track_id", "aquarium_id",
            "x1", "y1", "x2", "y2", "confidence",
            "x_center_px", "y_center_px"
        ]
        assert columns == expected


class TestIntegrationMultiAquariumRecording:
    """Integration tests for complete multi-aquarium recording workflow."""

    def test_full_workflow(self, tmp_path):
        """Test complete multi-aquarium recording workflow."""
        recorder = Recorder()

        # Setup zones with ROIs
        zones = {
            0: ZoneData(
                polygon=[(0, 0), (200, 0), (200, 300), (0, 300)],
                roi_polygons=[
                    [(10, 10), (50, 10), (50, 50), (10, 50)],
                    [(60, 10), (100, 10), (100, 50), (60, 50)],
                ],
                roi_names=["Top", "Bottom"],
            ),
            1: ZoneData(
                polygon=[(250, 0), (450, 0), (450, 300), (250, 300)],
                roi_polygons=[
                    [(260, 10), (300, 10), (300, 50), (260, 50)],
                ],
                roi_names=["Center"],
            ),
        }

        # Start multi-aquarium recording
        success = recorder.start_recording_multi_aquarium(
            output_folder=str(tmp_path),
            width=640,
            height=480,
            zones_by_aquarium=zones,
            write_video=False,
        )
        assert success

        # Simulate 100 frames of detections
        for frame in range(100):
            timestamp = frame / 30.0  # 30 fps
            partitioned = {
                0: [
                    (50 + frame % 100, 150, 70 + frame % 100, 170, 0.9, 1001, 1),
                    (80 + frame % 50, 200, 100 + frame % 50, 220, 0.85, 1002, 1),
                ],
                1: [
                    (300 + frame % 100, 150, 320 + frame % 100, 170, 0.88, 2001, 1),
                ],
            }
            recorder.write_partitioned_detection_data(timestamp, frame, partitioned)

        # Stop recording
        recorder.stop_recording_multi_aquarium()

        # Verify outputs
        for aq_id in [0, 1]:
            folder = tmp_path / f"aquarium_{aq_id}"
            assert folder.exists()

            # Check Parquet files exist
            processing_area = folder / f"1_ProcessingArea_aquarium_{aq_id}.parquet"
            areas_of_interest = folder / f"2_AreasOfInterest_aquarium_{aq_id}.parquet"
            coord_movimento = folder / f"3_CoordMovimento_aquarium_{aq_id}.parquet"

            assert processing_area.exists()
            assert areas_of_interest.exists()
            assert coord_movimento.exists()

            # Verify detection data
            table = pq.read_table(coord_movimento)
            df = table.to_pandas()

            assert "aquarium_id" in df.columns
            assert (df["aquarium_id"] == aq_id).all()
            assert len(df) > 0

            # Aquarium 0 should have 2 detections per frame (200 total)
            # Aquarium 1 should have 1 detection per frame (100 total)
            if aq_id == 0:
                assert len(df) == 200
            else:
                assert len(df) == 100
