# warm_lns_refinement — designs

By [kesudh](https://github.com/kesudh). Exact shortest-path-tree warm refinement of
published routes. Per-case provenance is byte-verified in `meta.json`.

| legal | total delay | aggregate | runtime (s) |
|---:|---:|---:|---:|
| 3/3 | 203095 | 1.4773 | 90.30 |

Refined here: 0 of 3 cases. Carried verbatim from a credited
public entry: 3 (ctrl, int2float, router).
`runtime.json` is one end-to-end run of this router per case at a uniform 30 s
budget; see `runtime_scope` in `meta.json`.

Timed parallel search is nondeterministic, so a repeat can return a different legal
route. No global-optimality claim is made.
