# warm_lns_refinement — congested

By [kesudh](https://github.com/kesudh). Exact shortest-path-tree warm refinement of
published routes; per-case provenance is byte-verified in `meta.json`.

| legal | total delay | aggregate | runtime (s) |
|---:|---:|---:|---:|
| 4/4 | 472599 | 1.3590 | 115.70 |

## Attribution

Routes carried verbatim, with the ref the shipped bytes were taken from:

| entry | author | ref | commit | routes |
|---|---|---|---|---:|
| coordinated_refinement | jay-tau | pull/47 head cb435d0a7559 | `cb435d0a7559` | 1 |

Warm starts: the 3 case(s) refined here were warm-started from the best
published route for that case, published by coordinated_refinement (jay-tau),
drama3d-portfolio / cuda-have-been-shorter (YJ Kim), leonid-popryho (Leonid
Popryho) or pathfinder_lns (Tazeem Mahashin).

Conflict-based search is adapted from Sharon et al. (see `algorithm_references`).
`runtime.json` is one end-to-end run of this router per case; 43 of 45 cases at a
uniform 30 s search budget on 4 threads, and the two most recent refinements at theengine-reported wall clock of the run whose output is shipped (25.15 s and 25.22 s, 2threads). Timed parallel search is nondeterministic, so a repeat can return adifferent legal route. No global-optimality claim is made.
