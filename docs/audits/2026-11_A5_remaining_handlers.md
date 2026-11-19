# A5 — the remaining silent handlers, and the guard that stays (TASK-087)

Register row A5-01 closed the A5 front with "the 11 handlers read one by one are closed; the
other 29 of the 2026-11 scan were not read". This report reads every handler of that shape in
the current code, records a verdict for each, and describes the ratchet that keeps new ones
out: `tests/quality/test_no_silent_handlers.py`.

Code read: branch `claude/audit-guards-bd8d1c`, cut from `worktree-cov-plugins-utils` at
`858d0a13`; `src/` was not changed by this work. Line numbers are of that tree.

## Result

**No handler hides a data failure.** None needed a red test or a fix. 47 handlers have the
silent shape; 33 are legitimate and 14 should log (12 `diagnostic`, 2 `ux`), all of them in
probes, labels and UI gating, never on the path that writes or reads research data.

| Classification | Silent (in the allowlist) | Documented fallback | Total |
| --- | --- | --- | --- |
| hides a real failure | 0 | 0 | 0 |
| should log | 12 | 2 | 14 |
| legitimate | 15 | 18 | 33 |
| **total** | **27** | **20** | **47** |

## Method

The shape is the one of the original scan (section 1 of
[`2026-11_A5_silent_failures.md`](2026-11_A5_silent_failures.md)), made exact so a test can
apply it:

- **broad**: bare `except:`, `except Exception` / `BaseException` (alone or in a tuple), or a
  `with contextlib.suppress(Exception)` block;
- **quiet**: the body only passes, continues, breaks, returns or assigns, and nothing in it calls
  anything (so it neither logs, re-raises nor notifies);
- **documented fallback**: a quiet body that returns or assigns, with a comment explaining it
  inside the handler or in the comment block right above the `except` (the project's
  `# except Exception justified: <why>` convention). A comment of fewer than two words does not
  count, and neither does any comment that carries a tool directive (`pragma:`, `noqa`,
  `type: ignore`, `nosec`): `# pragma: no cover - defensive` explains nothing, and such comments
  come and go with coverage work. `pass`/`continue`/`break` are never a fallback, and
  `suppress(Exception)` is always silent.

A quiet, undocumented handler is SILENT. All 47 quiet handlers were read in context below,
silent or not.

### Where the 29 went

The 2026-11 scan listed 41 sites. Since then `multi_aquarium_coordinator.py:352` was fixed
(A5-S-010, it now logs `multi_aquarium.assignment.config_invalid`). The exact shape also catches
seven handlers the first scan's text filter missed because their value is not a literal
constant: `roi.py:1240` (`invalid += 1`), `arduino_bindings_panel.py:680` and
`polygon_drawing_service.py:21` (`return []`), `processing_worker.py:1581` (a dict item),
`experimental_design_step.py:128` (`return self.min_val`), `model_selection_step.py:393`
(`devices = ()`) and the nested Pillow fallback of `video_display.py:148`. 41 − 1 + 7 = 47. The 29
the register left unread are among the 40 survivors of the first list; each now has a verdict.

## Silent handlers (27, listed in `ALLOWED_SILENT`)

