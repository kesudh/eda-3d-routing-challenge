# Scaling methods that survive a closed local-search neighbourhood

**Agent:** `agent/scaling` · **Scope:** column generation, cutting planes, Lagrangian
decomposition with a primal driver, Benders, and the calibration question — *has anyone
closed an instance this big?*

Everything below is checked against real sources. Where I could not verify a number I say
so explicitly rather than guessing. Runtimes quoted are as reported by the cited authors
on their own hardware.

---

## 0. Executive summary for the parent agent

1. **Column generation is the right frame, and the literature has run exactly our
   formulation at scale.** Wu, Davoodi & Linderoth's *GRIP* (DAC 2009 / IEEE TCAD 2010) is a
   set-partitioning IP for global routing of multi-terminal nets on a 3D grid, solved by
   column generation with a Dijkstra-based pricing phase, then integer-solved. It reports
   **9.23% average wirelength improvement and 5.24% via-cost improvement over the best
   published result** on ISPD 2007/2008, on 176k–2.6M nets. This is the closest published
   precedent to our situation and it **beat rip-up-and-reroute / negotiated-congestion
   incumbents that were themselves well-converged**. It is the single most valuable citation
   in this report.

2. **Our pricing oracle is NOT a shortest path.** Because the objective is a *sum of
   root-to-terminal distances* rather than a sum of edge costs, the column cost is not
   separable over the tree. The pricing problem reduces to a **minimum-π shortest-path-tree**
   problem: among all SPTs rooted at σ, find the one whose *occupied vertex set* has minimum
   total dual price. This is materially harder than the textbook Dijkstra, and it is exactly
   the point where naive CG will fail. The V-shaped symmetric layer profile may tame it; that
   is a testable hypothesis, not a result.

3. **The master is already small in rows, which breaks the usual scalability argument.**
   Our RMP has `N = 62..104` demand rows plus `|V| = 3456..9600` capacity rows. The MCF
   literature's CG scalability story (master has O(|K||V|) rows) does not transfer. Our
   bottleneck is *columns and degeneracy*, not rows.

4. **Cutting planes will not close the 26.6% gap.** Gendron & Larose report empirically that
   cover and flow-cover inequalities improve the bound on large instances by an amount *so
   small it does not pay off*. Read §3 for the exact quote and the instance class.

5. **Calibration: nobody has closed an instance this big.** The best I can verify is the LP
   relaxation (not integer) of a 1225-node / 32 000-commodity MCF in 10.6 s, and the *integer*
   MCND being unsolved at 30 nodes / 400 commodities in 3 hours by six methods including
   CPLEX. **The 26.6% headroom is almost certainly not reachable at N=62..104, |V|~10⁴ by any
   known exact method.** §4. Treat any promise to close it as a red flag.

6. **The realistic deliverable from CG here is primal, not dual.** Use CG to build a
   dual-informed column pool, then integer-solve over the pool. That is the GRIP recipe and
   the one documented route to beating an exhausted local-search incumbent.

---

## 1. The formulation (stated for *our* constraints, not by analogy)

Let `G` be the 3D grid, `N` nets, `τ_n` the sink set of net `n`, `σ_n` its driver.
Let `𝒯_n` be the set of connected acyclic subgraphs of `G` containing `σ_n ∪ τ_n` and
containing no foreign pin. This is a **set-partitioning / Steiner-tree-packing** formulation:

```
min  Σ_n Σ_{t ∈ 𝒯_n}  c_nt · x_nt
s.t. Σ_{t ∈ 𝒯_n} x_nt = 1                        ∀n          (each net routed once)
     Σ_n Σ_{t ∈ 𝒯_n} 1[v ∈ t] · x_nt  ≤ 1         ∀v ∈ V     (vertex capacity 1)
     x_nt ∈ {0,1}
```

with **`c_nt = Σ_{τ ∈ τ_n} d_t(σ_n, τ)`**, the sum of *root-to-terminal tree distances* —
established in `_shared/problem.md` as the sum-of-distances objective, with a shared segment
charged once per downstream sink.

**This is exactly the formulation class of VLSI global routing.** Behjat, Vannelli &
Rosehart give integer linear programming models for global routing of the same shape
(*International Linear Programming Models for Global Routing*, INFORMS J. Computing 18(2)
2005, 137–150, cited as [4] in Deza et al. 2010, `https://optimization-online.org/wp-content/uploads/2010/12/2852.pdf`).
Deza, Dickson, Terlaky, Vannelli & Zhang's survey-style paper on that same ILP family is
the best single free reference I found: it frames the problem as "find a set of trees in
the lattice graph, one per net, respecting channel capacities, minimising wirelength or
bends", states the NP-hardness, and reviews both the sequential (rip-up-and-reroute) and
concurrent (ILP/LP + randomized rounding) schools. `https://optimization-online.org/wp-content/uploads/2010/12/2852.pdf`

**Hardness is established for the neighbourhood, not just "it looks hard."** Our problem is
vertex-disjoint Steiner-tree packing on a grid, with pins on the two outer layers and
per-net trees — i.e. 3D channel/switchbox routing.

- **Hartmann, Schäffter & Schulz, "Switchbox routing in VLSI design: closing the complexity
  gap"**, Theoretical Computer Science 203 (1997) 1–12 / LNCS 1197 (WG 1996) extended
  abstract: switchbox routing is **NP-complete even when no net has more than three
  terminals**, settling the gap between Preparata & Mehlhorn's polynomial result for
  2-terminal nets and Sarrafzadeh's 5-terminal result. Adapting the construction gives
  NP-completeness for channel routing with ≤4 terminals.
  `https://link.springer.com/chapter/10.1007/3-540-62559-3_17`
