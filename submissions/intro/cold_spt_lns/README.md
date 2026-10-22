# cold_spt_lns

Independent routing entry by [kesudh](https://github.com/kesudh), generated on
2026-10-22. This directory contains the complete solver source and the runner
shared by this entry's five tiers.

Entered tiers: intro (20 cases), hard (9), scale (8), congested (4), and designs
(3), for 44 complete cases. This entry does not enter the stress tier.

## Inputs and independence

Each solver process receives exactly one benchmark instance JSON and an output
path. Its temporary working directory initially contains only that instance.
The solver has no solution-input option and contains no route data, trained
weights, reference-solution reader, or case-specific routing settings. All five
tiers use the same seed and fixed work counts. No geometry from
`warm_lns_refinement` or another submission is used.

The Rust implementation is new for this entry. It uses the challenge's grid,
pin, capacity, and delay definitions. Its algorithmic ingredients are
shortest-path trees, PathFinder-style history/present congestion prices, and
group rip-up and reroute. These are algorithmic techniques, not route inputs.
The previous entry remains a separate warm-start experiment.

## Method

1. Begin with no routes. Construct driver-rooted shortest-path trees while
   forbidding other nets' pins. Shared vertices are temporarily allowed during
   construction, with accumulated history and current-occupancy penalties.
2. Reroute conflicting nets until all resources have capacity one. Construction
   is limited to 200 rounds per start; a failed start supplies no candidate.
3. Perform six shuffled exact single-net sweeps with all other nets fixed.
   Multi-goal A* uses the exact obstacle-free layered-grid distance as an
   admissible heuristic. It minimizes the sum of driver-to-sink distances for
   one net, rather than the sum of tree-edge weights.
4. Attempt 128 local group moves, each removing two to six nearby nets. Keep a
   legal rearrangement only when the group's total sink delay does not increase.
   Finish with two exact single-net sweeps.
5. Repeat from an empty routing for a second start, inside the same invocation,
   and write the better legal result. Both starts and all intermediate work are
   included in that invocation's runtime.

The seed is 20261022. All decisions use integer arithmetic, fixed work counts,
and an explicit pseudorandom generator; wall time does not control the output.
No global-optimality claim is made. The included Rust tests compare the
single-net objective with exhaustive tiny-grid trees and compare multi-goal A*
with full Dijkstra on random layered grids, including obstacles and congestion
prices.

## Build and reproduce

Requirements: Python 3.9+, Cargo/Rust with edition 2021 and Cargo lockfile v4
support (Cargo 1.83+). The producing machine used Cargo/Rust 1.98.1. Python uses
only the standard library and the repository's checker. Cargo downloads the
locked JSON-parser dependencies when first built; routing requires no network.

From the challenge repository root:

```sh
cargo test --locked --manifest-path submissions/intro/cold_spt_lns/router/Cargo.toml
python submissions/intro/cold_spt_lns/run.py --check-only
python submissions/intro/cold_spt_lns/run.py --reproduce
```

`--check-only` validates the committed solutions and their recorded instance,
source, and output hashes. `--reproduce` rebuilds the locked source, runs every
case in a fresh temporary directory, invokes the independent checker, and fails
on any byte mismatch. It does not overwrite the committed routes or their
original runtime measurements. A different executable hash on another platform
is expected; route bytes must still match.

To replay a subset:

```sh
python submissions/intro/cold_spt_lns/run.py --reproduce --tier hard --case case_06
```

To generate a new measurement without overwriting this submission:

```sh
python submissions/intro/cold_spt_lns/run.py --out-root /tmp/cold-spt-results --hardware "CPU model, RAM, OS"
```

Each selected tier is complete. To locate Cargo explicitly, pass `--cargo` with
its executable path. The direct solver interface is:

```sh
cargo build --release --locked --manifest-path submissions/intro/cold_spt_lns/router/Cargo.toml
submissions/intro/cold_spt_lns/router/target/release/cold-spt-lns INSTANCE.json OUTPUT.sol.json --seed 20261022 --starts 2 --rounds 200 --sweeps 6 --moves 128
```

## Runtime and provenance

One CPU thread per case, Intel Core i7-13700HX (16 cores / 24 logical threads),
31.7 GiB RAM, Windows 11. Other local jobs may run concurrently; these are
observed wall times on this machine, not normalized CPU times. `runtime.json` is
measured with Python's monotonic performance counter around one solver process,
from process launch through instance loading, both cold starts, construction,
all refinement, serialization, output-file close, and process exit. Compilation,
copying the instance into the temporary directory, and the independent checker
after the process exits are excluded. No producer time from another entry is
substituted, and no best-of-external-runs selection is used.

Each tier's `runs.json` records the actual wall time, command arguments, input
SHA-256, output SHA-256, source SHA-256 values, producing executable SHA-256,
hardware, and complete solver progress log for each shipped case. The runtime
file and run record refer to the same invocation. Reproduction checks leave
these measurements intact.

`input_sha256` hashes the instance text with CRLF normalized to LF, so it agrees
across Git checkout styles. `input_file_sha256` records the exact bytes actually
passed to the producing solver. The solver still reads the original instance
without changing it. Source and output hashes use exact bytes; the entry's
`.gitattributes` preserves those bytes across checkouts.

This entry is submitted for review under both the current contribution rules
and the proposed [judging rules in PR #66](https://github.com/partcleda/eda-3d-routing-challenge/pull/66).
Maintainer reproduction and the `verified` column remain for the maintainers
to assess.

`copy_audit.json` records a separate post-generation comparison using PR #66's
unmodified canonical route-hash function against actual Git blobs from `main`
and every open upstream PR head pinned in that report. No non-exempt case
matches a published route. Intro `case_01` has six nets and is exempt under that
policy. Published routes are read only by this audit, after the solver has
finished, and never by the solver or its generation/reproduction runner.
