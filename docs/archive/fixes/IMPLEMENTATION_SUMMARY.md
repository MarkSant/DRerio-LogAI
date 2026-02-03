# Implementation Summary: Unified Report Generation Fixes

**Date**: December 13, 2025
**Issue**: Unified report generation had three critical bugs affecting UI responsiveness, data accuracy, and schema consistency.

## Problems Fixed

### 1. **UI Status Stuck on "Gerando relatório unificado"**
- **Symptom**: Status bar showed "Gerando relatório unificado..." indefinitely even after reports were generated
- **Root Cause**: Missing `Events.UI_SET_STATUS` call to clear status to "Pronto." after completion
- **Fix**: Added status clearing in `_generate_unified_report` at line 1845 of `processing_coordinator.py`

### 2. **Metadata Shows "unassigned" and "unknown" in Unified Reports**
- **Symptom**: Excel unified reports showed `group_id="unassigned"` and `experiment_id="unknown"` even though project metadata had correct values
- **Root Cause**: System read old parquet files directly without re-enriching with current project metadata
- **Fix**: Added metadata re-enrichment logic after `pd.read_parquet()` that updates only rows with "unassigned"/"unknown" using current project metadata

### 3. **DataFrame Concatenation Warnings and Schema Mismatches**
- **Symptom**: FutureWarning about DataFrame concatenation, inconsistent columns in unified Excel reports
- **Root Cause**: Summary parquets had different ROI column schemas (video1: roi1/roi2, video2: roiA/roiB) because columns were generated per-video instead of using project-wide standardization
- **Fix**: Implemented defensive column alignment before concatenation + user warning dialog + proactive schema standardization for future parquets

## Files Modified

### Core Changes

1. **`src/zebtrack/coordinators/processing_coordinator.py`**
   - Added `_find_project_roi_names()` helper method (finds ROI names from first video with zone data)
   - Modified `generate_unified_report()`: metadata re-enrichment + DataFrame alignment + warning
   - Modified `generate_parquet_summaries()`: collect expected ROI names and pass through pipeline
   - Modified `_process_summary_video()`: added `expected_roi_names` parameter
   - Updated `export_summary_data()` call to pass `expected_roi_names`

2. **`src/zebtrack/analysis/data_transformer.py`**
   - Added `standardize_roi_columns()` method: pads missing ROI columns with NaN (metrics) or 0 (counts)

3. **`src/zebtrack/analysis/reporter.py`**
   - Modified `export_summary_data()`: added `expected_roi_names` parameter, calls `standardize_roi_columns()` before export

4. **`src/zebtrack/settings.py`**
   - Added `suppress_roi_mismatch_warning: bool` field to `UIFeatureFlags` model

5. **`config.yaml`**
   - Added `suppress_roi_mismatch_warning: false` to `ui_features` section with documentation

6. **`src/zebtrack/ui/components/processing_reports.py`**
   - Removed dead event emission `self.emit_event("reports.generate_unified", {})` from button click handler

### Tests Added

7. **`tests/coordinators/test_unified_report.py`** (NEW FILE - 660 lines)
   - `test_status_clears_after_unified_report_success`
   - `test_status_not_cleared_on_failure`
   - `test_metadata_enrichment_updates_unassigned_group_id`
   - `test_metadata_enrichment_updates_unknown_experiment_id`
   - `test_metadata_enrichment_preserves_existing_values`
   - `test_dataframe_alignment_with_mismatched_schemas`
   - `test_roi_mismatch_warning_shown_when_schemas_differ`
   - `test_roi_mismatch_warning_suppressed_by_setting`
   - `test_find_project_roi_names_returns_first_video_rois`
   - `test_find_project_roi_names_returns_none_when_no_zones`
   - `test_unified_report_full_workflow_with_different_rois` (integration test)

8. **`tests/analysis/test_data_transformer.py`** (220 lines added)
   - `test_standardize_roi_columns_pads_missing_columns`
   - `test_standardize_roi_columns_returns_unchanged_when_no_expected_rois`
   - `test_standardize_roi_columns_handles_empty_expected_list`
   - `test_standardize_roi_columns_preserves_existing_data`
   - `test_standardize_roi_columns_adds_all_expected_metric_types`
   - `test_standardize_roi_columns_uses_correct_default_values`
   - `test_standardize_roi_columns_handles_multiple_rois`
   - `test_standardize_roi_columns_does_not_modify_original_dataframe`