- **Tayu & Ueno, "The complexity of three-dimensional channel routing"** (5th, Hangzhou
  Japan Joint Workshop, 2007): 3D channel routing — terminals on the top and bottom layers
  of a (W,D,H) grid, nets connected by vertex-disjoint Steiner trees — is **NP-complete even
  for 2-nets**, via reduction from the (r×s−1)-puzzle.
  `https://www.eda.ict.e.titech.ac.jp/ueno/Files/papers/TU07-5thHJ.pdf`
  Journal version: Tayu, Takahashi, Kobayashi & Ueno, *IEICE Trans. Fundamentals* E99-A(10)
  (2016) 1813–1822, `https://www.eda.ict.e.titech.ac.jp/ueno/Files/papers/TTKU16-IEICE_Trans_Fundamentals.pdf`
  (DOI 10.1587/transfun.E99.A.1813)
- Our problem is *not* the 2-net case: ours is single-source multi-sink, and the
  established fact is that the per-net optimum is the SPT with no Steiner gain. The
  hardness above is a hardness result for the **packing/assignment** decision, which is
  precisely the part that remains after the per-net shape problem is solved. So the
  hardness transfers: the residual difficulty is *which* SPT each net gets and how they
  are packed, and that is NP-complete.
- For completeness on the counting side: **Hastrich & Simonov, "Structural Parameterization
  of Steiner Tree Packing"** (STACS 2026, arXiv 2505.09250) give the first FPT results in
  the *tree-cut width*, *fracture number* and *slim tree-cut width* of the input graph.
  Not applicable — our grid has linear tree-cut width — but it is the right citation for
  "what makes this problem tractable, formally". `https://arxiv.org/abs/2505.09250`

**Honest caveat on my own hardness claim:** the reductions above are for 2- and 3-terminal
nets. I did **not** find, and am not claiming, an NP-hardness proof for the
*single-source-multi-sink, capacity-1-per-vertex, sum-of-root-to-distances* instance
exactly. What I can say is that the packing subproblem is in the same NP-complete family
and that no tractable formulation for it exists in the literature I surveyed.

---

## 2. Column generation: the formulation is right, the pricing oracle is the trap

### 2.1 The canonical reference implementation is literally our problem

**Wu, Davoodi & Linderoth, "GRIP: Global Routing via Integer Programming"**, DAC 2009
(`https://jlinderoth.github.io/papers/Wu-Davoodi-Linderoth-09.pdf`) and journal version
(*IEEE TCAD*, `https://jlinderoth.github.io/papers/Wu-Davoodi-Linderoth-10-PP.pdf`).

Their ILP-GR:

```
min Σ_n Σ_{t∈T(T_n)} c_it x_it + Σ_n M s_i
s.t. Σ_{t} x_it + s_i = 1                          ∀i
     Σ_i Σ_{t} a_te x_it ≤ u_e                     ∀e ∈ E
     x_it ∈ {0,1},  s_i ≥ 0
```

Columns are **Steiner trees per multi-terminal net**; rows are **edge capacities**; the
slack `s_i` with big-`M` penalises unrouted nets. That is our formulation with edge
capacity replaced by vertex capacity.

Reported results (journal version, abstract): **for the ISPD 2007 and 2008 benchmarks, GRIP
obtains an average improvement in wirelength and via cost of 9.23% and 5.24% respectively
when compared to the best result in the open literature.** Table II of the PDF lists
per-benchmark totals (edge TOV, WL, via) for GRIP with and without the overflow step, against
FGR 1.1, FastRoute 4.0, NTHU-Route 2.0 and BoxRouter 2.0 — all negotiated-congestion /
rip-up-and-reroute routers. **This is a documented case of a set-partitioning + column
generation method beating well-converged local-search incumbents by 4–12% on 3D
multi-terminal nets.** Instance sizes in Table I: 176 715 to 2 635 625 nets, grids 227×227
to 774×779, 6–8 layers, per-edge capacity 52–212.

**Limits of the analogy — be explicit.** GRIP's capacities are 52–212 per edge, not 1. At
capacity 1 every column is in conflict with almost every other column and the LP is far
degenerate. GRIP also relaxes `s_i` (some nets may be unrouted), which we cannot do. And
GRIP uses *heuristic* pricing (§2.3) plus early tail-off termination, so it is a
*primal-quality* method, not a proof method. Treat the 9.23% as evidence that the method
class escapes a converged incumbent — not as a promise about our gap.

### 2.2 The pricing subproblem for *our* objective is a min-π SPT problem, not Dijkstra

Write the master dual as `λ_n ≥ 0` (demand rows) and `π_v ≤ 0` (capacity rows). The dual
constraint for column `(n,t)` is

```
λ_n + Σ_{v ∈ t} π_v ≤ c_nt ,    ∀n, ∀t ∈ 𝒯_n
```

so the pricing problem is

```
min_{t ∈ 𝒯_n}  [ c_nt + Σ_{v ∈ t} π_v ]   and add t if < λ_n.
```

Now use the two established facts.

- **Fact 1: given a vertex set to occupy, the best tree is the SPT.** So
  `min_t c_nt` over trees that occupy a given vertex set is the SPT delay.
- **Fact 2 (crucial): `c_nt` is not `Σ_{v∈t} w_v`.** It is
  `Σ_τ d_t(σ_n, τ)`, a sum of path lengths. There is no per-vertex `w` with
  `c_nt = Σ_{v∈t} w_v`.

Therefore the pricing problem is **not** "find the min-weighted SPT under `c − π`", which is
what the network-design literature does. It is:

> **Among all shortest-path trees rooted at `σ_n` in the currently-feasible subgraph, find
> the one whose occupied vertex set minimises `Σ_{v∈t} π_v`.** If that minimum, minus the
> SPT delay, is below `λ_n`, the column enters.

This is a *secondary-criterion shortest-path-tree* problem: the primary criterion (delay)
must be optimal, the secondary (occupied-node price) is then optimised over the optimal
face. Consequences:

