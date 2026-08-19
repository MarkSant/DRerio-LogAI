"""Extended unit tests for ui/payloads.py."""

from __future__ import annotations

from pathlib import Path

from zebtrack.ui.payloads import (
    AnalysisMetadataPayload,
    AnalysisTaskStatusPayload,
    AquariumDetectionProgressPayload,
    CameraDisconnectPayload,
    DetectionOverlayPayload,
    DetectorSetupPayload,
    DetectorSetupZonesPayload,
    DetectorUpdateParametersPayload,
    EmptyPayload,
    ErrorOccurredPayload,
    ExternalTriggerNoticePayload,
    FrameDisplayPayload,
    FramePayload,
    ItemIdPayload,
    LiveBatchCompletedPayload,
    MessagePayload,
    ProcessingCountPayload,
    ProcessingStatsPayload,
    ProcessingStatsWrapperPayload,
    ProjectApplySettingsPayload,
    ProjectClearAquariumSubjectPayload,
    ProjectContextMenuClickPayload,
    ProjectCreatedPayload,
    ProjectCreatePayload,
    ProjectDeleteAquariumPayload,
    ProjectDeleteAssetPayload,
    ProjectDeleteDayPayload,
    ProjectDeleteGroupPayload,
    ProjectDeleteSubjectPayload,
    ProjectGenerateSummariesPayload,
    ProjectImportVideosPayload,
    ProjectManagerReplacedPayload,
    ProjectOpenedPayload,
    ProjectOpenPayload,
    ProjectProcessVideosPayload,
    ProjectResetAnalysisDataPayload,
    ProjectVideoSelectedPayload,
    RoiSettingsApplyPayload,
    SelectionPayload,
    SetAquariumSelectorVisiblePayload,
    SocialSummaryPayload,
    StatusPayload,
    TrackIdPayload,
    UISelectTabPayload,
    UpdateAquariumSelectorPayload,
    UpdateButtonStatePayload,
    UpdateProcessingModePayload,
    VideoLoadedPayload,
    VideoPathPayload,
    VideoPathsPayload,
    WizardCreateProjectPayload,
    ZoneAutoDetectClickedPayload,
    ZoneAutoDetectPayload,
    ZoneDisplayClearedPayload,
    ZoneTemplateApplyPayload,
    ZoneVideoDoubleClickPayload,
    ZoneVideoSearchChangedPayload,
)


