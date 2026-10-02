# warm_lns_refinement — hard

By [kesudh](https://github.com/kesudh). Incremental warm refinement of published
routes, with complete upstream credits and source hashes in `meta.json`.

This revision has 9/9 legal cases, total delay
144,975, and aggregate 1.388562903791. It improves
PR24 at `58585d7b496d505dfa35f2426df4269974e583fa` by 12 total-delay units.

`runtime.json` reports 25.348778 seconds across this tier. These
are measured **incremental refinement** times, including private ancestor
stages and independent checking. They exclude public warm-start generation,
compilation and the tuning campaign; they are not from-scratch routing times.
Hardware: i7-13700HX, Windows; worker counts are recorded per command. Timing
was measured alongside other workloads and is not normalized across authors.

The method uses exact radix/A* shortest-path trees with feasible per-sink
bounds, neutral and group moves, preserved-route repair, bounded excursions,
CPU search portfolios, and two-parent minimum-cut crossover following PR24.
The CUDA prototypes were benchmarked separately and did not produce these routes.

The versioned Windows replay bundle, source, commands and full provenance are
in `submissions/intro/warm_lns_refinement/replay`. Timed parallel searches can
produce different legal routes when repeated. Current experimental detour and
pair-sweep operators are included in the latest source but did not improve the
selected hard-case routes. No global optimality or immunity to future tuning
is claimed.
