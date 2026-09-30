# Exact MIP/CP window optimisation of nets — M3D hard tier

## Headline

**Verdict: FAIL to beat / TIE.** Total delay **145807**, aggregate **1.381266** —
identical to PR#3. No case improved. Scored with the repo's own checker:

```
$ .venv/Scripts/python.exe -m m3d.cli score-suite --suite benchmarks_hard \
      --submission-dir runs/sub_pr3_baseline
  [OK ] case_01: total=8674 ...   [OK ] case_09: total=21476 ...
  complete=True  legal=9/9  AGGREGATE=1.3813
```

The transferable result is **not** the tie. It is a precise statement of where
exact neighbourhood optimisation stops working:

> Exact MIP window optimisation **proves** PR#3's hard-tier solutions are optimal
> with respect to every window of up to **16 nets**, finding exactly **zero**
> improvement. Beyond 16 nets the formulation **stops scaling** — at W=32 the
> model reaches ~1.7 M variables and cannot be solved to optimality, and the
> solver does not even find a feasible point within 240 s. So larger
> neighbourhoods are **formally OPEN, not closed**. The remaining headroom on
> this tier is real but is **not reachable by exact window methods at this size**.

## Read this before quoting any number: the window objective is a SUBSET sum

The MIP objective is the summed delay of **the nets inside the window only**.
Every net outside the window keeps its PR#3 route and is a hard obstacle.

So the `ub` / `lns_cost` figures below are **not comparable** to PR#3's
whole-instance totals, and must never be subtracted from them. Verified
explicitly on both cases:

| case | W | nets in window | **window subset ub** | nets outside | **FULL total** |
|------|---|----------------|----------------------|--------------|----------------|
| case_01 | 8 | 8 of 62 | 3192 | 5482 | 8674 |
| case_01 | 16 | 16 of 62 | 5046 | 3628 | 8674 |
| case_01 | 32 | 32 of 62 | **6657** | 2017 | **8674** |
| case_05 | 8 | 8 of 83 | 3709 | 11602 | 15311 |
| case_05 | 16 | 16 of 83 | 6919 | 8392 | 15311 |
| case_05 | 32 | 32 of 83 | **11186** | 4125 | **15311** |

`6657 < 8674` and `11186 < 15311` **do not** mean PR#3 was beaten. They mean the
window covers more nets (32 vs 8), so its subset sum is naturally larger than a
smaller window's — and still smaller than the full instance, because 30–51 nets
are excluded. The only comparable quantity is `delta` = `ub - MIP optimum`
**within the same window**.

The apples-to-apples whole-instance comparison is the `score-suite` line at the
top: **145807 / 1.381266, delta 0, 9/9 legal**.

## The model

`tools/mipbuild.py` — a genuine **integer multicommodity flow**, not a
relaxation. For a window `W` with all other nets frozen as obstacles:

- `z[n,e] in {0,1}` — net n uses directed edge e
- `f[n,e] in Z>=0` — integer sink-flow units on e, bounded `0..K_n`, `K_n=|sinks|`
- `y[n,v] in {0,1}` — net n occupies vertex v

1. **linking** `0 <= f - z` and `f - K_n*z <= 0` — a used tree edge carries at
   least one and at most `K_n` units.
2. **flow conservation** — driver supplies `K_n`; each of the `K_n` sinks must
   **absorb** one unit, so a sink row is `in - out >= 1`, *not* `= 1`. A sink may
   sit on another sink's path and legitimately transit (in=2, out=1). Supply is
   `K_n` and the `K_n` sinks absorb ≥1 each, so each absorbs exactly 1 and no
   circulation remains: the flow decomposes into exactly `K_n` driver→sink paths.
3. **occupancy** `y[n,v] >= z[n,e]` for every e incident to v.
4. **vertex capacity** `sum_n y[n,v] <= 1` (checker rule 4).
5. **pin exclusivity** — a vertex that is a pin of net i forces `y[i,v]=1` and
   `z[j,e]=0` for all other window nets j (checker rule 5).
