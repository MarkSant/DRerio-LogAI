"""``io/object_sidecar.py`` — schema, metadata, reader and multi-aquarium routing (ADR-010)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from structlog.testing import capture_logs

from zebtrack.analysis import time_base
from zebtrack.core.detection.class_roles import resolve_class_role_map
from zebtrack.io import object_sidecar
from zebtrack.io.object_sidecar import (
    CLOCK_CAPTURE,
    CLOCK_PTS,
    HEARTBEAT_CLASS_ID,
    HEARTBEAT_ROLE,
    OBJECT_COLUMNS,
    OBJECTS_SCHEMA_VERSION,
    ObjectSidecarMetadata,
    build_object_table,
    object_sidecar_schema,
    partition_object_observations,
    read_object_sidecar,
    read_object_sidecar_metadata,
    resolve_object_sidecar,
    trajectory_sidecars,
)

_ADR_SCHEMA = [
    ("frame", pa.int64()),
    ("timestamp", pa.float64()),
    ("t_event_s", pa.float64()),
    ("class_id", pa.int16()),
    ("class_name", pa.dictionary(pa.int32(), pa.string())),
    ("role", pa.dictionary(pa.int32(), pa.string())),
    ("x1", pa.float32()),
    ("y1", pa.float32()),
    ("x2", pa.float32()),
    ("y2", pa.float32()),
    ("confidence", pa.float32()),
    ("track_id", pa.int64()),
    ("aquarium_id", pa.int16()),
]


def _heartbeat(frame: int, t: float, aquarium_id: int | None = None) -> dict:
    return {
        "frame": frame,
        "timestamp": t,
        "t_event_s": t,
        "class_id": HEARTBEAT_CLASS_ID,
        "class_name": None,
        "role": HEARTBEAT_ROLE,
        "x1": None,
        "y1": None,
        "x2": None,
        "y2": None,
        "confidence": None,
        "track_id": None,
        "aquarium_id": aquarium_id,
    }


def _object(frame: int, t: float, **overrides) -> dict:
    row = {
        "frame": frame,
        "timestamp": t,
        "t_event_s": t,
        "class_id": 2,
        "class_name": "experimenter",
        "role": "context",
        "x1": 10.0,
        "y1": 20.0,
        "x2": 30.0,
        "y2": 40.0,
        "confidence": 0.75,
        "track_id": None,
        "aquarium_id": None,
    }
    row.update(overrides)
    return row


def _metadata(**overrides: Any) -> ObjectSidecarMetadata:
    fields: dict[str, Any] = {
        "class_names": {0: "arena", 1: "rat", 2: "experimenter"},
        "class_roles": {"arena": "arena", "rat": "subject", "experimenter": "context"},
        "weight_sha256": "ab" * 32,
        "clock": CLOCK_PTS,
        "analysis_interval_frames": 1,
        "class_roles_source": "weight",
    }
    fields.update(overrides)
    return ObjectSidecarMetadata(**fields)


def _write(path: Path, rows: list[dict], metadata: ObjectSidecarMetadata | None = None) -> Path:
    table = build_object_table(rows, metadata or _metadata())
    pq.write_table(table, path)
    return path


# ---------------------------------------------------------------------------
# Schema and table building
# ---------------------------------------------------------------------------


class TestSchema:
    def test_columns_and_types_follow_the_adr_exactly(self):
        schema = object_sidecar_schema(_metadata())

        assert [(f.name, f.type) for f in schema] == _ADR_SCHEMA
        assert list(OBJECT_COLUMNS) == [name for name, _type in _ADR_SCHEMA]

    def test_schema_carries_the_key_value_metadata(self):
        raw = object_sidecar_schema(_metadata()).metadata

        assert raw[b"zebtrack.objects_schema"] == OBJECTS_SCHEMA_VERSION.encode()
        assert OBJECTS_SCHEMA_VERSION == "1"
        assert json.loads(raw[b"class_names"]) == {"0": "arena", "1": "rat", "2": "experimenter"}
        assert json.loads(raw[b"class_roles"])["experimenter"] == "context"
        assert raw[b"weight_sha256"] == ("ab" * 32).encode()
        assert raw[b"clock"] == b"pts"
        assert raw[b"analysis_interval_frames"] == b"1"
        assert raw[b"class_roles_source"] == b"weight"

    def test_only_heartbeat_and_bbox_columns_are_nullable_in_practice(self):
        table = build_object_table([_heartbeat(0, 0.0)], _metadata())

        row = table.to_pylist()[0]
        assert row["class_id"] == -1
        assert row["role"] == "frame"
        assert row["class_name"] is None
        assert [row[c] for c in ("x1", "y1", "x2", "y2", "confidence")] == [None] * 5
        assert row["track_id"] is None
        assert row["aquarium_id"] is None

    def test_rows_keep_their_values_and_types(self):
        table = build_object_table(
            [_heartbeat(3, 0.3), _object(3, 0.3, track_id=7, aquarium_id=1)], _metadata()
        )

        assert table.schema.equals(object_sidecar_schema(_metadata()), check_metadata=True)
        obj = table.to_pylist()[1]
        assert obj["class_name"] == "experimenter"
        assert obj["role"] == "context"
        assert obj["x1"] == pytest.approx(10.0)
        assert obj["confidence"] == pytest.approx(0.75)
        assert obj["track_id"] == 7
        assert obj["aquarium_id"] == 1

    def test_heartbeat_constant_matches_the_time_base_reader(self):
        """F1's ``time_base`` filters on its own constant; both must agree."""
        assert HEARTBEAT_CLASS_ID == time_base.HEARTBEAT_CLASS_ID == -1


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestMetadata:
    def test_round_trip(self):
        metadata = _metadata()

        decoded = ObjectSidecarMetadata.from_parquet_metadata(metadata.to_parquet_metadata())

        assert decoded == metadata

    def test_unknown_interval_round_trips_as_none(self):
        metadata = _metadata(analysis_interval_frames=None)

        raw = metadata.to_parquet_metadata()

        assert raw[b"analysis_interval_frames"] == b""
        assert ObjectSidecarMetadata.from_parquet_metadata(raw).analysis_interval_frames is None

    def test_missing_schema_key_is_rejected(self):
        raw = _metadata().to_parquet_metadata()
        del raw[b"zebtrack.objects_schema"]

        with pytest.raises(ValueError, match="objects_schema"):
            ObjectSidecarMetadata.from_parquet_metadata(raw)

    def test_newer_schema_version_is_rejected(self):
        raw = _metadata().to_parquet_metadata()
        raw[b"zebtrack.objects_schema"] = b"2"

        with pytest.raises(ValueError, match="objects_schema"):
            ObjectSidecarMetadata.from_parquet_metadata(raw)

    def test_from_role_map_reads_the_resolved_map(self):
        role_map = resolve_class_role_map(
            {0: "arena", 1: "Rat", 2: "experimenter"},
            weight_entry={
                "class_roles": {"arena": "arena", "rat": "subject", "experimenter": "context"}
            },
            weight_sha256="cd" * 32,
        )

        metadata = ObjectSidecarMetadata.from_role_map(
            role_map, clock=CLOCK_PTS, analysis_interval_frames=5
        )

        assert metadata.class_names == {0: "arena", 1: "Rat", 2: "experimenter"}
        assert metadata.class_roles == {
            "arena": "arena",
            "rat": "subject",
            "experimenter": "context",
        }
        assert metadata.weight_sha256 == "cd" * 32
        assert metadata.clock == CLOCK_PTS
        assert metadata.analysis_interval_frames == 5
        assert metadata.class_roles_source == "weight"

    def test_explicit_sha_beats_the_maps(self):
        role_map = resolve_class_role_map({0: "arena", 1: "zebrafish"}, weight_sha256=None)

        metadata = ObjectSidecarMetadata.from_role_map(
            role_map, clock=CLOCK_CAPTURE, analysis_interval_frames=2, weight_sha256="ee" * 32
        )

        assert metadata.weight_sha256 == "ee" * 32
        assert metadata.clock == CLOCK_CAPTURE

    def test_without_a_role_map_the_class_fields_are_empty(self):
        metadata = ObjectSidecarMetadata.from_role_map(
            None, clock=CLOCK_PTS, analysis_interval_frames=10
        )

        assert metadata.class_names == {}
        assert metadata.class_roles == {}
        assert metadata.weight_sha256 == ""
        assert metadata.class_roles_source == ""

    def test_unknown_clock_is_rejected(self):
        with pytest.raises(ValueError, match="clock"):
            _metadata(clock="wall")


