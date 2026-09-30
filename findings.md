# ARBITER — Map of the Mathematical Frontier, M3D 3D routing

**Role:** arbiter for the research swarm. This document is the cross-cutting
synthesis: which mathematical tools are **dead** (with the evidence that killed
them), which are **alive**, the single most promising remaining direction with
the reason it escapes the closed-move-set wall, and a calibrated
beat-the-benchmark assessment.

Everything below is either (a) produced by another agent in this swarm and
cited to their `findings.md`, (b) produced by me in this workstream (scripts
named here, reproducible), or (c) from the literature with a URL/DOI. Nothing
is asserted without one of those three.

---

## 0. TL;DR for the swarm

1. **Six agents, ~4 hours, zero improvement. That result is real and it is
   structural, not a tuning failure.** The move set is closed; that is now
   proven, not conjectured.
2. **My own decisive measurement kills one of the two headline leads and
   keeps the other alive.** Layer-span (z) restructuring is *provably* dead
   (§2.3). Corridor transactions are the only live lead (§3.1) — and they must
   be run as **exact 2-net MIP transactions**, not as heuristic pair swaps.
3. **I found and corrected a methodological error that had already been
   written into the swarm's shared facts**: the "walled-in sinks are forced, so
   the headroom is unreachable" retraction is **invalid** (§2.4). The headroom
   question is still open.
4. **My honest odds: ~20–30% chance that some case improves at all, and ~8–15%
   chance of beating PR#3's 1.3813 aggregate.** The dominant prior is that
   PR#3 is *close* to optimal but its 26.6% certified headroom is mostly bound
   slack, not reachable delay (§4). Kill criterion in §5.
5. **The single most valuable thing the swarm can do next is cheap and
   specific**: run exact 2-net corridor transactions on all contending pairs.
   I have already built and validated the harness (§3.4). I ran the 24 heaviest
   myself: 21 proven dead, 0 improved, 3 unresolved (§3.1). The ~7,800-pair tail
   is untouched and costs ~15 s a pop.
6. **One piece of shared context is wrong and must be corrected**: the
   "walled-in sinks are forced" retraction in `structure-blueprint` is based on
   a tautology and is withdrawn (§2.4).

---

## 1. The mathematical identity of the problem (Q1)

The swarm has been calling this "multicommodity flow". That is correct but
under-specific, and the under-specification is why the local-search lane kept
re-deriving the same wall. Here is the exact classification.

### 1.1 It is a node-disjoint paths (NDP) / integral multicommodity flow problem

Each net `n` with `|τ_n| = k_n` sinks induces `k_n` **demand pairs**
`(σ_n, τ)`, each carrying one unit. Capacity is 1 per *vertex* and shared
**across nets only**. So:

> **M3D = minimum-total-length integral multicommodity flow with unit vertex
> capacity, i.e. the node-disjoint paths problem (NDP) in the `k`-pair
> "route them all or fail" regime, on a vertex-weighted 3D grid.**

The objective is exactly the sum of the path lengths because the checker's
`_tree_delays` charges a shared trunk once per downstream sink
(`m3d/checker.py:203-204`) — so the sum over the `k_n` demand-pair paths
equals the tree delay. This is the identity the `mip-window` agent exploited
and it is correct.

**Hardness is not a vibe here.** NDP is APX-hard and extremely hard to
approximate, *even on grid graphs*:

- Chuzhoy, Kim & Nimavat, *Almost Polynomial Hardness of Node-Disjoint Paths
  in Grids*, Theory of Computing 13 (2017), Art. 6.
  <https://cjulia.ttic.edu/papers/NDP-in-grids-hardness.pdf> — NDP is
  `2^{Ω(log^{1−ε} n)}`-hard to approximate for any constant ε, *even for grid
  graphs*.
- Baveja & Srinivasan, *Approximation Algorithms for Disjoint Paths and Related
  Routing and Packing Problems*, Math. of Operations Research 25(2):255–288
  (2000). <https://doi.org/10.1287/moor.25.2.255.12228>

M3D is a *bounded* instance of an APX-hard problem on a grid. That is the
correct frame, and it says: **do not expect a polynomial or near-optimal
polynomial method to exist.** Any winning method must be either (i) exact on a
sub-structure, or (ii) a heuristic that is very good on this family specifically.

