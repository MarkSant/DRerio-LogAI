# Event Audit Report

## Event: Events.UI_OPEN_ADD_VIDEOS_DIALOG

  Publishers:
    - src/zebtrack/core/video_orchestrator.py:227 [Keys: ]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: Events.UI_UPDATE_PROJECT_INFO

  Publishers:
    - src/zebtrack/core/viewmodels/project_view_model.py:78 [Keys: ]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: PROCESSING_MODE_CHANGED

  Publishers:
    - src/zebtrack/coordinators/session_coordinator.py:1049 [Keys: mode, source]
    - src/zebtrack/coordinators/hardware_coordinator.py:1090 [Keys: mode, source]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: PROCESSING_MODE_RESTORE

  Publishers:
    - src/zebtrack/coordinators/session_coordinator.py:1138 [Keys: source]
    - src/zebtrack/coordinators/hardware_coordinator.py:1162 [Keys: source]
    - src/zebtrack/coordinators/hardware_coordinator.py:1489 [Keys: source]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: StateCategory.DETECTOR

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/state_synchronizer.py:44
    - src/zebtrack/core/main_view_model.py:256

## Event: StateCategory.PROCESSING

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/state_synchronizer.py:39
    - src/zebtrack/core/main_view_model.py:257

## Event: StateCategory.PROJECT

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/state_synchronizer.py:49
    - src/zebtrack/core/main_view_model.py:255

## Event: StateCategory.RECORDING

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/state_synchronizer.py:34

## Event: UIEvents.ANALYSIS_COMPLETED

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/ui_coordinator.py:142

## Event: UIEvents.ANALYSIS_STARTED

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/ui_coordinator.py:141

## Event: UIEvents.ANALYSIS_TASK_STATUS_UPDATED

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/ui_coordinator.py:147

## Event: UIEvents.ERROR_OCCURRED

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/gui.py:123

## Event: UIEvents.EXTERNAL_TRIGGER_NOTICE

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/ui_coordinator.py:152

## Event: UIEvents.EXTERNAL_TRIGGER_NOTICE_CLEARED

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/ui_coordinator.py:153

## Event: UIEvents.POLYGON_EDIT_REQUESTED

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/ui_coordinator.py:122
    - src/zebtrack/ui/components/canvas_manager.py:68

## Event: UIEvents.PROCESSING_STATS_UPDATED

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/ui_coordinator.py:143

## Event: UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/ui_coordinator.py:136

## Event: UIEvents.READINESS_SNAPSHOT_UPDATED

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/ui_coordinator.py:133
    - src/zebtrack/ui/components/project_view_manager.py:67

## Event: UIEvents.SOCIAL_SUMMARY_UPDATED

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/ui_coordinator.py:146

## Event: UIEvents.VIDEO_HIERARCHY_SNAPSHOT_REQUESTED

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/ui_coordinator.py:129

## Event: UIEvents.VIDEO_HIERARCHY_SNAPSHOT_UPDATED

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/project_view_manager.py:72

## Event: UIEvents.VIDEO_LOADED

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/ui_coordinator.py:125

## Event: UIEvents.VIDEO_TREE_REFRESH_REQUESTED

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/ui_coordinator.py:126
    - src/zebtrack/ui/components/project_view_manager.py:61

## Event: UIEvents.ZONES_UPDATED

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/ui_coordinator.py:121
    - src/zebtrack/ui/components/canvas_manager.py:64

## Event: analysis.cancel_requested

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/widget_factory.py:440

## Event: analysis.track_selected

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/widget_factory.py:439

## Event: calibration:copy_to_project

  Publishers:
    - src/zebtrack/ui/dialogs/calibration_dialog.py:992 [Keys: ]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: calibration:save_to_project

  Publishers:
    - src/zebtrack/ui/dialogs/calibration_dialog.py:1000 [Keys: ]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: config.reset_requested

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/widget_factory.py:396

## Event: config.roi_rule_changed

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/widget_factory.py:397

## Event: config.save_requested

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/widget_factory.py:395

## Event: control.process_video

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/integration_example.py:151

