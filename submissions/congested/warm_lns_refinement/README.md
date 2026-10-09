# warm_lns_refinement — congested

By [kesudh](https://github.com/kesudh). Exact shortest-path-tree warm refinement of
published routes. Per-case provenance is byte-verified in `meta.json`.

| legal | total delay | aggregate | runtime (s) |
|---:|---:|---:|---:|
| 4/4 | 472647 | 1.3589 | 120.56 |

Refined here: 1 of 4 cases. Carried verbatim from a credited
public entry: 3 (case_02, case_03, case_04).
`runtime.json` is one end-to-end run of this router per case at a uniform 30 s
budget; see `runtime_scope` in `meta.json`.

Timed parallel search is nondeterministic, so a repeat can return a different legal
route. No global-optimality claim is made.
