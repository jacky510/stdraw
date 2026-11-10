# Cache lifecycle and the rounded-key aliasing verdict

How the routing caches interact with the byte-for-byte determinism promise,
and why every `layout()` call starts by wiping them.

## The caches

| Cache | Location | Scope | Key shape |
|---|---|---|---|
| `_ROUTE_CACHE` | `stdraw/visibility.py` | module-level (process-wide) | `(src, dst, rects, clearance)` with every coordinate **rounded to 0.001px** |
| `_CORNER_VIS_CACHE` | `stdraw/visibility.py` | module-level (process-wide) | rounded corner/edge geometry |
| `_edge_world_cache`, `_anchor_cache`, `_coi_geom_cache`, `_snap_plan_cache` | `stdraw/routing.py` (`Router` instance attributes) | per-`Router` instance | n/a — a fresh `Router` is constructed inside every `layout()` / trial, so these cannot outlive one layout call |

## Verdict: cross-layout key collision is REAL (in theory)

The module-level cache keys round coordinates to three decimal places.
Rounding is a **lossy map**: two *different* input geometries whose
coordinates differ by less than 0.001px alias to the same key. Within a
single graph the documented "pure function, same input same output" claim
still holds exactly. But across layouts in one process:

- graph A computes a route and populates the cache;
- graph B later produces a query whose *rounded* key equals A's entry while
  its *true* geometry differs by sub-milli-pixel amounts;
- B receives A's route — and whichever of A/B runs first changes the result.

The probability is low (it needs two graphs whose edge endpoints and all
inflated obstacle boxes nearly coincide after rounding), but it is not zero,
and a single hit violates the byte-for-byte reproducibility promise while
depending on processing order. Verdict: **real hazard, fix required** — not
a "cannot happen" case.

## The fix: reset per layout

`layout_auto.layout()` calls `visibility.reset_caches()` as its first
action: both module-level caches start empty for every graph, so no result
can depend on what ran earlier in the same process. Router-level caches
need no reset (instance-scoped, see table above).

Cost: cache reuse *across* layouts is given up. Within one layout the cache
still works as before (retry sweeps and anchor snap re-query the same
geometries repeatedly, which is where the hits actually are), so the
performance impact on a single graph is nil.

## Enforcement

`tests/test_layout_cache_order.py` pins the guarantee at three levels:

1. `reset_caches()` empties both module caches (direct unit check);
2. a warm-cache in-process rerun of the same graph is byte-identical;
3. the same two graphs laid out in two different orders inside one process
   produce byte-identical payloads.

The heavier corpus-level proof lives in the release sweep discipline:
classic 21 + corpus 80 double runs compared by `layout.json` sha256.