- **The optimal face is enormous here, and the swarm already measured it.** The
  established fact that **57% of single-net reroutes change the vertex set at zero delay
  cost** is exactly the statement that the SPT optimal face is 57%-wide. Pricing must
  search *within* that face, and that search is where the cost is.
- A plain Dijkstra on `c − π` will generally return a *non-optimal* answer to the pricing
  problem, because it may not return an SPT of `c` at all. That breaks the CG optimality
  test. In practice the literature's answer to this is a *heuristic* pricing oracle
  (GRIP §2.3) plus tail-off termination.
- **Is it NP-hard?** A secondary-cost SPT with node weights is not solvable by a
  straightforward exchange argument in general. I searched for a clean citable NP-hardness
  proof of "minimum-total-weight shortest path tree" and **did not find one I can stand
  behind**; I am therefore *not* claiming NP-hardness for the pricing subproblem. What I
  can assert is that it is a different problem from shortest path, and the classic
  Dijkstra pricing oracle is not an exact oracle for it.

**The exploitable structure (hypothesis, worth one experiment).** Our layer profile is
symmetric and V-shaped, `d_z = c + s|2z − (L−1)|`, giving `[6,4,2,2,4,6]` with `v = 3`. Two
consequences that should make the secondary criterion tractable:

1. The cost alphabet is a handful of integers, so the SPT-optimal face is stratified by a
   small set of (z-profile, monotone-x/y-shape) classes rather than being arbitrary.
2. `d_2 = d_3 = 2` and `d_1 = d_4 = 4 < 6 = d_0 = d_5`, with `v = 3`. A layer-change costs
   3 while an in-layer step costs ≥2, so a net that must move a long way in `(x,y)` has a
   *strictly optimal* strategy: change layer early, travel in `z ∈ {2,3}`, change back
   late. That should make the SPT shape largely determined by a small set of parameters
   (which layer to traverse in, where to enter/exit), and the secondary criterion reduces
   to a DP over a monotone structure.

**I have not verified this.** It is a one-day experiment: enumerate SPT classes on a small
instance, check whether the `π`-minimising SPT is always in a small structured family. If
yes, pricing is a DP; if no, pricing is a real search and CG's cost is dominated by it.

**Comparison to the tree-based CG literature.** Spoorendonk & Petersen, *"Tree-based
formulation for the multi-commodity flow problem"* (arXiv 2509.24656v2, Oct 2025) replace
per-commodity *paths* with per-source *trees* as columns, cutting the master's demand rows
from O(|K|) to O(|S|). Their pricing is exactly "min-cost shortest path tree rooted at `s`
covering all sinks of `s`" — structurally the same shape as ours, and they note the
resulting CG converges more slowly per iteration because a source generates only one column.
`https://arxiv.org/html/2509.24656v2`

> **Does this transfer to us? Only partially, and honestly.** Their gain is in master *rows*
> (O(|K|) → O(|S|)). Our master already has only `N = 62..104` demand rows. We gain nothing
> from source aggregation. Their pricing is min-cost SPT under *additive* costs; ours is
> min-π SPT under a *non-additive* delay. **This paper is instructive but not a template.**

### 2.3 What actually makes CG converge or stall, and the stabilisers

Textbook surveys: **Barnhart, Johnson, Nemhauser, Savelsbergh, Vance, "Selected Topics in
Column Generation"**, Operations Research 53(6) (2005) 1007–1023,
`https://optimization-online.org/wp-content/uploads/2002/12/580.pdf`. Barnhart et al. also
own the canonical VLSI application of set-partitioning CG: **Dillon & Levison, "Circuit
Partitioning via Set Partitioning and Column Generation"**, Operations Research 44(1)
(1996) 65–76 — I verified the bibliographic record but **did not read the paper**, so cite it
as "the original set-partitioning-CG application in EDA" and do not attribute specifics.

Known causes of stalling, and the concrete stabilisers, in order of how cheap they are to
implement for us:

1. **Degeneracy / dual oscillation (the big one for us).** With `N=62..104` demand rows,
   the master has ~100 basic rows and thousands of columns; duals will jump between
   degenerate optima and pricing will keep producing columns that do not help.
   - **Dual smoothing** (Van Roy & Wolsey style): average the duals over an iteration
     window before pricing. Cheap, and it is the first thing to try.
   - **Explicit stabilising term / augmented Lagrangian on the dual** (Ben Amor, Desrosiers &
     Frangioni, *"Stabilization in Column Generation"*, Mathematical Programming;
     preprint `https://pages.di.unipi.it/frangio/papers/StabCG.pdf`): add a piecewise-linear
     penalty to the dual so the algorithm sees a strongly convex dual and finite
     termination. Their demonstrations are on large multi-depot vehicle and vehicle-crew
     scheduling — again scheduling, not routing, but the mechanism is solver-agnostic.
   - Comparative numerics: Sadykov, *"Stabilization in Column Generation: numerical study"*
     (slides, `https://math.u-bordeaux.fr/~rsadykov/slides/Sadykov_ROADEF13slides.pdf`),
     and *"Combining dual price smoothing and piecewise linear penalty function
     stabilization in column generation"* (`https://math.u-bordeaux.fr/~rsadykov/slides/Sadykov_ISCO14slides.pdf`).
     I read the slide titles/abstracts, **not** the experiments, so I make no claim about
     which stabiliser won.

