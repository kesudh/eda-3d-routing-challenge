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

The current generator captures each source file's bytes once and installs
completed immutable files atomically with separate temporary files per writer.
Eight concurrent capture/validation processes passed without manifest races.

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

Fourteen Rust tests cover exhaustive tiny-grid optima, full-Dijkstra differential
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

`--compact-shortest-tree 1` adds greedy shared-branch candidates to the joint
pool. It chooses paths inside the exact physical shortest-path predecessor DAG,
so each sink keeps its shortest distance while the candidate tries to use fewer
vertices. It does not claim a minimum-size Steiner arborescence. A tiny-grid test
checks connectivity, sink distances, compactness and foreign-resource avoidance.

`--post-cbs-trials N` adds a conflict-search phase after the normal refinement,
using only this invocation's own best route. `--cbs-nodes` sets the fixed node
budget per conflict search (default 256). Every phase is included in producing
runtime, and the final phase retains a non-worsening incumbent.

`--joint-neutral 1` samples equal-delay, equal-footprint combinations in joint
search instead of always preserving the current geometry. Mode 2 also permits
larger footprints at equal delay; mode 0 preserves the original behavior.
Physical delay never increases in this joint move. A selection test checks
delay/footprint policy, tie diversity and outside-resource restoration.

`--penalized-astar 1` uses a physical-distance lower bound for congestion-priced
searches with up to eight sinks. Queue entries preserve the original floating
distance separately from priority, and the final equal-priority plateau is
completed before extraction. Differential tests include history, soft occupancy,
foreign pins and hard blockers. The default is 0 for compatibility.

In one matched 12,000-trial hard/case_01 pilot, this option preserved the exact
9,060 route bytes while observed full time fell from 50.886s to 32.995s. Search
expansions fell from 79,693,415 to 28,946,893 across the two phases. These are
single-case observations under concurrent workloads, not a general speed claim
or replacement timings for retained routes.

`--emit-global-pool 1` requires a separate `--out-root` and exports research
alternatives generated from the current invocation's own incumbent. The output
route is still independently checked. No external pool selector is part of this
producer, and offline research selection results are not eligible submissions.

`--retain-compact-best 1` retains a smaller tree when physical delay ties the
best seen delay. This lets the next phase and final polishing use the compact
geometry. It does not count footprint changes as delay improvements. The
default is 0 for compatibility with archived runs.

Experimental `--flow-pricing 1` divides a resource's congestion price by the
number of sink paths using it in this invocation's previous tree. Mode 2 uses
the square root of that count. An unused resource has count one, internal sinks
contribute to the count, and each net resets the counts before rerouting. This
replaces the global fanout divisor for root-SPT construction only. It is a
heuristic for the difference between per-tree resource use and per-sink delay;
there is no convergence or approximation guarantee. Default 0 preserves the
original pricing, and a fresh uniform fallback disables flow pricing. A test
checks branching, internal sinks and reset between nets. Pilots have mixed
results and do not establish a general quality improvement.

`--joint-group-max 6` extends joint candidate generation and compatible
selection to six interfering nets. The default remains four. Selection is
exact over its finite pool, with no claim of global tree optimality. The
exhaustive selector test covers two through six nets and fixed outside
resources. Larger groups can take more work. A matched 12k hard01 pilot gave
9040 for six nets versus9086 for four (43.625s versus42.538s observed), still
above the retained8866; broader experiments are needed.

A subsequent cold invocation using60k mixed-joint trials with the six-net
option, followed by1k conflict-search trials, reached8856 in293.355s. Its
mixed-joint phase ended at8866 and the last improvement came during conflict
search. This supports the combined configuration, not an isolated claim about
neighborhood size. The previous8866 configuration used different work and
settings, so its runtime is not a matched speed comparison.

`--penalized-integer-queue 1` uses integer queues for direct congestion prices
that are exact multiples of one quarter. It scales priorities by four, checks
a conservative u32 bound, and uses Dial buckets or a radix fallback for wider
costs. General floating history costs keep the original heap. Costs, sink
distances and tight-edge extraction stay in their original arithmetic. Tests
compare extracted trees with the floating heap, including entry prices, A*,
non-quarter costs, wide costs and overflow fallback. The default is 0.

One matched12k hard01 pair produced identical9086 route bytes and expansion
counts, with observed complete runtime43.526s versus40.488s for the option.
That is a single observation under concurrent workloads, not a general speed
claim. It does not replace timings for other retained runs.

A matched12k designs/router pair also produced identical76143 route bytes:
372.400s with the floating heap versus341.783s with the option. These are
observations under concurrent workloads, with original producing times kept.

`--refine-race-pilot P --refine-race-keep K` optionally allocates restart work
adaptively. It requires `--refine-each-start 1`, K no larger than `--starts N`,
and P no larger than `--refine-trials R`. Each start constructs fresh geometry
and receives P pilot trials. The best K successful pilots receive another
R-P trials with deterministic phase seeds. Post-CBS work is reserved for those
finalists. All construction, pilots, finalists and output work are timed in
one producing process. The controller retains its best completed pilot or
finalist; it imports no routes or learned artifacts. The maximum main-trial
count is N*P+K*(R-P), plus any explicitly configured post-CBS work.

This is a simple promotion stage inspired by adaptive resource allocation in
[Hyperband](https://arxiv.org/abs/1603.06560), not an implementation of its full
schedule or a transfer of its guarantees. Early pilot rankings can miss late
improvements. A four-start intro03 check with P=R=2000 preserved the uniform
control's exact1623 route bytes. P=500 and K=2 also reached1623, with5000 main
trials versus8000 in that control, and replayed byte-identically. Broader
equal-trial-budget comparisons are still required. Default P=0 disables racing.