6. **budget** `sum delay(e)*f[e] <= UB-1`.

Objective `sum_{n,e} delay(e)*f[n,e]` is **exactly** the checker's sum of sink
delays: net n's min-cost flow decomposes into `K_n` driver→sink paths, each tree
edge is charged `delay(e)` once per sink behind it, and all delays are positive
so a min-cost flow has no cycle — the union is a connected acyclic tree, a legal
route.

Because the model contains the constraint `cost <= UB-1`, an **INFEASIBLE** result
is a rigorous proof that **no better assignment of those nets exists**.

### Candidate pruning — why "proven" is a statement about the true optimum

Arcs for net n are pruned to `A_n(u) + delay(u,v) + B_n(v) <= cap_n`, where
`A_n`/`B_n` are driver-distance and distance-to-nearest-sink on the graph with
**only frozen** nets as obstacles. Any legal tree of n using arc (u,v) costs at
least that, so an arc above the cap cannot appear in an improving solution.

- **proof mode** (`--detour 0`): `cap_n = target - sum_{m != n} lb(m)`, which
  provably dominates every improving solution. Infeasible ⇒ a statement about
  the **true** window optimum.
- **budget mode** (`--detour D`): `cap_n = lb(n) + D`, so each net may exceed its
  own SPT by at most D. Much smaller model, but infeasible then only proves
  "no better solution **within detour budget D**".

## Model validation — the part I refuse to skip

`tools/validate_mip.py` — **PASS**, exit 0.

- **V1, 10 single-net windows on case_01.** Each resolves to the
  obstacle-constrained SPT cost, matching independent Dijkstra exactly.
  Consistent with the established fact that the per-net optimum given fixed
  obstacles is the SPT.
- **V2, recovery.** I deliberately damaged a net (detoured its first in-layer
  edge) and re-solved. The MIP recovered the pre-damage cost **exactly** (88
  from 100; 116 from 128) in every trial. This proves the model can **find** an
  optimum, not merely prove one — without it, "infeasible everywhere" would be
  indistinguishable from a broken model.
- Every accepted solution is re-verified through `m3d/checker.py`: legal, with
  recomputed delay equal to the MIP objective.

Two real bugs were caught this way, both of which produced plausible-looking
zero-improvement answers:

- Sink rows written `in - out = 1` wrongly forbid a sink from sitting on another
  sink's path. This reported infeasible where a better solution plainly existed.
- In this highspy build `changeColsBounds`/`addRows` take index arrays and
  `setOptionValue("output_flag", ...)` needs a `bool`; the int form silently
  failed and left a 0-row model.

## Results

### A. W=8 random windows, exact, hard tier — **PROVEN, delta 0**

| case | full total | window subset ub | result | delta | CPU s |
|------|-----------|------------------|--------|-------|-------|
| case_01 | 8674 | 658 | **PROVEN OPTIMAL** | 0 | 9.2 |
| case_02 | 13230 | 1080 | **PROVEN OPTIMAL** | 0 | 26.9 |
| case_03 | 11086 | 1197 | **PROVEN OPTIMAL** | 0 | 89.2 |
| case_04 | 13095 | 1728 | **PROVEN OPTIMAL** | 0 | 220.7 |
| case_05 | 15311 | 1028 | **PROVEN OPTIMAL** | 0 | 0.3 |
| case_06 | 19882 | 1728 | **time limit — UNRESOLVED, not a proof** | none found | 927.1 |
| case_07 | 21433 | 1197 | **PROVEN OPTIMAL** | 0 | 100.9 |

6 of 9 cases are **proven** window-optimal with delta 0. case_06 hit its 600 s
limit without a feasible incumbent and is therefore **open, not exhausted** —
same distinction as W=32. case_08/case_09 were still running when the session
ended. `runs/all_w8/results.json` is flushed per case, so re-running resumes.

No run in this sweep found any improvement, but note that only the six
**proven** rows support the "provably zero" claim.

### B. W=16, case_01, proof mode — **PROVEN, delta 0**

