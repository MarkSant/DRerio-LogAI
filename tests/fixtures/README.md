# Test Fixtures

Data files the test suite reads from disk. Everything else — videos, trajectories,
projects — is **generated at run time** by the test that needs it.

> An earlier version of this file documented `sample_video.mp4`,
> `sample_video_long.mp4`, `sample_detections.parquet`,
> `sample_detections_with_calibration.parquet`, `zones_project.yaml`,
> `calibration_project.yaml`, `yolo11n.pt` and three generator scripts
> (`scripts/generate_test_video.py`, `generate_test_detections.py`,
> `generate_test_projects.py`). **None of them existed.** A fixture index that
> lists files nobody can find sends a reader looking for the wrong thing; this
> file now lists only what is actually here.

## What is here

### `api_baseline.json`

Frozen public API of `ApplicationGUI`.

- Read by: `tests/ui/test_api_breaking_changes.py`, `scripts/check_public_api.py`
- Purpose: a method disappearing from the public surface has to be a deliberate,
  reviewable change rather than a side effect.

### `golden/`

Signed-off output of the pre-recorded single-video pipeline.

| File | Content |
| --- | --- |
| `prerecorded_single_trajectory.csv` | The full `3_CoordMovimento` trajectory, in the immutable column order |
| `prerecorded_single_report.json` | The whole analysis report: distance, speed, freezing, sharp turns, ROI attribution, geotaxis |

- Read by: `tests/integration/test_prerecorded_golden.py`
- Produced by: `tests/helpers/prerecorded_pipeline.py`, which drives the real
  `_WorkerProcess` loop over a generated video with a deterministic
  contour-finding plugin — no model weights, no inference variance.
- Purpose: catch a change in the NUMBERS. The pre-recorded flows were validated
  end to end in v6.1.0, and the existing end-to-end test asserts only that files
  exist — which is why PR #524 could change 7 of 9 analysis parameters on a real
  project with the suite green.

**Re-recording** is deliberate:

```bash
ZEBTRACK_UPDATE_GOLDEN=1 pytest tests/integration/test_prerecorded_golden.py -m ""
```

Do it when you changed analysis behaviour on purpose, and let the new numbers
appear in the diff where a reviewer can see which metric moved. Do **not** do it
to make a red test go green — that is the one failure mode the fixture exists to
prevent. If you did not intend a change, read
`tests/integration/test_flow_isolation.py`: something probably leaked through the
shared `Settings` object.

## Why the videos are generated, not committed

A committed `.mp4` is a binary blob whose contents nobody can review, and its
decoded frames depend on the codec build on the machine that reads it. The
fixture video is a few dozen lines of `cv2.rectangle` calls instead
(`tests/helpers/prerecorded_pipeline.py::write_golden_video`), so the trajectory
it produces is inspectable in the source and identical everywhere the codec is
available. Where `mp4v` is missing, the affected tests skip rather than fail.

## Adding a fixture

1. Prefer generating it in the test. Reach for a committed file only when the
   content itself is the thing under test (a frozen baseline, a malformed file
   you need to parse).
2. Keep it small and text-based where possible — a fixture that cannot be read
   in a diff cannot be reviewed.
3. Never commit real experiment data.
4. Add it to this file, with what reads it and why.
