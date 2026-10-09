# warm_lns_refinement — stress

By [kesudh](https://github.com/kesudh). Exact shortest-path-tree warm refinement of
published routes. Per-case provenance is byte-verified in `meta.json`.

| legal | total delay | aggregate | runtime (s) |
|---:|---:|---:|---:|
| 1/1 | 1042150 | 1.0986 | 43.43 |

Refined here: 0 of 1 cases. Carried verbatim from a credited
public entry: 1 (case_01).
`runtime.json` is one end-to-end run of this router per case at a uniform 30 s
budget; see `runtime_scope` in `meta.json`.

Timed parallel search is nondeterministic, so a repeat can return a different legal
route. No global-optimality claim is made.