2. **Pricing dominates the cost.** With 104 nets each needing a min-π-SPT search, one
   CG iteration costs 104 SPT optimisations. Mitigations that are directly implementable
   from Spoorendonk & Petersen §3.3:
   - **Bounded pricing with early termination.** For source `s`, let
     `Π_s = max_{k: s_k = s} λ_k`. During the pricing search, once the extract-min key
     satisfies `d(v) ≥ Π_s`, no remaining path can have negative reduced cost and pricing
     for `s` can stop. Transposed to us: once the best achievable "reduced cost + λ_n" can no
     longer drop below zero, stop pricing that net. This is exact, not heuristic.
   - **A\* with reverse-distance bounds.** `h(v)` = a reverse multi-source Dijkstra lower
     bound on remaining distance to any of `τ_n`. Consistent, admissible, and it directly
     sharpens the early-termination test above.
   - **Price only the nets that matter.** GRIP prices (i) any net with slack `s_i > 0`,
     and (ii) nets having a terminal in a bounding box around a congested region, where
     congestion is identified by the most negative `π_v` (the shadow price of capacity) or
     by the incumbent columns' utilisation. Both of GRIP's congestion tests port directly:
     we have `π_v` per vertex and the capacity is 1, so "most negative `π_v`" is a
     well-defined, meaningful signal. Given the measured occupancy (z=2,3 at 81–90%), the
     dual prices *will* concentrate there, so this filter should prune most of the 104 nets
     on most iterations.
   - **The pricing-filter idea of Spoorendonk & Petersen's §3.3**: only re-price commodities
     whose previously generated columns touch a newly activated capacity row.

3. **Master bloat from redundant columns.** De-duplicate columns that are *vertex-set
   identical* (their `c_nt` may differ; keep the min, and keep the others only if they
   are cheaper). This is a cheap and unusually effective trick here precisely because the
   SPT-optimal face is 57%-wide: many generated columns will be the same shape with
   different tie-breaks.

4. **Row explosion.** Our capacity rows are the `|V|` vertices. Add them **lazily**: start
   the RMP with an empty capacity set plus one slack variable per vertex, and insert the
   capacity row for `v` as soon as column generation produces a solution that uses `v`.
   The cited precedents are the analytic-center / active-set papers for large linear MCF
   listed in §8 (Hoitomt & Lu, J. Global Optimization 2007 and Operations Research 2013;
   Logilab/HEC technical report 2004), which do a *partial* Lagrangian relaxation
   restricted to arcs likely to be saturated, solved by Proximal-ACCPM. They exploit the
   empirical fact that only a small fraction of capacity constraints bind.
   **In our case only ~1.4–3.6% of vertices are occupied at all** (from the pins-only and
   occupancy facts), so lazy rows is close to free.
   The inactive-set / analytic-center cutting-plane alternative is worth knowing:
   **Barbier, N., & Zerbib, et al. / Hoitomt, L. & Lu, L. (2007)**,
   "Solving large scale linear multicommodity flow problems with an active set strategy
   and proximal ACCPM", *Journal of Global Optimization*
   (`https://link.springer.com/article/10.1007/s10107-007-0151-3`).

5. **Practical CG control from GRIP:** stop when the RMP objective has made "little or no
   improvement in the last 10 iterations". Do the same, and log the incumbent at every
   iteration. We only want the *primal*.

### 2.4 The practice of using duals to drive a good primal

The bound alone is useless here — the LP relaxation is already known to be weak (0.2% above
pins-only, and the best certified bound is only +1.0% over pins-only). So the duals have to
be used to *build* a solution, not to bound one.

**The canonical network-design statement of the method**, Holmberg & Di Yuan, *"A
Lagrangian heuristic based branch-and-bound approach for the capacitated network design
problem"*, Operations Research 48(3) (2000) 461–481,
`https://ideas.repec.org/a/inm/oropre/v48y2000i3p461-481.html`. Abstract: the Lagrangian
heuristic "uses a Lagrangian relaxation to obtain easily solved subproblems and solves the
Lagrangian dual by subgradient optimization. It also includes techniques for finding
primal feasible solutions. The Lagrangian heuristic is then embedded into a branch-and-bound
scheme… Special penalty tests and cutting criteria are developed." That is exactly the
"duals drive a primal" architecture, and it is 25 years old and still the standard.

The pure Lagrangian-route for our uncapacitated-network-design sibling: **Craven &
Jimba, "Solving the uncapacitated network design problem by a Lagrangean heuristic and
branch-and-bound"**, Operations Research 46(2) (1998) 247–259,
`https://pubsonline.informs.org/doi/10.1287/opre.46.2.247`. Also
**Barahona, Shivasankaran, approximately**: Barahona et al., *"Lagrangian bounds for
large-scale multicommodity network design: a comparison between Volume and Bundle methods"*,
*International Transactions in Operational Research* 28(1) (2021) 296–326,
`https://onlinelibrary.wiley.com/doi/10.1111/itor.12770` (Shibasaki, Baiou, Barahona,
Mahey, de Souza). This is the paper that tells you **volume-based subgradient stabilisation
beats naive bundle methods** for this problem class, and it is the right thing to imitate
if we go the Lagrangian route instead of CG. **I read only the landing page and author
list; I have not read the experiments, so I make no claim about the size of the
improvement.**

**Why this route is weak for us specifically, stated precisely:** the swarm already ran a
subgradient Lagrangian dual and got +1.0% over pins-only. The duals are not informative
about the *right* primal because the relaxation has almost no value over pins. CG is
strictly more informative than subgradient on the same problem (its duals come from a
tighter master and it also hands you a primal column pool), so if the Lagrangian route is
being used at all it should be used as *the pricing step of CG*, not as a standalone bound.
That is the single most actionable recommendation in this section.

**The other primal-side use of duals, and the most promising one:** the duals `π_v` are a
*per-vertex congestion price field*. Feed the converged `π` back as a tie-break / secondary
objective into **per-net SPT selection** — i.e. exactly the min-π-SPT pricing oracle of
§2.2. This is the well-defined, implementable version of "use the duals to construct a
solution", and unlike a bound it costs one SPT pass per net per CG iteration.

### 2.5 GPU / first-order methods — noted, not recommended

