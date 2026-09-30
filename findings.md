# Region windows vs random windows — and a vacuity correction to earlier W=8 proofs

## The finding

Like-for-like on `hard/case_01`, 8-net windows, same 240s limit, same HiGHS:

| | random W=8 (seeded) | **region W=8** |
|---|---:|---:|
| window `ub` | 1,442 | 702 |
| sum of per-net lower bounds | 1,438 | 638 |
| **slack (`ub − Σlb`)** | **3** | **63** |
| per-net headroom | 3,3,3,3,3,3,3,3 | 63,63,63,63,63,63,63,63 |
| nets pinned to their SPT | **8 / 8** | **0 / 8** |
| n_arcs | 27,316 | 21,507 |
| n_vars | 61,568 | 48,710 |
| **n_rows** | **118,178** | **92,606** |
| result | **infeasible, proven, 2.7s** | limit, no incumbent, 240.6s |

**A random window is easy to "prove" because it is nearly degenerate.** With
`ub − Σlb = 3`, the 3 units of delay headroom shared across 8 nets effectively
pin every net to its own shortest-path tree. The model has almost no freedom and
HiGHS proves infeasibility in 2.7 seconds.

A region window has 63 units of slack spread over all 8 nets, so **all eight are
simultaneously free** and the search tree is the product of eight nets' choices.
That is a combinatorial explosion — and it happens **despite the region model
being smaller** (92,606 rows vs 118,178).

## ⚠ Vacuity correction to earlier reported results

This materially revises the earlier claim that "W=8 exact windows prove delta 0
on 6 of 9 hard cases." Those proofs were largely **vacuous**: random windows
carry almost no slack, so the infeasibility proof is nearly trivial and says much
less than it appears to.

The region windows are the first ones where the MIP does **real work**, and they
do not close at 8 nets (48,710 vars, 240s, no incumbent) or at 13–14 nets
(172k–233k vars). Correct framing: **W≥8 region windows are formally OPEN**, not
proven optimal. The honest frontier is that exact joint re-optimisation does not
close in the region where contention is actually concentrated.

This also explains the arbiter's `ub=6657 vs full 8674` subset artifact: subset
objectives are small numbers, hence small slack, hence trivially-seeming proofs.

## Two hypotheses tested and REFUTED before finding the real cause

1. **Tightness** (fraction of residual arcs on a shortest path ⇒ tied
   alternatives ⇒ bigger tree): **32.9% region vs 30.5% random.** Far too close to
   explain a 90x time difference. Red herring.
2. **Model size / free vertices**: region has *fewer* free vertices (1,798 vs
   ~1,900) and *fewer* rows. Refuted by the table above.

## Scale boundary (and a methodology bug)

The first "size sweep" at `max_nets` 14/18/22/26 ran **four identical models**:
the hottest crowded region on case_01 contains exactly **14 nets**, so
`region_windows` returns windows of size ≤14 and `max_nets ≥ 18` returns `[]`
(the run then exits 0 silently). All four produced identical
`(14, 217631), (13, 172388), (14, 233324)`. That burned ~4,340 CPU-seconds
measuring the same three MIPs four times. A real sweep is 8/10/12/14:

| window | nets | n_vars | status | proven | solve |
|---|---:|---:|---|---|---:|
| region | 8 | 48,710 | limit | False | 260.8s |
| region | 10 | 71,211 | limit | False | 240.2s |
| region | 12 | 139,457 | limit | False | 240.6s |
| region | 13 | 172,388 | limit | False | 301.2s |
| region | 14 | 217,631 | limit | False | 300.3s |

Full-instance total unchanged at 8,674, legal, in every case.

## The tractable version (untried)

Use `--detour D` to cap per-net headroom, i.e. **search mode instead of proof
mode**. This restores a real but bounded neighbourhood: it can return
"no better solution within detour budget D," which is weaker than a proof of
optimality but is genuine evidence rather than a vacuous infeasibility. Worth
running if region windows are pursued at all.

## Files

- `whyregion2.py`, `whyregion.py` — tightness and candidate-arc probes
- `tools/region.py` — the region-window driver
- `tools/mipbuild.py:114-133` — the per-net `cap` that produces the slack
