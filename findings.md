# fanout-price — findings

**Verdict: FAIL.** Total delay **189283** vs PR#3's **145807** (+29.8%);
aggregate **1.0630** vs **1.381266**. All 9 hard cases legal, scored by the
repo checker (`python -m m3d.cli score-suite --suite benchmarks_hard`).

The assigned hypothesis is not merely unsuccessful, it is **structurally void**.
Below is the proof, then the measurements, then what the evidence says the real
lever would have to be.

---

## 1. The capacity model is per-(net, vertex), not per-downstream-sink

The brief's premise: *"the objective charges every shared trunk segment once per
downstream sink, so the true marginal cost of a net occupying a contended vertex
depends on how many sinks sit downstream of that vertex."*

That is true of the **delay** term and false of the **capacity** term, and the
two must not be conflated. `m3d/checker.py:205` stores `net_vertices[net.id] =
vertices`, a **set**, and rule 4 conflicts a vertex only across *distinct* nets:

```python
for v in net_vertices[nid]:
    if v in vertex_owner and vertex_owner[v] != nid:   # short
```

So the resource constraint is `#{nets n : v in T_n} <= 1`. A trunk vertex
occupied by a 6-sink net consumes exactly **one** unit of capacity — the same as
a 1-sink net touching it once.

Measured on PR#3's own solutions:

| case | max **distinct nets** per vertex | vertices shared by >1 path **of the same net** |
|---|---|---|
| case_01 | **1** | 551 |
| case_09 | **1** | 1651 |

Intra-net sharing is free because a tree already reuses its own edges. So a
fanout-weighted price charges for a constraint the problem does not have.

**Independent falsification.** A dual built on the brief's premise
(`fanout/dual.py`, charging `pi_v * cnt(v)`) converged on case_01 to
**Z = 8766.7** — *above* PR#3's actual feasible **8674**. A valid lower bound
cannot exceed a known feasible solution, so that model is provably wrong. It
optimises a strictly harder fiction in which a 6-sink trunk is 6x dearer than a
1-sink touch. This is the cleanest available disproof and it needs no argument
about router quality.

## 2. Corrected dual, and the certified floor

`fanout/certified.py` implements the *correct* node-capacity Lagrangian. Its
per-net subproblem is a node-weighted Steiner tree, so the certified bound uses
valid per-net lower bounds (max of the free-pins bound and the priced-shortest-
path-to-farthest-sink bound). Ascent does not improve on the pins bound
(best Z = 7156 on case_01, degrading from there) — the relaxation is genuinely
weak, not badly tuned.

