"""Tests for the ``7_AnalysisWindow_<base>.json`` artifact (ADR-011, ``artifact.py``).

The artifact is what lets an analysis reuse a window instead of recomputing it,
so a torn write or a silently accepted foreign file would make the report cut
the recording at the wrong instant. Writes must be atomic; anything unreadable
must come back as ``None`` (recompute), never as an exception and never as a
half-valid object.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from zebtrack.core.conditions import (
    ARTIFACT_PREFIX,
    ARTIFACT_SCHEMA,
    AnalysisWindowArtifact,
    ArtifactEvent,
    ArtifactExternalEvent,
    EndOfStream,
    ExternalEvent,
    FirstOf,
    FrameObservation,
    FrameReached,
    OfflineWindow,
    OnlineWindow,
    WindowEvent,
    WindowResult,
    WindowSpec,
    artifact_path,
    evaluate_window,
    read_artifact,
    spec_hash,
    write_artifact,
)
from zebtrack.core.conditions import artifact as artifact_module

_SPEC = WindowSpec(
    start=FrameReached(frame=2),
    stop=FirstOf(children=(EndOfStream(), FrameReached(frame=50))),
)


def _result() -> WindowResult:
    frames = [FrameObservation(frame=i, t_s=i * 0.1) for i in range(10)]
    return evaluate_window(_SPEC, frames, role_names={})


def _artifact(**overrides: Any) -> AnalysisWindowArtifact:
    result = _result()
    fields: dict[str, Any] = {
        "clock": "pts",
        "fps_video": 9.9,
        "external_events": (ArtifactExternalEvent(t_s=3.2, source="arduino", code=1),),
        "online": OnlineWindow.from_result(result),
        "offline": OfflineWindow.from_result(
            result, inputs={"trajectory_sha": "abc", "objects_sha": None}
        ),
    }
    fields.update(overrides)
    return AnalysisWindowArtifact.for_spec(_SPEC, **fields)


class TestPath:
    def test_prefix_never_collides_with_the_trajectory(self) -> None:
        assert ARTIFACT_PREFIX == "7_AnalysisWindow_"
        assert not ARTIFACT_PREFIX.startswith("3_CoordMovimento")

    def test_single_aquarium_sits_next_to_the_trajectory(self, tmp_path: Path) -> None:
        assert artifact_path(tmp_path, "rat_01") == tmp_path / "7_AnalysisWindow_rat_01.json"

    def test_multi_aquarium_mirrors_the_recorder_layout(self, tmp_path: Path) -> None:
        # Recorder: <results>/aquarium_{id+1}/3_CoordMovimento_<base>_aquarium_{id+1}.parquet
        assert artifact_path(tmp_path, "fish", aquarium_id=0) == (
            tmp_path / "aquarium_1" / "7_AnalysisWindow_fish_aquarium_1.json"
        )
        assert artifact_path(str(tmp_path), "fish", aquarium_id=1) == (
            tmp_path / "aquarium_2" / "7_AnalysisWindow_fish_aquarium_2.json"
        )


class TestSchema:
    def test_dump_has_exactly_the_adr_keys(self) -> None:
        dumped = json.loads(_artifact().model_dump_json())
        assert set(dumped) == {
            "schema",
            "spec",
            "spec_hash",
            "clock",
            "fps_video",
            "aquarium_id",
            "external_events",
            "online",
            "offline",
        }
        assert dumped["schema"] == ARTIFACT_SCHEMA == "zebtrack.analysis_window/1"
        assert dumped["spec_hash"] == spec_hash(_SPEC)
        assert dumped["external_events"] == [{"t_s": 3.2, "source": "arduino", "code": 1}]
        assert set(dumped["offline"]) == {"start", "stop", "status", "inputs"}
        assert set(dumped["online"]) == {"start", "stop"}
        assert dumped["offline"]["start"] == {"frame": 2, "t_s": 0.2, "reason": "frame"}
        assert dumped["offline"]["stop"]["reason"] == "end_of_stream"
        assert dumped["offline"]["status"] == "censored"
        assert dumped["offline"]["inputs"] == {"trajectory_sha": "abc", "objects_sha": None}

    def test_spec_hash_must_match_the_spec(self) -> None:
        payload = json.loads(_artifact().model_dump_json())
        payload["spec_hash"] = "sha256:" + "0" * 64
        with pytest.raises(ValidationError) as exc:
            AnalysisWindowArtifact.model_validate(payload)
        assert "spec_hash_mismatch" in {e["type"] for e in exc.value.errors()}

    def test_unknown_schema_version_is_rejected(self) -> None:
        payload = json.loads(_artifact().model_dump_json())
        payload["schema"] = "zebtrack.analysis_window/2"
        with pytest.raises(ValidationError):
            AnalysisWindowArtifact.model_validate(payload)

    def test_offline_status_comes_from_the_result(self) -> None:
        not_met = WindowResult(start=None, stop=None, status="start_not_met", censored=False)
        offline = OfflineWindow.from_result(not_met, inputs={})
        assert (offline.start, offline.stop, offline.status) == (None, None, "start_not_met")

    def test_pending_result_cannot_be_stored_offline(self) -> None:
        pending = WindowResult(start=None, stop=None, status="pending", censored=False)
        with pytest.raises(ValueError, match="pending"):
            OfflineWindow.from_result(pending, inputs={})

    def test_inputs_missing_is_a_valid_offline_status(self) -> None:
        offline = OfflineWindow(status="inputs_missing", inputs={"trajectory_sha": None})
        assert offline.start is None

    def test_event_round_trip_keeps_frame_time_and_reason(self) -> None:
        event = WindowEvent(
            kind="stop", frame=9, t_s=0.9, reason="persist", confirmed_frame=12, confirmed_t_s=1.2
        )
        stored = ArtifactEvent.from_window_event(event)
        assert (stored.frame, stored.t_s, stored.reason) == (9, 0.9, "persist")

    def test_external_events_convert_from_the_engine_type(self) -> None:
        stored = ArtifactExternalEvent.from_event(
            ExternalEvent(source="manual", code=None, t_s=1.5)
        )
        assert (stored.t_s, stored.source, stored.code) == (1.5, "manual", None)


class TestWriteRead:
    def test_round_trip(self, tmp_path: Path) -> None:
        path = artifact_path(tmp_path, "rat_01")
        original = _artifact(aquarium_id=None)
        write_artifact(path, original)
        assert read_artifact(path) == original

    def test_write_accepts_a_plain_mapping_and_validates_it(self, tmp_path: Path) -> None:
        path = tmp_path / "7_AnalysisWindow_x.json"
        write_artifact(path, json.loads(_artifact().model_dump_json()))
        assert read_artifact(path) == _artifact()
        bad = json.loads(_artifact().model_dump_json())
        bad["clock"] = "processing"
        with pytest.raises(ValidationError):
            write_artifact(tmp_path / "7_AnalysisWindow_bad.json", bad)
        assert not (tmp_path / "7_AnalysisWindow_bad.json").exists()

    def test_write_leaves_no_temporary_file(self, tmp_path: Path) -> None:
        path = artifact_path(tmp_path, "rat_01")
        write_artifact(path, _artifact())
        write_artifact(path, _artifact(fps_video=10.0))
        assert sorted(p.name for p in tmp_path.iterdir()) == [path.name]
        loaded = read_artifact(path)
        assert loaded is not None
        assert loaded.fps_video == 10.0

    def test_failed_write_keeps_the_previous_artifact(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = artifact_path(tmp_path, "rat_01")
        write_artifact(path, _artifact())
        before = path.read_bytes()

        def exploding_fsync(fd: int) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(artifact_module.os, "fsync", exploding_fsync)
        with pytest.raises(OSError, match="disk full"):
            write_artifact(path, _artifact(fps_video=30.0))
        assert path.read_bytes() == before
        assert sorted(p.name for p in tmp_path.iterdir()) == [path.name]

    def test_failed_replace_cleans_the_temporary_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = artifact_path(tmp_path, "rat_01")

        def exploding_replace(src: Any, dst: Any) -> None:
            raise PermissionError("locked")

        monkeypatch.setattr(artifact_module.os, "replace", exploding_replace)
        with pytest.raises(PermissionError):
            write_artifact(path, _artifact())
        assert list(tmp_path.iterdir()) == []

    def test_temporary_file_is_created_in_the_target_folder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[str] = []
        real_replace = os.replace

        def spying_replace(src: Any, dst: Any) -> None:
            seen.append(os.path.dirname(os.fspath(src)))
            real_replace(src, dst)

        monkeypatch.setattr(artifact_module.os, "replace", spying_replace)
        path = artifact_path(tmp_path, "rat_01")
        write_artifact(path, _artifact())
        assert seen == [str(tmp_path)]

    def test_missing_file_reads_as_none(self, tmp_path: Path) -> None:
        assert read_artifact(tmp_path / "7_AnalysisWindow_nope.json") is None

    @pytest.mark.parametrize(
        "content",
        [
            b"",
            b"{not json",
            b'{"schema": "zebtrack.analysis_window/1"}',
            b"\xff\xfe\x00garbage",
            b"[]",
        ],
        ids=["empty", "truncated", "incomplete", "binary", "wrong-shape"],
    )
    def test_corrupted_file_reads_as_none(self, tmp_path: Path, content: bytes) -> None:
        path = tmp_path / "7_AnalysisWindow_bad.json"
        path.write_bytes(content)
        assert read_artifact(path) is None

    def test_tampered_spec_reads_as_none(self, tmp_path: Path) -> None:
        path = artifact_path(tmp_path, "rat_01")
        write_artifact(path, _artifact())
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["spec"]["start"]["frame"] = 3
        path.write_text(json.dumps(payload), encoding="utf-8")
        assert read_artifact(path) is None

    def test_unreadable_path_reads_as_none(self, tmp_path: Path) -> None:
        # A directory where the file should be: open() raises, read must not.
        path = tmp_path / "7_AnalysisWindow_dir.json"
        path.mkdir()
        assert read_artifact(path) is None
