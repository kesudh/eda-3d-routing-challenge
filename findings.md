# Sequential repair on PR#5: nothing found below 145,305 — and the reason is quantitative

**Verdict: PR#5's solutions are not just a local optimum of the *random-restart*
move class. They are drained against the disciplined directed move class too —
1,354 directed transactions on case_01, ~180k across the hard tier, **0
improving**. And unlike the earlier negative results, this one comes with a
*mechanism*, not just a null count.**

Target: PR#5 `coordinated_refinement`, hard total **145,305** (9/9 legal under
`m3d/checker.py`). This work did **not** beat it and does not claim to.

## The correction that matters

Two engines disagreed with `m3d/checker.py` earlier in this project, and one
falsely claimed a 9.6% win. So before any negative result was accepted, the
move class was proved **non-vacuous**. It nearly wasn't: the first sweep
reported *"59 starved nets, 0 contested triples"* — a vacuous measurement, and
the reason it looked like a result at all.

The cause was not the layer filter. `Grid` here is my own class in
`seqrepair/engine.py`, not `m3d.grid.Grid`; its `WH` is `W*H` = 576 and it
reproduces the encoder test points exactly (`enc(3,4,2)=1251 //576 = 2`,
`enc(3,4,3)=1827 //576 = 3`). The layer filter passes **83%** of starved-net
cells (1801 of 2173), so it was never the problem.

The real bug was a Python default-argument trap in `search.py`:

```python
if self.st.pin_owner.get(c, A) == A:   # WRONG
```

`pin_owner` holds only the 196 pin vertices. For every **non-pin** cell `get(c, A)`
returned the default `A`, so *every* candidate looked like "the victim's own pin"
and was discarded — 1355 real candidates silently filtered to 0. Fixed to
`get(c)`. Same class of bug appeared twice more in the same file and was swept.

Post-fix proofs that the instrument is live:

| check | value |
|---|---|
| starved nets (above obstacle-free optimum) | 59 / 62 |
| total gap available on case_01 | 1,512 |
| contested (victim, starved net, cell) triples | 1,355 |
| starved nets with ≥1 contested cell | **59 / 59** |
| distinct cells covered | 650 |
| transactions actually **evaluated** | **9,525** on case_01 |
| strictly improving | **0** |

`instrument.py` now asserts `len(triples) > 0`, `covered > 0` and
`n1 + n2 > 0`, so a vacuous sweep fails loudly instead of printing a null.

## The move class

Given fixed obstacles a net's optimum **is** its shortest-path tree, so a
single-net reroute can never change the total — it is a no-op or strictly worse.
The only move that can is a **transaction**: net A vacates cells, net B picks
them up for more than A pays. Three variants, all evaluated:

1. **single-cell** — A must give up one cell B's ideal tree wants
2. **whole-cluster** — A vacates *every* cell one starved net wants from it
   (mean 2.3 cells/move, max 22); this is the natural "sequential repair" step
3. **zero-cost plateau** — A rerouted by randomised equal-delay tie-breaking;
   delay-invariant by construction, so any gain is free

Candidates are restricted to the cheap middle layers z=2,3 (83% of starved-net
ideal cells live there), which is where contention is. Commits are
**steepest descent** (single best improving transaction, not first-improvement),
and `evaluate()`/`plateau()` are **pure** — no state mutation, so no rollback
path exists that could corrupt the incumbent. Every commit is re-verified
through `m3d/checker.py`, per-net as well as in total.

## Result: 0 improving on all 9 cases

| case | PR#5 | after sequential repair | transactions |
|---|---|---|---|
| case_01 | 8,668 | 8,668 | 9,925 |
| case_02 | 13,158 | 13,158 | 15,312 |
| case_03 | 11,072 | 11,072 | 15,657 |
| case_04 | 13,075 | 13,075 | 17,566 |
| case_05 | 15,211 | 15,211 | 18,024 |
| case_06 | 19,810 | 19,810 | 24,918 |
| case_07 | 21,361 | 21,361 | 26,262 |
| case_08 | 21,508 | 21,508 | 29,052 |
| case_09 | 21,442 | 21,442 | 26,654 |
| **total** | **145,305** | **145,305** | **179,410** |

Global 1-opt after the descent moved **0 nets on every case** — as predicted,
PR#5's solutions are exact 1-opt fixed points.

## Why: the cost side is 2–50× the gain side

This is the part that generalises. The null is not bad luck.