**The pins-only lower bound, all 9 hard cases (exact, from the repo's own data):**

| case | pins-LB | PR#3 | PR#3/LB |
|---|---|---|---|
| case_01 | 7156 | 8674 | 1.2121 |
| case_02 | 9976 | 13230 | 1.3262 |
| case_03 | 8744 | 11086 | 1.2678 |
| case_04 | 10253 | 13095 | 1.2772 |
| case_05 | 12129 | 15311 | 1.2623 |
| case_06 | 15332 | 19882 | 1.2968 |
| case_07 | 16461 | 21433 | 1.3020 |
| case_08 | 16576 | 21620 | 1.3043 |
| case_09 | 17404 | 21476 | 1.2340 |
| **TOTAL** | **114031** | **145807** | **1.2787** |

So ~22% of PR#3's delay is certified headroom in aggregate, but the pins bound
also cannot see trunk sharing, which is a real source of gain. The brief's
"7573 vs 8674 on case_01" is **not reproduced** by a correct dual: 7156 is the
value I get, and I could not find a valid dual that exceeds it.

## 3. Head-to-head pricing policies (same routing kernel)

`fanout/ab.py` holds the routing kernel fixed and varies only the per-vertex
price. case_01, PR#3 = 8674:

| policy | case_01 delay |
|---|---|
| plain (history + presence) | 11532 |
| **fanout (exact linear marginal, k x price)** | **13362** |
| sinks^-0.5 (PR#3's surrogate) | **10750** |
| outer (push low-fanout nets off z=2,3), pen 0.5 / 2.0 / 4.0 | 11038 / 14940 / 17062 |

The exact linear downstream-sink marginal is the **worst** policy tested, 24%
worse than PR#3's decaying `sinks^-0.5` surrogate on the same kernel. Charging a
6-sink trunk 6x makes high-fanout nets thrash instead of settling; the decaying
surrogate is better calibrated precisely because it does *not* have the
"correct" linear marginal. **The brief's central hypothesis is refuted
empirically as well as structurally.**

## 4. The OOB steer (push low-fanout nets outward) also fails

Following the mid-task steer — make z=2,3 dear for 1-sink nets so they take a
longer route on the sparse outer layers (z=1,4 ~40% full, z=0,5 ~16%):

- penalty 0.5 -> 11038, 2.0 -> 14940, 4.0 -> 17062 (case_01). Monotonically
  worse. Layer delay differences dominate: a longer outer route always costs
  more than the congestion it avoids.
- Attacking the six named walled-in nets on case_09 (28, 14, 95, 80, 7, 33)
  directly: ripping them up and rerouting optimally costs **+2** total. They are
  not rescuable — the nets that boxed them in are paying for the same vertices.

## 5. No improving move exists from PR#3's solutions

Re-verified established fact #1 independently: exact per-net reroute to
fixpoint on PR#3's own case_01 and case_09 moves **0 nets**. They are exactly
1-optimal, so *no* per-net congestion price can ever improve them.

Extending to joint moves (`fanout/lns.py`, rip up a set, reroute the set jointly
in both fanout orders, then 1-opt fixpoint over the set):

| case | base | best after 300 joint LNS trials | improvements | infeasible | worse |
|---|---|---|---|---|---|
| case_01 | 8674 | **8674** | **0** | 76 | 165 |
| case_09 | 21476 | **21476** | **0** | 62 | 178 |

Zero improvements in 600 trials. PR#3's hard solutions are a strong local optimum
under both 1-opt and rip-up-reroute. Congestion **pricing is not the lever**,
in any form.

## 6. What I actually shipped

A complete, legal 9/9 submission (my router, `sinks^-0.5` policy):

`submissions/hard/fanout_price_lns/case_01..09.sol.json`

| case | mine | PR#3 |
|---|---|---|
| case_01 | 10750 | 8674 |
| case_02 | 18722 | 13230 |
| case_03 | 14634 | 11086 |
| case_04 | 17237 | 13095 |
| case_05 | 19485 | 15311 |
| case_06 | 26518 | 19882 |
| case_07 | 27927 | 21433 |
| case_08 | 28314 | 21620 |
| case_09 | 25696 | 21476 |
| **TOTAL** | **189283** | **145807** |
| **aggregate** | **1.0630** | **1.381266** |

This is a competent-but-weak router, not a competitive one. It is reported for
completeness and honesty, not as a claim.

## Files

- `fanout/dual.py` — grid, per-net blocked masks, exact priced-SPT, the
  (disproven) fanout dual.
- `fanout/certified.py` — correct node-capacity Lagrangian + certified LB, and
  the written disproof of the fanout model.
- `fanout/ab.py` — pricing-policy A/B on a fixed kernel (plain / fanout /
  sinks^-0.5 / outer).
- `fanout/reopt.py` — load PR#3 state, per-net exact reroute, tree/edge helpers.
- `fanout/lns.py` — joint rip-up-and-reroute.

### Bug worth recording for other agents

Emitting every adjacency edge inside a net's vertex **set** is wrong. An SPT
path to the next sink can run alongside a vertex an earlier branch already
claimed, which adds an extra edge and yields `V` edges over `V` vertices — the
checker rejects it as "not a tree". Only genuine **parent** edges may be
emitted. This cost real debugging time and is easy to hit in any hand-rolled
multi-source SPT grow.

## Next

1. The gap is **not** in congestion pricing. 600 joint LNS trials and exact
   1-opt fixpoint both find zero improvement, so a better price function cannot
   be the answer.
2. The remaining candidate is a move that is *not* a reroute: layer/z-assignment
   restructuring (which nets are allowed near z=2,3 at all), or a much larger
   destroy set (50+ nets) with a global re-solve. My random subsets topped out at
   25 nets and were mostly infeasible.
3. The certified floor is 114031 aggregate (PR#3 is 1.2787x it). I could not
   beat the pins bound with a valid dual; strengthening the per-net LB to
   account for trunk sharing is the only way to learn how much of that 22% is
   real.

CPU: ~180 s total for all experiments.
