# SA / threshold accepting over joint moves — does it beat PR#3 on `hard`?

**Verdict: TIE.** No configuration tested improved any of the 9 hard cases by a
single unit of delay. The hypothesis is refuted for this move class, and the
reason is structural rather than a tuning failure.

| | total delay | aggregate |
|---|---|---|
| PR#3 (to beat) | 145807 | 1.381266 |
| SA over joint moves (this work) | **145807** | **1.381266** |
| delta | **0** | **+0.000000** |

Scored with the repo's own checker (ground truth), all 9 cases legal:

```
python -m m3d.cli score-suite --suite benchmarks_hard --submission-dir submissions/hard/sa_anneal
[OK] case_01: 8674    [OK] case_04: 13095   [OK] case_07: 21433
[OK] case_02: 13230   [OK] case_05: 15311   [OK] case_08: 21620
[OK] case_03: 11086   [OK] case_06: 19882   [OK] case_09: 21476
complete=True  legal=9/9  AGGREGATE=1.3813
```

Absolute paths: `F:/eda3d-wt/sa-accept/submissions/hard/sa_anneal/case_01.sol.json`
… `case_09.sol.json` (these are byte-equivalent in *score* to PR#3's; the router
re-derives them but never improves on them).

---

## What was built

`scripts/sa.cpp` — a standalone C++20 router (pure stdlib, no JSON parser;
`scripts/sa_prep.py` converts instance + PR#3 solution to a flat text format).

The move, in one line: **rip up a random set S of nets, re-insert them in a
random order, each taking its own optimal route (pruned SPT) in the occupancy
built so far.** Nets outside S are untouched, so the cost delta is exact and
local — no global recompute, which is what makes ~450k moves/case affordable.

Optional extensions, all measured:
- `--jitter J` — route with randomized edge weights `w·U(1−J, 1+J)` instead of
  the true SPT, so a net can voluntarily take a *different corridor*. This is
  the move class that pure order-based re-insertion cannot express.
- `--greedy 0` — keep the randomized route instead of immediately re-optimizing
  it back to the SPT (with greedy on, the re-optimization undoes the jitter).
- `--bestof N` — sample N candidate routings of S, propose the best.
- `--noanneal 1` — strict descent, the control experiment.

## Bugs found and fixed (all caught by the in-engine verifier, not by luck)

The engine carries a `verify_state()` that re-derives delay and legality from
the stored edge lists exactly as `m3d/checker.py` does, and **`exit(3)`s if it
disagrees with the incremental objective**. That gate is why these were caught
rather than reported as wins:

1. `pick_set` could draw the **same net twice**, double-counting its delay in
   the delta and double-claiming its vertices. This made the engine *claim*
   6280 on case_01 where the checker said 9238.
2. Dial's bucket ring dropped entries belonging to a future distance (circular
   buckets), silently losing vertices and making sinks spuriously unreachable.
3. `snapshot_best()` snapshotted on *any* change, not only improvement, so
   "best" was really "current".
4. `load_best()` restored routes without resetting `g_total`.
5. With randomized weights, the equal-cost tie-break could create a **parent
   cycle** in the SPT (dist[v] < dist[u] no longer holds), hanging the prune.
6. The ring-widening loop overshot (`7→14→28→56→112`) past `bucket[64]`.
7. The jitter delay BFS seeded at `verts[0]` (not the driver) and iterated in
   sorted rather than BFS order.

An early build also silently failed (a `| head` pipe swallowed the exit code).

## Temperature schedule, and why it was tuned that way

**Calibrated from the measured delta distribution, not guessed.** `--calib`
samples moves with acceptance disabled and reports the analytic acceptance rate
at a ladder of temperatures. case_01, k=4, jitter=0.5:

```
n=5896  npos(uphill)=5796  mean=114.4  p50=24  p75=128  p90=396  p99=796  max=1282
  T=  0.25  accept=0.017        T= 16.0  accept=0.309
  T=  0.50  accept=0.018        T= 32.0  accept=0.432
  T=  1.00  accept=0.024        T= 64.0  accept=0.549
  T=  2.00  accept=0.042        T=128.0  accept=0.661
  T=  4.00  accept=0.093        T=256.0  accept=0.753
  T=  8.00  accept=0.186        T=512.0  accept=0.842
```