| Site (`src/zebtrack/...`) | Body | Verdict | Severity | Why |
| --- | --- | --- | --- | --- |
| `__main__.py:39` | `log_path = "logs/analysis.log"` | legitimate | diagnostic | Crash reporter that runs before logging exists; the default path is the point. |
| `coordinators/calibration_coordinator.py:89` | `project_name = None` | should log | diagnostic | Only the label of the calibration scope; an unnamed project is shown. |
| `coordinators/video_processing_coordinator.py:262` | `return None` | legitimate | diagnostic | cv2 fallback that runs only when the metadata service is not injected, which DI never allows (A2-07, A5-S-011). |
| `core/recording/live_session_manager.py:931` | `elapsed_s = 0.0` | should log | diagnostic | The value only feeds the text of the `.cancelled` marker. |
| `core/video/shared_frame_buffer.py:198` | `pass` | legitimate | diagnostic | `SharedMemory.close()` in cleanup must not propagate. |
| `io/arduino.py:253` | `break` | should log | diagnostic | A serial read error ends the probe exactly like a timeout, so the panel says "no answer". |
| `ui/components/analysis_view_controller.py:182` | `processing_state = None` | should log | diagnostic | "Is a live session active" probe; falls through to the coordinator check. `get_processing_state` is a plain read. |
| `ui/components/analysis_view_controller.py:197` | `return False` | should log | diagnostic | Second half of the same probe. |
| `ui/components/canvas/event_handler.py:207` | `return None` | legitimate | diagnostic | Canvas destroyed during a drag. |
| `ui/components/canvas/event_handler.py:535` | `return None` | legitimate | diagnostic | Canvas item lookup on a destroyed canvas. |
| `ui/components/canvas/event_handler.py:540` | `continue` | legitimate | diagnostic | Item vanished between `find_withtag` and `gettags`. |
| `ui/components/canvas/renderer.py:98` | `return None` | legitimate | diagnostic | Canvas destroyed. |
| `ui/components/canvas_manager.py:156` | `return None` | legitimate | diagnostic | Canvas destroyed. |
| `ui/components/dialog_manager.py:1076` | `formatted_day = None` | legitimate | diagnostic | Cosmetic day label of the trigger notice; the raw day is shown. |
| `ui/components/event_dispatcher.py:161` | `processing_state = None` | should log | diagnostic | Live probe that decides whether partial live metadata is merged with the last payload. A wrong `False` only skips the merge; the probe is a plain read. |
| `ui/components/event_dispatcher.py:176` | `return False` | should log | diagnostic | Second half of the same probe. |
| `ui/components/global_model_configuration_panel.py:995` | `suppress(Exception)` around `after_cancel` | legitimate | diagnostic | `destroy()` cleanup; the poller may be gone. |
| `ui/components/menu_manager.py:209` | `version = "Unknown"` | should log | diagnostic | About dialog; a wrong `pyproject.toml` path in a packaged build would be invisible. |
| `ui/components/model_diagnostics_panel.py:789` | `resolved_openvino = False` | should log | ux | A failing `resolve_project_model_settings` makes the summary say OpenVINO is off while the project uses it. Display only: the detector resolves the model on its own path. |
| `ui/components/polygon_drawing_service.py:42` | `return False` | legitimate | diagnostic | Tk variable of a destroyed panel; "single aquarium" is the safe answer. |
| `ui/components/state_synchronizer.py:186` | `processing_state = None` | should log | diagnostic | Third copy of the live probe. |
| `ui/components/state_synchronizer.py:198` | `return False` | should log | diagnostic | Same. |
| `ui/components/video_display.py:148` | `RESAMPLING_LANCZOS = Image.BICUBIC` | legitimate | diagnostic | Pillow moved the constant between versions; BICUBIC is the last resort (should be `AttributeError`). |
| `ui/dialogs/block_detail_dialog.py:132` | `self._project_has_polygon = False` | should log | diagnostic | Only drives the "reused arena" badge. |
| `ui/wizard/custom_regex_dialog.py:719` | `return` | legitimate | diagnostic | Dialog destroyed while its geometry is set. |
| `ui/wizard/model_selection_step.py:393` | `devices = ()` | legitimate | diagnostic | OpenVINO device probe; with no devices the wizard offers only AUTO. Its only comment is a pragma, so the guard counts it as silent. |
| `ui/wizard/wizard_dialog.py:339` | `return` | legitimate | diagnostic | Same as the regex dialog. |

## Documented fallbacks (20, not in the allowlist)