class TestPayloadsExtended:
    def test_empty_payload(self):
        payload = EmptyPayload()
        assert payload is not None

    def test_message_and_status_payloads(self):
        msg = MessagePayload(title="Alert", message="Operation complete")
        assert msg.title == "Alert"
        assert msg.message == "Operation complete"

        status = StatusPayload(message="Ready", status_type="info", level="debug")
        assert status.message == "Ready"
        assert status.status_type == "info"
        assert status.level == "debug"

    def test_video_and_item_payloads(self):
        vp = VideoPathPayload(video_path="/path/to/video.mp4")
        assert vp.video_path == "/path/to/video.mp4"

        vps = VideoPathsPayload(video_paths=["/path/1.mp4", "/path/2.mp4"])
        assert len(vps.video_paths) == 2

        sel = SelectionPayload(selection=["id1", "id2"])
        assert len(sel.selection) == 2

        item = ItemIdPayload(item_id="item_42")
        assert item.item_id == "item_42"

        ctx = ProjectContextMenuClickPayload(item_id="tree_1", x=100, y=200, column_id="col_name")
        assert ctx.item_id == "tree_1"
        assert ctx.x == 100
        assert ctx.y == 200
        assert ctx.column_id == "col_name"

        track = TrackIdPayload(track_id=1001)
        assert track.track_id == 1001

    def test_frame_and_display_payloads(self):
        fp = FramePayload(frame="frame_data", frame_number=42)
        assert fp.frame == "frame_data"
        assert fp.frame_number == 42

        fd = FrameDisplayPayload(
            frame="img_data",
            detections=["d1", "d2"],
            frame_number=10,
            info={"fps": 30.0},
        )
        assert fd.frame == "img_data"
        assert fd.detections == ["d1", "d2"]
        assert fd.frame_number == 10
        assert fd.info == {"fps": 30.0}

    def test_processing_stats_payloads(self):
        stats = ProcessingStatsPayload(
            total_frames=1000,
            processed_frames=500,
            detected_frames=450,
            start_time=12345.67,
            current_frame=500,
        )
        assert stats.total_frames == 1000
        assert stats.processed_frames == 500
        assert stats.detected_frames == 450
        assert stats.start_time == 12345.67
        assert stats.current_frame == 500

        wrapper = ProcessingStatsWrapperPayload(stats={"total": 1000})
        assert wrapper.stats == {"total": 1000}

        count = ProcessingCountPayload(count=3)
        assert count.count == 3

    def test_ui_and_control_payloads(self):
        btn = UpdateButtonStatePayload(button_name="start", state="disabled", text="Running...")
        assert btn.button_name == "start"
        assert btn.state == "disabled"
        assert btn.text == "Running..."

        tab = UISelectTabPayload(tab_name="zones")
        assert tab.tab_name == "zones"

        vis = SetAquariumSelectorVisiblePayload(visible=True)
        assert vis.visible is True

        aq_sel = UpdateAquariumSelectorPayload(aquariums=[0, 1, 2], active_aquarium_id=1)
        assert aq_sel.aquariums == [0, 1, 2]
        assert aq_sel.active_aquarium_id == 1

        mode = UpdateProcessingModePayload(
            report={"metric": 1},
            mode="auto",
            single_subject_overlay_locked=True,
        )
        assert mode.mode == "auto"
        assert mode.single_subject_overlay_locked is True

    def test_project_and_lifecycle_payloads(self):
        proj_create = ProjectCreatePayload(
            project_path=Path("/tmp/proj"),
            project_name="MyProject",
            project_type="standard",
            wizard_data={"step": 1},
        )
        assert proj_create.project_name == "MyProject"
        assert proj_create.project_type == "standard"

        proj_created = ProjectCreatedPayload(project="proj_obj")
        assert proj_created.project == "proj_obj"

        batch_done = LiveBatchCompletedPayload(
            batch_id="batch_01",
            session_count=4,
            group="Control",
            day=1,
            subject_id="Fish1",
        )
        assert batch_done.batch_id == "batch_01"
        assert batch_done.session_count == 4
        assert batch_done.group == "Control"

        cam_disc = CameraDisconnectPayload(
            camera_index=0,
            action="reconnect",
            gap_duration_s=2.5,
            gap_start_time=100.0,
            experiment_id="exp_01",
            total_gaps=1,
        )
        assert cam_disc.camera_index == 0
        assert cam_disc.action == "reconnect"
        assert cam_disc.gap_duration_s == 2.5

    def test_analysis_metadata_and_summary_payloads(self):
        meta = AnalysisMetadataPayload(metadata={"group": "Treated", "day": 2})
        assert meta.metadata["group"] == "Treated"

        soc = SocialSummaryPayload(profile="Shoaling", stats={"dist": 1.2})
        assert soc.profile == "Shoaling"
        assert soc.stats == {"dist": 1.2}

        task = AnalysisTaskStatusPayload(
            index=1,
            total=10,
            experiment_id="exp_99",
            step="running",
            progress=0.1,
            progress_fraction=0.1,
        )
        assert task.index == 1
        assert task.total == 10
        assert task.step == "running"

        det_ov = DetectionOverlayPayload(detections=["det1"], report={"score": 0.9})
        assert det_ov.detections == ["det1"]
        assert det_ov.report == {"score": 0.9}

    def test_notices_and_video_loaded_payloads(self):
        notice = ExternalTriggerNoticePayload(
            folder_name="2026-08-17",
            session_label="Session_A",
            day=1,
            group="Control",
            cobaia="Fish_01",
            port="COM3",
            level="INFO",
        )
        assert notice.folder_name == "2026-08-17"
        assert notice.day == 1
        assert notice.port == "COM3"

        progress = AquariumDetectionProgressPayload(
            current_aquarium=1,
            total_aquariums=4,
            message="Detecting...",
            frame_number=100,
            max_frames=500,
            detected_bbox=(10, 20, 30, 40),
            is_valid=True,
        )
        assert progress.current_aquarium == 1
        assert progress.total_aquariums == 4
        assert progress.detected_bbox == (10, 20, 30, 40)
        assert progress.is_valid is True

        vl = VideoLoadedPayload(
            video_path="/path/test.avi",
            frame_count=1200,
            fps=30.0,
        )
        assert vl.video_path == "/path/test.avi"
        assert vl.frame_count == 1200
        assert vl.fps == 30.0

        err = ErrorOccurredPayload(
            title="Processing Error",
            message="Corrupted frame",
            category="VideoIO",
        )
        assert err.title == "Processing Error"
        assert err.category == "VideoIO"

        zd = ZoneDisplayClearedPayload(
            deleted_video_path="/path/test.avi",
            asset="arena",
        )
        assert zd.deleted_video_path == "/path/test.avi"
        assert zd.asset == "arena"

    def test_project_operations_payloads(self):
        po = ProjectOpenPayload(project_path="/proj/dir")
        assert po.project_path == "/proj/dir"

        pod = ProjectOpenedPayload(project_path="/proj/dir", project="proj")
        assert pod.project_path == "/proj/dir"
        assert pod.project == "proj"

        pmr = ProjectManagerReplacedPayload(new_manager="mgr")
        assert pmr.new_manager == "mgr"

        piv = ProjectImportVideosPayload(candidate_paths=["/v1.mp4"], process_after_import=True)
        assert piv.candidate_paths == ["/v1.mp4"]
        assert piv.process_after_import is True

        ppv = ProjectProcessVideosPayload(video_paths=["/v1.mp4"])
        assert ppv.video_paths == ["/v1.mp4"]

        pgs = ProjectGenerateSummariesPayload(video_paths=["/v1.mp4"])
        assert pgs.video_paths == ["/v1.mp4"]

        pas = ProjectApplySettingsPayload(settings={"fps": 30.0})
        assert pas.settings == {"fps": 30.0}

        pda = ProjectDeleteAssetPayload(video_path="/v1.mp4", asset="arena")
        assert pda.video_path == "/v1.mp4"
        assert pda.asset == "arena"

        pdg = ProjectDeleteGroupPayload(group_id="Control")
        assert pdg.group_id == "Control"

        pdd = ProjectDeleteDayPayload(group_id="Control", day_id="Day1")
        assert pdd.group_id == "Control"
        assert pdd.day_id == "Day1"

        pds = ProjectDeleteSubjectPayload(group_id="Control", day_id="Day1", subject_id="Fish1")
        assert pds.subject_id == "Fish1"

        pdaq = ProjectDeleteAquariumPayload(video_path="/v1.mp4", aquarium_id=0)
        assert pdaq.aquarium_id == 0

        pca = ProjectClearAquariumSubjectPayload(video_path="/v1.mp4", aquarium_id=0)
        assert pca.aquarium_id == 0

        pra = ProjectResetAnalysisDataPayload(video_path="/v1.mp4", aquarium_id=1)
        assert pra.aquarium_id == 1

        pvs = ProjectVideoSelectedPayload(video_path="/v1.mp4", video_entry={"fps": 30})
        assert pvs.video_path == "/v1.mp4"

        wcp = WizardCreateProjectPayload(wizard_data={"name": "P1"})
        assert wcp.wizard_data == {"name": "P1"}

    def test_zone_and_detector_payloads(self):
        dsp = DetectorSetupPayload(
            animal_method="yolo", use_openvino=True, active_weight_name="fish.pt"
        )
        assert dsp.animal_method == "yolo"
        assert dsp.use_openvino is True
        assert dsp.active_weight_name == "fish.pt"

        dsz = DetectorSetupZonesPayload(zone_data={"arena": []})
        assert dsz.zone_data == {"arena": []}

        dup = DetectorUpdateParametersPayload(rule="center", buffer_radius=5.0, confidence=0.8)
        assert dup.rule == "center"
        assert dup.buffer_radius == 5.0
        assert dup.confidence == 0.8

        rsa = RoiSettingsApplyPayload(rule="head", buffer_radius=10.0, overlap_ratio=0.5)
        assert rsa.rule == "head"
        assert rsa.buffer_radius == 10.0
        assert rsa.overlap_ratio == 0.5

        zta = ZoneTemplateApplyPayload(template_name="DefaultArena")
        assert zta.template_name == "DefaultArena"

        zac = ZoneAutoDetectClickedPayload(stabilization_frames=15)
        assert zac.stabilization_frames == 15

        zad = ZoneAutoDetectPayload(video_path="/v.mp4", stabilization_frames=10, expected_count=4)
        assert zad.video_path == "/v.mp4"
        assert zad.expected_count == 4

        zsc = ZoneVideoSearchChangedPayload(search_text="test")
        assert zsc.search_text == "test"

        zdc = ZoneVideoDoubleClickPayload(item_id="item_1")
        assert zdc.item_id == "item_1"


