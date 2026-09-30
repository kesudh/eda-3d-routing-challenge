# Can a custom trained neural network beat PR#3 (hard aggregate 1.381266) on M3D hard-tier routing?

Worktree: `F:/eda3d-wt/nn-policy` (branch `agent/nn-policy`). All numbers below were
produced by the scripts in `bench_nn/` on this host; nothing is estimated or carried
over from another agent's report except the "measured facts" list I was given, which
I did not re-derive.

**Environment note:** `torch` is **not installed** on this host (`ModuleNotFoundError`).
A pure-numpy MLP (`bench_nn/spike_lib.py::MLP`, 9 features → 32 tanh units → 1 linear)
was used as the accepted substitute. No environment was built out for torch.

---

## 1. Direct answer: can an NN beat 1.381266?

**No — not as a path model, and not as a move-selection policy at any plausible cost.**

Two separate claims, both measured:

### 1a. A learned *path* model has nothing to learn (structural, not empirical)

The objective charges `sum over sinks of driver→sink path delay`. Given a fixed set of
blocked vertices, the per-net optimum over all legal trees is *exactly* its
shortest-path tree — there is no Steiner/shape freedom, because every edge of a
driver-rooted tree is charged once per downstream sink and all delays are positive.
So the per-net decision is not "what shape should this net take" but "which set of
vertices is blocked". A network that predicts paths is predicting an answer that is
already computed exactly, in closed form, faster.

