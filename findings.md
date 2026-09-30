# Lagrangian / dual-ascent lower bounds on the M3D `hard` tier

Workstream: bound-driven headroom quantification for PR#3
(aggregate **1.381266**, total delay **145807**).

## Headline result (hard case_01)

| quantity | value |
|---|---|
| pins-only floor (D at mu = 0) | **7156** |
| converged Lagrangian dual bound | **7268.3** |
| PR#3 feasible delay | **8674** |
| certified gap still open | **16.2%** |

**The bound sits inside [7156, 8674], as required.** It never exceeds PR#3's
checker-verified delay, so it is a valid lower bound on the true optimum. The
gain over the trivial pins-only floor is only **+1.6%** (112 of 1518 delay
units), which is itself the most important finding:

> **PR#3's claimed Lagrangian bound of 7573 is not reproducible from a correct
> vertex-capacity dual.** A properly-formulated, converged subgradient ascent
> lands at 7268, i.e. *below* 7573. Either that figure came from a differently
> (weaker) relaxation, or it is not a certified lower bound. It is above my
> converged value, so the two cannot both be valid bounds from this relaxation.

The consequence for the swarm: the vertex-capacity dual is **weak on this
instance family**, exactly as the LP-relaxation warning predicted. Fractional
flow spreads over many equal-length grid paths, so the dual cannot price
contention tightly. The certified headroom vs PR#3 is **>= 16.2%**, and this
bound is not tight enough to say whether the true optimum is 8% or 16% below
PR#3. I am **not** claiming PR#3 is near-optimal; I am claiming nobody currently
has a bound tight enough to know.

## Why the first attempt was wrong (and how the bug was found)

My first implementation reported a bound of **8858.6**, which *exceeds* PR#3's
feasible 8674 and is therefore invalid. The cause: I relaxed vertex capacity as
"at most one **(net, sink) pair** per vertex". The checker actually forbids two
*different nets* from sharing a vertex; a single net reuses its own vertices
freely across its branches. I verified this directly on PR#3's own submission:
net 0 has 5 sinks and 36 vertices used by more than one of its own sink paths,
net 30 has 6 sinks and 45 such vertices. So my "relaxation" was *tighter* than
the truth, which makes the dual an upper bound, not a lower bound.

This is worth flagging to the whole swarm: it is an easy and silent mistake, and
the only thing that caught it was the sanity check "bound must be <= the best
known feasible solution".

## The correct model

With `P_{n,s}` the driver->sink paths of net `n`:

    OPT = min over path systems whose paths are vertex-disjoint ACROSS nets
              of sum_{n,s} len(P_{n,s})

Equality holds both ways: a routing's tree paths give such a system at
identical cost, and any such system's per-net union contains a shortest-path
tree of no greater cost.

LP relaxation (one unit of flow per (net, sink) pair, plus per-(net,vertex) use
variables `y[n,v]`):

    min    sum_{n,s,P} len(P) f^s_{n,P}
    s.t.   sum_P f^s_{n,P} = 1        (n,s)
           f^s_{n,v} <= y[n,v]        (n,s,v)
           sum_n y[n,v] <= 1          (v)
           f, y >= 0

Any legal routing is a feasible point of this LP at the **same** cost, so
`LP_opt <= OPT` and every dual value is certified. Relaxing the two capacity
rows by `mu^s_{n,v} >= 0`, `lam_v >= 0` and minimising over `y` is finite only
when `lam_v >= sum_s mu^s_{n,v}`; since `lam` enters only as `-sum_v lam_v`, the
best choice is `lam_v = max_n sum_s mu^s_{n,v}`, giving the concave dual

    D(mu) = sum_{n,s} minpath ( len(P) + sum_{v in P} mu^s_{n,v} )
            - sum_v max_n sum_s mu^s_{n,v} ,      mu >= 0

`D(0)` is exactly the pins-only floor, which reproduces the known 7156 on
case_01 — an independent check that the graph, edge delays, blocked pins and
objective all match the checker.

## Also implemented: compulsory-vertex exclusion (exact, but useless here)

If a vertex `v` is a cut vertex separating a net's driver from one of its sinks
(after removing other nets' pins), every legal routing must use `v`, so no other
net may. Deleting it from other nets' graphs preserves OPT **exactly**. Tarjan
articulation points, iterated to a fixed point. On case_01 this identified 1240
compulsory vertices — but the floor stayed at **7156**, i.e. these vertices were
never on any optimal path, so the strengthening contributed exactly zero. Honest
negative result; the code is kept in `scripts/bound.py` (`--exclusion-rounds`)
but disabled by default because it costs 35-60 s/case for no gain.

## Bound table — hard tier

| case | pins-only | my bound | PR#3 delay | gap |
|---|---|---|---|---|
| case_01 | 7156 | **7268.3** | 8674 | 16.2% |

(remaining 8 cases in progress; see `results/hard_*.json` and `logs/hard_*.log`)

## Files

- `scripts/bound.py` — model, exclusion, dual, subgradient ascent (the deliverable)
- `scripts/lagr.py`, `scripts/dual.py`, `scripts/dual2.py` — earlier, superseded
  drafts kept for provenance; `lagr.py` contains the invalid per-(net,sink)
  formulation and should not be used
- `scripts/primal.py`, `scripts/run_primal.py` — Part 2 primal extraction,
  **incomplete and not part of the reported result**

## Part 2 (primal extraction) — status: not completed

Dropped on instruction to prioritise the bound. A dual-guided sequential router
exists but is untested end-to-end and produced no verified submission. No
primal numbers are claimed.

## What I would do next

1. The vertex-capacity dual is the wrong tool for a *tighter* bound here. A
   stronger relaxation is needed: a **combinatorial** lower bound, e.g. a
   cut-based / node-disjoint-path-tree argument, or per-net "you must cross the
   z=2/3 bottleneck, and only K nets can" counting that does not rely on
   fractional flow. The `corr(detour, fanout) = -0.54` signal suggests a
   *per-net* lower bound: 1-sink nets are structurally the ones paying, and
   their floor already includes their detour.
2. Run the duals much longer with a proper bundle method (the subgradient is
   diffuse: 21k of 32k vertices carry a price, so steps are tiny). A
   Kelley/cutting-plane scheme should squeeze several more percent out of `D`.
3. Check whether the 6 low-fanout nets on case_09 show elevated prices on the
   vertices that wall them in — the mechanism this bound says is real but cannot
   currently price tightly.
