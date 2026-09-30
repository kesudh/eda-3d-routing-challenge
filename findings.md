# Structure blueprint — what PR#3's near-optimal solutions actually look like

Measured with `blueprint.py` on `benchmarks_hard` cases 01/05/09, using the
repo's own committed PR#3 solutions. Reproduce:
`python blueprint.py <sol_dir> case_09`

## The headline finding (it contradicts my own prior, so it is worth stating plainly)

**High-fanout nets are NOT the ones paying congestion. Low-fanout nets are.**

`corr(detour_per_sink, fanout)` on PR#3's solutions:

| case | corr |
|---|---|
| case_01 | **−0.544** |
| case_05 | **−0.379** |
| case_09 | **−0.436** |

Consistently and strongly negative. Per-sink detour falls monotonically with
fanout: on case_09, 1-sink nets pay 35.1 detour/sink, 6-sink nets pay 6.2 — a
5.6× spread. Total detour is dominated by *many small nets each paying a lot*,
not by a few big trunks paying a little.

I had assumed the opposite (that high-fanout trunks hog the cheap middle
layers and are therefore the pain). The data says PR#3's router has already
solved that: big nets are routed cleanly through the middle, and the residual
cost is concentrated in low-fanout nets that get boxed in.

**Implication for the swarm:** any congestion-pricing scheme that scales price
*up* with fanout is pushing on the wrong axis. `fanout-price` should test the
inverse — see the recommendation below.

## The layer-bucket picture (case_09, 40×40×6)

| z | delay | occupied |
|---|---|---|
| 0 | 6 | 16.1% |
| 1 | 4 | 37.8% |
| 2 | 2 | **80.7%** |
| 3 | 2 | **81.5%** |
| 4 | 4 | 39.8% |
| 5 | 6 | 16.8% |

z=2,3 are ~81% full. z=0,5 sit at ~16% — nearly free. Same on case_01
(79.5/89.2 vs 29.7/21.0) and case_05 (84.8/82.6 vs 17.6/24.4). The cheap
middle is the contended resource and the dies' own layers are the slack.

## The dive rule is NOT the lever I expected

`corr(mean_z, fanout)` ≈ 0 (+0.011, +0.001, −0.072) and
`corr(mean_z, spanxy)` ≈ 0 (+0.188, +0.037, −0.086).

Nets are not systematically diving deeper when they are long or high-fanout.
Mean z hovers at 2.2–2.9 for every bucket. The analytic break-even argument
(dive above ~6 edges of travel) is *satisfied* but nets do not exploit it as a
clean rule — they sit near the middle almost regardless. This means
**layer-band pre-assignment (`layerband`) has less headroom than I predicted**:
there is no large systematic misallocation of depth to correct. The interesting
asymmetry is not z-depth, it is *which specific vertices* in z=2,3 each net
takes.

## Where the money actually is (case_09 worst nets)

| net | fanout | delay | floor | detour | maxdet | spanXY | mean z |
|---|---|---|---|---|---|---|---|
| 96 | 5 | 786 | 636 | 150 | 46 | 68 | 3.20 |
| 3 | 3 | 438 | 302 | 136 | 68 | 61 | 1.86 |
| 36 | 5 | 695 | 563 | 132 | 54 | 63 | 2.65 |
| 28 | 1 | 174 | 78 | 96 | 96 | 33 | 0.53 |
| 82 | 2 | 212 | 124 | 88 | 44 | 27 | 4.10 |
| 14 | 1 | 164 | 80 | 84 | 84 | 34 | 0.65 |
| 95 | 1 | 156 | 76 | 80 | 80 | 32 | 4.37 |

Note the single-sink nets with `maxdet == detour`: the *entire* penalty is one
sink. Nets 28/14/95/80/7/33 are 1-sink nets where one sink is 72–96 delay worse
than its free distance. These are pins that got walled in — almost certainly a
low-fanout net whose sink sits in a pocket of z=2,3 that higher-priority nets
consumed. They are individually cheap to fix (≈80 delay each, ~500 total
across those six) and they are the most *attackable* target in the instance:
a targeted repair that finds walled-in 1-sink sinks and re-homes just those
nets, paying for it by re-routing the nets that boxed them in.

## Construction rulebook (what to do)

1. Route high-fanout nets FIRST and give them clean shortest paths through
   z=2,3. They tolerate contention best and their trunks are amortised.
2. Route 1–2 sink nets LAST, and give them explicit priority to escape the
   middle layers — they pay the most per unit of contention (35 detour/sink
   vs 6). A late low-fanout net should be allowed a longer path on z=1,4,0,5
   (37% and 16% full) rather than a short path stuck in an 81%-full z=2,3.
3. Do not bother with a global depth-assignment pre-pass; measured z-usage is
   already near-flat across net types.
4. Target the walled-in 1-sink sinks by name. They are a small, enumerable,
   high-value set — the natural seed set for a region/blocker LNS move.

## What this implies for the other agents

- `fanout-price`: test the **inverse** of the usual scaling. Price congestion
  per *downstream sink* is right in principle, but the measurement says the
  binding constraint is low-fanout nets, so the useful policy is "give the
  cheap middle to big trunks, push little nets outward" — which is what
  PR#3 already does, so a plain fanout-scaled price may well reproduce their
  result rather than beat it.
- `layerband`: reduced priority. Depth is not the misallocated resource.
- `spt-reselect` and `sa-accept`: the most promising remaining targets, because
  the residual is a *specific set of blocked-in pins*, not a global imbalance.
  A repair move that specifically hunts walled-in sinks is worth trying.
- `lagrangian-primal`: the only way to know if 4072 of detour on case_09 is
  forced or recoverable.

## Caveats

- Measured on 3 of 9 hard cases. The fanout↔detour correlation replicates on
  all three with the same sign and similar magnitude, but it is 3 samples.
- `meanz` is an unweighted mean over a net's vertices, so it under-weights
  trunks (a vertex shared by 6 sinks counts once). It is a coarse z-usage
  proxy, not a trunk-depth measure.
- Detour is measured against the pins-only floor, which is a relaxation; some
  of the 17–21% detour is genuinely forced by capacity, not recoverable.
