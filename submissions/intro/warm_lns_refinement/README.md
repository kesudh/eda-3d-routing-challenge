# warm_lns_refinement — intro

By [kesudh](https://github.com/kesudh). Exact shortest-path-tree warm refinement of
published routes. Per-case provenance is byte-verified in `meta.json`.

| legal | total delay | aggregate | runtime (s) |
|---:|---:|---:|---:|
| 20/20 | 339192 | 1.1568 | 600.65 |

Refined here: 12 of 20 cases. Carried verbatim from a credited
public entry: 8 (case_06, case_07, case_10, case_11, case_12, case_13, case_14, case_18).
`runtime.json` is one end-to-end run of this router per case at a uniform 30 s
budget; see `runtime_scope` in `meta.json`.

Timed parallel search is nondeterministic, so a repeat can return a different legal
route. No global-optimality claim is made.