# ---------------------------------------------------------------------------
# resolve_object_sidecar
# ---------------------------------------------------------------------------


class TestResolve:
    def test_sibling_of_the_trajectory_when_it_exists(self, tmp_path):
        trajectory = tmp_path / "3_CoordMovimento_CECT_4.parquet"
        sidecar = tmp_path / "3c_Objetos_CECT_4.parquet"
        sidecar.write_bytes(b"x")

        assert resolve_object_sidecar(trajectory) == sidecar
        assert resolve_object_sidecar(str(trajectory)) == sidecar

    def test_keeps_the_aquarium_suffix_of_the_base(self, tmp_path):
        trajectory = tmp_path / "3_CoordMovimento_exp_aquarium_2.parquet"
        sidecar = tmp_path / "3c_Objetos_exp_aquarium_2.parquet"
        sidecar.write_bytes(b"x")

        assert resolve_object_sidecar(trajectory) == sidecar

    def test_missing_sidecar_is_none(self, tmp_path):
        assert resolve_object_sidecar(tmp_path / "3_CoordMovimento_x.parquet") is None

    @pytest.mark.parametrize("value", [None, ""])
    def test_no_path_is_none(self, value):
        assert resolve_object_sidecar(value) is None

    def test_a_non_trajectory_name_is_none(self, tmp_path):
        (tmp_path / "3c_Objetos_x.parquet").write_bytes(b"x")

        assert resolve_object_sidecar(tmp_path / "x.parquet") is None

    def test_sidecar_name_never_starts_like_the_trajectory(self):
        assert not object_sidecar.object_sidecar_name("base").startswith("3_CoordMovimento")
        assert object_sidecar.object_sidecar_name("base") == "3c_Objetos_base.parquet"