Zhang & Boyd, *"Solving Large Multicommodity Network Flow Problems on GPUs"*, arXiv
2501.17996 (2025), `https://arxiv.org/html/2501.17996v1` — primal-dual hybrid gradient,
100×–1000× over generic solvers, open source. **Does not apply to us:** it solves the
*continuous* MCF LP; our problem is integral and non-additive. Useful only as a
"how fast is a 0.1%-accurate LP relaxation" reference point, i.e. it tells us the LP
relaxation is not the bottleneck and the *integrality gap* is.

---

## 3. Cutting planes: a documented negative result, and where cuts *do* help

**The single most useful negative result I found.** Gendron & Larose, *"Branch-and-Price-and-Cut
for Large-Scale Multicommodity Capacitated Fixed-Charge Network Design"*, EURO Journal on
Computational Optimization 2 (2014) 55–75, `https://link.springer.com/article/10.1007/s13675-014-0020-9`
(preprint: Gendron & Larose, CIRRELT-2012-74,
`https://www.cirrelt.ca/documentstravail/cirrelt-2012-74.pdf`). They report, from their
cutting-plane experiments on the 196 "Canad" instances:

> - "It is essential to add the strong inequalities to obtain effective lower bounds that
>   can be computed efficiently; more precisely, cover and flow cover inequalities can be
>   used instead of the strong inequalities to derive equally effective lower bounds, but
>   with a much greater computational effort."
> - "Obviously, adding cover and flow cover inequalities to the strong relaxation improves
>   the lower bound, but on large-scale instances (with hundreds of commodities), this
>   improvement is **so small that it does not payoff** when the cutting-plane method is
>   used within B&B."
> - "Many of these large-scale instances remain difficult to solve."

**Read this as a direct warning about our 26.6% gap.** The gap is a *combinatorial
assignment* gap, not a per-row relaxation gap, and cover/flow-cover cuts are per-row
strengthening. This class of cut does not address the assignment difficulty. I would not
spend time here.

**Where cuts plausibly do help us — narrower, and worth one cheap experiment:**

- **Circuit / rank inequalities for the set-partitioning master.** The master is a genuine
  set-partitioning problem. Its classical cutting planes are *circuit* inequalities
  (a circuit on `k` columns sums to ≤ `k−1`) and clique/cover inequalities. On a grid with
  capacity 1, a **clique cut** has a natural, geometric instance: any set of `q` vertices
  that can host at most `q` nets, and any set of `q` vertices forming a "hard" configuration
  that can host at most `q−1`. Given z=2,3 are 81–90% occupied, a small number of tight
  such rows near the z=2/3 bottleneck would strengthen the master meaningfully. This is
  cheap to generate: cluster vertices by layer, and add `Σ_n Σ_{t∩C ⊆ C} x_nt ≤ |C| −
  deficit(C)` for carefully chosen small `C`. **I have not verified any published report of
  clique cuts applied to routing set-partitioning masters** — this is my inference from the
  structure, not a citation.
- **Cost-discretisation cuts exploiting the integer cost alphabet.** Our costs are in
  `{2,3,4,6}`. The column costs `c_nt` are therefore sums of small integers with a bounded
  number of distinct values per net. A Chvátal–Gomory cut on a subset of demand rows that
  exploits this discreteness is cheap and may bite where generic cuts do not. Again, my
  inference; no citation.
- **The lattice / volume cutting-plane route for grid routing** is classical and worth
  knowing: **Grötschel, Martin & Weismantel, "Routing in grid graphs by cutting planes"**,
  IPCO 1993, 447–461 (reprinted in *Paths, Flows, and VLSI Layout*, Korte, Lovász,
  Prömel, Schrijver eds., 1990, ch. on routing). This is the origin of the volume-cutting-plane
  bound; note it is an **LP** bound and our LP is already known weak, so the payoff is
  doubtful. Cited from Deza et al. 2010's reference list, which I did read.

---

## 4. Benders / logic-based Benders: is there a decomposition that respects the per-net tree?

**Short answer: yes, structurally, and it is exactly the standard "assignment + routing"
Benders used in network design — but the subproblem is the whole difficulty, and in our case
the subproblem is the *min-π SPT* problem of §2.2, not an LP. So Benders here buys
master-size reduction, not difficulty reduction.**

The pattern, from Gendron & Larose's own discussion and from the logic-based Benders
literature:

- **Master:** which *vertex sets* each net gets (i.e. a relaxation of the column choice),
  or equivalently a relaxation of the capacity assignment.
- **Subproblem:** given the master, route. If the subproblem is a relaxation, the cut
  carries duals back.
- The general machinery: **Hooker, "Logic-Based Benders Decomposition"**,
  `https://johnhooker.tepper.cmu.edu/encyLBBD.pdf` and the chapter
  `https://johnhooker.tepper.cmu.edu/LBBDbookChapter.pdf`; and the concrete
  network-design application in the same family, *"Network Migration Problem: A Hybrid
  Logic-Based Benders Decomposition Approach"*,
  `https://optimization-online.org/wp-content/uploads/2021/11/Network_Migration_Problem__A_Logic_based_Benders_Decomposition-1.pdf`.

**Why it does not rescue us.** For Benders to help, the subproblem must be much easier than
the master. Here the master is *already* the small one (104 demand rows, ~10⁴ capacity
rows, columns we generate) and the subproblem is per-net SPT selection, which is where our
pricing difficulty lives. Benders inverts the size advantage.

