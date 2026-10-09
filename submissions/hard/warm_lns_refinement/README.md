# warm_lns_refinement — hard

By [kesudh](https://github.com/kesudh). Exact shortest-path-tree warm refinement of
published routes. Per-case provenance is byte-verified in `meta.json`.

| legal | total delay | aggregate | runtime (s) |
|---:|---:|---:|---:|
| 9/9 | 142299 | 1.4139 | 270.15 |

Refined here: 3 of 9 cases. Carried verbatim from a credited
public entry: 6 (case_01, case_02, case_03, case_04, case_07, case_08).
`runtime.json` is one end-to-end run of this router per case at a uniform 30 s
budget; see `runtime_scope` in `meta.json`.

Timed parallel search is nondeterministic, so a repeat can return a different legal
route. No global-optimality claim is made.