**The gain side is real and large.** If a starved net's contested cells were
freed *for free*, it would improve steeply:

```
net 20: 130 -> 58   net 50: 506 -> 458   net 9: 96 -> 50   net 2: 216 -> 168
```

The whole 1,512 gap on case_01 is reachable *in principle*. The obstacle is
entirely on the giving side.

**557 of 1,352 applicable transactions produce a genuine gain.** So the search
finds the benefit — it just never covers the cost. Best observed trade on
case_01: `cost=4, gain=2` (A=31→B=38), then cost=4/gain=2, cost=6/gain=2. The
distribution is one-sided:

```
cost to vacate a contested cell (penalty=inf, cell MUST be released):
   min 0 | 25th pct 40 | median 102 | long tail to 446+
gain distribution: 2 (152x), 12 (76x), 4 (68x), 6 (53x), 42 (40x), 48 (39x)
```

Median cost-to-release is **102**; the largest gain any transaction could
produce is ~56. **The median transaction loses by roughly 2×.** No amount of
search over this move class fixes that, because the arithmetic is structural:
releasing a cell forces the victim's *whole* shortest-path tree to re-route
around it, and that cost is charged across all its sinks, while the gain is
only the starved net's single trunk.

Widening the cost cap from 12 to unbounded changes nothing but the number of
survivors — best stays `delta=0`:

```
cap=12   hist={skip 3138, worse 60, equal 7}   best delta=0
cap=30   hist={skip 2748, worse 125, equal 7}  best delta=0
cap=100  hist={skip 1872, worse 271, equal 7}  best delta=0
cap=inf  hist={worse 580, equal 7, skip 18}     best delta=0
```

(The +2 delay quantum is a *per-sink* quantum, so a fanout-6 victim pays up to
12 to release one cell — the default cap of 12 was already generous.)

## What this rules out, and what it does not

**Ruled out:** PR#5's "sequential repair / bounded conflict-based search"
cannot be re-derived as a *single-victim* transaction over middle-layer cells.
The mechanism is not a better tie-break or a smarter search order — the
cost/gain arithmetic forbids a win, so a random search failing here was
*expected*, not a weakness of the instrument.

**Not ruled out:** multi-victim transactions where several nets release
*simultaneously*, so a starved net's alternative route opens without any single
victim bearing the full detour cost. The structure is there and it is the one
remaining seam: the worst starved net (net 50) has contested cells spread over
**18 distinct victims**. That is a coordinated multi-net move, not a
single-victim one, and it needs a joint (not sequential) formulation — likely a
MIP or a flow formulation over the victim set. It is a different instrument
from the one PR#5 describes, and it is where I would look next.

## Bugs found and fixed in this work

All four were caught by the `verify_state()` gate or by explicit non-vacuity
assertions, never by a plausible-looking number:

1. **`_w` mis-classified y-steps as vias.** A y-step changes the flat index by
   `W`, not 1; my hand-rolled weight helper turned an in-layer step into a via
   and inflated every delay. Now delegates to `inst.edge_delay`.
2. **Forward-only adjacency.** Edges were emitted only for `+x,+y,+z`, making
   Dijkstra monotone — it could never travel down, left, or down a layer, so
   most nets appeared "unreachable". Now mirrored to undirected.
3. **`pin_owner.get(c, A)` default-argument trap** (above) — the one that made
   a live measurement vacuous.
4. **`extract_tree` raised on unreachable vertices** instead of returning
   `None`, and penalised cells that were the victim's own pins.

Also carried from prior work: only **parent** edges are emitted, deduplicated
(`|E| == |V|-1`); a 1-opt is **delay-descending**; capacity is per-net.

## Files

- `seqrepair/engine.py` — grid, Dijkstra, tree extraction, ownership, `verify_state()`
- `seqrepair/search.py` — starved/contested candidate generation, pure transactions, plateau
- `seqrepair/run.py` — steepest-descent driver over all 9 cases
- `seqrepair/instrument.py` — non-vacuity-asserting instrumentation
- `seqrepair/baseline.py` — PR#5 load + 1-opt fixpoint harness
- `work/run_all.log` — full run output

**CPU:** 1,164 s (~19.4 min) wall for the full 9-case descent — pure
single-threaded Python, no compiled extensions — plus ~10 min of
instrumentation and diagnostics, so **~30 min total**. Per-case descent time
ranged 18.5 s (case_01) to 317.8 s (case_09). No parallel workers were used.
