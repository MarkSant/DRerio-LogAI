# F2 — core/viewmodels coverage audit (TASK-087)

| id | location | what is wrong | evidence | status |
| --- | --- | --- | --- | --- |
| F2-1 | `src/zebtrack/core/viewmodels/main_view_model_runtime.py` `handle_event` | `PROJECT_DELETE_GROUP`, `PROJECT_DELETE_DAY` and `PROJECT_DELETE_SUBJECT` are subscribed and published by `reports_tree_manager.py`, but the `match` had no arm for them: they fell into `case _` (debug log only), so deleting a group, day or subject from the tree did nothing. | `test_delete_group/day/subject_routes_to_hierarchy_deletion` failed with `handle_delete_hierarchy_node called 0 times`; green after adding the three events to the project-misc arm. | fixed |

Skipped on purpose (no publisher per the event audit): `RECORDING_TOGGLE`, `MODEL_ADD_WEIGHT`, `MODEL_CLEAR_OPENVINO_CACHE`, `MODEL_VALIDATE_WEIGHTS`, `CALIBRATION_COPY_TO_PROJECT`, `CALIBRATION_SAVE_TO_PROJECT`.
