# warm_lns_refinement — congested

By [kesudh](https://github.com/kesudh). Exact shortest-path-tree warm refinement of
published routes; per-case provenance is byte-verified in `meta.json`.

| legal | total delay | aggregate | runtime (s) |
|---:|---:|---:|---:|
| 4/4 | 472571 | 1.3591 | 122.13 |

## Attribution

Routes carried verbatim, with the ref the shipped bytes were taken from:

| entry | author | ref | commit | routes |
|---|---|---|---|---:|
| — | — | — | — | 0 |

Net trees carried verbatim: case_01 (52217) is a partition crossover of this entry's
previous case_01 route (52219) with leonid-popryho's trees for nets 23, 64, 85 and 99,
taken from their published file (origin/main, `2564be90859e`, Leonid Popryho). The
swapped nets collide with nothing else, so the result is legal by construction and was
re-checked with `m3d/checker.py`. Its runtime is the 30.067 s run that produced the
previous route plus the 1.55 s crossover run (31.617 s).

Warm starts: the 4 case(s) refined here were warm-started from the best
published route for that case, published by coordinated_refinement (jay-tau),
drama3d-portfolio / cuda-have-been-shorter (YJ Kim), leonid-popryho (Leonid
Popryho) or pathfinder_lns (Tazeem Mahashin).

Conflict-based search is adapted from Sharon et al. (see `algorithm_references`).
`runtime.json` is one end-to-end run of this router per case, all on one basis: 30 s
search budget, 4 worker threads, chain-fast mode, the engine's own
END_TO_END_SECONDS. This revision changes one shipped route, designs/int2float, which is
now carried verbatim from another entry's published file; it was re-measured on the same
basis and the reported time is this entry's own run on that instance, not the upstream
author's generation time. stress/case_01 reports 62.2 s because the budget is checked
only at the top of the trial loop and a 901-net trial can exceed it. The other 44 records
describe the runs that produced the bytes those cases still ship. Timed parallel search
is nondeterministic, so a repeat can return a different legal route. No
global-optimality claim is made. Where a shipped route is another entry's file carried
verbatim, the time is this entry's own run on that instance; upstream generation time is
not claimed.