## Event: control.start_recording

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/integration_example.py:149

## Event: control.stop_recording

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/integration_example.py:150

## Event: detector:update_parameters

  Publishers:
    - src/zebtrack/ui/components/zone_controls.py:710 [Keys: rule]
    - src/zebtrack/ui/components/zone_controls.py:717 [Keys: rule, buffer_radius, overlap_ratio]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:491

## Event: frame.error

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/integration_example.py:74

## Event: frame.loaded

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/integration_example.py:73

## Event: model:delete_weight

  Publishers:
    - src/zebtrack/ui/dialogs/manage_weights_dialog.py:214 [Keys: name]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: model:manage_weights

  Publishers:
    - src/zebtrack/ui/gui.py:1004 [Keys: ]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: model:run_diagnostic

  Publishers:
    - src/zebtrack/ui/dialogs/calibration_dialog.py:944 [Keys: config]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: model:set_openvino

  Publishers:
    - src/zebtrack/ui/dialogs/calibration_dialog.py:872 [Keys: use_openvino, dialog]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: model:set_weight

  Publishers:
    - src/zebtrack/ui/dialogs/calibration_dialog.py:867 [Keys: name, dialog]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: project.refresh_requested

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/widget_factory.py:528

## Event: project.video_double_click

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/widget_factory.py:532

## Event: project.video_right_click

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/widget_factory.py:536

## Event: project:close

  Publishers:
    - src/zebtrack/ui/components/tab_builder.py:47 [Keys: ]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: project:closed

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:163

## Event: project:create

  Publishers:
    - src/zebtrack/ui/gui.py:1242 [Keys: ]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: project:delete_asset

  Publishers:
    - src/zebtrack/ui/components/menu_manager.py:357 [Keys: video_path, asset, delete_source]
    - src/zebtrack/ui/components/menu_manager.py:367 [Keys: video_path, asset]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: project:generate_summaries

  Publishers:
    - src/zebtrack/ui/components/project_view_manager.py:732 [Keys: video_paths]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: project:manager_replaced

  Publishers:
    - src/zebtrack/orchestrators/project_orchestrator.py:77 [Keys: new_manager]
  Subscribers:
    - src/zebtrack/core/main_view_model.py:664

## Event: project:open

  Publishers:
    - src/zebtrack/ui/gui.py:1250 [Keys: project_path]
    - src/zebtrack/ui/components/dialog_manager.py:539 [Keys: project_path]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: project:process_videos

  Publishers:
    - src/zebtrack/ui/components/control_panel.py:144 [Keys: ]
    - src/zebtrack/ui/components/project_view_manager.py:705 [Keys: video_paths]
    - src/zebtrack/ui/components/tab_builder.py:195 [Keys: ]
  Subscribers:
    - src/zebtrack/coordinators/processing_coordinator.py:246
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:95

## Event: recording.started

  Publishers:
    - src/zebtrack/core/recording_facade.py:105 [Keys: video_path, output_dir]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: recording.stopped

  Publishers:
    - src/zebtrack/core/recording_facade.py:147 [Keys: ]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: recording:start

  Publishers:
    - src/zebtrack/ui/components/control_panel.py:136 [Keys: ]
    - src/zebtrack/ui/components/tab_builder.py:178 [Keys: ]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: recording:stop

  Publishers:
    - src/zebtrack/ui/components/control_panel.py:140 [Keys: ]
    - src/zebtrack/ui/components/tab_builder.py:185 [Keys: ]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: report:generate

  Publishers:
    - src/zebtrack/ui/components/project_view_manager.py:748 [Keys: videos, report_type]
    - src/zebtrack/ui/components/project_view_manager.py:1051 [Keys: videos, report_type]
    - src/zebtrack/ui/components/project_view_manager.py:1086 [Keys: videos, report_type]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: ui:append_arduino_log

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:304

## Event: ui:clear_external_trigger_notice

  Publishers:
    - src/zebtrack/coordinators/session_coordinator.py:464 [Keys: ]
    - src/zebtrack/coordinators/session_coordinator.py:496 [Keys: ]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:190 [Keys: ]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:304 [Keys: ]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:200

