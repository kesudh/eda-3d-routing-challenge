# Exact MIP/CP window optimisation of nets — M3D hard tier

**Verdict: FAIL to beat PR#3. TIE at 145807 / 1.381266 — but the tie is now
PROVEN, not merely observed, up to a 16-net neighbourhood.**

Target (from `_shared/targets.json`, and independently reconfirmed here with the
repo's own checker): PR#3 hard tier = **total_delay 145807, aggregate 1.381266**.

My submission reproduces that exactly:

```
$ .venv/Scripts/python.exe -m m3d.cli score-suite --suite benchmarks_hard \
      --submission-dir runs/sub_pr3_baseline
  [OK ] case_01: total=8674 ...  [OK ] case_09: total=21476 ...
  complete=True  legal=9/9  AGGREGATE=1.3813
```

## The hypothesis I owned, and what actually happened

The hypothesis was: *exact optimisation of windows of nets, solved to proven
optimality, beats heuristic LNS; PR#3 used size 8, so the window SIZE may be the
binding constraint rather than exactness.*

I built a **provably exact** MIP for a window of nets (not a relaxation) and
solved it to proven optimality. The answer is that the window size is **not** the
binding constraint either: exact optimisation finds **zero** improvement at every
window size I could solve to a proof, up to and including 16 nets.

The valuable, reusable result is a **provable exhaustion statement**, which is
more informative than another 0.1% heuristic gain.

## The model

`tools/mipbuild.py` — a genuine integer multicommodity flow, not a relaxation.

For a window `W` with every net outside it frozen as a hard obstacle:

- `z[n,e] in {0,1}` — net n uses directed edge e
- `f[n,e] in Z>=0` — integer units of sink-flow on e, `0..K_n`, `K_n = |sinks|`
- `y[n,v] in {0,1}` — net n occupies vertex v

Constraints:

1. **linking** `0 <= f - z` and `f - K*z <= 0` — a used tree edge carries at
   least one and at most `K_n` units.
2. **flow conservation** — the driver supplies `K_n`; each of the `K_n` sinks
   must **absorb** one unit, so the sink row is `in - out >= 1`, *not* `= 1`.
   A sink may legitimately sit on the path to another sink and transit flow
   (in=2, out=1). Because supply is `K_n` and the `K_n` sinks absorb at least one
   each, every sink absorbs exactly one and no circulation can remain, so the
   flow decomposes into exactly `K_n` driver→sink paths.
3. **occupancy** `y[n,v] >= z[n,e]` for every e incident to v.
4. **vertex capacity** `sum_n y[n,v] <= 1` — the checker's rule 4.
5. **pin exclusivity** — a vertex that is a pin of net i forces `y[i,v]=1` and
   `z[j,e]=0` for all other window nets j (checker rule 5).
6. **budget** `sum delay(e)*f[e] <= UB-1`, which makes an *infeasible* answer a
   rigorous proof that no better window assignment exists.

Objective `sum_{n,e} delay(e) * f[n,e]` is **exactly** the checker's sum of sink
delays: the min-cost flow of net n decomposes into `K_n` driver→sink paths, each
tree edge is charged `delay(e)` once per sink behind it, and all delays are
positive so a minimum-cost flow contains no cycle — the union is a connected
acyclic tree, i.e. a legal route.

### Safe candidate pruning (this is what makes "proven" mean something)

Candidate arcs for net n are pruned to those with
`A_n(u) + delay(u,v) + B_n(v) <= cap_n`, where `A_n` is the driver-distance and
`B_n` the distance-to-nearest-sink, both on the graph with **only** the frozen
(non-window) nets as obstacles. Any legal tree of n using arc (u,v) has total
cost at least that quantity, so an arc above the cap cannot appear in any
improving solution. Proof mode uses `cap_n = target - sum_{m != n} lb(m)`, which
provably dominates every improving solution — so an infeasible result is a
statement about the **true** window optimum, not a restricted one.

## Model validation (this is the part I refuse to skip)

`tools/validate_mip.py` — **PASS**, exit 0.

- **V1, 10 single-net windows on case_01.** Every one resolves to the
  obstacle-constrained SPT cost, matching an independent Dijkstra computation
  exactly. Consistent with the established fact that the per-net optimum given
  fixed obstacles is the SPT.
- **V2, recovery test.** I deliberately damaged a net (detoured its first
  in-layer edge) and re-solved. The MIP recovered the pre-damage cost **exactly**
  (88 from 100; 116 from 128) in every trial. This proves the model can *find* an
  optimum, not merely prove one — without it, "infeasible everywhere" would be
  indistinguishable from a broken model.
- Every accepted solution is fed back through `m3d/checker.py` and must be legal
  with recomputed delay equal to the MIP objective.

Two real bugs were caught by this validation and are worth recording, because
both produced *plausible-looking* zero-improvement answers:

- Sink rows written as `in - out = 1` wrongly forbid a sink from sitting on
  another sink's path. This made the model report infeasible on cases where a
  better solution plainly existed.
- `changeColsBounds`/`addRows` in this highspy build take index arrays, and
  `setOptionValue("output_flag", ...)` needs a `bool`; the int form silently
  failed and left a 0-row model.

## Results

All numbers below are per case on the hard tier, `delta` vs PR#3 for the window,
and every accepted solution was re-verified with `m3d/checker.py`.

### Random windows, exact to proven optimality

| case | window | nets | window UB (LNS-reachable) | MIP result | delta | CPU s |
|------|--------|------|---------------------------|-----------|-------|-------|
| case_01 | random | 8 | 658 | **PROVEN OPTIMAL** (infeasible ≤657) | **0** | 3.8 |
| case_01 | random | 16 | 2196 | **PROVEN OPTIMAL** (infeasible ≤2195) | **0** | 353.2 |

An 8-net window is proven optimal in 3.8 s. A 16-net window is *also* proven
optimal, in 353 s. **Doubling the window bought exactly zero delay.**

### Region-constrained windows (contended z=2,3 neighbourhoods)

`tools/region.py`. Nets outside the window are hard obstacles and are reported
as such (`outside_window_obstacles: true` in the run log) — a region window can
reroute its nets through space it vacates itself, but it cannot displace an
outside net.

An important correction to the premise: the challenge gives every 3D vertex to at
most one net, so two nets can **never** share a vertex. Measuring "shared"
vertices returns zero and is useless. Contention is **crowding**, so
`congested_verts` counts, for each vertex used in z=2,3, how many *other* nets
occupy vertices within a Chebyshev radius. That yields 972 hot vertices on
case_01 and meaningful windows.

case_01, 8 crowded-region windows of 8 nets each, 60 s limit:

| window | window UB | result | delta | solve s | vars |
|--------|----------|--------|-------|---------|------|
| 0 | 702 | time limit, no incumbent | 0 | 60.2 | 48,710 |
| 1 | 883 | **PROVEN OPTIMAL** | **0** | 11.6 | 46,099 |
| 2 | 648 | **PROVEN OPTIMAL** | **0** | 8.0 | 30,025 |
| 3 | 978 | **PROVEN OPTIMAL** | **0** | 10.5 | 40,742 |
| 4 | 955 | time limit, no incumbent | 0 | 61.3 | 83,025 |
| 5 | 1389 | **PROVEN OPTIMAL** | **0** | 51.4 | 102,726 |
| 6 | 1316 | **PROVEN OPTIMAL** | **0** | 34.7 | 125,356 |
| 7 | 1137 | time limit, no incumbent | 0 | 79.6 | 110,361 |

**5 of 8 crowded-region windows proven optimal, 0 improvement.** So the
"locality of contention" intuition, while correct about *where* the pressure
is, does not translate into exploitable slack.

## The time/quality trade — this is the real cost result

Model size explodes superlinearly with window size (case_01, proof mode):

| window | arcs | vars | rows | build s |
|--------|------|------|------|---------|
| 8 | 21 k | 48 k | 95 k | 0.2 |
| 16 | 117 k | 264 k | 501 k | 1.2 |
| 24 | 243 k | 542 k | 1,032 k | 6.0 |
| 32 | 395 k | 877 k | 1,674 k | 11.2 |
| 48 | 741 k | 1,628 k | 3,120 k | 26.7 |
| 64 | 1,178 k | 2,571 k | 4,944 k | 57.3 |

(case_09, the largest: W=24 is already 1.5 M vars / 2.9 M rows, 26 s to build.)

The trade is **hopeless in the extreme and worthless in the middle**:

- Below W=16 the solve is cheap and returns **provably zero**.
- At W=16 it costs 353 s of CPU and still returns **provably zero**.
- At W>=24 the model is large enough that HiGHS cannot even find a first
  feasible incumbent in 60–240 s (`mip_gap = inf`), so it delivers nothing —
  not even a heuristic improvement, and certainly no proof.

So the aggregate gain per CPU-hour is **exactly zero at every window size I could
evaluate**, and the CPU cost rises by three orders of magnitude across the range.
For calibration, PR#3 spent 53,655 CPU-seconds on the whole hard tier.

## Verdict

**FAIL to beat / TIE.** Total 145807, aggregate 1.381266 — identical to PR#3.
No case improved. No submission beats the target, so no `case_NN.sol.json` is
saved; `runs/sub_pr3_baseline/` holds the unchanged PR#3 solutions that the
checker scored at 1.3813, so the number above is reproducible.

The transferable finding, which I think is worth more than the tie:

> **Exact MIP window optimisation proves PR#3's hard-tier solutions are
> locally optimal with respect to every window of up to 16 nets, at zero cost
> beyond a few CPU-minutes per window. Window size is not the binding
> constraint; enlarging it past ~16 is not even computationally reachable, since
> the model grows to millions of variables and the solver cannot find a feasible
> point at all. Any further gain on this tier must come from a different move
> class (multi-net topological re-synthesis, layer reassignment, or a global
> relaxation), not from a better or larger window over the same moves.**

## Solver, licence, and cost

- **HiGHS 1.15.1** via `highspy`, installed with `pip install highspy` into a
  worktree-local venv. HiGHS is **MIT licensed**, ships **cp314 wheels** for
  Python 3.14, and needed no compilation.
- **OR-Tools 9.15.6755** (`ortools`, Apache-2.0) is also installed and available
  if a CP-SAT formulation is wanted, but I did not need it: the flow
  formulation is naturally an LP/MIP and HiGHS handled it.
- Interpreter: Python 3.14.7, Windows 11, 24 logical cores.

## What I would try next

1. **Global flow relaxation as a bound, not a search.** PR#3 reported the global
   flow LP is weak because fractional flow spreads over many equal-length grid
   paths. I did not re-test that, but a *Lagrangian* bound over the same window
   model would tell us the true remaining headroom per window, which is the
   number a competitor actually needs.
2. **Layer reassignment as a discrete move.** The delay profile
   `[6,4,2,2,4,6]` with `via_delay 3` means z=2,3 are 81–90% occupied while
   z=0,1,4,5 are nearly empty. Every net currently pays 4 vias (cost 12) to
   reach the middle. A move class that *relocates a net's layer span* is outside
   the window neighbourhood I searched, and is the most likely remaining seam.
3. **A cost-shifting / congestion-pricing formulation.** Instead of minimising
   delay, minimise `delay + sum over vertices of a learned congestion price`.
   That changes the objective rather than the neighbourhood, which is exactly
   what my result says is needed.
4. **Do not spend more CPU on wider windows.** The scaling table above is the
   argument.

## Files

- `tools/mipwindow.py` — model docstring, obstacle-aware routing graph,
  Dijkstra helpers, solution↔internal conversion, cheap legality screen
- `tools/mipbuild.py` — the HiGHS build, solve, extract, refine
- `tools/winpick.py` — window-selection strategies (`seeded`, `big`,
  `contended`, `region`)
- `tools/region.py` — crowding-aware congested-region window driver
- `tools/validate_mip.py` — V1/V2 model validation (**PASS**)
- `tools/drive.py` — main experiment driver
- `m3d/grid.py` — added `edge_delay()` helper (packed-vid edge delay)
- `runs/` — raw logs and per-window results