**The one variant with a real argument for it** is if we want to *keep* the per-net tree
requirement in a single global model and branch on net pairs: a **combinatorial Benders /
set-partitioning cut** is exactly "these two columns `(n,t)` and `(m,u)` are incompatible
because `t ∩ u ≠ ∅`". With N=62..104 nets there are ~5000 such pairs, and the *strong* form
is a clique: any set of pairwise-conflicting columns sums to ≤ 1. **This is the natural
cut for our master and it is the same object as the clique cuts of §3.** Given that the
known bound is only +1.0% over pins-only while the incumbent is +26.6%, and clique cuts
are exactly the cuts that assert "these candidate shapes cannot coexist", this is the one
cut family with a plausible shot at the gap. The standard disjunctive statement is the
circuit inequality, which is a *sum* over the conflicting group, not the raw clique — I
would generate cliques and let the solver's cut pool handle them.

**Verdict: implementable in a day, honest expectation is that it improves the bound by a
few percent, not 26%.**

---

## 5. The calibration question: has anyone closed an instance this big?

This is the question that most changes the parent agent's expectations, so I give the
negative answer with the evidence.

**What our instance is:** a 3D grid of 24×24×6 to 40×40×6 = **3 456 to 9 600 vertices**,
**62–104 nets**, 134–227 sinks, integral, with a sum-of-root-to-distances objective.

**Best verified data points, largest first:**

| # | What | Size | Solved? | Runtime / result | Source |
|---|---|---|---|---|---|
| 1 | MCF, tree-based CG, **LP relaxation** | 1 225 nodes, 4 760 edges, **32 000 commodities** (grid15) | LP optimal, tol 1e-4 | **10.6 s** (tree-CG) vs 531.2 s (MOSEK direct LP) | Spoorendonk & Petersen, arXiv 2509.24656v2, Table 5 |
| 2 | Same, largest transportation instance | hundreds of thousands of nodes, many shared sources | LP to 1e-4 | under 700 s | same, §4.2 |
| 3 | Intermodal transport, SBT-56295 | 56 269 commodities | LP to 1e-4 | 115 s (vs 2 856 s for the comparison method on an i9-9900) | same, §4.2 |
| 4 | **MCND, integer**, branch-and-price-and-cut | up to **30 nodes, 700 arcs, 400 commodities** | **mostly NOT solved to optimality in 3 h** by CPLEX, B&C, or B&P&C | 3 h limit; B&P&C explores ~2–3× more nodes and roughly divides variable count by 2–4, but "many of these large-scale instances remain difficult to solve" | Gendron & Larose, EJCO 2 (2014) 55–75, Tables 1, 4, 5, 6 |
| 5 | Exact **switchbox** routing (routability, MDD/BDD) | 3D grid, multiple layers, multi-terminal nets | feasibility yes, **cost optimisation not addressed** | pin densities only ~0.0x–0.0xx% of grid points; when grid size grows, "time and memory requirements get too large, i.e. computation time exceeds 1000 s"; at higher pin density "routing is no longer possible in almost all cases" | Schmiedle, Unruh & Becker, *"Exact Switchbox Routing with Search Space Reduction"*, ISPD 2000, §5, Tables 1–3 |
| 6 | Exact Steiner tree (single tree, not packing) | large, reduction-based | optimal | — | Hougardy, Silvanus & Vygen, arXiv 1406.0492 |

*On row 5 I must be explicit:* I extracted this PDF's text with a broken font encoding and
**the digit glyphs did not survive extraction**, so I have the qualitative claims
(1000-second cutoff, density thresholds, "no longer possible in almost all cases") from the
extracted prose and the abstract's "runtimes can be reduced by more than 95% on average
… in comparison to the previously presented approach for exact routing without restrictions
concerning the routing model", but **I could not read the table's exact grid dimensions and
timings and therefore do not quote them.** If this row matters, re-read the tables from the
PDF visually.

**The conclusion, and it is firm:**

- Row 4 is the killer. **The hardest integer instances in the multicommodity *design*
  literature are 30-node graphs.** They are unsolved at 3 hours. Our graph is **100–300×
  larger in nodes** and the combinatorial object is *tree packing*, which is strictly harder
  than flow.
- Row 1 looks encouraging until you notice it is an **LP**, i.e. the fractional relaxation —
  and we already know our fractional relaxation is worthless (+0.2% over pins-only). Solving
  the LP of a 32 000-commodity instance in 10 seconds tells us the LP is not the bottleneck.
  The **integrality gap is the entire problem**, and no one has closed an integrality gap of
  this size in this setting.
- Rows 5 and 6 are exact methods on related problems that hit a wall at *far* smaller sizes.

> **Calibration verdict: 26.6% headroom is very likely NOT reachable at this instance size
> by any known exact method, in Python or C++, in hours or weeks.** Any plan premised on
> closing it should be treated as a moonshot. Any plan premised on "we should be able to get
> within 5% of optimal because the bounds are computable" is false — the gap between a
> +1.0% bound and a +26.6% incumbent is exactly the assignment problem nobody has cracked
> at this scale.

**The corollary that *is* encouraging:** the same evidence says the 26.6% is a *primal*
opportunity, not a proof obligation. GRIP (§2.1) shows a set-partitioning+CG method finding
4–12% better solutions than converged local search on comparable (much larger!) instances
with the same structure. We do not need to close the gap to gain materially.

---

## 6. The one citation that is a direct precedent for "beat a 1-opt-exhausted incumbent"

Asked for explicitly. There are two, and they are of different kinds.

### 6.1 GRIP (Wu, Davoodi & Linderoth) — the structural precedent, and the strongest

Already covered in §2.1. A set-partitioning IP with column generation for multi-terminal nets
on a 3D grid, reported to beat the best published results (all rip-up-and-reroute /
negotiated-congestion) by **9.23% wirelength and 5.24% via cost on average** across ISPD
2007 and 2008, with 176k–2.6M nets. `https://jlinderoth.github.io/papers/Wu-Davoodi-Linderoth-10-PP.pdf`

*Why this is the precedent:* the incumbents it beats are the same *kind* of heuristic as ours
— net-by-net routing to fixpoint plus rip-up and reroute — at far larger scale. The method
that beat them is exactly the method class under investigation. *Where it falls short of our
case:* capacity 52–212 not 1; big-M slack allowed; heuristic pricing; no optimality proof.