# ---------------------------------------------------------------------------
# read_object_sidecar
# ---------------------------------------------------------------------------


class TestRead:
    def test_round_trip_with_nullable_columns_and_metadata(self, tmp_path):
        path = _write(
            tmp_path / "3c_Objetos_a.parquet",
            [_heartbeat(0, 0.0), _object(0, 0.0, track_id=4), _heartbeat(1, 0.1)],
        )

        df = read_object_sidecar(path)

        assert df is not None
        assert list(df.columns) == list(OBJECT_COLUMNS)
        assert df["class_id"].tolist() == [-1, 2, -1]
        assert df["role"].tolist() == ["frame", "context", "frame"]
        assert df["class_name"].tolist() == [None, "experimenter", None]
        assert str(df["track_id"].dtype) == "Int64"
        assert str(df["aquarium_id"].dtype) == "Int16"
        assert df["track_id"].tolist()[1] == 4
        assert pd.isna(df["track_id"].iloc[0])
        assert np.isnan(df["x1"].iloc[0])
        assert df.attrs["objects_metadata"] == _metadata()

    def test_metadata_only_read(self, tmp_path):
        path = _write(tmp_path / "3c_Objetos_a.parquet", [_heartbeat(0, 0.0)])

        assert read_object_sidecar_metadata(path) == _metadata()

    def test_missing_file_is_none(self, tmp_path):
        assert read_object_sidecar(tmp_path / "nope.parquet") is None
        assert read_object_sidecar_metadata(tmp_path / "nope.parquet") is None

    def test_corrupted_file_degrades_with_a_warning(self, tmp_path):
        path = tmp_path / "3c_Objetos_a.parquet"
        path.write_bytes(b"PAR1 not really a parquet file")

        with capture_logs() as logs:
            assert read_object_sidecar(path) is None
            assert read_object_sidecar_metadata(path) is None

        events = [entry["event"] for entry in logs]
        assert events.count("object_sidecar.read.failed") == 2
        assert all(entry["log_level"] == "warning" for entry in logs)

    def test_missing_column_is_an_incompatible_schema(self, tmp_path):
        table = build_object_table([_heartbeat(0, 0.0)], _metadata()).drop_columns(["role"])
        path = tmp_path / "3c_Objetos_a.parquet"
        pq.write_table(table, path)

        with capture_logs() as logs:
            assert read_object_sidecar(path) is None

        assert logs[0]["event"] == "object_sidecar.read.schema_mismatch"

    def test_reordered_columns_are_an_incompatible_schema(self, tmp_path):
        table = build_object_table([_heartbeat(0, 0.0)], _metadata())
        names = list(table.column_names)
        names[0], names[1] = names[1], names[0]
        path = tmp_path / "3c_Objetos_a.parquet"
        pq.write_table(table.select(names), path)

        assert read_object_sidecar(path) is None

    def test_wrong_column_type_is_an_incompatible_schema(self, tmp_path):
        table = build_object_table([_heartbeat(0, 0.0)], _metadata())
        index = table.column_names.index("class_id")
        table = table.set_column(index, "class_id", pa.array(["-1"], type=pa.string()))
        path = tmp_path / "3c_Objetos_a.parquet"
        pq.write_table(table, path)

        assert read_object_sidecar(path) is None

    def test_newer_schema_version_degrades(self, tmp_path):
        table = build_object_table([_heartbeat(0, 0.0)], _metadata())
        raw = dict(table.schema.metadata)
        raw[b"zebtrack.objects_schema"] = b"2"
        path = tmp_path / "3c_Objetos_a.parquet"
        pq.write_table(table.replace_schema_metadata(raw), path)

        with capture_logs() as logs:
            assert read_object_sidecar(path) is None

        assert logs[0]["event"] == "object_sidecar.read.schema_mismatch"

    def test_columns_added_at_the_end_are_accepted(self, tmp_path):
        """ADR-010: columns are additions only, so a later writer stays readable."""
        table = build_object_table([_heartbeat(0, 0.0)], _metadata())
        table = table.append_column("future", pa.array([1.5]))
        path = tmp_path / "3c_Objetos_a.parquet"
        pq.write_table(table, path)

        df = read_object_sidecar(path)

        assert df is not None
        assert list(df.columns)[: len(OBJECT_COLUMNS)] == list(OBJECT_COLUMNS)

    def test_the_heartbeat_is_the_time_base_source(self, tmp_path):
        rows = [_heartbeat(i, i * 0.1) for i in range(11)]
        path = _write(tmp_path / "3c_Objetos_a.parquet", rows)
        trajectory = pd.DataFrame({"timestamp": [0.0, 0.5], "frame": [0, 5]})

        base = time_base.resolve_time_base(trajectory, objects_df=read_object_sidecar(path))

        assert base.source == time_base.SOURCE_HEARTBEAT
        assert base.t_last == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Multi-aquarium routing
