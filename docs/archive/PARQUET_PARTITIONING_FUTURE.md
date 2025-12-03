# Parquet Partitioning - Future Enhancement

**Status**: Documented (Not Implemented)
**Priority**: LOW
**Improvement**: #3
**Expected Benefit**: 20-30% faster batch processing for projects with 50+ videos

## Summary

IMPROVEMENT #3 proposes partitioned Parquet storage for multi-video projects to reduce file I/O overhead and centralize metadata management.

## Current Architecture

```
project_results/
  video1_results/
    3_CoordMovimento_video1.parquet    (2.5 MB)
  video2_results/
    3_CoordMovimento_video2.parquet    (2.3 MB)
  ...
  video50_results/
    3_CoordMovimento_video50.parquet   (2.1 MB)
```

**Issues**:
- 50 separate Parquet files = 50 open/close operations
- Separate metadata for each file (schema stored 50 times)
- Overhead for small files (<5 MB)

## Proposed Architecture

```
project_data/
  trajectories/                        # Partitioned dataset
    video=video1/
      part-0.parquet
    video=video2/
      part-0.parquet
    ...
    video=video50/
      part-0.parquet
  _common_metadata                     # Shared schema
  _metadata                            # Partition index
```

**Benefits**:
- **Centralized metadata**: Schema stored once, not N times
- **Efficient queries**: `pq.ParquetDataset` API for multi-file reads
- **Batch processing**: Read multiple videos in parallel
- **Arrow integration**: Better integration with PyArrow table API

## Implementation Plan (Future Work)

### Phase 1: Recorder Refactoring

**File**: `src/zebtrack/io/recorder.py`

```python
class PartitionedRecorder:
    """
    Recorder that writes to partitioned Parquet dataset.

    Replaces individual Parquet files with a partitioned structure
    for improved batch processing performance.
    """

    def __init__(self, project_root: Path, video_id: str):
        self.project_root = project_root
        self.video_id = video_id
        self.partition_path = project_root / "trajectories" / f"video={video_id}"
        self.partition_path.mkdir(parents=True, exist_ok=True)

    def start_recording(self, ...):
        """Initialize partitioned writer."""
        # Use pq.ParquetWriter with partition_cols=['video']
        # Write to project_root/trajectories/ with partitioning
        pass

    def flush_detection_data(self):
        """Flush data to partitioned dataset."""
        # Append to partition with consistent schema
        pass
```

### Phase 2: Analysis Service Update

**File**: `src/zebtrack/analysis/analysis_service.py`

```python
def load_trajectory_dataframe_partitioned(
    self, project_root: Path, video_id: str | None = None
) -> pd.DataFrame:
    """
    Load trajectory data from partitioned dataset.

    Args:
        project_root: Root path to project
        video_id: If provided, load only this video. Otherwise load all.

    Returns:
        pd.DataFrame with trajectories
    """
    import pyarrow.parquet as pq

    dataset_path = project_root / "trajectories"
    dataset = pq.ParquetDataset(
        dataset_path,
        partitioning=pq.partitioning(pa.schema([("video", pa.string())])),
    )

    if video_id:
        # Filter for specific video
        table = dataset.read(filters=[("video", "=", video_id)])
    else:
        # Read all videos
        table = dataset.read()

    return table.to_pandas()
```

### Phase 3: Migration Tool

Create migration script to convert existing projects:

```python
def migrate_project_to_partitioned(project_path: Path) -> None:
    """
    Migrate existing project from individual files to partitioned format.

    Steps:
    1. Find all 3_CoordMovimento_*.parquet files
    2. Create new partitioned dataset
    3. Copy data to partitions
    4. Verify data integrity
    5. Archive old files
    """
    pass
```

## Performance Impact (Estimated)

### Batch Processing (50 videos)

| Metric | Current | Partitioned | Improvement |
|--------|---------|-------------|-------------|
| File opens | 50 | 1 | **-98%** |
| Metadata reads | 50 × 2KB = 100KB | 1 × 2KB = 2KB | **-98%** |
| Total I/O time | ~500ms | ~150ms | **-70%** |

### Query Performance

```python
# Current: Load all videos (SLOW)
dfs = [pd.read_parquet(f) for f in parquet_files]
df_all = pd.concat(dfs)

# Partitioned: Single read (FAST)
df_all = pd.read_parquet("project_data/trajectories")
```

**Speedup**: 20-30% for batch operations

## When to Implement

Consider implementing when:
1. **Project size**: Regular projects with 50+ videos
2. **Batch analysis**: Users frequently analyze multiple videos together
3. **Cloud storage**: S3/GCS where file count matters for performance
4. **Team collaboration**: Multiple users sharing project data

## Compatibility Considerations

### Backward Compatibility

- Keep support for individual Parquet files
- Add `--partitioned` flag to recorder
- Auto-detect format on load:
  ```python
  if (project_root / "trajectories").exists():
      # Load partitioned
      return load_trajectory_dataframe_partitioned(project_root, video_id)
  else:
      # Load individual file (legacy)
      return load_trajectory_dataframe(parquet_path)
  ```

### Migration Strategy

1. **Opt-in**: New projects can use partitioned format
2. **Gradual migration**: Migrate projects on first load
3. **Dual support**: Support both formats for 1-2 versions
4. **Deprecation**: Eventually deprecate individual files

## Related Work

**2025 Best Practices**:
- [Apache Arrow: Partitioned Datasets Guide](https://arrow.apache.org/docs/python/parquet.html#partitioned-datasets)
- [Pandas Performance Patterns](https://pandas.pydata.org/docs/user_guide/enhancingperf.html)
- [Dask Partitioning Strategies](https://docs.dask.org/en/stable/dataframe-parquet.html)

## Decision Rationale

**Why not implemented now**:
1. **LOW priority**: Current architecture works well for typical projects (5-20 videos)
2. **Breaking change**: Would require migration tool and version upgrade
3. **Complexity**: Requires significant refactoring of recorder and analysis service
4. **ROI unclear**: Benefit only significant for very large projects (50+ videos)

**When to reconsider**:
- User feedback requests batch processing improvements
- Projects regularly exceed 50 videos
- Cloud storage usage increases (S3/GCS)
- PyArrow ecosystem matures further

## Implementation Effort

**Estimated effort**: 3-5 days
- Day 1: Refactor Recorder for partitioned writes
- Day 2: Update AnalysisService for partitioned reads
- Day 3: Create migration tool
- Day 4: Update tests and documentation
- Day 5: Integration testing and validation

## References

- **Audit Document**: `docs/DATA_PIPELINE_AUDIT.md` (Section 5.2)
- **PyArrow Docs**: https://arrow.apache.org/docs/python/parquet.html
- **Hive-style Partitioning**: Standard format used by Spark, Dask, Arrow

---

**Conclusion**: Documented as future enhancement. Implementation deferred until user needs justify the complexity and breaking changes.