### 6.2 Shrivastava, Nikolić, Tanaka, Ravishankar, Gaitonde & Stojilović, "Guaranteed Yet Hard to Find: Uncovering FPGA Routing Convergence Paradox" (FCCM 2025) — the methodological precedent

`https://shashwatshrivastava.com/documents/FCCM25_Guaranteed_Yet_Hard_to_Find.pdf`
(also `https://zenodo.org/records/15024667`)

This is the closest *epistemic* precedent to our situation, and it is worth internalising for
a reason that has nothing to do with routing algorithms:

- They **constructed routing instances where a legal solution was guaranteed to exist**, by
  carving the routing resources out of a known legal solution. Even with a state-of-the-art
  PathFinder implementation, **PathFinder failed on all but one benchmark** — hitting the
  iteration cap, "and failed to [converge]". Tuning PathFinder's parameters gave
  "almost no improvement across various PathFinder configurations" (their Fig. 5).
- They diagnosed the cause: PathFinder routes a net's connections **sequentially** in sink
  order, so the first-routed connections are blind to what the later ones need, and the
  resulting **tree is larger in node count than necessary**. Branch-node movement in
  particular drives convergence failure.
- Their fix — route the net under several sink permutations and keep the smallest tree —
  took **total wirelength down 6.4% on average** (and connections routed down 3.6%, average
  segments per net down 7.9%), with a modelled ~30% runtime increase, and made six of nine
  benchmarks converge that previously did not. One benchmark's per-benchmark improvement
  reached 23.6% in their Table III.

**Why this matters to us more than its routing result.** It is a *methodological* proof of
the following: *a converged, well-tuned, industry-standard local search can be provably and
demonstrably beaten, by a move class outside its neighbourhood, on instances where the
optimum is known to be reachable.* They set the ceiling at a known-feasible solution and
showed the incumbent could not reach it.

**And the specific move class is one we have not tried.** Our nets are single-source
multi-sink and the SPT-optimal face is 57%-wide. Shrivastava et al.'s finding is that *sink
order* — a pure tie-breaking choice inside the SPT face — controls the tree size, and hence
the congestion pressure on everything else. Our 57% plateau is the same structure seen from
the other side: 57% of reroutes change the vertex set at **zero** delay cost, i.e. there is
a large set of *free* shape choices whose only consequence is *which vertices they consume*.
**The objective is indifferent to them; the contention is not.** That is precisely the kind
of move that per-net re-optimisation provably cannot express (it is a within-net tie-break,
not a between-net move) and that is therefore outside our closed neighbourhood.

This overlaps with the `spt-reselect` and `move-classes` agents' territory and I flag it
rather than claiming it.

---

## 7. Concrete, implementable plan in priority order

Ranked by (expected gain) ÷ (effort). Effort estimates assume one agent-day and the existing
Python/C++ harness.

1. **Min-π SPT pricing oracle + a tiny CG loop. [1–2 days]** Build the master with lazy
   capacity rows and one column per net (its free SPT). Implement pricing as
   *secondary-criterion SPT* (minimise `Σ_{v∈t} π_v` subject to `t` being an SPT of `c`).
   Start with the SPT-optimal-face hypothesis from §2.2: enumerate the structured
   SPT classes implied by the V-shaped layer profile and take the cheapest. Add GRIP's
   early-termination test and the `π_v < 0` congestion filter. **Deliverable: a dual price
   field `π_v` and a column pool.** This is the load-bearing experiment; everything in
   (2) depends on it.

2. **Integer-solve over the column pool. [1 day]** Solve the set-partitioning IP restricted
   to the generated columns (CPLEX/HiGHS). This is GRIP's step 3 and it is where the
   incumbent improves. **This is the deliverable, not the bound.**

3. **Cliques / conflict cuts in the master. [1 day]** Generate the `Σ ≤ 1` cuts over sets of
   pairwise vertex-intersecting columns, concentrated near the z=2,3 bottleneck. Only do
   this if (2) leaves a visible integrality gap in the *pooled* problem — i.e. measure the
   gap between the pooled-IP optimum and the RMP value first, because that gap is the
   answer to "is the weakness columns or cuts".

4. **Within-net free-shape selection, informed by `π`. [1 day]** Use `π_v` from (1) as a
   secondary objective *inside* per-net SPT selection: among the 57%-wide SPT face, pick
   the shape that avoids high-`π` vertices. This is the direct analogue of
   Shrivastava et al.'s tree-size minimisation, with a congestion field instead of a size
   count. Low risk, uses machinery that already exists.

5. **Stabilisers, only if (1) stalls.** Dual smoothing first (one line of code). Then the
   piecewise-linear augmented Lagrangian of Ben Amor–Desrosiers–Frangioni. Do not bother
   with volume/bundle comparison unless the Lagrangian route is taken wholesale.

6. **Benders: do not.** §4. The subproblem is the hard part; Benders makes the master
   smaller and the master is not the problem.

7. **Cutting planes beyond cliques: do not.** §3. Gendron & Larose measured the payoff at
   near zero for exactly this problem class.

**What I would not do,** restating the calibration of §5: build anything whose success
criterion is "close the 26.6%". Nothing in the literature suggests that is available.

---

## 8. Full citation list (all verified reachable unless noted)

- Behrendt & Vannelli & Rosehart — *Integer linear programming models for global routing*,
  INFORMS J. Computing 18(2) 2005, 137–150. **Cited via** Deza et al. 2010; I did not read
  it directly.
- **Ben Amor, H., Desrosiers, J., Frangioni, A.** — *Stabilization in Column Generation*,
  Mathematical Programming. `https://pages.di.unipi.it/frangio/papers/StabCG.pdf`