# ---------------------------------------------------------------------------

_LEFT = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.int32)
_RIGHT = np.array([[200, 0], [300, 0], [300, 100], [200, 100]], dtype=np.int32)
_POLYGONS = {0: _LEFT, 1: _RIGHT}


def _obs(role: str, bbox, aquarium_id, class_id=1, confidence=0.9) -> dict:
    return {
        "class_id": class_id,
        "class_name": "rat" if role == "subject" else "hand",
        "role": role,
        "bbox": bbox,
        "confidence": confidence,
        "aquarium_id": aquarium_id,
    }


class TestPartition:
    def test_subject_goes_only_to_its_aquarium(self):
        parts = partition_object_observations([_obs("subject", (210, 10, 220, 20), 1)], _POLYGONS)

        assert parts[0] == []
        assert [item["aquarium_id"] for item in parts[1]] == [1]

    def test_subject_seen_by_the_neighbouring_crop_belongs_where_it_is(self):
        """A widened crop of aquarium 0 sees the animal standing in aquarium 1."""
        parts = partition_object_observations([_obs("subject", (210, 10, 220, 20), 0)], _POLYGONS)

        assert parts[0] == []
        assert [item["aquarium_id"] for item in parts[1]] == [1]

    def test_subject_outside_every_polygon_keeps_the_crop_that_saw_it(self):
        parts = partition_object_observations([_obs("subject", (140, 150, 160, 170), 1)], _POLYGONS)

        assert parts[0] == []
        assert [item["aquarium_id"] for item in parts[1]] == [1]

    def test_subject_seen_by_both_crops_is_kept_once(self):
        left = _obs("subject", (90, 10, 110, 30), 0, confidence=0.9)
        right = _obs("subject", (91, 10, 111, 30), 1, confidence=0.5)

        parts = partition_object_observations([left, right], _POLYGONS)

        assert [item["confidence"] for item in parts[0]] == [0.9]
        assert parts[1] == []

    def test_different_classes_are_never_merged(self):
        hand = _obs("context", (140, 150, 160, 170), 0, class_id=3)
        box = _obs("context", (140, 150, 160, 170), 1, class_id=4)

        parts = partition_object_observations([hand, box], _POLYGONS)

        assert [item["class_id"] for item in parts[0]] == [3, 4]

    def test_the_same_crop_never_merges_its_own_boxes(self):
        """Two overlapping hands from ONE crop survived that crop's NMS: both real."""
        first = _obs("context", (140, 150, 160, 170), 0, class_id=3)
        second = _obs("context", (141, 150, 161, 171), 0, class_id=3)

        parts = partition_object_observations([first, second], _POLYGONS)

        assert len(parts[0]) == 2

    def test_context_inside_an_aquarium_is_assigned_to_it(self):
        parts = partition_object_observations(
            [_obs("context", (210, 10, 230, 30), 0, class_id=3)], _POLYGONS
        )

        assert parts[0] == []
        assert [item["aquarium_id"] for item in parts[1]] == [1]

    def test_context_outside_every_aquarium_goes_to_all_with_null_aquarium(self):
        parts = partition_object_observations(
            [_obs("context", (140, 150, 160, 170), 0, class_id=3)], _POLYGONS
        )

        assert [item["aquarium_id"] for item in parts[0]] == [None]
        assert [item["aquarium_id"] for item in parts[1]] == [None]

    def test_context_seen_by_both_crops_is_kept_once(self):
        """Widened context crops overlap; the same hand must not count twice."""
        seen_left = _obs("context", (140, 150, 160, 170), 0, class_id=3, confidence=0.6)
        seen_right = _obs("context", (141, 150, 161, 171), 1, class_id=3, confidence=0.8)

        parts = partition_object_observations([seen_left, seen_right], _POLYGONS)

        assert len(parts[0]) == 1
        assert parts[0][0]["confidence"] == pytest.approx(0.8)
        assert len(parts[1]) == 1

    def test_distinct_context_objects_are_both_kept(self):
        first = _obs("context", (140, 150, 160, 170), 0, class_id=3)
        far = _obs("context", (150, 300, 170, 320), 1, class_id=3)

        parts = partition_object_observations([first, far], _POLYGONS)

        assert len(parts[0]) == 2

    def test_input_observations_are_not_mutated(self):
        item = _obs("context", (140, 150, 160, 170), 0, class_id=3)

        partition_object_observations([item], _POLYGONS)

        assert item["aquarium_id"] == 0

    def test_subject_without_a_known_aquarium_is_routed_by_centroid(self):
        parts = partition_object_observations([_obs("subject", (10, 10, 20, 20), None)], _POLYGONS)

        assert [item["aquarium_id"] for item in parts[0]] == [0]
        assert parts[1] == []

    def test_subject_outside_every_aquarium_is_dropped(self):
        parts = partition_object_observations(
            [_obs("subject", (140, 150, 160, 170), None)], _POLYGONS
        )

        assert parts == {0: [], 1: []}

    def test_border_counts_as_inside(self):
        """Same convention as ``ZoneScaler.point_in_polygon`` (inclusive)."""
        parts = partition_object_observations(
            [_obs("context", (90, 40, 110, 60), 0, class_id=3)], _POLYGONS
        )

        assert [item["aquarium_id"] for item in parts[0]] == [0]