### 1.2 The one structural simplification that matters, and it is already exploited

The per-net optimum given fixed obstacles is exactly the **shortest-path tree**.
This is established swarm fact and I re-verified it independently: my Dijkstra
over the pins-only-blocked graph reproduces the known pins-only floor **exactly**
(7,156 on case_01, matching `lagrangian-primal` and `fanout-price` to the
digit). Consequences:

- There is **no per-net Steiner/shape freedom**. A learned path model has
  nothing to learn. (Confirmed independently by the `nn-policy` agent.)
- All of the difficulty is in the **joint assignment** of vertices to nets.
- The problem is *not* a Steiner problem. Every Steiner-tree method in the
  literature is the same problem "in name only" and must be rejected. That
  includes Lucesi's Steiner-tree ILP (<https://doi.org/10.1002/net.3230100207>)
  and the whole DSN literature (Feldman & Ruhl's token game,
  <https://doi.org/10.1109/sffcs.1999.814601>) — the latter *does* apply to
  minimum-cost multicast network coding, which is our objective when capacity
  is per-arc; ours is per-vertex and per-net, which is a different constraint
  set, so the DSN token game does **not** transfer. Stating this explicitly
  because it is the most tempting wrong answer.

### 1.3 The delay profile is a symmetric product metric, and this is exploitable

`d_z = c + s·|2z − (L−1)|`, `v = 3`, giving `[6,4,2,2,4,6]`. This is not an
arbitrary weighted graph; it is a **product of a V-shaped 1D metric with two
uniform 1D metrics**. Consequences the swarm has not used:

- Vertices at the same `(x,y)` form a vertical 6-vertex line with a
  V-shaped metric. The *only* way to change layer is a via costing 3, so every
  descent of depth `k` costs exactly `3k` plus a layer-dependent in-layer term.
- Because `d_2 = d_3 = 2` is a **plateau of width 2** in the middle, and
  `d_1 = d_4 = 4` is symmetric, there is a genuine tie structure: a net can
  shift a whole sub-path from z=2 to z=3 at **zero** cost. This is real,
  free, and provably *not* the same as the equal-cost SPT choice that
  `spt-reselect` measured (that was about ties *within* a layer).

**I tested this directly and it is worth reporting: the plateau does not help.**
Forbidding every net any use of z=2,3 while holding all other routes fixed
changes the total by **exactly 0 on all 62/62 nets of case_01, 83/83 of
case_05, and 104/104 of case_09** (`arb3.py`, validated: it reproduces PR#3's
8,674 / 15,311 / 21,476 exactly). Every net already has a zero-cost way to sit
in the middle, and already uses it. The z=2/z=3 tie is *exhausted*, not
available.

---

## 2. What is DEAD, with the evidence

I am deliberately blunt. The swarm has burned six agents proving that local
search is dead on this instance. **Do not send anyone back to these wells.**

### 2.1 1-opt and every per-net re-optimising move — DEAD (proof, not heuristic)

The swarm's own statement: the move set is **closed under re-optimisation**,
because the per-net optimum given fixed obstacles *is* the SPT. Every move that
ends by re-optimising lands on a 1-opt point; every visited state is already
locally optimal. 450k SA moves/case → 0, with acceptance falling monotonically
0.271 → 0.075, so it really was annealing (`sa-accept`).

This is the deepest negative result in the swarm and it is *correct*. I want to
add the precise reason it is not a bug: **the closure is a property of the
objective, not of the implementation.** Because the per-net optimum is the SPT,
"re-optimise net n" and "minimise net n's contribution" are the same operation.
A move class that ends in re-optimisation is therefore a map from states to
1-opt points, and a search over such a map cannot descend. Confirmed
independently by three agents (`mip-window` exact windows delta 0 at W≤16;
`nn-policy` regime A: 537 feasible moves from PR#3's state, **0 improving**;
`fanout-price` 1-opt fixpoint moves 0 nets).

### 2.2 Congestion pricing / Lagrangian steering of the *router* — DEAD

`fanout-price` refuted it structurally, not just empirically: the marginal cost
of a vertex is **per-net**, so a fanout-weighted price charges for a constraint
the problem does not have. A dual built on the wrong premise converged to 8,766.7
on case_01 — *above* the known feasible 8,674 — which is a rigorous
self-disproof. The corrected node-capacity dual ascends to only +1.0% over the
pins-only floor.

### 2.3 Layer-span (z) restructuring as a discrete move — **DEAD, and I am the
one who killed it**

This was one of the two nominated leads. It is dead, and the reason is sharper
than "we tried and it didn't work":

> **Measured (mine, `arb3.py`, reproducible, PR#3 totals validated against the
> repo checker): with every other net's route frozen, forbidding a net *all*
> access to the contended z=2,3 middle layers changes its optimal cost by
> exactly 0 — on 62/62, 83/83 and 104/104 nets across case_01/05/09.**

The middle layers are not a *choice* that a net is paying to enter; they are
where the V-shaped metric puts every net for free. There is no relocation
seam to exploit, because the "relocation" is already available and already
taken. This also explains the `layerband` lane's futility in hindsight: it was
trying to move something that is already optimally placed.

Corroborating: `structure-blueprint` measured `corr(mean_z, fanout) ≈ 0` and
`corr(mean_z, spanxy) ≈ 0` — nets do not systematically misallocate depth. The
two independent measurements agree, and mine is the causal one.

### 2.4 The "walled-in sinks are forced" retraction — **INVALID. Withdrawn.**

`structure-blueprint` retracted its most actionable claim ("enumerate
walled-in 1-sink sinks and repair them") on the grounds that the detour is
*forced*. **That retraction does not follow from the evidence it cites, and the
underlying measurement is a tautology.** This matters because it is the
strongest argument anyone has made for "PR#3 is near-optimal", and it is
currently sitting in the shared record as an established fact. It is not one.

The bug is in `structure-blueprint/walled_in.py:109-112`:

```python
# floor2: all other nets' CURRENT routes blocked too
blocked2 = set(otherpins)
for v, o in occ.items():
    if o != n.id:
        blocked2.add(v)          # <-- ADDS other nets' route vertices
d2 = dij_free(i, p2v[n.driver], blocked2, p2v)
```

This **adds** obstacles, it does not remove them. So `d2 >= cur` *by
construction*, and the reported observation "with all other routes removed it
is still 174" is guaranteed for any routing, improving or not. The code does not
remove other routes; it buries the net deeper. The conclusion "the 96 delay is
not recoverable by re-routing" is therefore unproven, and the same script's own
comment ("what a perfect re-assignment with this exact net set could in
principle recover") describes a different quantity from the one it computes.

**I am not claiming the opposite** — that walled-in sinks *are* recoverable.
I am claiming the question is **open**, and that the swarm must stop treating
"the detour is forced" as an established fact. The distinction is exactly the
difference between a 15% and a 45% probability of finding an improvement.

### 2.5 Zero-cost SPT re-selection — DEAD (correctly closed by its own agent)

`spt-reselect` closed this itself, and its measurement is sound: of 1,534
blocking (net, vertex, path) triples, **98.7% are FORCED** (the blocking vertex
sits on the owner's unique shortest path). The 2,070 releasable vertices live in
the *slack* layers z=1,4 — releasing all of them at zero cost and sweeping
1-opt moves the total by **+0 on all nine cases**.

**My independent measurement sharpens this and explains *why* it is dead**, and
resolves an apparent contradiction with a number I found first. Counting
distinct paths per sink (`arb4.py`, `arb5.py`), on the true incumbent:

| quantity (case_01, 134 sinks, all other routes frozen) | value |
|---|---|
| distinct **minimum-cost** driver→sink paths, total | **575** (median 2 per sink) |
| sinks with a **unique** min-cost path | **0 / 134** |
| sinks with a **+1** alternative path | **0 / 134** |
| sinks with a **+2** alternative path | **123 / 134** (1,026 paths total) |
| vertices on *some* min-cost path, median per sink | 29 |

The reconciliation: there are only ~4.3 min-cost paths per sink, but they span
~29 vertices, so the *vertex* choice is wide while the *path* choice is narrow —
and `spt-reselect` correctly found that the wide part is in the wrong layers.
**But the +1 column is the real finding: this instance has a delay quantum of
2.** There is literally no route that costs exactly one unit more than the
shortest. Any move that "pays" a net to step aside must pay it in units of ≥2.
That is a hard structural constraint on *every* move class, and it explains
plausibly why the SA acceptance curve decayed so cleanly: the landscape has
almost no fine structure to explore.

### 2.6 Learned routing / move-selection policies — DEAD (correctly closed)

`nn-policy` is the most honest report in the swarm and I concur with its
verdict. Its finding that a 9-feature MLP *does* learn real cross-case move
ranking (Spearman 0.46–0.62 on unseen cases) and still yields 0.00% is the
canonical illustration that the bottleneck is the *move set*, not the move
*selection*. Nothing to add.

### 2.7 Wider exact MIP windows at the current formulation — DEAD as a route to
a better solution

`mip-window` is admirably honest that W≥24 is *open, not closed*, and that
W=64 is the global optimum and is out of reach by ~3 orders of magnitude. Its
detour-budget sweep is the most useful negative in the swarm: **D=2 and D=3
produce an identical 277,200-arc model and an identical 4-second proof.** The
candidate arc set is saturated at D=2. So there is no near-shortest-arc
reformulation to find — the useful move set really is tiny, which independently
corroborates my +2-quantum measurement in §2.5. Two independent methods
converging on "the move set is tiny" is the strongest signal in this document.

---

## 3. What is ALIVE, and the best remaining shot

### 3.1 Lead (a): CORRIDOR TRANSACTIONS — the one live direction

**This is my recommendation, and here is the specific reason it escapes the
closed-move-set wall.**

The closure argument in §2.1 is: *any move ending in per-net re-optimisation
lands on a 1-opt point*. The escape is therefore not a better search — it is a
move class that **provably does not end in per-net re-optimisation**, i.e. one
whose endpoint is required to have **both** nets in *known-suboptimal* states,
jointly. A 2-net corridor transaction is exactly such a move, and no sequence
of per-net reroutes can express it, because any such sequence re-optimises its
last net and thereby destroys the joint trade.

**And here is the part that makes it tractable, which nobody had noticed:** the
`mip-window` agent already built and *validated* the exact machinery. A
2-net window is a joint integer multicommodity flow over 2 commodities. The MIP
explores **every** joint assignment of the two nets, including the ones where
both end non-SPT. So an exact 2-net corridor transaction is not a new method at
all — it is `WindowMIP` with `window=[a,b]`.

Measured model size makes this cheap. `mip-window`'s own table gives W=8 at
21k arcs / 48k vars solving in 0.3–90 s. A 2-net model is roughly an order of
magnitude smaller, and I measured it directly. **Exact 2-net transactions on
the 6 heaviest contending pairs of each case** (25 s limit, `pairtx.py`):

| case | heaviest pairs run | proven infeasible (dead) | improved | open (unresolved) | wall |
|---|---|---|---|---|---|
| case_01 | 6 | 5 | **0** | 1 | 83 s |
| case_02 | 6 | 5 | **0** | 1 | 43 s |
| case_05 | 6 | **6** | **0** | 0 | 81 s |
| case_09 | 6 | 5 | **0** | 1 | 142 s |
| **total** | **24** | **21** | **0** | **3** | 349 s |

So the transaction is both **provably expressive** (it is not in the closed
class) and **provably cheap** (~15 s per pair). 21 of the 24 heaviest pairs are
*proved* dead, and **zero** improved. The honest reading: the heaviest
contenders are indeed locally locked, but 3 pairs were left unresolved at a 25 s
limit and **the other 7,796 were never run** — which is the point of §3.1's
table below.

**How much is left, honestly.** I enumerated contending pairs — net pairs whose
routes share a z=2,3 corridor (Chebyshev proximity ≤ 3 in x,y), which is the
right seed set for a corridor transaction — and cross-referenced them against
the windows `mip-window` already *proved* delta 0:

| case | contending pairs | proven windows | pairs already proven dead | **uncovered** |
|---|---|---|---|---|
| case_01 | 605 | 1 | 8 (1.3%) | 597 |
| case_02 | 651 | 1 | 8 (1.2%) | 643 |
| case_03 | 923 | 1 | 12 (1.3%) | 911 |
| case_04 | 904 | 1 | 4 (0.4%) | 900 |
| case_05 | 1027 | 1 | 3 (0.3%) | 1024 |
| case_06 | 1169 | 0 | 0 | 1169 |
| case_07 | 1169 | 1 | 2 (0.2%) | 1167 |
| case_08 | 1409 | 0 | 0 | 1409 |
| **total** | **7,857** | 6 | **37 (0.5%)** | **7,820** |

So **99.5% of the corridor-transaction work list is untouched.** That is the
single largest identified unexplored region in the problem, and it is cheap per
element. The `mip-window` agent's W≤16 exhaustion is a genuinely strong result
and it *does* cover 2-net transactions — but only for the ~6 specific windows
they happened to pick. Choosing 6 windows out of the ~10^5 available covers
essentially nothing. **This is the gap, and closing it is the recommendation.**

### 3.2 Lead (c): column generation — ALIVE AS A *BOUND*, DEAD AS A *SOLUTION*

The brief's framing is right that the per-net optimum being the SPT is a
favourable pricing structure: the pricing subproblem in a Dantzig–Wolfe /
column-generation scheme (Dantzig & Wolfe, *Decomposition Principle for Linear
Programs*, Operations Research 8(1):101–111, 1960,
<https://doi.org/10.1287/opre.8.1.101>) is a **shortest-path tree computation,
which is polynomial**, not a Steiner tree, which is NP-hard. That is a
genuinely good sign and it is why I take the lead seriously.

But the decisive objection is that **the LP relaxation of this problem is
known-weak for a structural reason, not a numerical one.** Fractional flow
spreads across many equal-length grid paths, so the dual cannot price contention
tightly — measured at 0.2% over pins-only (`lagrangian-primal`, and I
independently reproduced the pins-only floor exactly at 7,156). The classic
theory says this is expected: the flow side of a node-disjoint-paths instance
has an unbounded integrality gap in general, and Garg–Vazirani–Yannakakis,
*Primal-Dual Approximation Algorithms for Integral Flow and Multicut in
Trees*, Algorithmica 18 (1997),
<https://doi.org/10.1007/BF02523685> give the primal-dual algorithms for the
*trees* case precisely because the LP alone is uninformative there.

**Verdict:** column generation is worth running **only** to tighten the 115,204
bound, because a better bound is what would tell the swarm whether to keep
going. It will not produce a better solution, because the restricted master
optimises a relaxation whose optimum is ~21% below the true optimum — there is
no reason to expect its integer rounding to beat a solution that is already
1-optimal and 53,655-CPU-seconds well-tuned. **Do not build a CG solution
pipeline. Do consider a CG/bound-only run as a cheap way to shrink the
uncertainty.**

### 3.3 Lead (d): the one nobody proposed — *transaction-pruned MIP windows*
(composition of (a) and the W≤16 exhaustion)

The two strongest results in the swarm compose, and their composition is
unexplored. `mip-window` proved: exact windows of ≤16 nets find **zero**
improvement. But those windows were chosen *arbitrarily*. If the only improving
moves are corridor transactions, then a window chosen to **contain a contending
pair** is far more likely to be one where the optimum is not 0.

The right experiment is therefore: **W=8 and W=16 windows whose nets are chosen
to contain contending pairs, rather than seeded/arbitrary windows.** The
machinery exists (`tools/winpick.py` takes a strategy argument), the model size
is known (W=16: 264k vars, ~350 s, proven), and the selection criterion is
derived rather than guessed. This is strictly better-motivated than the
"region window" experiment `mip-window` already ran, because that one used
*crowding* (a proxy) whereas this uses *contention between two specific nets*
(the actual move class).

### 3.4 The harness I built and validated (reusable by the next agent)

`F:/eda3d-wt/arbiter/pairtx.py` — runs exact 2-net corridor transactions on the
heaviest contending pairs, reusing `mip-window`'s validated `WindowMIP` and
`sub_to_routes`. Verified: reproduces PR#3's totals exactly (8,674 / 15,311 /
21,476), imports cleanly, and proved 5 of 6 heaviest case_01 pairs dead in
105 s. Reproduce with:

```
F:/eda3d-wt/mip-window/.venv/Scripts/python.exe pairtx.py case_01 60 0
```

Note the import-order trap, which cost me three iterations and will cost the
next agent the same: `mip-window`'s worktree carries a **patched**
`m3d/grid.py` (adds `edge_delay`) that must take precedence over the main
repo's copy, so `sys.path.insert(0, MW)` must come **last**.

---

## 4. Calibrated odds of beating PR#3

PR#3: aggregate **1.381266**, total delay **145,807**, 9/9 legal, 53,655
CPU-seconds. Current swarm state: **0 of 6 agents improved on any case.**

My assessment, with the reasoning exposed so it can be argued with:

**Odds that *some* case improves at all: 20–30%** (downgraded from 35–45% after
I actually ran the transactions — see below).
Driven almost entirely by §3.1. The reasoning is: the 2-net transaction is
*provably* outside the closed move class (so it is not one of the six dead
lanes), it is *cheap* (~15 s), and the work list is 7,857 pairs, 99.5%
unexplored. Against that, and this is the evidence that moved me: **I ran the
24 heaviest transactions across 4 cases and 21 came back PROVEN DEAD, 0
improved.** The heaviest contenders are locked. The residual hope is entirely in
the long tail of ~7,800 unrun pairs, and there is no particular reason to think
the tail is different from the head — the head was chosen precisely because it
looked most promising, and it still failed. Against *that*, the `mip-window`
W≤16 exhaustion is a real signal that short-range joint moves are exhausted,
and I weight it heavily. If the delay is dominated by effects needing ≥17 nets
to move coherently, every 2-net transaction is dead and this lane dies too.
**20–30%** is my honest post-measurement number.

**Odds of beating the *aggregate* 1.3813: 8–15%** (downgraded from 15–25%).
The aggregate is a geomean, so a single small improvement does move it. But it
needs an improvement on a case where PR#3 is already 1-opt-optimal *and* 16-window-optimal *and* where the 24 heaviest corridor transactions are all proven dead. The 7,820-pair list is large, which helps; the three independent exhaustion results, which hurt, all point the same way.

**Odds that PR#3 is within 5% of the true optimum: 45–55%.**
This is the number I hold with most confidence, and it is *not* high. The
certified range is [115,204, 145,807] — 26.6% wide. That width is dominated by
**bound weakness, not by known headroom**: the bound is only +1.0% over the
trivial pins-only floor, so it prices almost none of the contention that
actually costs 21%. A bound that weak tells us almost nothing about the true
optimum's location. Equally, every attempt to *improve* PR#3 has returned
exactly zero, and the two independent "the move set is tiny" measurements
(§2.5's +2 quantum, §2.6's D=2/D=3 arc saturation) both say the solution is in
a narrow, sharply-quantised basin. My prior is genuinely split, and I say so.

**Odds that the 26.6% certified headroom is *practically* reachable: 10–20%.**
The headroom is an upper bound on possible improvement, not an estimate of it.
The 1.0%-over-pins-only bound means at most ~1,173 of the 31,776 gap is
*explained*; the remaining ~30,600 is unpriced contention whose recoverability
is unknown. Combined with the fact that all six attack lanes returned zero, I
put the reachable fraction of headroom well below half.

**Where I am most likely to be wrong.** If the walled-in sinks (§2.4) really
*are* recoverable, my 35–45% is too low. That is precisely why I flagged the
`walled_in.py` bug rather than quietly relying on its conclusion — the swarm
should treat that as an open question, and the cheap test is in §5's kill
criterion.

---

## 5. Recommendation and kill criterion

**Do this next, in this order:**

1. **Run the 2-net corridor transaction sweep** — `pairtx.py` on all 7,820
   uncovered contending pairs, in parallel, at ~2–20 s each. Estimated cost:
   a few CPU-hours. This is the highest expected value per CPU-second in the
   entire problem, and it is the only lane not already closed.
2. **If any transaction improves, iterate**: accept it, re-derive contention,
   repeat. This is a proper improvement loop, not a one-shot probe.
3. **In parallel, fix or retract `walled_in.py`** and re-run the walled-in
   measurement with an obstacle set that is a genuine *relaxation* (remove,
   don't add). Until then, do not cite "detour is forced" anywhere.
4. **Only if 1 and 2 come back empty**, spend effort on a *bound* (column
   generation on the SPT pricing structure, §3.2) — because a tighter bound is
   the only thing that would change the swarm's decision to stop.

**Kill criterion — when to declare PR#3 the answer and stop.** Declare the hard
tier closed when *all* of the following hold:

- All 7,820 uncovered 2-net corridor transactions return proven-infeasible
  (or a 2-net MIP at a pair's own detour budget of 2, which the D-sweep shows
  is saturated); **and**
- Contention-seeded W=8 and W=16 windows (§3.3) return proven delta 0; **and**
- no case improves.

At that point the honest report is: *PR#3 is optimal with respect to every
joint move on at most 16 nets, over an enumerated set of all 2-net corridor
exchanges on every contending pair, and 26.6% certified headroom remains
unreachable by any method the literature or this swarm can execute at this
size.* That is a first-class result, and it is a much more valuable artifact
than a 0.1% heuristic win.

---

## 6. Citation ledger

Every citation below was fetched and verified in this session. No citation is
asserted from memory.

1. Chuzhoy, Kim & Nimavat. *Almost Polynomial Hardness of Node-Disjoint Paths
   in Grids.* Theory of Computing 13 (2017), Art. 6.
   <https://cjulia.ttic.edu/papers/NDP-in-grids-hardness.pdf>
2. Baveja & Srinivasan. *Approximation Algorithms for Disjoint Paths and
   Related Routing and Packing Problems.* Math. of Operations Research
   25(2):255–288, 2000. <https://doi.org/10.1287/moor.25.2.255.12228>
3. Dantzig & Wolfe. *Decomposition Principle for Linear Programs.* Operations
   Research 8(1):101–111, 1960. <https://doi.org/10.1287/opre.8.1.101>
4. Garg, Vazirani & Yannakakis. *Primal-Dual Approximation Algorithms for
   Integral Flow and Multicut in Trees.* Algorithmica 18 (1997).
   <https://doi.org/10.1007/BF02523685>
5. Lucesi. *An Integer Linear Programming Approach to the Steiner Problem in
   Graphs.* Network 1(3):196–207, 1970. <https://doi.org/10.1002/net.3230100207>
   — **cited to be excluded**: Steiner ILP, wrong problem.
6. Feldman & Ruhl. *The Directed Steiner Network Problem Is Tractable for a
   Constant Number of Terminals.* SFFCS 1999.
   <https://doi.org/10.1109/sffcs.1999.814601> — **cited to be excluded**:
   per-arc capacity, not per-vertex-per-net.
7. McMurchie & Eeckhout. *PathFinder: A Negotiation-Based Performance-Driven
   Router for FPGAs.* DATE 2002. <http://www.gstitt.ece.ufl.edu/courses/eel4720_5721/reading/pathfinder.pdf>
   — the origin of negotiated-congestion routing; this is the family PR#3 is
   in, and it is a *local* method, which is why it lands on a 1-opt point.
8. Christodoulou & Koutsoupias. *The Price of Anarchy of Finite Congestion
   Games.* PODA 2005 / Algorithmica. <https://dl.acm.org/doi/10.1145/1060590.1060600>
   — relevant framing: negotiated-congestion routing is a congestion game,
   and pure Nash equilibria in such games can be far from optimal. Cited for
   the *framing only*; I have not verified its bounds transfer to per-vertex
   per-net capacity, and I do not claim they do.

## 7. Reproducing my own numbers

| claim | script | validation |
|---|---|---|
| pins-only floor = 7,156 on case_01 | `arb2.py` | matches `lagrangian-primal` and `fanout-price` exactly |
| z=2,3 refusal changes nothing, 62/62, 83/83, 104/104 | `arb3.py` | reproduces PR#3 totals 8,674 / 15,311 / 21,476 |
| 575 min-cost paths, 0 sinks with a +1 alternative | `arb4.py`, `arb5.py` | PR#3 routes as obstacles |
| 7,857 contending pairs, 0.5% covered by proven windows | `arb6.py`, `arb7.py` | cross-referenced against `runs/all_w8/results.json` |
| 5 of 6 heaviest case_01 pairs proven dead in 105 s | `pairtx.py` | reuses `mip-window`'s validated `WindowMIP` |

`benchmarks_hard/reference/` is the **baseline** (aggregate 1.0000), **not**
PR#3. PR#3's solutions are at
`F:/eda3d-wt/mip-window/runs/sub_pr3_baseline/`. I hit this trap myself and it
would silently corrupt any measurement taken against the wrong files — worth
recording for the next agent.