A textbook annealing curve, monotone across four decades of T. Schedule:
**geometric, T_hi = 0.8·p50(uphill Δ) down to T_hi/32, three ILS cycles each
restarting from the incumbent best.** The whole ladder T_hi ∈ {16, 32, 64, 128,
256, 400} was swept; every one returns exactly 8674 on case_01.

### Measured acceptance rate vs temperature during the real run

case_01, 3 cycles × 150k moves (`work/logs_main/case_01.out`):

```
       T     tried   accepted
 76.197    30000    0.2713      <- start of anneal
 48.001    30000    0.2568
 30.239    30000    0.2353
 19.049    30000    0.2149
 12.000    30000    0.1890
  7.560    30000    0.1510
  4.762    30000    0.1113
  3.000    30000    0.0753      <- end of anneal
```

Monotone decreasing as T falls, on every case (case_09: 0.318 → 0.066). This
is the evidence that the SA **is genuinely annealing and not random walking** —
31k–38k uphill moves were accepted per case, i.e. it really does pay the
uphill toll. It simply never repays it.

## Why it fails — the structural reason

This is the substantive finding, and it extends the established fact that the
incumbent is a hard 1-opt local optimum.

**The move set is closed under re-optimization.** Every move ends by routing
each ripped net to its own optimum given the others' occupancy. Established
fact 2 says that per-net optimum given fixed obstacles *is* the SPT. So after
any move, every net in S is again 1-opt optimal, and nets outside S are
untouched — meaning **every point the search visits is itself a 1-opt local
optimum**. The search cannot descend, and there is no direction in which the
plateau slopes. Barrier crossing requires states that are *not* 1-opt optimal;
`--greedy 0 --jitter` was added specifically to try to reach them, and it does
(below), but returning from them does not pay.

Supporting measurements:
- **Strict descent (`--noanneal 1`), k=1 and k=4: 0 improvement in 200k
  moves.** Independently reproduces the established 1-opt exhaustion.
- **Route churn is enormous and free.** With `p_tie=0.5`, **57% of single-net
  reroutes change the vertex set at zero delay cost** (17219/30000). With
  jitter, 700–850% per move. The plateau is huge — but it is genuinely flat.
  Equal-cost SPT choice is a large, completely free, and completely useless
  search space here.
- **SA heats and never returns.** case_01, T=128→4: current cost climbs to
  13462 by iteration 5000 and decays only to ~10150 by 100k — always far above
  8674. The anneal is not failing to explore; it is failing to *return*.

## Cost / quality trade, honestly

| | CPU-seconds (hard tier) |
|---|---|
| PR#3 | 53655 |
| this work | **~15 700** |

~15.7k CPU-seconds: 13 275 for the final 9-case run (1475 s wall × 9 processes,
run in parallel on 24 cores) plus ~2 400 s of serial calibration and sweeps.
Roughly 3.4× cheaper than PR#3 — and worth exactly nothing. The cheapness is
real (incremental exact deltas, ~2 500 moves/second/case); it simply buys
nothing, because there is no improvement to buy.

## What I would try next

The evidence points away from the accept rule and toward the **neighbourhood**:

1. **Moves that leave a net deliberately non-optimal at the end.** Every
   candidate move here re-optimizes to the SPT, which is exactly why the search
   is trapped. A move class that ends with 2–3 nets in *known-suboptimal*
   states (e.g. force a net onto a specific reserved corridor, then let SA
   decide whether the pair is worth it) is the untested direction.
2. **Multi-net corridor trading as an explicit transaction.** Enumerate pairs
   (A,B) where A and B currently contend for the same middle-layer corridor
   (z=2,3 are 81–90% occupied on this tier), and evaluate the swap
   exhaustively. That is a 2-opt the current move set provably cannot express,
   because it requires *both* nets to end non-SPT.
3. **Per-net delay decomposition to target the search.** ~1/3 of total delay is
   in a handful of high-fanout nets (the established 12.7% certified headroom
   on case_01 came from a Lagrangian bound on exactly one case). An SA that
   allocates moves proportional to a per-net lower-bound gap, rather than
   uniformly at random, would spend its budget where slack actually exists.

The honest summary: the accept rule is not the bottleneck. PR#3's descent is
already sitting in a very good basin, and no reordering of *when to accept* gets
you out of it — you need moves that are allowed to end somewhere worse.