# ---------------------------------------------------------------------------
# The artifact set that travels with a trajectory
# ---------------------------------------------------------------------------


class TestTrajectorySidecars:
    def test_lists_exactly_the_same_base(self, tmp_path):
        names = [
            "3_CoordMovimento_CECT_4.parquet",
            "3b_Mascaras_CECT_4.parquet",
            "3c_Objetos_CECT_4.parquet",
            "6_FrameLedger_CECT_4.csv",
            "6_FrameLedger_CECT_4.parquet",
            "6_FrameLedger_CECT_4_anchor.json",
            "7_AnalysisWindow_CECT_4.json",
            # Another subject whose name merely starts the same way.
            "3c_Objetos_CECT_40.parquet",
            "6_FrameLedger_CECT_40_anchor.json",
            # Not part of the set.
            "1_ProcessingArea_CECT_4.parquet",
            "5_ClosedLoop_CECT_4.csv",
        ]
        for name in names:
            (tmp_path / name).write_bytes(b"x")

        found = trajectory_sidecars(tmp_path / "3_CoordMovimento_CECT_4.parquet")

        assert sorted(p.name for p in found) == [
            "3b_Mascaras_CECT_4.parquet",
            "3c_Objetos_CECT_4.parquet",
            "6_FrameLedger_CECT_4.csv",
            "6_FrameLedger_CECT_4.parquet",
            "6_FrameLedger_CECT_4_anchor.json",
            "7_AnalysisWindow_CECT_4.json",
        ]

    def test_window_prefix_matches_the_condition_artifact(self):
        from zebtrack.core.conditions.artifact import ARTIFACT_PREFIX

        assert object_sidecar.ANALYSIS_WINDOW_PREFIX == ARTIFACT_PREFIX

    def test_not_a_trajectory_has_no_set(self, tmp_path):
        assert trajectory_sidecars(tmp_path / "video.parquet") == []

    def test_sidecar_suffix_maps_to_a_new_base(self, tmp_path):
        trajectory = tmp_path / "3_CoordMovimento_old.parquet"
        anchor = tmp_path / "6_FrameLedger_old_anchor.json"

        assert object_sidecar.rebase_sidecar_name(anchor, trajectory, "new") == (
            "6_FrameLedger_new_anchor.json"
        )
