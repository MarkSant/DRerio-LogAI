"""Comprehensive unit tests for ui/payloads.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from zebtrack.ui.payloads import (
    AnalysisCompletedPayload,
    AnalysisMetadataPayload,
    AnalysisStartedPayload,
    AnalysisTaskStatusPayload,
    ArduinoLogEventPayload,
    ArduinoPortUpdateRequestedPayload,
    ArduinoSetupPayload,
    BatchAnalysisCompletedPayload,
    BehavioralConfigGeotaxisToggledPayload,
    BehavioralConfigPerspectiveChangedPayload,
    BehavioralConfigValuesChangedPayload,
    CalibrationCopyToProjectPayload,
    CalibrationRunLivePayload,
    CalibrationSaveToProjectPayload,
    CameraDisconnectPayload,
    ConfigSaveRequestedPayload,
    ConfigValidationErrorPayload,
    ControlIntervalChangedPayload,
    ControlPreviewToggledPayload,
    DetectionOverlayPayload,
    EmptyPayload,
    ErrorOccurredPayload,
    ExternalTriggerNoticePayload,
    FrameDisplayPayload,
    FrameErrorPayload,
    FramePayload,
    ItemIdPayload,
    LiveBatchCompletedPayload,
    LivePolygonSourceChangedPayload,
    LiveRecordingCancelledPayload,
    LiveRecordingPendingPayload,
    LiveRecordingResumeRequestedPayload,
    LiveSessionStartedPayload,
    LiveSessionStoppedPayload,
    MessagePayload,
    ModelAddWeightPayload,
    ModelClearOpenVinoCachePayload,
    ModelConvertOpenVinoPayload,
    ModelDeleteWeightPayload,
    ModelLoadNewWeightPayload,
    ModelReclassifyTargetPayload,
    ModelRunDiagnosticPayload,
    ModelSetDefaultForPayload,
    ModelSetOpenVinoPayload,
    ModelSetWeightPayload,
    ModelUpdateOpenVinoStatusPayload,
    PolygonEditRequestedPayload,
    ProcessingCountPayload,
    ProcessingExportSummariesPayload,
    ProcessingGenerateTrajectoriesPayload,
    ProcessingProgressPayload,
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
    ProjectRefreshRequestedPayload,
    ProjectResetAnalysisDataPayload,
    ProjectSelectionChangedPayload,
    ProjectVideoSelectedPayload,
    ProjectViewsRefreshRequestedPayload,
    ReadinessSnapshotUpdatedPayload,
    RecordingStartedPayload,
    RecordingStartPayload,
    RecordingStoppedPayload,
    RecordingTriggerPayload,
    ReportGeneratePayload,
    ReportsDeleteUnifiedPayload,
    ReportsGeneratePartialPayload,
    ReportsGenerateUnifiedPayload,
    RoiSettingsApplyPayload,
    SelectionPayload,
    SetAquariumSelectorVisiblePayload,
    SocialSummaryPayload,
    StatusPayload,
    TrackIdPayload,
    TrackingCompletePayload,
    UIAppendArduinoLogPayload,
    UIRequestWeightActionPayload,
    UIRequestWeightFilePayload,
    UIRequestWeightTypePayload,
    UISelectTabPayload,
    UISetActiveWeightPayload,
    UIUpdateArduinoCommandPayload,
    UIUpdateArduinoStatusPayload,
    UIUpdateOpenVinoCheckboxPayload,
    UIUpdateOpenVinoStatusPayload,
    UIUpdateWeightsListPayload,
    UnknownPayload,
    UpdateButtonStatePayload,
    UpdateProcessingModePayload,
    VideoHierarchySnapshotUpdatedPayload,
    VideoLoadedPayload,
    VideoMetadataUpdatedPayload,
    VideoPathPayload,
    VideoPathsPayload,
    VideoReconfigureSubjectsPayload,
    VideoTreeRefreshRequestedPayload,
    WizardCreateProjectPayload,
    ZoneAquariumAssignmentCompletedPayload,
    ZoneAquariumConfigConfirmedPayload,
    ZoneAquariumConfigUpdatedPayload,
    ZoneAquariumCountConfirmedPayload,
    ZoneAquariumSelectedPayload,
    ZoneAutoDetectPayload,
    ZoneDisplayClearedPayload,
    ZoneListItemPayload,
    ZoneListItemRightClickPayload,
    ZoneMultiAutoDetectFailedPayload,
    ZoneMultiAutoDetectPayload,
    ZoneMultiAutoDetectSuccessPayload,
    ZoneMultiDetectCompletedPayload,
    ZoneProcessingModeChangedPayload,
    ZoneShowAquariumAssignmentDialogPayload,
    ZonesUpdatedPayload,
    ZoneTemplateApplyPayload,
    ZoneVideoDoubleClickPayload,
    ZoneVideoFrameLoadPayload,
    ZoneVideoSearchChangedPayload,
)


class TestPayloadsInstantiationAndImmutability:
    """Test all payload dataclasses instantiation, default values, and frozen immutability."""

    def test_empty_payload(self):
        p = EmptyPayload()
        assert repr(p) == "EmptyPayload()"

    def test_message_payload(self):
        p = MessagePayload(title="Title", message="Body")
        assert p.title == "Title"
        assert p.message == "Body"
        with pytest.raises(AttributeError):
            p.title = "New"  # type: ignore[misc]

    def test_status_payload(self):
        p = StatusPayload(message="Status ok", status_type="info", level="debug")
        assert p.message == "Status ok"
        assert p.status_type == "info"
        assert p.level == "debug"

    def test_video_paths_payload(self):
        p1 = VideoPathPayload(video_path="/path/v.mp4")
        assert p1.video_path == "/path/v.mp4"

        p2 = VideoPathsPayload(video_paths=["/a.mp4", "/b.mp4"])
        assert len(p2.video_paths) == 2

    def test_selection_and_item_id_payloads(self):
        p_sel = SelectionPayload(selection=["id1", "id2"])
        assert p_sel.selection == ["id1", "id2"]

        p_item = ItemIdPayload(item_id="item_42")
        assert p_item.item_id == "item_42"

    def test_context_menu_and_track_id_payloads(self):
        p_cm = ProjectContextMenuClickPayload(item_id="video1", x=100, y=200, column_id="col1")
        assert p_cm.item_id == "video1"
        assert p_cm.x == 100
        assert p_cm.y == 200

        p_track = TrackIdPayload(track_id=7)
        assert p_track.track_id == 7

    def test_frame_and_display_payloads(self):
        p_frame = FramePayload(frame="fake_frame", frame_number=12)
        assert p_frame.frame == "fake_frame"
        assert p_frame.frame_number == 12

        p_disp = FrameDisplayPayload(
            frame="fake",
            detections=[(1, 2, 3, 4)],
            frame_number=5,
            info={"fps": 30.0},
        )
        assert p_disp.frame_number == 5
        assert p_disp.info == {"fps": 30.0}

    def test_processing_stats_payloads(self):
        p_stats = ProcessingStatsPayload(
            total_frames=1000,
            processed_frames=500,
            detected_frames=450,
            start_time=123.456,
            current_frame=500,
        )
        assert p_stats.total_frames == 1000
        assert p_stats.processed_frames == 500

        p_wrap = ProcessingStatsWrapperPayload(stats={"fps": 60})
        assert p_wrap.stats == {"fps": 60}

        p_count = ProcessingCountPayload(count=3)
        assert p_count.count == 3

    def test_detection_overlay_and_analysis_metadata(self):
        p_ov = DetectionOverlayPayload(detections=[1, 2], report={"status": "ok"})
        assert len(p_ov.detections) == 2

        p_meta = AnalysisMetadataPayload(metadata={"group": "Control", "day": 1})
        assert p_meta.metadata["group"] == "Control"

    def test_social_summary_and_task_status(self):
        p_soc = SocialSummaryPayload(profile="shoaling", stats={"dist": 10.0}, tracks=[1, 2])
        assert p_soc.profile == "shoaling"

        p_task = AnalysisTaskStatusPayload(
            index=1,
            total=10,
            experiment_id="exp1",
            step="tracking",
            progress=50.0,
            progress_fraction=0.5,
        )
        assert p_task.progress == 50.0

    def test_update_button_and_mode_payloads(self):
        p_btn = UpdateButtonStatePayload(button_name="btn_start", state="disabled", text="Running")
        assert p_btn.button_name == "btn_start"

        p_mode = UpdateProcessingModePayload(
            report="rep",
            mode="single",
            single_subject_overlay_locked=True,
        )
        assert p_mode.mode == "single"

    def test_tab_and_visibility_payloads(self):
        p_tab = UISelectTabPayload(tab_name="tab_analysis")
        assert p_tab.tab_name == "tab_analysis"

        p_vis = SetAquariumSelectorVisiblePayload(visible=True)
        assert p_vis.visible is True

    def test_video_loaded_and_errors(self):
        p_vl = VideoLoadedPayload(video_path="/path/v.mp4", frame_count=300, fps=25.0)
        assert p_vl.fps == 25.0

        p_err = ErrorOccurredPayload(title="Error", message="Fail", category="IO")
        assert p_err.category == "IO"

    def test_external_trigger_and_camera_disconnect(self):
        p_ext = ExternalTriggerNoticePayload(
            folder_name="f1",
            session_label="s1",
            day=1,
            group="G1",
            cobaia="1",
            port="COM3",
            level="warn",
        )
        assert p_ext.port == "COM3"

        p_cam = CameraDisconnectPayload(
            camera_index=0,
            action="retry",
            gap_duration_s=2.5,
            gap_start_time=100.0,
            experiment_id="exp1",
            total_gaps=1,
        )
        assert p_cam.gap_duration_s == 2.5

    def test_project_payloads(self):
        p_cr = ProjectCreatePayload(
            project_path=Path("/proj"),
            project_name="MyProj",
            project_type="live",
            wizard_data={"k": "v"},
        )
        assert p_cr.project_name == "MyProj"

        p_crd = ProjectCreatedPayload(project="proj_obj", path="/proj")
        assert p_crd.path == "/proj"

        p_op = ProjectOpenPayload(project_path="/proj")
        assert p_op.project_path == "/proj"

        p_opd = ProjectOpenedPayload(project_path="/proj", project="proj_obj")
        assert p_opd.project_path == "/proj"

        p_rep = ProjectManagerReplacedPayload(new_manager="mgr")
        assert p_rep.new_manager == "mgr"

        p_imp = ProjectImportVideosPayload(
            candidate_paths=["/v1.mp4", "/v2.mp4"], process_after_import=True
        )
        assert p_imp.process_after_import is True

        p_proc = ProjectProcessVideosPayload(
            video_paths=["/v1.mp4"],
            analysis_config={"roi": True},
            aquarium_filter={"/v1.mp4": [0, 1]},
        )
        assert len(p_proc.video_paths) == 1

        p_sum = ProjectGenerateSummariesPayload(video_paths=["/v1.mp4"])
        assert p_sum.video_paths == ["/v1.mp4"]

        p_app = ProjectApplySettingsPayload(settings={"det": "seg"})
        assert p_app.settings == {"det": "seg"}

        p_del_a = ProjectDeleteAssetPayload(video_path="/v.mp4", asset="trajectory")
        assert p_del_a.asset == "trajectory"

        p_del_g = ProjectDeleteGroupPayload(group_id="Control", delete_files=True)
        assert p_del_g.group_id == "Control"

        p_del_d = ProjectDeleteDayPayload(group_id="Control", day_id="Dia_1", delete_files=False)
        assert p_del_d.day_id == "Dia_1"

        p_del_s = ProjectDeleteSubjectPayload(
            group_id="Control", day_id="Dia_1", subject_id="Sub_1"
        )
        assert p_del_s.subject_id == "Sub_1"

        p_del_aq = ProjectDeleteAquariumPayload(video_path="/v.mp4", aquarium_id=0)
        assert p_del_aq.aquarium_id == 0

        p_clr_aq = ProjectClearAquariumSubjectPayload(video_path="/v.mp4", aquarium_id=1)
        assert p_clr_aq.aquarium_id == 1

        p_rst = ProjectResetAnalysisDataPayload(video_path="/v.mp4")
        assert p_rst.video_path == "/v.mp4"

        p_vs = ProjectVideoSelectedPayload(video_path="/v.mp4", video_entry={"status": "complete"})
        assert p_vs.video_path == "/v.mp4"

        p_sc = ProjectSelectionChangedPayload(selection=["/v1.mp4"])
        assert len(p_sc.selection) == 1

        p_v_ref = ProjectViewsRefreshRequestedPayload(reason="reload", immediate=True)
        assert p_v_ref.immediate is True

        p_p_ref = ProjectRefreshRequestedPayload(reason="update")
        assert p_p_ref.reason == "update"

        p_wiz = WizardCreateProjectPayload(wizard_data={"name": "Test"})
        assert p_wiz.wizard_data["name"] == "Test"

    def test_zone_payloads(self):
        p_auto = ZoneAutoDetectPayload(video_path="/v.mp4", stabilization_frames=15)
        assert p_auto.stabilization_frames == 15

        p_tpl = ZoneTemplateApplyPayload(template_name="standard_2x2")
        assert p_tpl.template_name == "standard_2x2"

        p_roi_set = RoiSettingsApplyPayload(rule="center", buffer_radius=5.0, overlap_ratio=0.5)
        assert p_roi_set.rule == "center"

        p_multi_suc = ZoneMultiAutoDetectSuccessPayload(
            video_path="/v.mp4",
            polygons=[[(0, 0), (10, 10)]],
            count=1,
            method="seg",
        )
        assert p_multi_suc.count == 1

        p_multi_fail = ZoneMultiAutoDetectFailedPayload(
            video_path="/v.mp4", reason="Contrast too low"
        )
        assert p_multi_fail.reason == "Contrast too low"

        p_multi_comp = ZoneMultiDetectCompletedPayload(count=2, aquariums=[0, 1])
        assert p_multi_comp.count == 2

        p_aq_sel = ZoneAquariumSelectedPayload(aquarium_id=1)
        assert p_aq_sel.aquarium_id == 1

        p_aq_conf = ZoneAquariumConfigConfirmedPayload(configs=[{"id": 0}])
        assert len(p_aq_conf.configs) == 1

        p_aq_upd = ZoneAquariumConfigUpdatedPayload(
            aquarium_id=0, config={"name": "A"}, video_path="/v.mp4"
        )
        assert p_aq_upd.video_path == "/v.mp4"

        p_cnt_conf = ZoneAquariumCountConfirmedPayload(count=4)
        assert p_cnt_conf.count == 4

        p_ass_comp = ZoneAquariumAssignmentCompletedPayload(
            configs=[{"id": 0}], apply_to_all=True, video_path="/v.mp4"
        )
        assert p_ass_comp.apply_to_all is True

        p_ass_dlg = ZoneShowAquariumAssignmentDialogPayload(
            video_path="/v.mp4", polygons=[], count=1
        )
        assert p_ass_dlg.count == 1

        p_proc_mode = ZoneProcessingModeChangedPayload(sequential=True)
        assert p_proc_mode.sequential is True

        p_srch = ZoneVideoSearchChangedPayload(search_text="test")
        assert p_srch.search_text == "test"

        p_dclick = ZoneVideoDoubleClickPayload(item_id="item_1")
        assert p_dclick.item_id == "item_1"

        p_fload = ZoneVideoFrameLoadPayload(item_id="item_2")
        assert p_fload.item_id == "item_2"

        p_zitem = ZoneListItemPayload(item_id="zone_0")
        assert p_zitem.item_id == "zone_0"

        p_zrc = ZoneListItemRightClickPayload(item_id="zone_0", x=10, y=20)
        assert p_zrc.x == 10

        p_zupd = ZonesUpdatedPayload(zone_data="data")
        assert p_zupd.zone_data == "data"

        p_poly_edit = PolygonEditRequestedPayload(polygon="poly", preselect_all=True)
        assert p_poly_edit.preselect_all is True

        p_multi_detect = ZoneMultiAutoDetectPayload(video_path="/v.mp4", expected_count=2)
        assert p_multi_detect.expected_count == 2

        p_disp_clr = ZoneDisplayClearedPayload(deleted_video_path="/v.mp4", asset="zones")
        assert p_disp_clr.asset == "zones"

    def test_arduino_payloads(self):
        p_ard_set = ArduinoSetupPayload(port="COM4", baudrate=9600)
        assert p_ard_set.port == "COM4"
        assert p_ard_set.baudrate == 9600

        p_ard_log = ArduinoLogEventPayload(event="Trigger received", timestamp=123.4)
        assert p_ard_log.event == "Trigger received"

        p_ard_ports = ArduinoPortUpdateRequestedPayload(ports=["COM1", "COM4"])
        assert len(p_ard_ports.ports) == 2

        p_ard_stat = UIUpdateArduinoStatusPayload(connected=True, port="COM4")
        assert p_ard_stat.connected is True

        p_ard_append = UIAppendArduinoLogPayload(message="Log line", level="info")
        assert p_ard_append.message == "Log line"

        p_ard_cmd = UIUpdateArduinoCommandPayload(command=1, success=True)
        assert p_ard_cmd.success is True

    def test_model_and_weights_payloads(self):
        p_set_w = ModelSetWeightPayload(name="yolo11", weight_name="yolo11.pt")
        assert p_set_w.name == "yolo11"

        p_ov = ModelSetOpenVinoPayload(use_openvino=True, device="CPU")
        assert p_ov.use_openvino is True

        p_conv = ModelConvertOpenVinoPayload(weight_name="yolo11", format="FP16")
        assert p_conv.format == "FP16"

        p_ov_stat = ModelUpdateOpenVinoStatusPayload(message="Converting...", progress_pct=45.0)
        assert p_ov_stat.progress_pct == 45.0

        p_add = ModelAddWeightPayload(weight_path="/w/model.pt", name="model")
        assert p_add.name == "model"

        p_del = ModelDeleteWeightPayload(name="old_model")
        assert p_del.name == "old_model"

        p_diag = ModelRunDiagnosticPayload(weight_name="yolo11", test_video="/v.mp4")
        assert p_diag.weight_name == "yolo11"

        p_load_w = ModelLoadNewWeightPayload(weight_path="/w/new.pt", weight_type="seg")
        assert p_load_w.weight_type == "seg"

        p_def = ModelSetDefaultForPayload(name="model", method="seg", target="zebrafish")
        assert p_def.target == "zebrafish"

        p_reclass = ModelReclassifyTargetPayload(name="model", target="aquarium")
        assert p_reclass.target == "aquarium"

        p_clr = ModelClearOpenVinoCachePayload(name="model")
        assert p_clr.name == "model"

        p_wlist = UIUpdateWeightsListPayload(weights=["w1", "w2"])
        assert len(p_wlist.weights) == 2

        p_rwf = UIRequestWeightFilePayload(filepath="/path/w.pt")
        assert p_rwf.filepath == "/path/w.pt"

        p_rwt = UIRequestWeightTypePayload(filepath="/path/w.pt")
        assert p_rwt.filepath == "/path/w.pt"

        p_rwa = UIRequestWeightActionPayload(weight_type="seg", filepath="/path/w.pt")
        assert p_rwa.weight_type == "seg"

        p_act_w = UISetActiveWeightPayload(weight_name="seg_weight")
        assert p_act_w.weight_name == "seg_weight"

        p_ov_cb = UIUpdateOpenVinoCheckboxPayload(is_checked=True)
        assert p_ov_cb.is_checked is True

        p_ov_st = UIUpdateOpenVinoStatusPayload(status="ready", message="OK", progress=100.0)
        assert p_ov_st.progress == 100.0

    def test_recording_and_reports_payloads(self):
        p_cal_live = CalibrationRunLivePayload(camera_index=0, duration_sec=5.0)
        assert p_cal_live.duration_sec == 5.0

        p_cal_copy = CalibrationCopyToProjectPayload(calibration_data={"ratio": 10.0})
        assert p_cal_copy.calibration_data == {"ratio": 10.0}

        p_cal_save = CalibrationSaveToProjectPayload(calibration_data={"ratio": 10.0})
        assert p_cal_save.calibration_data == {"ratio": 10.0}

        p_rec_start = RecordingStartPayload(camera_index=1)
        assert p_rec_start.camera_index == 1

        p_rec_started = RecordingStartedPayload(
            folder_name="f", output_folder="/out", trigger_source="manual", duration=60.0
        )
        assert p_rec_started.duration == 60.0

        p_rec_stopped = RecordingStoppedPayload(
            session_id="s1", duration_sec=60.0, frames_recorded=1800
        )
        assert p_rec_stopped.frames_recorded == 1800

        p_rec_trig = RecordingTriggerPayload(trigger_signal="START", source="hardware")
        assert p_rec_trig.trigger_signal == "START"

        p_live_start = LiveSessionStartedPayload(session_id="s1", video_path="/v.mp4")
        assert p_live_start.session_id == "s1"

        p_live_stop = LiveSessionStoppedPayload(
            session_id="s1", output_path="/out.mp4", frame_count=1000
        )
        assert p_live_stop.frame_count == 1000

        p_live_pend = LiveRecordingPendingPayload(experiment_id="exp1", group="G1", day="Dia_1")
        assert p_live_pend.experiment_id == "exp1"

        p_live_resume = LiveRecordingResumeRequestedPayload(experiment_id="exp1")
        assert p_live_resume.experiment_id == "exp1"

        p_live_cancel = LiveRecordingCancelledPayload(experiment_id="exp1")
        assert p_live_cancel.experiment_id == "exp1"

        p_live_poly_src = LivePolygonSourceChangedPayload(source="auto")
        assert p_live_poly_src.source == "auto"

        p_live_batch_comp = LiveBatchCompletedPayload(
            batch_id="b1", session_count=4, group="G", day="D1"
        )
        assert p_live_batch_comp.session_count == 4

        p_v_tree_ref = VideoTreeRefreshRequestedPayload(filter_text="filter")
        assert p_v_tree_ref.filter_text == "filter"

        p_v_hier = VideoHierarchySnapshotUpdatedPayload(snapshot={"groups": []})
        assert "groups" in p_v_hier.snapshot

        p_ready = ReadinessSnapshotUpdatedPayload(
            ready_with_trajectory=[], ready_with_zones=[], arena_only=[], without_arena=[]
        )
        assert len(p_ready.ready_with_trajectory) == 0

        p_gen_traj = ProcessingGenerateTrajectoriesPayload(selection=["/v.mp4"])
        assert len(p_gen_traj.selection) == 1

        p_exp_sum = ProcessingExportSummariesPayload(selection=["/v.mp4"], format="csv")
        assert p_exp_sum.format == "csv"

        p_rep_part = ReportsGeneratePartialPayload(selection=["/v.mp4"], video_path="/v.mp4")
        assert p_rep_part.video_path == "/v.mp4"

        p_rep_uni = ReportsGenerateUnifiedPayload(selection=["/v.mp4"], multi_aquarium=True)
        assert p_rep_uni.multi_aquarium is True

        p_del_uni = ReportsDeleteUnifiedPayload(video_path="/v.mp4")
        assert p_del_uni.video_path == "/v.mp4"

        p_rep_gen = ReportGeneratePayload(video_path="/v.mp4", format="pdf", report_type="summary")
        assert p_rep_gen.report_type == "summary"

        p_proc_prog = ProcessingProgressPayload(total_frames=100, processed_frames=50)
        assert p_proc_prog.total_frames == 100

        p_trk_comp = TrackingCompletePayload(
            video_path="/v.mp4", total_tracks=1, avg_track_length=500
        )
        assert p_trk_comp.total_tracks == 1

        p_ana_start = AnalysisStartedPayload(video_path="/v.mp4", roi_count=3)
        assert p_ana_start.roi_count == 3

        p_ana_comp = AnalysisCompletedPayload(video_path="/v.mp4", roi_results=[])
        assert p_ana_comp.video_path == "/v.mp4"

        p_batch_comp = BatchAnalysisCompletedPayload(
            total_videos=5, successful_count=5, failed_count=0
        )
        assert p_batch_comp.successful_count == 5

        p_frm_err = FrameErrorPayload(error="Corrupted frame", frame_number=10)
        assert p_frm_err.frame_number == 10

        p_beh_geo = BehavioralConfigGeotaxisToggledPayload(enabled=True)
        assert p_beh_geo.enabled is True

        p_beh_persp = BehavioralConfigPerspectiveChangedPayload(perspective="top_down")
        assert p_beh_persp.perspective == "top_down"

        p_beh_val = BehavioralConfigValuesChangedPayload(config={"key": "val"})
        assert p_beh_val.config == {"key": "val"}

        p_cfg_save = ConfigSaveRequestedPayload(values={"settings": {}})
        assert p_cfg_save.values is not None

        p_cfg_err = ConfigValidationErrorPayload(error="Invalid FPS")
        assert p_cfg_err.error == "Invalid FPS"

        p_ctrl_int = ControlIntervalChangedPayload(interval=5)
        assert p_ctrl_int.interval == 5

        p_ctrl_prev = ControlPreviewToggledPayload(preview_enabled=True)
        assert p_ctrl_prev.preview_enabled is True

        p_vid_meta = VideoMetadataUpdatedPayload(video_path="/v.mp4", metadata={"fps": 30.0})
        assert p_vid_meta.metadata is not None
        assert p_vid_meta.metadata["fps"] == 30.0

        p_vid_rec = VideoReconfigureSubjectsPayload(video_path="/v.mp4", current_entries=[])
        assert len(p_vid_rec.current_entries) == 0

    def test_unknown_payload_dict_access(self):
        p = UnknownPayload({"custom_key": 42, "status": "ok"})
        assert p.data == {"custom_key": 42, "status": "ok"}