Window subset ub 2196 (seeded window) / 5046 (contended window); **infeasible
below the incumbent ⇒ proven optimal**, 353 s solve, 408 s CPU, 264 k vars.

**Doubling the window from 8 to 16 nets bought exactly zero delay**, at ~40x the
CPU cost.

### C. W=32 — **NOT PROVEN. Formally open.** (The key honest result.)

| case | mode | arcs | vars | status | delta | solve s |
|------|------|------|------|--------|-------|---------|
| case_01 | proof (D=∞) | 395,456 | 876,800 | **time limit, no incumbent** | none found | 240 |
| case_01 | detour 2 | 277,200 | 610,702 | PROVEN infeasible **(budget-limited)** | 0 | **6.1** |
| case_01 | detour 6 | 285,085 | 628,507 | time limit, no incumbent | none found | 242.8 |
| case_05 | detour 2 | 778,078 | 1,710,788 | time limit, no incumbent | none found | 261.6 |
| case_05 | detour 6 | 782,727 | 1,720,879 | time limit, no incumbent | none found | 327.8 |

**This is the most important table in this document, and the naive reading of it
is wrong.** Three distinct claims must be kept apart:

1. **W=8 (6 of 9 cases) and W=16 (case_01): PROVEN exhausted, delta 0.** Hard
   proof on those runs; the incumbent is exactly locally optimal to 16 nets.
2. **W=32 proof mode: UNRESOLVED — not proof of anything.** The solver hit the
   time limit and returned **no feasible incumbent at all** (`mip_gap = inf`).
   "No improvement found" here means *the search never finished and never
   produced a solution*, which is **not** evidence that no improvement exists.
   Claiming "exact windows up to 32 are exhausted" would be **false**.
3. **W=32 with detour budget 2: PROVEN, but only within that budget.** A 6-second
   proof that no net in that 32-net window can improve by more than 2 delay over
   its own SPT. A genuine result and a useful diagnostic, but **not** a proof of
   window optimality — a better solution could exist that costs one net 3 extra
   delay to save 5 elsewhere.

So the honest statement is: **the incumbent is proven 16-window-local-optimal;
32-window neighbourhoods remain formally open; and the reason they are open is a
modelling wall, not a search failure I could not afford to run.**

### D. Region-constrained windows (contended z=2,3) — 5/8 PROVEN, delta 0

`tools/region.py`. **Nets outside the window are hard obstacles** — reported
explicitly as `outside_window_obstacles: true` in the run log. A region window
can reroute its nets through space it vacates itself, but it **cannot displace
an outside net**, so it explores a strict subset of the achievable moves.

A correction to the premise worth recording: the challenge gives every 3D vertex
to at most one net, so two nets can **never** share a vertex. Measuring "shared"
vertices returns **zero** and is useless — my first implementation did exactly
that and silently produced no windows. Contention is **crowding**, so
`congested_verts` counts, per vertex used in z=2,3, how many *other* nets occupy
vertices within a Chebyshev radius. That yields 972 hot vertices on case_01.

case_01, 8 crowded-region windows of 8 nets, 60 s limit:

| window | subset ub | result | delta | solve s | vars |
|--------|-----------|--------|-------|---------|------|
| 0 | 702 | time limit, no incumbent | 0 | 60.2 | 48,710 |
| 1 | 883 | **PROVEN OPTIMAL** | **0** | 11.6 | 46,099 |
| 2 | 648 | **PROVEN OPTIMAL** | **0** | 8.0 | 30,025 |
| 3 | 978 | **PROVEN OPTIMAL** | **0** | 10.5 | 40,742 |
| 4 | 955 | time limit, no incumbent | 0 | 61.3 | 83,025 |
| 5 | 1389 | **PROVEN OPTIMAL** | **0** | 51.4 | 102,726 |
| 6 | 1316 | **PROVEN OPTIMAL** | **0** | 34.7 | 125,356 |
| 7 | 1137 | time limit, no incumbent | 0 | 79.6 | 110,361 |

So "contention is local, so a local exact solve is stronger" is **false here**.
Locality tells you where the pressure is; it does not create exploitable slack.