## Event: ui:display_frame

  Publishers:
    - src/zebtrack/core/video_orchestrator.py:727 [Keys: frame]
    - src/zebtrack/core/video_processing_service.py:682 [Keys: frame]
    - src/zebtrack/core/video_processing_service.py:793 [Keys: frame]
    - src/zebtrack/core/video_processing_service.py:1161 [Keys: frame]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:257 [Keys: frame]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:417 [Keys: frame]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:335

## Event: ui:display_video_frame

  Publishers:
    - src/zebtrack/coordinators/dialog_coordinator.py:205 [Keys: video_path]
    - src/zebtrack/core/video_orchestrator.py:156 [Keys: video_path]
    - src/zebtrack/orchestrators/ui_state_controller.py:427 [Keys: video_path]
    - src/zebtrack/orchestrators/analysis_orchestrator.py:99 [Keys: video_path]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:342

## Event: ui:navigate_from_analysis_view

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:317

## Event: ui:navigate_to_analysis_view

  Publishers:
    - src/zebtrack/core/main_view_model.py:517 [Keys: ]
    - src/zebtrack/orchestrators/ui_state_controller.py:565 [Keys: ]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:314

## Event: ui:navigate_to_project_view

  Publishers:
    - src/zebtrack/ui/project_workflow_adapter.py:175 [Keys: ]
    - src/zebtrack/ui/project_workflow_adapter.py:272 [Keys: ]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: ui:navigate_to_welcome

  Publishers:
    - src/zebtrack/ui/project_workflow_adapter.py:106 [Keys: ]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:159

## Event: ui:open_manage_weights_dialog

  Publishers:
    - src/zebtrack/orchestrators/ui_state_controller.py:138 [Keys: ]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: ui:redraw_zones

  Publishers:
    - src/zebtrack/coordinators/dialog_coordinator.py:264 [Keys: ]
    - src/zebtrack/ui/project_workflow_adapter.py:312 [Keys: ]
    - src/zebtrack/core/main_view_model.py:502 [Keys: zone_data]
    - src/zebtrack/orchestrators/ui_state_controller.py:464 [Keys: ]
    - src/zebtrack/orchestrators/zone_arena_orchestrator.py:89 [Keys: ]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:350

## Event: ui:refresh_project_views

  Publishers:
    - src/zebtrack/analysis/analysis_service.py:849 [Keys: reason, append_summary]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:259

## Event: ui:request_weight_action

  Publishers:
    - src/zebtrack/orchestrators/ui_state_controller.py:249 [Keys: weight_type, filepath]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:367

## Event: ui:request_weight_file

  Publishers:
    - src/zebtrack/ui/dialogs/calibration_dialog.py:890 [Keys: ]
    - src/zebtrack/orchestrators/ui_state_controller.py:231 [Keys: ]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: ui:request_weight_type

  Publishers:
    - src/zebtrack/orchestrators/ui_state_controller.py:242 [Keys: filepath]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:361

## Event: ui:select_tab

  Publishers:
    - src/zebtrack/coordinators/dialog_coordinator.py:200 [Keys: tab_name]
    - src/zebtrack/coordinators/session_coordinator.py:1191 [Keys: tab_name]
    - src/zebtrack/coordinators/session_coordinator.py:1224 [Keys: tab_name]
    - src/zebtrack/core/video_orchestrator.py:151 [Keys: tab_name]
    - src/zebtrack/orchestrators/ui_state_controller.py:424 [Keys: tab_name]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:369 [Keys: tab_name]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:400 [Keys: tab_name]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:212

## Event: ui:set_active_weight

  Publishers:
    - src/zebtrack/ui/project_workflow_adapter.py:179 [Keys: weight_name]
    - src/zebtrack/ui/project_workflow_adapter.py:261 [Keys: weight_name]
    - src/zebtrack/core/main_view_model.py:509 [Keys: weight_name]
    - src/zebtrack/orchestrators/ui_state_controller.py:153 [Keys: weight_name]
    - src/zebtrack/orchestrators/ui_state_controller.py:176 [Keys: weight_name]
    - src/zebtrack/orchestrators/ui_state_controller.py:202 [Keys: weight_name]
    - src/zebtrack/orchestrators/ui_state_controller.py:212 [Keys: weight_name]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:269