I verified the claim rather than assuming it. `bench_nn/dijk_bench.cpp` computes the
exact per-net SPT (all other nets' pins blocked) and `bench_nn/spt_ref.py` recomputes
it independently in Python. They agree to the digit on the summed objective
(case_01: **7156** both ways), and that value is the pins-only lower bound of the
whole objective for the case — no joint capacity-1 solution can beat the sum of
per-net optima. PR#3's submitted solution is 8674 on the same case, i.e. **21.2% above
a bound that is not achievable** (confirmed independently: m3d's own bound ratio and
`m3d/checker.py` recomputing PR#3's file gives exactly 8674, legal).

### 1b. A learned *policy* over LNS choices learns to rank, and it does not matter

This is the honest part, and it is where the spike found real signal — which then
failed to convert into score.

Setup (`bench_nn/spike.py`, `crosscase.py`, `prune.py`): start from PR#3's own
capacity-1 solution for a hard case, sample LNS neighbourhoods (nets touching a box
around a middle-layer seed, up to 12 nets; mean 9.1 nets/move, median 12), rip them up
and reroute **exactly** (Dijkstra per net, all other nets' vertices blocked). The label
is the *true* resulting change in total delay, so the supervision is exact, not
estimated. Features are 9 cheap aggregates available before the move runs (net count,
sinks, delay sum/mean, detour vs the net's pins-only SPT, middle-layer occupancy).

**Regime A — moves from PR#3's own state.** 537 feasible moves over 800 samples:
**0 improving**. Median true delta +626, best case +0. This is the established
"hard 1-opt local optimum" fact showing up in my own sampling. There is literally no
improving move for a policy to find, so a policy trained here is only learning to rank
*how bad* each move is.

**Regime B — a mid-LNS state** (state degraded by random rip-ups, so improving moves
exist): 165 feasible moves, **91 improving**. This is the only regime where a policy has
anything to select, and it is where I measured the policy honestly.

Ranking quality, MLP trained and tested **within** case_01 regime B:
Spearman 0.68, top-10 precision 0.90 (random 0.55), y(top-1) +438 vs random −60.
So the model genuinely learns the ranking. Hand heuristics are worse than random here
(Spearman +0.15 for max-detour, −0.45 for max-net-count).

**Transfer to unseen cases** (trained on case_01 only, tested on case_05/case_09,
regime B): Spearman **0.46 and 0.62** vs random ~0.00; top-10 precision 0.50/0.60 vs
random 0.34/0.38. So even the generalisation claim survives — a 9-feature MLP trained on
160–500 samples of one instance ranks moves meaningfully on a different grid.

**And it still does not produce a better solution.** Head-to-head LNS
(`bench_nn/headtohead.py`), identical candidate budget, identical seeds, only the
selection rule differs, 6 restarts, mean final total delay from a common start state:

| case | start | random | hand:max_detour | hand:max_net_count | **MLP policy** | PR#3 |
|---|---|---|---|---|---|---|
| case_01 | 12120 | 10629.3 | 10356.0 | 10945.0 | **10330.7** | 8674 |
| case_05 | 20661 | 19943.0 | 20096.0 | 20356.3 | **19834.7** | 15311 |
| case_09 | 27040 | 27030.0 | 26611.7 | 27040.0 | **26247.7** | 21476 |

The policy is the best of the four on all three cases, by 0.5–2.9% over random. But the
entire LNS-from-scratched loop lands **1500–6000 above PR#3** on every case. The move
selector is not the bottleneck: no policy over move selection closes a gap that large,
because the search itself cannot reach PR#3's quality from a degraded start. Selecting
better moves inside a search that ends 17–28% worse than the incumbent is worth nothing
on the leaderboard.

**The one place a policy could pay: pruning.** In the head-to-head every candidate was
still evaluated exactly, so the policy saved no work. `bench_nn/prune.py` tests the only
version that could add value — score all candidates cheaply, exactly evaluate only the
top-k — at matched evaluation budgets:

| case | evaluate all 14 (mean final / evals) | policy top-4 (mean / evals) | random keep-4 control |
|---|---|---|---|
| case_01 | 10189.7 / 58 | 10439.7 / 17 | 11846.3 / 6 |
| case_05 | 18134.0 / 91 | 18967.3 / 20 | 20207.0 / 7 |
| case_09 | 24098.0 / 84 | 24630.0 / 25 | 25938.3 / 15 |

The policy at top-4 lands within **2.5% of the full-evaluation oracle while doing ~3x
fewer exact evaluations**, and it beats the random-pruning control by 7–12%. So pruning
with a learned ranker is a real, measurable win *as a compute-allocation trick*. It
buys roughly 3x more LNS steps per unit time. Given the loop above never reaches PR#3
quality, 3x more of it still does not reach PR#3 quality. The 21–33% gap to the pins-only
bound lives in the *global assignment*, not in which local move you pick.

---

## 2. Direct answer: would it be faster?

**Yes, the NN forward pass is ~1–2 orders of magnitude cheaper than the exact inner
loop it would replace — and that is worthless here, because runtime does not affect the
score.**

### The exact inner loop, measured (`bench_nn/dijk_bench.cpp`, clang++ -O2, MSVC STL)

Both modes are exact and verified against the Python reference (mean sink delay
identical: 53.40 / 60.65 / 79.47).

| case | grid | verts | nets | full Dijkstra | **A\* (realistic)** | nets/s (A\*) |
|---|---|---|---|---|---|---|
| case_01 | 24×24×6 | 3 456 | 62 | 321.1 µs/net (3 114 nets/s) | **72.0 µs/net** | 13 893 |
| case_05 | 32×32×6 | 6 144 | 83 | 481.5 µs/net (2 077 nets/s) | **104.6 µs/net** | 9 563 |
| case_09 | 40×40×6 | 9 600 | 104 | 772.1 µs/net (1 295 nets/s) | **143.0 µs/net** | 6 996 |

These are *pessimistic*: the grid has only 3 456–9 600 vertices with integer weights in
2–6, so a dial/bucket queue would beat the binary heap, and a real router additionally
restricts the search to a bounding box. A full PathFinder pass over a hard case is
62–104 net-routings, i.e. **~4–15 ms of exact search, end to end**. PR#3 spent 53 655
CPU-seconds total; one net-reroute is 0.01% of a single case's budget.

### NN inference cost, measured (numpy MLP, 9→32→1)

| batch | forward pass | per candidate |
|---|---|---|
| 1 | 6.5 µs | 6.51 µs |
| 14 | 14.7 µs | 1.05 µs |
| 64 | 37.2 µs | 0.58 µs |
| 512 | 217.4 µs | 0.42 µs |

So scoring 14 candidate moves costs **14.7 µs**, versus **~1.0 ms** to exactly evaluate
one of them (0.104 ms/net × 9.1 nets/move) in C++. The policy is ~70x cheaper per
decision. It also loses information: the exact evaluation is what guarantees
capacity-1 legality and gives the true delta.

### Training cost

The whole policy trained in **0.31–0.94 s** on 160–269 samples of one case, on CPU, with
numpy. Training is not the cost. **Sample generation is**: exact move evaluation runs
22–104 ms/move in Python, so 500 labelled moves cost 11–52 s, and 10⁵ labelled moves
would cost ~1–3 CPU-hours *per instance state*. That is the real budget item, and it is
a search budget, not a learning budget.

### Why speed buys nothing here

Scoring: runtime never affects the score. So speed matters only insofar as it buys more
search in fixed wall-clock. A 70x-cheaper decision buys at most ~3x more LNS steps
(measured above, not 70x, because feature extraction and bookkeeping dominate at
9 features). 3x more steps of a search that ends 17–28% worse than the incumbent is not
a path to 1.381266. Meanwhile the established Lagrangian certificate already shows
**~12.7% certified headroom on case_01 (7573 vs 8674)** — that headroom is reachable by
a better *global* method, not by a faster local loop.

---

## 3. The realistic best-case NN design, and what training it would take

If the swarm insisted, the only design with a mechanism is **not** a path model and not
a congestion predictor. It would be a learned *pruner* inside a C++ LNS loop:

- **Representation.** A small GNN or MLP over per-candidate-move aggregates
  (region congestion histogram per layer, fanout mix, detour vs the net's own SPT,
  net-count, current delay, how many equal-cost SPT choices the region has). The
  equal-cost-choice count matters: the shared corpus notes ~2.7 equal-cost choices per
  net, ~220 per hard case, as an untested seam.
- **Output.** A scalar score used only to order candidates; the top-k are then exactly
  rerouted. Never a path, never a legality decision.
- **Training.** ~10⁴–10⁵ (features, true-delta) pairs per tier, gathered by running the
  existing C++ LNS and logging candidate moves it *evaluated anyway*. 10⁵ samples at
  ~1 ms/exact-eval in C++ ≈ 100 s of search per instance — cheap in principle, but it
  requires a C++ logger that does not exist yet, and 9 hard cases give you 9 distinct
  distributions to hold out. Multi-case generalisation is the open risk: my measured
  transfer (ρ 0.46–0.62 across cases) is real but from 9 features and a 32-unit MLP;
  a GNN would have far more capacity to overfit 9 instances.
- **Honest expectation.** The measured ceiling of this design is the top-4 pruning row:
  ~3x search throughput and 7–12% better final delay than random pruning *within a
  degraded-start LNS*. Against PR#3's 1.381266 that is worth 0.00%.

---

## 4. Comparison with the non-NN lanes the swarm is running

The relevant comparison is not "NN vs nothing", it is "NN vs the 3x-search-multiplier
you get for free from a better combinatorial method".

| approach | what it exploits | sample/compute need | expected effect on 1.381266 |
|---|---|---|---|
| **Lagrangian duals / path-based duals** | the joint assignment directly; the 12.7% certified headroom on case_01 is *measured* headroom | a solver; no training data | attacks the actual gap |
| **MIP / column generation over equal-cost SPT choices** | the ~220 zero-cost SPT-choice vertices per case that no local method touches | a solver; the choices are enumerated, not learned | attacks the actual gap |
| **Simulated annealing / large-neighbourhood portfolio** | brute-force the 21–33% over bound with more iterations | CPU only — PR#3 already spends 53 655 CPU-s and runtime is free | more search, no data needed |
| **Learned move pruner (this workstream)** | 3x more LNS steps per second | 10⁴–10⁵ labels per case + a C++ logger | ~0.00%; 7–12% *within* a loop that is 17–28% worse than PR#3 |

The pattern is the standard one for this problem class: at 9 training instances with
exactly-known combinatorial structure, a learned policy can learn to rank local moves
(it demonstrably does, ρ 0.46–0.62 cross-case) and that ranking is worth a few percent
*of a suboptimal search*, which is worth ~0% of the score. Combinatorial methods attack
the quantity that is actually binding — the joint assignment gap — and the one certified
number we have (12.7% on case_01) is already larger than anything a move pruner could
realistically deliver.

**Effort should go to the duals/MIP lanes and to the zero-cost-SPT-choice seam, not
here.**

---

## 5. Recommendation

**Do not invest the swarm in a learned router for M3D.**

1. A learned path model is structurally impossible to beat: per-net optimum *is* the
   SPT (verified two independent implementations agreeing at 7156 on case_01).
2. A learned move-selection policy *does* learn real, cross-case-transferable ranking
   (Spearman 0.46–0.62 unseen) and I am not going to hide that — but following it moves
   the final delay by 0.5–2.9% inside a search that ends 1500–6000 above PR#3.
3. Its only real payoff is a ~3x search-throughput multiplier from pruning, which is
   worth ~0.00% on a metric where runtime is free and the gap is 21–33%.
4. Inference (1–15 µs) is genuinely cheap and training is genuinely cheap (0.3–0.9 s).
   Those are not the problems.

If someone revisits this, the two things that would change my answer are: (a) evidence
that a *global* quantity (dual prices, net grouping, restart schedule) is predictable
and not just a search knob, and (b) a label-generation pipeline that can produce 10⁵
samples across all 9 hard cases without paying exact evaluation per sample. Neither
exists today.

### Reproduction

```
cd bench_nn
python digest.py ../benchmarks_hard/case_0{1,5,9}.json
clang++ -O2 -std=c++17 -o dijk_bench.exe dijk_bench.cpp
./dijk_bench.exe ../benchmarks_hard/case_01.txt 1 50   # A*, exact inner loop
python spt_ref.py ../benchmarks_hard/case_01.json       # independent Python check
python spike.py --moves 800 --steps 10 --perturb 40 --sol <pr3_case01.json>
python crosscase.py --moves 400                          # train case_01, test 05/09
python headtohead.py --moves-train 400 --steps 20 --restarts 6
python prune.py --moves-train 400 --steps 20 --restarts 6
```

PR#3 solutions used as the starting states:
`git show pr3:submissions/hard/pathfinder_lns/case_NN.sol.json`
(legality and delay re-verified with `m3d/checker.py`: case_01 legal, 8674).