class TestPayloadsExtended2:
    def test_empty_payload(self):
        p = EmptyPayload()
        assert repr(p) == "EmptyPayload()"

    def test_message_payload(self):
        p = MessagePayload(title="Alert", message="Operation complete")
        assert p.title == "Alert"
        assert p.message == "Operation complete"

    def test_status_payload(self):
        p = StatusPayload(message="Ready", status_type="info", level="DEBUG")
        assert p.message == "Ready"
        assert p.status_type == "info"
        assert p.level == "DEBUG"

    def test_video_path_payload(self):
        p = VideoPathPayload(video_path="/path/vid.mp4")
        assert p.video_path == "/path/vid.mp4"

    def test_video_paths_payload(self):
        p = VideoPathsPayload(video_paths=["/path/v1.mp4", "/path/v2.mp4"])
        assert len(p.video_paths) == 2

    def test_selection_payload(self):
        p = SelectionPayload(selection=["item1", "item2"])
        assert p.selection == ["item1", "item2"]

    def test_item_id_payload(self):
        p = ItemIdPayload(item_id="node_42")
        assert p.item_id == "node_42"

    def test_project_context_menu_click_payload(self):
        p = ProjectContextMenuClickPayload(item_id="row_1", x=100, y=200, column_id="name")
        assert p.item_id == "row_1"
        assert p.x == 100
        assert p.y == 200
        assert p.column_id == "name"

    def test_track_id_payload(self):
        p = TrackIdPayload(track_id=1001)
        assert p.track_id == 1001

    def test_frame_payload(self):
        p = FramePayload(frame="frame_data", frame_number=42)
        assert p.frame == "frame_data"
        assert p.frame_number == 42

    def test_frame_display_payload(self):
        p = FrameDisplayPayload(frame="frame_arr", detections=[1, 2], frame_number=10)
        assert p.frame == "frame_arr"
        assert p.frame_number == 10

    def test_processing_count_payload(self):
        p = ProcessingCountPayload(count=3)
        assert p.count == 3

    def test_detection_overlay_payload(self):
        p = DetectionOverlayPayload(detections=[{"box": [0, 0, 10, 10]}], report={"score": 0.95})
        assert len(p.detections) == 1
        assert p.report is not None
        assert p.report["score"] == 0.95
