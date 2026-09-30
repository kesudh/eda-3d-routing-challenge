# Zero-cost SPT re-selection on benchmarks_hard — CLEAN NEGATIVE

**Verdict: FAIL (TIE with PR#3, exactly).** Hard tier stayed at **145807 /
aggregate 1.381266**. Not a single case moved.

Hypothesis tested: an SPT of a net attains every sink's free-graph minimum
simultaneously, so **every** SPT of a net costs exactly the same delay, and
re-selecting one is a zero-cost move that frees contested middle-layer vertices
for neighbours. ~1976 "choice vertices" exist across the 9 hard cases.

## Result

| case | PR#3 | after maximal zero-cost release + 1-opt | delta |
|---|---|---|---|
| case_01 | 8674 | 8674 | 0 |
| case_02 | 13230 | 13230 | 0 |
| case_03 | 11086 | 11086 | 0 |
| case_04 | 13095 | 13095 | 0 |
| case_05 | 15311 | 15311 | 0 |
| case_06 | 19882 | 19882 | 0 |
| case_07 | 21433 | 21433 | 0 |
| case_08 | 21620 | 21620 | 0 |
| case_09 | 21476 | 21476 | 0 |
| **total** | **145807** | **145807** | **0** |

Scored with the repo's own checker
(`python -m m3d.cli score-suite --suite benchmarks_hard --submission-dir ...`),
which independently recomputes delay and rejects illegal routes.

## The seam is real but pointed the wrong way

Two independent measurements locate exactly why.

**1. 97-100% of blocking vertices are not releasable at all.**
For every (detoured net m, free-optimal path, blocking vertex v owned by net o)
triple: can net o choose a *different* SPT that avoids v? (`measure_seam.py`)

```
case_01 119 triples   115 FORCED (96.6%)    4 CHOICE (3.4%)
case_03 130 triples   130 FORCED (100.0%)   0 CHOICE
case_07 211 triples   209 FORCED (99.1%)    2 CHOICE
... TOTAL 1534 triples  1514 FORCED (98.7%)  20 CHOICE (1.30%)
```

Only 1.3% of the vertices actually standing between a net and its free optimum
can be released by an equal-cost re-selection of their owner. The rest sit on
the owner's *unique* shortest path — there is no alternative tree.

**2. The releasable vertices are in the wrong layers.** (`seam_exact.py` +
layer profile) Of 54,595 occupied vertices across the 9 cases, 2,070 (3.79%)
are releasable — this reproduces the brief's 1,976 count. But broken down by
layer:

| case | releasable z=0 | z=1 | **z=2** | **z=3** | z=4 | z=5 |
|---|---|---|---|---|---|---|
| case_01 | 15 | 38 | **6** | **2** | 29 | 20 |
| case_05 | 39 | 72 | **7** | **2** | 117 | 30 |
| case_09 | 51 | 188 | **8** | **7** | 204 | 51 |

The contended middle layers z=2,3 are ~85% occupied, yet they contain almost
none of the choice vertices. The choice vertices are in the *slack* layers
z=1,4 — exactly the layers nobody is waiting for. So the seam, taken to its
logical maximum, frees precisely the vertices that were never contended.

That is why `seam_maximal.py` — which forces **every** net to release the union
of all its choice vertices simultaneously (2,038 vertices freed at provably
zero cost), followed by three full 1-opt sweeps — moves the total by **+0 on all
nine cases**. No net was ever waiting for those vertices.

## What was run

- `spt_search.py` — flat 3D grid, indexed vertices, per-net Dijkstra over the
  blocked graph, SPT built only from **tight** predecessors
  (`d[u] + w == d[v]`) so every tree is a genuine SPT with unchanged sink
  delays. Verified round-trip against `m3d/checker.py` (case_01: 8674, legal).
- `spt_directed.py` — directed move generator: find a detoured net, locate the
  blocking vertex on its free-optimal path, force its owner to release it, sweep,
  accept only on strict improvement. 296 iterations on case_01, 0 improvements.
- `upper_bound.py` — whole-suite re-selection under `minverts` (minimise own
  vertex count), `minmid` (avoid z=2,3), `maxouter` (prefer z=1,4), all with
  full sweeps: 145807 → 145807 on every variant.
- `seam_stochastic.py` — random tight-DAG tie-breaks, 35% of nets perturbed per
  trial, 2 sweeps, accept only strict improvement: **2,869 trials across all 9
  cases, 0 improvements.**
- `measure_seam.py` / `seam_exact.py` / `seam_maximal.py` — the measurements
  above.

Two implementation bugs were found and fixed en route (documented here because
they explain the earlier "buggy and slow" prior attempt): a **one-directional
adjacency list** (only +x/+y/+z neighbours, so Dijkstra explored 274 of 3,456
vertices), and a **non-minimal SPT** (every reachable vertex was kept, producing
a 1,652-vertex route for a 49-vertex net). Both are fixed; a legal net route is
a *tree*, so it must be pruned to the vertices lying on some tight src→sink path.

## Recommendation

Mark this seam **closed** and do not reallocate effort to it. It is not a
low-yield seam, it is a *wrong-direction* seam: the equal-cost choice
freedom is real (2,070 vertices) but lives in the slack layers, while the
contention that costs 145,807-119,000 lives in z=2,3 where the routing is
essentially forced. Closing the gap needs something that changes the *cost* of
a middle-layer vertex (a Lagrangian/negotiated-pressure reformulation, per the
one certified bound: hard case_01 7573 vs PR#3 8674), not a different
shortest path tree.

## Cost

~28 min wall-clock, ~4 CPU-min of actual search on top of measurements.