## Technical Details

### Metadata Re-Enrichment Logic

```python
# After reading parquet, check for stale metadata
if entry:
    current_metadata = entry.get("metadata", {})
    if current_metadata:
        # Update only "unassigned" rows
        if "group_id" in df.columns and (df["group_id"] == "unassigned").any():
            group_id = current_metadata.get("group_id") or current_metadata.get("group")
            if group_id:
                df.loc[df["group_id"] == "unassigned", "group_id"] = str(group_id)

        # Update only "unknown" rows
        if "experiment_id" in df.columns and (df["experiment_id"] == "unknown").any():
            exp_id = current_metadata.get("experiment_id") or entry.get("experiment_id")
            if exp_id:
                df.loc[df["experiment_id"] == "unknown", "experiment_id"] = str(exp_id)
```

### DataFrame Alignment Logic

```python
# Collect all unique columns
all_columns = set()
for df in dfs:
    all_columns.update(df.columns)

# Detect schema mismatch
schema_mismatch = any(len(df.columns) < len(all_columns) for df in dfs)

# Pad missing columns
aligned_dfs = []
for df in dfs:
    df_copy = df.copy()
    for col in all_columns:
        if col not in df_copy.columns:
            df_copy[col] = pd.NA
    aligned_dfs.append(df_copy[sorted(all_columns)])

# Concatenate aligned DataFrames
aggregated_df = pd.concat(aligned_dfs, ignore_index=True)

# Show warning if schemas differed
if schema_mismatch and not settings_obj.ui_features.suppress_roi_mismatch_warning:
    self._publish_event(Events.UI_SHOW_WARNING, {...})
```

### ROI Column Standardization

```python
# In DataTransformer
roi_column_templates = [
    ("tempo_no_{}_s", pd.NA),           # NaN for continuous metrics
    ("entradas_no_{}", 0),               # 0 for count metrics
    ("latencia_para_{}_s", pd.NA),
    ("distancia_no_{}_cm", pd.NA),
    # ... etc
]

for roi_name in expected_roi_names:
    for template, default_value in roi_column_templates:
        col_name = template.format(roi_name)
        if col_name not in df.columns:
            df[col_name] = default_value
```

## User-Facing Changes

1. **Status Bar**: Now correctly clears to "Pronto." after unified report generation completes
2. **Metadata Accuracy**: Unified reports now show correct `group_id` and `experiment_id` values from project metadata
3. **ROI Consistency Warning**: User is warned when videos have different ROI schemas (can be suppressed via `config.yaml`)
4. **Future Reports**: New summary parquets will have standardized column schemas based on project ROIs

## Configuration

Users can suppress the ROI mismatch warning by adding to `config.yaml`:

```yaml
ui_features:
  suppress_roi_mismatch_warning: true
```

## Testing

Run tests with:
```bash
# All unified report tests
poetry run pytest tests/coordinators/test_unified_report.py -v

# DataTransformer ROI standardization tests
poetry run pytest tests/analysis/test_data_transformer.py::test_standardize_roi_columns -v

# Full test suite (fast tests only)
poetry run pytest -q
```

## Backward Compatibility

- **Existing parquets**: Will be handled by alignment logic (no regeneration needed)
- **Config files**: New setting has safe default (`suppress_roi_mismatch_warning: false`)
- **API compatibility**: All changes are backward compatible (added optional parameters with defaults)

## Future Improvements

1. Consider caching `expected_roi_names` in project metadata for performance
2. Add migration script to regenerate old summaries with standardized schemas (optional)
3. Add validation to warn about ROI naming conflicts across videos
4. Consider adding "Don't show again" checkbox to warning dialog itself

## Related Issues

- Fixes the terminal warning: `event_bus.dispatch.no_handlers ... event_name=reports.generate_unified`
- Resolves FutureWarning about DataFrame concatenation behavior
- Addresses user-reported issue with metadata not appearing in unified reports

---

**Status**: ✅ Implementation Complete
**Test Coverage**: 19 new tests added (11 unified report + 8 data transformer)
**Files Changed**: 6 core files + 2 test files
**Lines Added**: ~600 lines (including tests)