| Site (`src/zebtrack/...`) | Body | Verdict | Severity | Why |
| --- | --- | --- | --- | --- |
| `analysis/roi.py:1240` | `invalid += 1; continue` | legitimate | diagnostic | Unreadable WKB row of the mask sidecar. The count is logged with the coverage (`roi.seg_overlap.masks_loaded`), and a sidecar with no valid geometry degrades with a report warning. Residual, already noted by A5: a PARTLY corrupt sidecar reaches the log, not the report. |
| `coordinators/live_calibration_coordinator.py:2211` | `confidences = None` | legitimate | diagnostic | `conf` varies across Ultralytics versions; degrades to area ordering. |
| `core/detection/zone_scaler.py:33` | `return "centroid"` | legitimate | diagnostic | Stub settings; the default is a valid rule. |
| `core/recording/live_session_manager.py:1038` | `stacks[name] = "<stack formatting failed>"` | legitimate | diagnostic | Thread dump at a hung shutdown; the failure is written into the dump. |
| `core/services/zone_autoimport_policy.py:82` | `return ""` | legitimate | diagnostic | An unusable path never matches. |
| `core/video/processing_worker.py:1581` | `frame_msg["frame"] = preview_frame` | legitimate | diagnostic | Shared-memory write failed; the preview frame goes in the pickle payload instead. Preview only. |
| `core/viewmodels/hardware_status_view_model.py:306` | `aquarium_method = animal_method = None` | legitimate | diagnostic | Settings may be a mock; the slot list falls back to all slots. |
| `ui/components/analysis_window_panel.py:1081` | `return False` | legitimate | diagnostic | Editor window destroyed. |
| `ui/components/analysis_window_panel.py:1196` | `return False` | legitimate | diagnostic | Panel destroyed. |
| `ui/components/analysis_window_panel.py:1576` | `zone_data = None` | should log | ux | Comment says "unavailable early on"; a genuinely broken `get_zone_data()` leaves the window editor without the project's ROIs. |
| `ui/components/arduino_bindings_panel.py:262` | `return False` | legitimate | diagnostic | Panel destroyed. |
| `ui/components/arduino_bindings_panel.py:680` | `return []` | should log | ux | Same as `analysis_window_panel.py:1576`, for the bindings panel's ROI list. |
| `ui/components/canvas/renderer.py:510` | `return` | legitimate | diagnostic | Notebook gone while drawing the overlay. |
| `ui/components/class_roles_panel.py:1031` | `return False` | legitimate | diagnostic | Panel destroyed. |
| `ui/components/polygon_drawing_service.py:21` | `return []` | legitimate | diagnostic | Documented choice: skip the duplicate-name check rather than refuse the drawing. |
| `ui/components/weight_hardware_manager.py:296` | `return False` | legitimate | diagnostic | Probe during UI refresh. |
| `ui/components/zone_controls.py:314` | `return False` | legitimate | diagnostic | Panel destroyed. |
| `ui/gui.py:97` | `return False` | legitimate | diagnostic | A panel's own liveness check must not decide the rebind loop. |
| `ui/gui.py:107` | `return False` | legitimate | diagnostic | Panel destroyed. |
| `ui/wizard/experimental_design_step.py:128` | `return self.min_val` | legitimate | diagnostic | `IntVar` dirtied before construction. |

The 14 "should log" handlers are left as they are: each is a UI probe or label, and logging them
is a diagnostic improvement, not a correction. Logging one removes its allowlist entry.

## The guard

`tests/quality/test_no_silent_handlers.py` scans `src/zebtrack` with the rules above. A silent
handler fails unless its `<path>::<enclosing function>` is in `ALLOWED_SILENT` with at least that
many handlers; an allowance with fewer handlers than listed fails as stale, so the list only
shrinks. Each entry carries the verdict of the table above. The scanner has its own tests (every
silent shape found, every answering shape spared, `suppress` broad vs narrow, a directive comment
not counting as documentation, counting per scope).

### Proof that the guard sees

Appended to `src/zebtrack/io/recorder_factory.py`:

```python
def _planted_swallow(callback):
    try:
        callback()
    except Exception:
        pass
```

The guard failed with `src/zebtrack/io/recorder_factory.py::_planted_swallow (1)`. The file was
restored by copy; SHA-256 prefix `14f6c58528eca492` before and after. The proof was run again
after the final rule change (directive comments never document) with the same result.
