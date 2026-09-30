# MAIZEROUTER extreme edge shifting on M3D — CLOSED BY PROOF

**Verdict: FAIL (and provably so). PR#3's 8674 on case_01 is unchanged.**

Source of the move class: Moffitt et al., *MAIZEROUTER: Engineering an Effective
Global Router*, ASPDAC 2008 (<https://cecs.uci.edu/~papers/aspdac08/pdf/p226_3A-1.pdf>).
Reported there: full routability on all ten instances, 7.5x faster than BoxRouter,
2.02% shorter wirelength than BoxRouter and **2.92% shorter than FastRoute 2.0** —
the single documented case in the literature of a global router beating a
1-opt-exhausted incumbent, which is exactly our situation.

## Result

330 candidate edge relocations across all 41 fanout-1 nets of case_01.
**0 accepted.** Global total 8674 -> 8674.

## The move was NOT vacuous

A "0 improvements" result is worthless unless the move class was actually
exercised — two earlier results in this project were vacuous by construction.
Instrumenting the rejection pipeline showed all 330 candidates found a **legal
reconnection**, so the move class had purchase:

| outcome | count |
|---|---:|
| relocation achieved exactly A's current delay | 320 |
| disconnected a sink | 10 |
| **relocation made A strictly worse** | **0** |

## The fix that mattered

The first implementation guarded with `if ndelay >= d0: continue`, which
**rejected exactly the compound moves that escape the closed neighbourhood** —
MAIZEROUTER's whole point is to accept a locally-worse tree when the global
objective improves. That guard can never fire here.

Re-ran enumerating **every** free bridge (not just the cheapest) and applying the
compound step (relocate A, then 1-opt every other net to fixpoint, accept only on
strict global improvement). Still 0 compound candidates.

## Why: the reachable delay set for a fanout-1 net is a SINGLETON

This is the structural reason, not a failed attempt.

A fanout-1 net has a single sink, so its delay is `dist(driver, sink)`. Cutting
one tree edge splits the tree into two components; reconnecting through **any**
legal free bridge lands on the same shortest-path DAG. Measured over all bridges
of all edges:

```
net  1: current delay  84, achievable over bridges: [84]
net  3: current delay  88, achievable over bridges: [88]
net  9: current delay  96, achievable over bridges: [96]
...  12/12 nets tested: EVERY bridge gives exactly the current delay
distinct achievable-delay counts: {1: 12}
```

There is no "make A worse" state to compound with. The move class is empty for
the nets that matter.

This generalises the previously measured **+2 delay quantum** (only ~4.3 min-cost
paths per sink, zero sinks with a +1 alternative): the reachable delay set is
tiny, and for fanout-1 nets it is a singleton.

## Why the published 2.92% does not transfer

MAIZEROUTER repairs **overflow** in a soft-congestion global router, where
relocating an edge frees space a later net can use. M3D has **hard per-net
capacity** and PR#3's solution is already legal, so there is no overflow to
repair and nothing for a relocation to free. The move needs a second net to want
the vacated space, and after 1-opt every net already holds its exact optimum —
which is the idempotence of the evaluation operator `E` again, the same wall
every other router hit.

## Files

- `maizerouter.py` — the move, with the instrumented rejection pipeline
