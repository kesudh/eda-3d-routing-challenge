# cold_spt_lns

Independent cold-start routing by [kesudh](https://github.com/kesudh). The entry covers
all 45 cases across intro, hard, scale, stress, congested and designs. Green
CI establishes submission compliance; winning requires leading the independent
field under the maintainers' judging rules.

## Algorithm and independence

Each invocation reads one benchmark instance and constructs its own initial
geometry. There is no published-solution input, trained artifact or embedded
route data. The constructor overwrites the output path before refinement reads
it, so refinement only receives geometry made in that same invocation.

The current source supports exact or weighted multi-goal A* with negotiated
present/history congestion prices, fanout-aware price normalization, optional
compact tree growth and continued global renegotiation after a legal layout. Exact per-net
SPT descent, fixed-count group LNS, negotiated repair and displacement chains
then improve that set. Portfolio mode runs mixed search followed by chain search
inside the same process. Joint-search variants generate alternate trees from
the current invocation and use branch and bound to choose a vertex-disjoint
combination for a small net group. That selection is exact only over its finite
candidate pool. All phases are timed.

The refinement implementation is adapted from kesudh's own earlier Rust engine.
Search code is reused; no previous entry's route geometry is an input. Finite
trial counts and trial-based cooling determine the result. Wall time controls
logging and measurement only. One solver thread is used.

The original producing version used two cold starts, six sweeps and 128 group
moves. Retained cases keep that source and configuration. Each case's archived
source version and arguments are authoritative; changing CLI defaults never
changes the provenance or runtime of a retained case. No global optimum or
leading score is claimed without a current field comparison.

## Check and reproduce

Requirements: Python 3.9+ standard library and Cargo/Rust with lockfile v4
support. Producing toolchain: Rust/Cargo 1.98.1, Windows 11.

From the repository root:

    cargo test --locked --manifest-path submissions/intro/cold_spt_lns/router/Cargo.toml
    python submissions/intro/cold_spt_lns/run.py --check-only
    python submissions/intro/cold_spt_lns/run.py --reproduce

The checker validates legal routes, delay totals, runtime records, input/output
hashes and the complete archived producing source. Reproduction builds that
exact version, supplies only the instance and recorded arguments, and requires
byte-identical output. Builds use an operating-system temporary cache to avoid
Windows linker path-length limits. Original runtimes are preserved.

To reproduce one case:

    python submissions/intro/cold_spt_lns/run.py --reproduce --tier hard --case case_01

To generate strict improvements from raw instances:

    python submissions/intro/cold_spt_lns/run.py --tier hard --refine-trials 12000 --refine-mode portfolio --only-improvements

Use --out-root PATH for separate candidates and --hardware to describe the
producing machine. Submitted routes are read only after the candidate finishes,
by the adoption checker. They never become solver inputs.

## Source versions and runtime

The immutable reproducer directory named by source_version in runs.json contains
the actual producing source and runner. Its source.json hashes every file. The
version identifier is SHA-256 of sorted relative-path:file-sha256 lines, each
terminated by LF. Per-case solver_args provide the complete command.

runtime.json measures one complete solver process: launch, input parsing, cold
construction, every internal refinement stage, output serialization, file close
and process exit. Compilation, pre-run instance copying and post-run official
checking are excluded. No producer times from another entry are substituted.

Hardware: Intel Core i7-13700HX (16 cores / 24 logical threads), 31.7 GiB RAM,
Windows 11, one solver thread per case. Other local workloads may be active;
these are observed wall times on that hardware.

input_sha256 normalizes CRLF to LF for portable input comparison. The actual
producing bytes have a separate input_file_sha256. The solver reads the original
input. Source/output hashes use exact bytes preserved by .gitattributes.

## Validation

Ten Rust tests cover exhaustive tiny-grid optima, full-Dijkstra differential
checks, shared-trunk objective accounting, entry pricing, direct-chain pricing
bounded conflict splitting, exhaustive compatible-candidate selection, and strict
repair success/rollback on crossing nets. Every adopted output also passes the official
independent checker.

copy_audit.json describes the published revision's post-generation comparison
with pinned published Git blobs. It is refreshed when publishing improvements;
it does not automatically describe later uncommitted experiments. Other entries
are read by this audit after generation, never by the solver.

Maintainers control verification.json, reproduction status and final winners.
This submission does not edit that file or infer a win from green CI.

## Research and algorithm credit

The implementation uses general routing concepts described by
[PathFinder](https://janders.eecg.utoronto.ca/1387_2015/readings/pathfinder.pdf)
and [FastRoute](https://doi.org/10.1155/2012/608362). Fanout-aware congestion
pricing and finite-pool joint selection were also informed by the publicly
disclosed [Luna router](https://github.com/IrwinJam/m3d-router/blob/81e4729b7c17c40987a8f57436fa94b9cb1ece96/router.py).
These additions are independently written here. No opponent source code or route
geometry was copied. Algorithmic similarity is not used as evidence of geometry
independence: the publication audit compares canonical route hashes against the
pinned main and open-PR Git blobs, and rejects matching non-exempt candidates.

An experimental `--cost-distance 1` constructor merges weighted sink components
using congestion cost plus sink-multiplicity-weighted path delay, then extracts a
physical root-distance tree from the embedded union. It is informed by
[Held and Perner (2025)](https://arxiv.org/html/2503.04419v1). The vertex-resource
adaptation is tested independently and claims no inherited approximation bound.
A full-Dijkstra differential test covers its weighted nearest-component search.

`--refine-each-start 1 --starts N` runs a complete internal refinement for each
fresh construction and selects the best final bytes. The producing runtime
includes every start and every refinement stage. `--refine-temperature`,
`--refine-slack` and `--refine-group-max` expose deterministic exploration
settings. `--refine-mode portfolio-cbs` uses bounded conflict-based search
followed by displacement chains; the conflict search has a fixed node budget
and makes no global optimality claim when that budget is exhausted.
