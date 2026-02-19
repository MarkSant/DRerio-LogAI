# Coverage Standards Analysis — Evidence-Based Gate Justification

> **Phase 8.2**: Documentation & Standardization
> **Date**: 2025-07-24
> **Status**: Accepted

## 1. Scientific Software Coverage Standards (Research Summary)

### 1.1 Standards Surveyed

| Standard / Authority | Coverage Requirement | Source |
|---|---|---|
| **JOSS** (Journal of Open Source Software) | "Good: An automated test suite hooked up to CI" | [Review Criteria](https://joss.readthedocs.io/en/latest/review_criteria.html) |
| **pyOpenSci** | "Automated tests: Package has a testing suite and is tested via CI" | [Editor-in-Chief Guide](https://www.pyopensci.org/software-peer-review/our-process/editors-guide.html) |
| **OpenSSF Best Practices — Passing** | "SUGGESTED: cover most (or ideally all) code branches" | [Criteria](https://www.bestpractices.dev/en/criteria) |
| **OpenSSF Best Practices — Silver** | **≥80% statement coverage** (MUST) | [Silver Criteria](https://www.bestpractices.dev/en/criteria/1) `[test_statement_coverage80]` |
| **OpenSSF Best Practices — Gold** | **≥90% statement + ≥80% branch** (MUST) | [Gold Criteria](https://www.bestpractices.dev/en/criteria/2) `[test_statement_coverage90]`, `[test_branch_coverage80]` |

### 1.2 Key Insight

JOSS and pyOpenSci — the primary publication venues for scientific Python software —
require **tests + CI** but specify **no numeric coverage threshold**. The first
numeric threshold appears at OpenSSF Silver (80% statement). This means any
coverage percentage above 0% with CI already satisfies JOSS/pyOpenSci; the
question is how far toward Silver/Gold the project should aim.

## 2. Current Coverage Baseline (Measured 2025-07-24)

### 2.1 Per-Gate Measurements

| CI Gate | Test Command | Current % | Current Threshold |
|---|---|---|---|
| Linux core | `pytest -m "not gui" --cov=zebtrack` | **46.1%** | 45% |
| Linux GUI | `pytest -m gui -n0 --cov=zebtrack` | ~30% | 30% |
| Windows core | `pytest -m "not gui" --ignore=tests/ui --cov=zebtrack` | ~25% | 25% |
| Local (pytest.ini) | `pytest --cov=zebtrack` | ~46% | 40% |

### 2.2 Per-Package Breakdown (Non-GUI Tests)

| Coverage | Package | Category |
|---|---|---|
| 85.4% | `ui.builders` | Core-adjacent |
| 83.7% | `analysis` | Core |
| 79.6% | `core.services` | Core |
| 79.0% | `core.detection` | Core |
| 78.2% | `io` | Core |
| 77.2% | `core` | Core |
| 76.2% | root (`zebtrack`) | Core |
| 74.0% | `tracker` | Core |
| 66.5% | `core.project` | Core |
| 62.2% | `utils` | Core |
| 61.6% | `core.viewmodels` | Core |
| 59.2% | `plugins` | Core |
| 55.6% | `analysis.reporters` | Core |
| 54.3% | `core.video` | Core |
| 47.2% | `ui` (main) | UI-dependent |
| 42.8% | `core.recording` | Core |
| 39.5% | `coordinators` | Core/UI bridge |
| 30.7% | `ui.components.canvas` | UI |
| 28.4% | `ui.components` | UI |
| 23.7% | `ui.components.project_views` | UI |
| 16.9% | `ui.wizard` | UI |
| 9.7% | `ui.dialogs` | UI |
| 0.0% | `core.events` | Untested |

### 2.3 Architecture-Adjusted Analysis

ZebTrack-AI is a **desktop Tkinter application** where UI code (dialogs, wizard
steps, canvas managers) constitutes ~60% of the codebase. This code:

- Requires a display server or Xvfb to test
- Tests run sequentially (`-n0`) and are inherently slow
- Many components create real Tk widgets that are fragile in CI

**Core business logic** (detection, analysis, IO, services) achieves **60-85%
coverage** — which already approaches OpenSSF Silver for those modules.

## 3. Coverage Gate Proposal

### 3.1 Methodology

The new thresholds are set using a **ladder approach**:

1. No gate should be set below the current measured value (prevents regressions)
2. Each gate increases by a realistic increment toward OpenSSF Silver
3. GUI coverage grows slower due to inherent Tkinter testing constraints
4. Windows coverage trails Linux due to limited CI test scope

### 3.2 New Thresholds

| CI Gate | Old → New | Increment | Rationale |
|---|---|---|---|
| **Linux core** | 45% → **50%** | +5% | Nearest round number above current 46.1%; adds buffer for variance |
| **Linux GUI** | 30% → **32%** | +2% | Modest increase; GUI testing has high overhead |
| **Windows core** | 25% → **28%** | +3% | Windows CI ignores `tests/ui/` entirely; must stay realistic |
| **Local (pytest.ini)** | 40% → **45%** | +5% | Matches Linux core gate |

### 3.3 Roadmap to OpenSSF Silver (80%)

| Phase | Linux Core Target | Focus Area |
|---|---|---|
| Phase 8 (current) | 50% | Fix regressions + baseline measurement |
| Phase 9 (future) | 58% | Coordinator tests + recording service tests |
| Phase 10 (future) | 66% | Reporter tests + plugin tests |
| Phase 11 (future) | 74% | Integration tests + edge cases |
| Phase 12 (future) | 80% | OpenSSF Silver compliance |

### 3.4 Justification vs. User's Initial Request (65/40/40)

The user initially proposed 65/40/40 as "moderate" targets before baseline
measurement. Now that we have data:

- **65% Linux core** requires covering ~7,600 additional source lines — approximately
  200+ new test functions. This exceeds the scope of a documentation/standardization
  phase.
- **50/32/28** is an achievable improvement that establishes the measurement
  infrastructure and prevents regressions, while documenting a clear roadmap.

## 4. Codecov Configuration

The project uses `codecov.yml` with `auto` targets. This configuration
automatically ratchets coverage upward based on recent measurements, which
complements the hard CI gates defined in `ci.yml`.

### 4.1 Recommended Changes

- Keep `codecov.yml` targets at `auto` (self-adjusting)
- Core Windows and GUI Linux flags remain `informational: true`
- The authoritative gates are in `ci.yml` (`--cov-fail-under`)

## 5. References

- [JOSS Review Criteria](https://joss.readthedocs.io/en/latest/review_criteria.html)
- [pyOpenSci Editor Guide](https://www.pyopensci.org/software-peer-review/our-process/editors-guide.html)
- [OpenSSF Best Practices Criteria](https://www.bestpractices.dev/en/criteria)
- Wilson et al. (2017). "Good enough practices in scientific computing."
  *PLOS Computational Biology*, 13(6), e1005510.
