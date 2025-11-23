import inspect

from zebtrack.ui.gui import ApplicationGUI

# List of expected public API methods (Total: 50)
EXPECTED_PUBLIC_API = [
    # 1. Project View Management
    'refresh_project_views',
    '_request_overview_refresh',
    '_update_project_overview_summary',
    '_refresh_processing_reports_tab',

    # 2. Zone & ROI Management
    '_maybe_offer_zone_reuse',
    '_edit_selected_zone_vertices',

    # 3. Live Recording
    'show_external_trigger_notice',
    'clear_external_trigger_notice',

    # 4. Analysis Progress & Statistics
    # Methods removed in Phase 3.1 (Event-Driven)

    # 5. Processing Reports (Internal delegation)
    '_on_processing_reports_item_double_click',
    '_on_processing_reports_generate_partial',
    '_determine_status_tag',
    '_sort_key_for_reports',
    '_build_report_hierarchy',
    '_populate_reports_tree_from_hierarchy',
    '_append_report_artifacts',

    # 6. Video Hierarchy & Metadata
    '_format_status_token',
    '_format_subject_for_reports',

    # 7. Single Video
    'setup_zone_definition_for_single_video',
    '_on_analyze_single_video_clicked',

    # 8. Core UI API (Wrappers & Status)
    'show_info',
    'show_warning',
    'show_error',
    'set_status',

    # 9. Other Public Methods
    'update_weights_dropdown',
    '_on_canvas_click',
    '_on_report_item_double_click',
    '_handle_report_file_node',
    '_handle_report_video_node',

    # 10. Wrappers & Utilities (Added during audit)
    'ask_directory',
    'ask_missing_metadata',
    'ask_ok_cancel',
    'ask_open_filenames',
    'ask_recording_details_unified',
    'ask_save_filename',
    'ask_string',
    'hide_progress_bar',
    'show_pending_videos_dialog',
    'show_progress_bar',
    'update_button_state',
    'update_idletasks',
    'update_progress',
]

def test_public_api_methods_exist():
    """Ensure all documented public API methods exist in ApplicationGUI."""
    missing_methods = []
    for method_name in EXPECTED_PUBLIC_API:
        if not hasattr(ApplicationGUI, method_name):
            missing_methods.append(method_name)

    assert not missing_methods, f"Missing {len(missing_methods)} public API methods: {missing_methods}"

def test_public_api_has_decorator():
    """Ensure all public methods have @public_api decorator."""
    missing_decorator = []
    for method_name in EXPECTED_PUBLIC_API:
        if not hasattr(ApplicationGUI, method_name):
            continue

        method = getattr(ApplicationGUI, method_name)
        # Check if the method has the __public_api__ attribute set by the decorator
        if not getattr(method, '__public_api__', False):
            missing_decorator.append(method_name)

    assert not missing_decorator, f"Missing @public_api decorator on {len(missing_decorator)} methods: {missing_decorator}"

def test_total_public_api_count():
    """Ensure we haven't accidentally marked too many methods as public."""
    count = 0
    for name, method in inspect.getmembers(ApplicationGUI, predicate=inspect.isfunction):
        if getattr(method, '__public_api__', False):
            count += 1

    # We expect exactly the number of methods in our list to be marked
    assert count == len(EXPECTED_PUBLIC_API), f"Expected {len(EXPECTED_PUBLIC_API)} public methods, found {count}"