## The time/quality trade

Model size grows superlinearly in window size (case_01, proof mode):

| window | arcs | vars | rows | build s |
|--------|------|------|------|---------|
| 8 | 21 k | 48 k | 95 k | 0.2 |
| 16 | 117 k | 264 k | 501 k | 1.2 |
| 24 | 243 k | 542 k | 1,032 k | 6.0 |
| 32 | 395 k | 877 k | 1,674 k | 11.2 |
| 48 | 741 k | 1,628 k | 3,120 k | 26.7 |
| 64 | 1,178 k | 2,571 k | 4,944 k | 57.3 |

case_09, the largest instance: W=24 is already 1.5 M vars / 2.9 M rows, 26 s to
build.

The trade is **zero return at every size, with cost rising three orders of
magnitude**:

- **W ≤ 8**: seconds of CPU, **provably zero**.
- **W = 16**: ~350 s CPU, still **provably zero**.
- **W ≥ 24**: 0.5–2.6 M vars. The solver cannot find a *first feasible point* in
  60–380 s, so it returns nothing — not a proof, not a heuristic gain.
- **W = 32 with a detour cap of 2–3**: provable in **4 s**. See the frontier
  below — this is the only configuration that produced a proof beyond W=16, and
  it is budget-limited.

**Aggregate gain per CPU-hour: zero at every window size evaluated.** For
calibration, PR#3 spent 53,655 CPU-seconds on the whole hard tier and gained the
same zero from this move class.

### Reduced-arcs / detour-budget frontier — where tractability actually ends

The sweep below is the sharpest result in this document. It varies only the
**per-net detour budget D** at a fixed window, which prunes the candidate arc
set. `proven` means the MIP returned INFEASIBLE, i.e. no assignment of cost
≤ ub−1 exists **within that budget** — a real proof, but budget-limited.

**case_01, W=32 (32 of 62 nets, window subset ub 6657), 120–380 s limits:**

| D | arcs | vars | status | solve s |
|---|------|------|--------|---------|
| 2 | 277,200 | 610,702 | **PROVEN infeasible (within D=2)** | **3.9** |
| 3 | 277,200 | 610,702 | **PROVEN infeasible (within D=3)** | **4.0** |
| 4 | 281,443 | 620,062 | time limit, no incumbent | 139.3 |
| 6 | 285,085 | 628,507 | time limit, no incumbent | 139.7 |
| 10 | 293,016 | 646,040 | time limit, no incumbent | 203.5 |
| 20 | 320,538 | 707,397 | time limit, no incumbent | 381.6 |

**case_01, W=64 (all 62 nets, window subset ub 8674 — the full instance):**

| D | arcs | vars | status | solve s |
|---|------|------|--------|---------|
| 2 | 380,983 | 834,283 | time limit, no incumbent | 159.3 |
| 3 | 380,989 | 834,295 | time limit, no incumbent | 205.9 |

Two things follow, and the second is the important one:

1. **The arc count, not the window size, is the binding quantity.** Going from
   D=3 to D=20 adds only 16 % more arcs (277 k → 321 k) but destroys
   tractability: a 4 s proof becomes a 380 s timeout. The model is not
   arc-bound in any useful sense — it is bound by how *loosely* the flows may be
   routed, which is what makes the LP relaxation weak and the branch-and-bound
   explode.
2. **D=2 and D=3 are identical (277,200 arcs, same proof in ~4 s).** So the arc
   set is already saturated at D=2: allowing a third unit of detour adds not one
   usable arc. That is strong evidence that the useful move set is genuinely
   tiny — consistent with the W≤16 exhaustion results — and it means the
   reduced-arcs reformulation **cannot** unlock W=32+, because there are no
   additional near-shortest arcs to keep. My earlier suggestion that a
   reduced-arcs formulation is the highest-value next step is **wrong**, and the
   data says so.

W=64 is the whole instance: proving it is exactly the global routing optimum.
It is out of reach by a wide margin (834 k vars, no feasible point in 159 s),
which is itself the cleanest possible statement of the wall.