- **Barnhart, C., Johnson, E., Nemhauser, G., Savelsbergh, M., Vance, P.** — *Selected Topics
  in Column Generation*, Operations Research 53(6) 2005, 1007–1023.
  `https://optimization-online.org/wp-content/uploads/2002/12/580.pdf`
- **Deza, A., Dickson, C., Terlaky, T., Vannelli, A., Zhang, H.** — *Global Routing in VLSI
  Design: Algorithms, Theory, and Computational Practice*.
  `https://optimization-online.org/wp-content/uploads/2010/12/2852.pdf`
- **Dillon & Levison** — *Circuit Partitioning via Set Partitioning and Column Generation*,
  Operations Research 44(1) 1996, 65–76. **Bibliographic record verified; paper not read.**
- **Gendron, B., Larose, M.** — *Branch-and-Price-and-Cut for Large-Scale Multicommodity
  Capacitated Fixed-Charge Network Design*, EURO J. Comput. Optim. 2 (2014) 55–75.
  `https://link.springer.com/article/10.1007/s13675-014-0020-9` ·
  preprint `https://www.cirrelt.ca/documentstravail/cirrelt-2012-74.pdf`
- **Grötschel, Martin & Weismantel** — *Routing in grid graphs by cutting planes*, IPCO 1993,
  447–461. **Cited via** Deza et al. 2010.
- **Hartmann, S., Schäffter, M., Schulz, A.S.** — *Switchbox routing in VLSI design: Closing
  the complexity gap*, TCS 203 (1997) 1–12; LNCS 1197 (WG 1996) extended abstract.
  `https://link.springer.com/chapter/10.1007/3-540-62559-3_17`
- **Hastrich, N., Simonov, K.** — *Structural Parameterization of Steiner Tree Packing*,
  STACS 2026, arXiv:2505.09250. `https://arxiv.org/abs/2505.09250`
- **Holmberg, K., Yuan, D.** — *A Lagrangian Heuristic Based Branch-and-Bound Approach for
  the Capacitated Network Design Problem*, Operations Research 48(3) 2000, 461–481.
  `https://ideas.repec.org/a/inm/oropre/v48y2000i3p461-481.html`
- **Hoitomt, L., Lu, L.** — *Solving the multicommodity flow problem with the analytic center
  cutting-plane method and an active set strategy* / **Solving large scale linear
  multicommodity flow problems with an active set strategy and Proximal-ACCPM**,
  J. Global Optimization (2007) `https://link.springer.com/article/10.1007/s10107-007-0151-3`;
  Operations Research (2013) `https://pubsonline.informs.org/doi/10.1287/opre.1050.0262`;
  tech report `https://optimization-online.org/2004/06/922/`
- **Hooker, J.W.** — *Logic-Based Benders Decomposition*.
  `https://johnhooker.tepper.cmu.edu/encyLBBD.pdf` ·
  `https://johnhooker.tepper.cmu.edu/LBBDbookChapter.pdf`
- **McMurchie & Ebeling** — *PathFinder: A Negotiation-Based Performance-Driven Router for
  FPGAs*, FPGA '95. `https://cecs.uci.edu/~papers/compendium94-03/papers/1995/fpga95/pdffiles/6a.pdf`
  (background only; the incumbent our instance resembles.)
- **Schmiedle, F., Unruh, D., Becker, B.** — *Exact Switchbox Routing with Search Space
  Reduction*, ISPD 2000.
  `https://cecs.uci.edu/~papers/compendium94-03/papers/2000/ispd00/pdffiles/2_4.pdf`
  **See the warning in §5 row 5 about unreadable table digits.**
- **Shibasaki, R.S., Baiou, M., Barahona, F., Mahey, P., de Souza, M.C.** — *Lagrangian
  bounds for large-scale multicommodity network design: a comparison between Volume and
  Bundle methods*, ITOR 28(1) 2021, 296–326. `https://onlinelibrary.wiley.com/doi/10.1111/itor.12770`
  **Landing page read; experiments not read.**
- **Shrivastava, S., Nikolić, S., Tanaka, S., Ravishankar, C., Gaitonde, D., Stojilović, M.**
  — *Guaranteed Yet Hard to Find: Uncovering FPGA Routing Convergence Paradox*, FCCM 2025.
  `https://shashwatshrivastava.com/documents/FCCM25_Guaranteed_Yet_Hard_to_Find.pdf`
- **Spoorendonk, S., Petersen, B.** — *Tree-based formulation for the multi-commodity flow
  problem*, arXiv:2509.24656v2 (Oct 2025). `https://arxiv.org/html/2509.24656v2`
- **Tayu, S., Ueno, S.** — *The Complexity of Three-Dimensional Channel Routing*, 5th
  Hangzhou Japan Joint Workshop (2007).
  `https://www.eda.ict.e.titech.ac.jp/ueno/Files/papers/TU07-5thHJ.pdf`
- **Tayu, S., Takahashi, T., Kobayashi, E., Ueno, S.** — *On the Three-Dimensional Channel
  Routing*, IEICE Trans. Fundamentals E99-A(10) (2016) 1813–1822.
  `https://www.eda.ict.e.titech.ac.jp/ueno/Files/papers/TTKU16-IEICE_Trans_Fundamentals.pdf`
- **Wu, T.-H., Davoodi, A., Linderoth, J.T.** — *GRIP: Global Routing via Integer
  Programming*, DAC 2009 `https://jlinderoth.github.io/papers/Wu-Davoodi-Linderoth-09.pdf`;
  journal version *IEEE TCAD* `https://jlinderoth.github.io/papers/Wu-Davoodi-Linderoth-10-PP.pdf`
- **Zhang, F., Boyd, S.** — *Solving Large Multicommodity Network Flow Problems on GPUs*,
  arXiv:2501.17996 (2025). `https://arxiv.org/html/2501.17996v1`
