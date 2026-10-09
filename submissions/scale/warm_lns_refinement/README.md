# warm_lns_refinement — scale

By [kesudh](https://github.com/kesudh). Exact shortest-path-tree warm refinement of
published routes. Per-case provenance is byte-verified in `meta.json`.

| legal | total delay | aggregate | runtime (s) |
|---:|---:|---:|---:|
| 8/8 | 531470 | 1.1403 | 241.40 |

Refined here: 0 of 8 cases. Carried verbatim from a credited
public entry: 8 (case_01, case_02, case_03, case_04, case_05, case_06, case_07, case_08).
`runtime.json` is one end-to-end run of this router per case at a uniform 30 s
budget; see `runtime_scope` in `meta.json`.

Timed parallel search is nondeterministic, so a repeat can return a different legal
route. No global-optimality claim is made.
