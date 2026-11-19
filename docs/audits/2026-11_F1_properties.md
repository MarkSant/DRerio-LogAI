# F1 — property tests for `utils/geometry` and `utils/cache` (TASK-087 item 1.8)

Hypothesis properties now cover every public function of `utils/geometry.py` and the
`TTLCache` / `ttl_cache` pair in `utils/cache.py` (`tests/utils/test_geometry.py`,
`tests/utils/test_cache.py`). Every property runs with `derandomize=True` and no example
database, so CI replays the same draws a developer sees locally. The cache never sleeps: a
fake clock replaces the `time` module inside `zebtrack.utils.cache`, in whole seconds so the
TTL boundary is hit exactly. Mutation blocks `geometry_properties` and `ttl_cache_model`
(16 mutations, all killed) sit at the end of `scripts/mutation_catalog.yaml`.

## Defects the properties found

| id | location | what is wrong | evidence | status |
| --- | --- | --- | --- | --- |
| F1-1 | `utils/geometry.py` `polygon_centroid` | Degeneracy was tested with `math.isclose(area_twice, 0.0)`, whose default `abs_tol=0` makes it true only for an exact zero. Collinear vertices with float coordinates leave a signed area of ~1e-16, and the shoelace divided by it: `(0.3, 0.9), (0.4, 1.2), (1.1, 3.3)` on `y = 3x` returned `x = 0.233`, off its own segment. Far from the origin the products also cancelled, so the triangulation and translation properties failed by up to 6e-5 px. | `test_collinear_vertices_have_no_centroid`, `test_collinear_float_vertices_do_not_produce_a_centroid_off_the_line`, `test_it_is_the_area_weighted_mean_of_any_triangulation`, `test_it_moves_with_a_translation` red before the fix. | fixed: the sum is taken relative to the first vertex and the area is compared with a tolerance scaled to `vertices × extent × (extent + magnitude)` (`_DEGENERATE_AREA_RTOL = 1e-12`). Integer pixel clicks are unaffected: their area was already exact. |
| F1-2 | `utils/cache.py` `TTLCache.set` | Overwriting a key kept its FIRST dict slot, and eviction breaks timestamp ties by slot. Under a clock that does not move between writes, `set a, set b, set a, set c` with `maxsize=2` evicted `a` (written last but one) and kept `b` (the stalest). | `test_rewriting_a_key_makes_it_the_newest_entry_for_eviction` and `test_the_cap_keeps_exactly_the_most_recently_written_keys` red before the fix. | fixed: `set` pops the key before re-inserting it. No production caller sets `maxsize` today (`VideoManager._scan_cache`, `WizardService._hw_cache`). |
| F1-3 | `utils/cache.py` `ttl_cache` | The key was `args + tuple(sorted(kwargs.items()))`, so `f(("a", 1))` and `f(a=1)` shared the key `(("a", 1),)` and the second call returned the first call's result. | `test_every_call_reads_back_its_own_result` found `[([], {'a': 0}), ([('a', 0)], {})]`; `test_a_keyword_argument_never_reads_a_positional_tuples_entry` red before the fix. | fixed: a private marker separates keyword pairs from positionals, as `functools.lru_cache` does. The decorator has no caller in `src` today. |

## Reported, not changed

| id | location | observation | why it was left |
| --- | --- | --- | --- |
| F1-4 | `utils/cache.py` | Expiry uses `time.time()`, a wall clock. An NTP step backwards keeps every entry alive past its TTL; a step forwards expires them all at once. `time.monotonic()` is the usual clock for a TTL. | A behaviour change, not a defect a property exposed. Three call sites (`get`, `set`, `in`); the fake clock in the tests would then stand in for `time.monotonic`. |
| F1-5 | `utils/cache.py` `TTLCache.__len__` / `info().currsize` | Both count entries that have expired but were not read since: only `get`, `in` and `set` purge. The model test encodes this lazy semantics. | Documented nowhere, harmless for the two callers (neither reads the size). Worth a docstring line, or a purge in `__len__`. |
| F1-6 | `utils/geometry.py` `snap_point_to_axes` | The comment says the center "wins over the axis projections" on a tie. A center ties with its vertical projection `(cx, py)` only when `cy == py`, which makes them the same point (likewise for the horizontal one), so that order can never change the result. The observable tie orders are anchors before centers, earlier items first, and an anchor's vertical alignment before its horizontal one; those are what the properties pin. | Comment-only; `src` edits outside a bug fix were out of scope for this pass. |
| F1-7 | `utils/geometry.py` `simplify_polygon` | `cv2.approxPolyDP(closed=True)` is not strictly ε-bounded: after Douglas-Peucker it drops isolated vertices within ε/√2 of the next chord, so an input vertex can end up `(1 + 1/√2)·ε` from the simplified outline (1.4 ε measured on star-shaped outlines). The shape property asserts that bound, not ε. | cv2 behaviour; the docstring never promised ε. |