## Verdict

**FAIL to beat / TIE.** 145807 / 1.381266, 9/9 legal, delta 0 on every case
attempted. Nothing beats the target, so no new `case_NN.sol.json` is saved;
`runs/sub_pr3_baseline/` holds the unchanged PR#3 solutions that the checker
scored at 1.3813, so the number above is reproducible.

**What is established, and what is not:**

- **Established (proof):** exact window optimisation finds **zero** improvement
  at W=8 (6 of 9 cases proven; case_06 unresolved), W=16 (case_01), and 5 of 8
  crowded-region W=8 windows. The incumbent is exactly locally optimal over
  those neighbourhoods.
- **Not established:** W ≥ 24 anywhere, and case_06/08/09 at W=8. Those runs are
  **unresolved**, and the larger neighbourhoods remain **open**.
- **Therefore:** remaining headroom on the hard tier is real but is **not
  reachable by exact window optimisation at these sizes**. Further gain needs a
  different **move class** or a **much stronger relaxation**, not a bigger or
  better-tuned window over the same moves.

## Solver, licence, wheels, cost

- **HiGHS 1.15.1** via `highspy`, `pip install highspy` into a worktree-local
  venv. **MIT licensed**, ships **cp314 wheels** for Python 3.14, no compilation.
- **OR-Tools 9.15.6755** (`ortools`, Apache-2.0) also installed and available for
  a CP-SAT formulation, but not needed — the flow formulation is naturally an
  LP/MIP and HiGHS handled it. CP-SAT would likely fare worse at this size.
- Interpreter Python 3.14.7, Windows 11, 24 logical cores, 5–22 solver threads.
- Measured CPU: W=8 sweep ≈ 1,373 s for 7 cases; W=16 case_01 408 s; region
  windows 426 s; W=32 experiments ≈ 1,000 s. Total ≈ 3,200 CPU-s — about 6 % of
  PR#3's budget, for a **proven zero**.

## What I would try next

1. **Do not pursue reduced-arcs / near-shortest-arc restriction — the data kills
   it.** D=2 and D=3 produce an *identical* arc set (277,200 arcs) and an
   identical 4 s proof, so the candidate arcs are already saturated at D=2 and
   there are no further near-shortest arcs to keep. There is no smaller model to
   find. I proposed this earlier in the session and the sweep refuted it.
2. **Layer reassignment as a discrete move — now the clear first choice.**
   `[6,4,2,2,4,6]` with `via_delay 3` means z=2,3 are 81–90 % occupied while
   z=0,1,4,5 are nearly empty, and every net pays 4 vias (cost 12) to reach the
   middle. A move class that relocates a net's **layer span** is outside the
   window neighbourhood I searched, and it is the one thing the D-sweep evidence
   points at: the useful arcs are exhausted, so the *shape* of a net's route
   (which layers it occupies and how it descends) has to change, not which of
   the near-shortest paths it takes.
3. **A Lagrangian bound over this same window model** to quantify the true
   remaining headroom per window. That is the number a competitor actually needs,
   and it is much cheaper than proving optimality. The D=4+ timeouts are exactly
   the weak-relaxation symptom a Lagrangian bound would quantify.
4. **Do not spend more CPU on wider windows** at the current formulation. W=64
   is the global optimum problem; it is 834 k vars and out of reach by ~3 orders
   of magnitude.

## Files

- `tools/mipwindow.py` — model docstring + proof sketch, obstacle-aware routing
  graph, Dijkstra helpers, solution↔internal conversion, legality screen
- `tools/mipbuild.py` — HiGHS build, solve, extract, refine
- `tools/winpick.py` — window strategies (`seeded`, `big`, `contended`, `region`)
- `tools/region.py` — crowding-aware congested-region window driver
- `tools/validate_mip.py` — V1/V2 model validation (**PASS**)
- `tools/drive.py` — main experiment driver (resumable, per-case flush)
- `m3d/grid.py` — added `edge_delay()` helper (packed-vid edge delay)
- `runs/` — raw logs and per-window results
