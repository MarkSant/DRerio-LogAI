# Commit Message (Sugestão)

```
fix(live-analysis): resolve Canvas Preto - frames now display in Analysis tab

CRITICAL FIX: Live camera frames were not appearing in integrated Analysis tab.

Root Causes Fixed:
1. Event publication moved OUTSIDE preview_window check (line 1180)
   - Previously inside `if self.preview_window:` block
   - Now executes regardless of window creation

2. Inverted use_external_preview logic corrected (line 361)
   - Was: `if not use_external_preview` → created window (WRONG)
   - Now: `if use_external_preview` → creates window (CORRECT)

3. Variable name error fixed (lines 1191, 1207)
   - Was: frame_count (undefined)
   - Now: frame_number (from queue)

Additional Improvements:
- Suppressed RECORDING_STARTED warning (fire-and-forget event)
- Changed polygon validation log from error → debug level
- Added session_coordinator to AnalysisControlViewModel for cancel support

User-Facing Impact:
✅ Live frames now display correctly in Analysis tab
✅ Animal detections visible in real-time with bounding boxes
✅ External window no longer opens unexpectedly
✅ Cancel button now works for live sessions
✅ No runtime crashes from undefined variables
✅ Clean logs without scary warnings

Files Changed:
- src/zebtrack/core/live_camera_service.py (event publication fix)
- src/zebtrack/ui/event_bus.py (warning suppression)
- src/zebtrack/coordinators/processing_coordinator.py (log level)
- src/zebtrack/core/viewmodels/analysis_control_view_model.py (cancel support)
- src/zebtrack/ui/components/canvas_manager.py (debug logs)

Tests Added:
- tests/test_live_analysis_integration.py (9 tests, all passing)

Documentation:
- docs/decisions/ADR-003-live-analysis-canvas-integration-fix.md
- docs/LIVE_ANALYSIS_CANVAS_FIX.md
- docs/INDEX.md (updated with new docs)

Resolves: Canvas Preto bug (Phase 3 blocker)
Unblocks: Phases A & B consolidation
```

---

# Git Commands (Para executar)

```bash
# Stage all changes
git add src/zebtrack/core/live_camera_service.py
git add src/zebtrack/ui/event_bus.py
git add src/zebtrack/coordinators/processing_coordinator.py
git add src/zebtrack/core/viewmodels/analysis_control_view_model.py
git add src/zebtrack/ui/components/canvas_manager.py
git add src/zebtrack/coordinators/recording_coordinator.py
git add src/zebtrack/coordinators/session_coordinator.py
git add src/zebtrack/ui/events.py
git add tests/test_live_analysis_integration.py
git add tests/coordinators/test_recording_coordinator.py
git add docs/decisions/ADR-003-live-analysis-canvas-integration-fix.md
git add docs/LIVE_ANALYSIS_CANVAS_FIX.md
git add docs/INDEX.md

# Commit with detailed message
git commit -m "fix(live-analysis): resolve Canvas Preto - frames now display in Analysis tab" -m "CRITICAL FIX: Live camera frames were not appearing in integrated Analysis tab." -m "Root Causes Fixed:
1. Event publication moved OUTSIDE preview_window check (line 1180)
2. Inverted use_external_preview logic corrected (line 361)
3. Variable name error fixed (lines 1191, 1207)
4. Added session_coordinator to AnalysisControlViewModel for cancel support

User-Facing Impact:
✅ Live frames now display correctly in Analysis tab
✅ Animal detections visible in real-time
✅ Cancel button now works for live sessions
✅ No crashes or scary warnings

Tests: 9/9 passing in test_live_analysis_integration.py
Resolves: Canvas Preto bug (Phase 3 blocker)
Unblocks: Phases A & B consolidation"

# Push to remote
git push origin main
```