## Event: ui:set_status

  Publishers:
    - src/zebtrack/coordinators/live_camera_coordinator.py:646 [Keys: message]
    - src/zebtrack/coordinators/session_coordinator.py:442 [Keys: message]
    - src/zebtrack/coordinators/session_coordinator.py:503 [Keys: message]
    - src/zebtrack/coordinators/session_coordinator.py:942 [Keys: message]
    - src/zebtrack/coordinators/session_coordinator.py:1067 [Keys: message]
    - src/zebtrack/coordinators/session_coordinator.py:1081 [Keys: message]
    - src/zebtrack/coordinators/session_coordinator.py:1142 [Keys: message]
    - src/zebtrack/coordinators/hardware_coordinator.py:1072 [Keys: message]
    - src/zebtrack/coordinators/hardware_coordinator.py:1405 [Keys: message]
    - src/zebtrack/coordinators/hardware_coordinator.py:1493 [Keys: message]
    - src/zebtrack/core/analysis_coordinator.py:537 [Keys: message]
    - src/zebtrack/core/video_orchestrator.py:373 [Keys: message]
    - src/zebtrack/core/video_processing_service.py:595 [Keys: message]
    - src/zebtrack/core/video_processing_service.py:606 [Keys: message]
    - src/zebtrack/core/video_processing_service.py:734 [Keys: message]
    - src/zebtrack/core/viewmodels/analysis_control_view_model.py:150 [Keys: message]
    - src/zebtrack/orchestrators/ui_state_controller.py:299 [Keys: message]
    - src/zebtrack/orchestrators/ui_state_controller.py:309 [Keys: message]
    - src/zebtrack/orchestrators/ui_state_controller.py:325 [Keys: message]
    - src/zebtrack/orchestrators/ui_state_controller.py:385 [Keys: message]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:933 [Keys: message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:137 [Keys: message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:197 [Keys: message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:282 [Keys: message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:646 [Keys: message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:692 [Keys: message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:704 [Keys: message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:757 [Keys: message]
    - src/zebtrack/orchestrators/analysis_orchestrator.py:72 [Keys: message]
    - src/zebtrack/orchestrators/analysis_orchestrator.py:162 [Keys: message]
    - src/zebtrack/orchestrators/analysis_orchestrator.py:222 [Keys: message]
    - src/zebtrack/orchestrators/project_orchestrator.py:353 [Keys: message]
    - src/zebtrack/orchestrators/project_orchestrator.py:400 [Keys: message]
    - src/zebtrack/orchestrators/model_diagnostics_orchestrator.py:171 [Keys: message]
    - src/zebtrack/orchestrators/model_diagnostics_orchestrator.py:434 [Keys: message]
    - src/zebtrack/orchestrators/model_diagnostics_orchestrator.py:508 [Keys: message]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:206

## Event: ui:setup_interactive_polygon

  Publishers:
    - src/zebtrack/coordinators/session_coordinator.py:1121 [Keys: polygon]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:739 [Keys: polygon]
    - src/zebtrack/orchestrators/analysis_orchestrator.py:144 [Keys: polygon]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:144

## Event: ui:setup_zone_definition_for_single_video

  Publishers:
    - src/zebtrack/core/viewmodels/analysis_control_view_model.py:94 [Keys: video_path, config]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:220

## Event: ui:show_error

  Publishers:
    - src/zebtrack/coordinators/dialog_coordinator.py:355 [Keys: title, message]
    - src/zebtrack/coordinators/dialog_coordinator.py:363 [Keys: title, message]
    - src/zebtrack/coordinators/dialog_coordinator.py:371 [Keys: title, message]
    - src/zebtrack/coordinators/dialog_coordinator.py:380 [Keys: title, message]
    - src/zebtrack/coordinators/live_camera_coordinator.py:659 [Keys: title, message]
    - src/zebtrack/coordinators/session_coordinator.py:419 [Keys: title, message]
    - src/zebtrack/coordinators/session_coordinator.py:953 [Keys: title, message]
    - src/zebtrack/coordinators/session_coordinator.py:1039 [Keys: title, message]
    - src/zebtrack/coordinators/session_coordinator.py:1092 [Keys: title, message]
    - src/zebtrack/coordinators/session_coordinator.py:1128 [Keys: title, message]
    - src/zebtrack/coordinators/session_coordinator.py:1181 [Keys: title, message]
    - src/zebtrack/coordinators/session_coordinator.py:1198 [Keys: title, message]
    - src/zebtrack/coordinators/hardware_coordinator.py:1011 [Keys: title, message]
    - src/zebtrack/coordinators/hardware_coordinator.py:1060 [Keys: title, message]
    - src/zebtrack/coordinators/hardware_coordinator.py:1155 [Keys: title, message]
    - src/zebtrack/coordinators/hardware_coordinator.py:1237 [Keys: title, message]
    - src/zebtrack/coordinators/hardware_coordinator.py:1291 [Keys: title, message]
    - src/zebtrack/coordinators/hardware_coordinator.py:1308 [Keys: title, message]
    - src/zebtrack/coordinators/hardware_coordinator.py:1325 [Keys: title, message]
    - src/zebtrack/coordinators/hardware_coordinator.py:1371 [Keys: title, message]
    - src/zebtrack/coordinators/hardware_coordinator.py:1432 [Keys: title, message]
    - src/zebtrack/coordinators/hardware_coordinator.py:1479 [Keys: title, message]
    - src/zebtrack/ui/project_workflow_adapter.py:159 [Keys: title, message]
    - src/zebtrack/ui/project_workflow_adapter.py:191 [Keys: title, message]
    - src/zebtrack/ui/project_workflow_adapter.py:248 [Keys: title, message]
    - src/zebtrack/core/analysis_coordinator.py:189 [Keys: title, message]
    - src/zebtrack/core/analysis_coordinator.py:288 [Keys: title, message]
    - src/zebtrack/core/video_orchestrator.py:132 [Keys: title, message]
    - src/zebtrack/core/video_orchestrator.py:210 [Keys: title, message]
    - src/zebtrack/core/video_orchestrator.py:216 [Keys: title, message]
    - src/zebtrack/core/video_orchestrator.py:273 [Keys: title, message]
    - src/zebtrack/core/video_orchestrator.py:520 [Keys: title, message]
    - src/zebtrack/core/video_processing_service.py:1662 [Keys: title, message]
    - src/zebtrack/core/video_processing_service.py:1694 [Keys: title, message]
    - src/zebtrack/core/viewmodels/analysis_control_view_model.py:70 [Keys: title, message]
    - src/zebtrack/orchestrators/ui_state_controller.py:157 [Keys: title, message]
    - src/zebtrack/orchestrators/ui_state_controller.py:182 [Keys: title, message]
    - src/zebtrack/orchestrators/ui_state_controller.py:321 [Keys: title, message]
    - src/zebtrack/orchestrators/ui_state_controller.py:393 [Keys: title, message]
    - src/zebtrack/orchestrators/ui_state_controller.py:430 [Keys: title, message]
    - src/zebtrack/orchestrators/ui_state_controller.py:477 [Keys: title, message]
    - src/zebtrack/orchestrators/ui_state_controller.py:488 [Keys: title, message]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:509 [Keys: title, message]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:762 [Keys: title, message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:131 [Keys: title, message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:260 [Keys: title, message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:361 [Keys: title, message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:377 [Keys: title, message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:445 [Keys: title, message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:651 [Keys: title, message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:668 [Keys: title, message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:715 [Keys: title, message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:745 [Keys: title, message]
    - src/zebtrack/orchestrators/analysis_orchestrator.py:109 [Keys: title, message]
    - src/zebtrack/orchestrators/analysis_orchestrator.py:150 [Keys: title, message]
    - src/zebtrack/orchestrators/model_diagnostics_orchestrator.py:120 [Keys: title, message]
    - src/zebtrack/orchestrators/model_diagnostics_orchestrator.py:159 [Keys: title, message]
    - src/zebtrack/orchestrators/model_diagnostics_orchestrator.py:241 [Keys: title, message]
    - src/zebtrack/orchestrators/model_diagnostics_orchestrator.py:293 [Keys: title, message]
    - src/zebtrack/orchestrators/model_diagnostics_orchestrator.py:335 [Keys: title, message]
    - src/zebtrack/orchestrators/model_diagnostics_orchestrator.py:352 [Keys: title, message]
    - src/zebtrack/orchestrators/model_diagnostics_orchestrator.py:369 [Keys: title, message]
    - src/zebtrack/orchestrators/model_diagnostics_orchestrator.py:403 [Keys: title, message]
    - src/zebtrack/orchestrators/model_diagnostics_orchestrator.py:461 [Keys: title, message]
    - src/zebtrack/orchestrators/model_diagnostics_orchestrator.py:496 [Keys: title, message]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:183

## Event: ui:show_external_trigger_notice

  Publishers:
    - src/zebtrack/coordinators/session_coordinator.py:432 [Keys: folder_name, day, group, cobaia, port]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:272 [Keys: folder_name, day, group, cobaia, port]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:192

## Event: ui:show_info

  Publishers:
    - src/zebtrack/coordinators/dialog_coordinator.py:209 [Keys: title, message]
    - src/zebtrack/coordinators/dialog_coordinator.py:255 [Keys: title, message]
    - src/zebtrack/coordinators/dialog_coordinator.py:297 [Keys: title, message]
    - src/zebtrack/coordinators/session_coordinator.py:1225 [Keys: title, message]
    - src/zebtrack/coordinators/hardware_coordinator.py:1470 [Keys: title, message]
    - src/zebtrack/ui/project_workflow_adapter.py:275 [Keys: title, message]
    - src/zebtrack/ui/project_workflow_adapter.py:344 [Keys: title, message]
    - src/zebtrack/core/analysis_coordinator.py:239 [Keys: title, message]
    - src/zebtrack/core/analysis_coordinator.py:278 [Keys: title, message]
    - src/zebtrack/core/analysis_coordinator.py:299 [Keys: title, message]
    - src/zebtrack/core/analysis_coordinator.py:354 [Keys: title, message]
    - src/zebtrack/core/analysis_coordinator.py:366 [Keys: title, message]
    - src/zebtrack/core/analysis_coordinator.py:514 [Keys: title, message]
    - src/zebtrack/core/video_orchestrator.py:160 [Keys: title, message]
    - src/zebtrack/core/video_orchestrator.py:201 [Keys: title, message]
    - src/zebtrack/core/video_orchestrator.py:281 [Keys: title, message]
    - src/zebtrack/core/video_orchestrator.py:314 [Keys: title, message]
    - src/zebtrack/core/video_orchestrator.py:392 [Keys: title, message]
    - src/zebtrack/core/video_orchestrator.py:439 [Keys: title, message]
    - src/zebtrack/core/video_orchestrator.py:471 [Keys: title, message]
    - src/zebtrack/core/video_orchestrator.py:489 [Keys: title, message]
    - src/zebtrack/core/live_camera_service.py:1307 [Keys: title, message]
    - src/zebtrack/orchestrators/ui_state_controller.py:466 [Keys: title, message]
    - src/zebtrack/orchestrators/ui_state_controller.py:533 [Keys: title, message]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:141 [Keys: title, message]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:175 [Keys: title, message]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:576 [Keys: title, message]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:643 [Keys: title, message]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:675 [Keys: title, message]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:693 [Keys: title, message]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:718 [Keys: title, message]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:737 [Keys: title, message]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:890 [Keys: title, message]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:951 [Keys: title, message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:402 [Keys: title, message]
    - src/zebtrack/orchestrators/analysis_orchestrator.py:199 [Keys: title, message]
    - src/zebtrack/orchestrators/model_diagnostics_orchestrator.py:488 [Keys: title, message]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:169

## Event: ui:show_warning

  Publishers:
    - src/zebtrack/coordinators/dialog_coordinator.py:347 [Keys: title, message]
    - src/zebtrack/coordinators/session_coordinator.py:1107 [Keys: title, message]
    - src/zebtrack/core/analysis_coordinator.py:142 [Keys: title, message]
    - src/zebtrack/core/analysis_coordinator.py:266 [Keys: title, message]
    - src/zebtrack/core/analysis_coordinator.py:344 [Keys: title, message]
    - src/zebtrack/core/analysis_coordinator.py:528 [Keys: title, message]
    - src/zebtrack/core/video_orchestrator.py:119 [Keys: title, message]
    - src/zebtrack/core/video_orchestrator.py:262 [Keys: title, message]
    - src/zebtrack/core/video_orchestrator.py:461 [Keys: title, message]
    - src/zebtrack/core/video_orchestrator.py:546 [Keys: title, message]
    - src/zebtrack/core/viewmodels/project_view_model.py:51 [Keys: title, message]
    - src/zebtrack/orchestrators/ui_state_controller.py:445 [Keys: title, message]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:129 [Keys: title, message]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:626 [Keys: title, message]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:707 [Keys: title, message]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:781 [Keys: title, message]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:729 [Keys: title, message]
    - src/zebtrack/orchestrators/analysis_orchestrator.py:87 [Keys: title, message]
    - src/zebtrack/orchestrators/analysis_orchestrator.py:125 [Keys: title, message]
    - src/zebtrack/orchestrators/analysis_orchestrator.py:213 [Keys: title, message]
    - src/zebtrack/orchestrators/project_orchestrator.py:337 [Keys: title, message]
    - src/zebtrack/orchestrators/project_orchestrator.py:382 [Keys: title, message]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:176

## Event: ui:update_analysis_metadata

  Publishers:
    - src/zebtrack/core/video_processing_service.py:936 [Keys: metadata]
  Subscribers:
    - NONE FOUND (Possible Dead Event)

## Event: ui:update_analysis_task_status

  Publishers:
    - src/zebtrack/core/video_processing_service.py:649 [Keys: payload]
    - src/zebtrack/core/video_processing_service.py:946 [Keys: payload]
    - src/zebtrack/core/video_processing_service.py:1130 [Keys: payload]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:382 [Keys: payload]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:238

## Event: ui:update_arduino_status

  Publishers:
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:119 [Keys: connected, port]
  Subscribers:
    - src/zebtrack/ui/components/arduino_dashboard.py:73
    - src/zebtrack/ui/components/event_dispatcher.py:295

## Event: ui:update_button_state

  Publishers:
    - src/zebtrack/coordinators/session_coordinator.py:355 [Keys: button_name, state]
    - src/zebtrack/coordinators/session_coordinator.py:358 [Keys: button_name, state]
    - src/zebtrack/coordinators/session_coordinator.py:497 [Keys: button_name, state]
    - src/zebtrack/coordinators/session_coordinator.py:500 [Keys: button_name, state]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:109 [Keys: button_name, state]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:113 [Keys: button_name, state]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:134 [Keys: button_name, state]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:191 [Keys: button_name, state]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:194 [Keys: button_name, state]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:520 [Keys: button_name, state]
    - src/zebtrack/orchestrators/recording_session_orchestrator.py:523 [Keys: button_name, state]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:328

## Event: ui:update_detection_overlay

  Publishers:
    - src/zebtrack/core/video_orchestrator.py:730 [Keys: detections, report]
    - src/zebtrack/core/video_processing_service.py:674 [Keys: detections, report]
    - src/zebtrack/core/video_processing_service.py:1154 [Keys: detections, report]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:260 [Keys: detections, report]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:409 [Keys: detections, report]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:244

## Event: ui:update_openvino_checkbox

  Publishers:
    - src/zebtrack/ui/project_workflow_adapter.py:176 [Keys: is_checked]
    - src/zebtrack/ui/project_workflow_adapter.py:258 [Keys: is_checked]
    - src/zebtrack/core/main_view_model.py:511 [Keys: is_checked]
    - src/zebtrack/orchestrators/ui_state_controller.py:273 [Keys: is_checked]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:281

## Event: ui:update_openvino_status

  Publishers:
    - src/zebtrack/orchestrators/ui_state_controller.py:363 [Keys: status]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:275

## Event: ui:update_processing_mode

  Publishers:
    - src/zebtrack/orchestrators/ui_state_controller.py:356 [Keys: report]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:334 [Keys: source, force]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:402 [Keys: source, force]
    - src/zebtrack/orchestrators/analysis_orchestrator.py:158 [Keys: source, force]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:320

## Event: ui:update_processing_stats

  Publishers:
    - src/zebtrack/core/video_orchestrator.py:722 [Keys: stats]
    - src/zebtrack/core/video_processing_service.py:664 [Keys: stats]
    - src/zebtrack/core/video_processing_service.py:1144 [Keys: stats]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:251 [Keys: stats]
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:396 [Keys: stats]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:226

## Event: ui:update_social_summary

  Publishers:
    - src/zebtrack/analysis/analysis_service.py:762 [Keys: profile, stats, tracks]
    - src/zebtrack/core/video_processing_service.py:1751 [Keys: profile, stats, tracks]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:232

## Event: ui:update_weights_list

  Publishers:
    - src/zebtrack/orchestrators/ui_state_controller.py:149 [Keys: weights]
    - src/zebtrack/orchestrators/ui_state_controller.py:171 [Keys: weights]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:287

## Event: ui:update_zone_list

  Publishers:
    - src/zebtrack/ui/project_workflow_adapter.py:313 [Keys: ]
    - src/zebtrack/core/main_view_model.py:503 [Keys: zone_data]
    - src/zebtrack/orchestrators/ui_state_controller.py:465 [Keys: ]
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:356

## Event: ui:video_hierarchy_snapshot_updated

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:253

## Event: video:analyze_single

  Publishers:
    - src/zebtrack/ui/components/event_dispatcher.py:608 [Keys: video_path, config]
  Subscribers:
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:81

## Event: video:cancel_analysis

  Publishers:
    - src/zebtrack/ui/components/widget_factory.py:434 [Keys: ]
  Subscribers:
    - src/zebtrack/orchestrators/video_processing_orchestrator.py:89

## Event: video:start_single_processing

  Publishers:
    - src/zebtrack/ui/gui.py:1390 [Keys: video_path, config, zone_data]
  Subscribers:
    - src/zebtrack/coordinators/processing_coordinator.py:238

## Event: zone.auto_detect_clicked

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/integration_example.py:111
    - src/zebtrack/ui/components/event_dispatcher.py:427

## Event: zone.discard_arena

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:486

## Event: zone.draw_arena

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:433

## Event: zone.draw_main_polygon

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/integration_example.py:112

## Event: zone.draw_roi

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/integration_example.py:113
    - src/zebtrack/ui/components/event_dispatcher.py:436

## Event: zone.list_item_double_click

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:469

## Event: zone.list_item_right_click

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:473

## Event: zone.save_arena

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:483

## Event: zone.template_apply

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/integration_example.py:114
    - src/zebtrack/ui/components/event_dispatcher.py:442

## Event: zone.template_import

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:448

## Event: zone.template_save

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:445

## Event: zone.toggle_view

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:439

## Event: zone.video_double_click

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:459

## Event: zone.video_frame_load

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:463

## Event: zone.video_refresh

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:456

## Event: zone.video_search_changed

  Publishers:
    - NONE FOUND (Possible Dead Subscriber Code)
  Subscribers:
    - src/zebtrack/ui/components/event_dispatcher.py:453

## Event: zone:auto_detect

  Publishers:
    - src/zebtrack/ui/gui.py:1348 [Keys: video_path, stabilization_frames]
    - src/zebtrack/core/viewmodels/analysis_control_view_model.py:197 [Keys: <payload>]
  Subscribers:
    - src/zebtrack/coordinators/processing_coordinator.py:253

## Event: zone:save_manual_arena

  Publishers:
    - src/zebtrack/ui/components/canvas_manager.py:746 [Keys: polygon_points]
  Subscribers:
    - NONE FOUND (Possible Dead Event)
