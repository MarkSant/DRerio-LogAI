# ADR-004: Live Camera Display Divergence

**Status:** Accepted
**Date:** 2025-12-02
**Decision Makers:** Development Team
**Context:** Phase 4 Architecture Cleanup

---

## Context

During the Phase 3/4 architecture consolidation, we identified that the Live Camera feature uses a different display mechanism than the recorded video analysis:

| Feature | Display Method | Event Used |
| --------- | --------------- | ------------ |
| Recorded Video Analysis | `CanvasManager` | `Events.UI_DISPLAY_FRAME` |
| Live Camera Preview | `LivePreviewWindow` | Direct `root.after()` calls |

This divergence was flagged as a potential architectural inconsistency (Vulnerability V5 in the audit).

---

## Decision

**We will DOCUMENT this divergence as an intentional design decision, NOT unify the implementations.**

---

## Rationale

### 1. Different Threading Models

- **Recorded Video:** Uses `ProcessingWorker` in a separate process with queue-based frame delivery
- **Live Camera:** Uses daemon threads for capture + processing with direct callback updates

Forcing both through the same channel would require:

- Adding queue overhead to live camera (latency impact)
- Or modifying `CanvasManager` to support multiple threading models

### 2. Different Lifecycle Requirements

- **CanvasManager:** Bound to the main application window, always exists
- **LivePreviewWindow:** Created/destroyed per camera session, independent Toplevel

### 3. Recent Stabilization

Live camera was unified and stabilized in Phase 8 (January 2025). The current implementation:

- Works reliably
- Has no user complaints
- Has proper thread cleanup (daemon threads)

### 4. Risk vs. Benefit Analysis

| Factor | Unify | Document |
| -------- | ------- | ---------- |
| Development Time | 2-3 weeks | 1 day |
| Risk of Regression | High | None |
| User Impact | None (internal) | None |
| Code Complexity | Increases | Stays same |
| Maintenance Burden | Slightly lower | Acceptable |

---

## Consequences

### Positive

1. **No regression risk** - Live camera continues to work as-is
2. **Clear documentation** - Future developers understand the intentional divergence
3. **Time saved** - Focus on higher-value refactoring work

### Negative

1. **Feature Asymmetry** - Drawing tools built for `CanvasManager` won't work on live preview
2. **Two display paths** - Slightly more complex mental model

### Accepted Trade-offs

If drawing tools are needed for live camera in the future, they should be implemented specifically for `LivePreviewWindow` rather than trying to route live frames through `CanvasManager`.

---

## Implementation

### Files Updated

1. **`docs/SYSTEM_INTEGRATION_MAP.md`** - Section 3.3 expanded with justification
2. **`src/zebtrack/core/live_camera_service.py`** - Docstring added explaining divergence
3. **This ADR** - Formal decision record

### Code Changes

None required - this is a documentation-only decision.

---

## Related Documents

- `docs/LIVE_CAMERA_UNIFICATION.md` - Phase 8 unification details
- `docs/SYSTEM_INTEGRATION_MAP.md` - Event flow documentation
- `purring-questing-eclipse.md` - Vulnerability correction plan

---

## Review

This ADR should be reviewed if:

- Users request drawing tools for live camera
- Performance issues are found with current live camera implementation
- Major refactoring of display layer is planned
