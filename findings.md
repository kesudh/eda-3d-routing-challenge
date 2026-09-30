# Escaping a closed 1-opt neighbourhood: what the literature actually offers

**Area.** Q2 only: which move classes provably escape per-net re-optimisation, and
is a plateau-walking method plausible at all.
**Verdict up front.** The move set is closed *because every move evaluated in it
returns to per-net re-optimisation*. That is a statement about the *evaluation
operator*, not about the solution space. The literature says the cure is to change
what a move is allowed to change simultaneously (a **compound / k-exchange move**
that is solved as one subproblem) and — critically — the industry routers that
actually win do not re-optimise the net at all; they do **local topological surgery
on a segment** and score it against a **global** cost. Both are provably outside
1-opt. Details, with the trap flagged, in §4 and §5.

---

## 1. Why the neighbourhood is closed, stated as a general fact

Write the state as a set of per-net routes `r = (r_1 … r_N)` over `G`, with
feasibility `F(r)`. Let `Opt_n(r_{-n})` be the *exact* per-net optimum for net `n`
holding all other nets fixed. Then the operator

```
E(r) = ( Opt_1(r_{-1}), … , Opt_N(r_{-N}) )
```

is a **projection onto the per-net-optimal set**, and `E(E(r)) = E(r)`: the
neighbourhood-closure the swarm proved is exactly the statement that `E` is
idempotent. Any search whose move is "perturb, then apply `E`" can therefore only
ever visit points of the fixed-point set of `E` — a set of 1-opt points. This is
the general shape of a **closed neighbourhood under a repair operator**, the same
object as the "local optimality after repair" that LNS literature assumes for
free.[6] Note the consequence that matters: closure is a property of `E`, so
**no amount of extra randomness, restarts, or accept/reject policy changes
`E`-closedness.** Only replacing `E` does. That is a theorem-shaped statement, and
it is why six agents' 450k-move SA runs all landing on 1-opt is not bad luck.

The vocabulary the literature uses for the cure is *strongly* vs *weakly* local
optimality. The honest summary of what I could verify: in the classical
facility-location and local-search approximation literature the terms are
`1/2`-optimality / `1.5`-optimality / `k`-optimality (a solution is `p`-optimal if
no `p`-optimal local move improves it), and the standard cure for a bad local
optimum guarantee is the *multi-exchange* operation that exchanges several
facilities simultaneously — explicitly "a new local improvement operation … that
possibly exchanges multiple facilities simultaneously", improving the guarantee
from 7.88 to `3+2√2`.[10] I searched for "strongly locally optimal" / "weakly
locally optimal" as formal named solution concepts in this literature and **could
not verify a canonical, citable definition**; the closest verified statements are
the `p`-optimality hierarchy and the `1/2`-vs-`1`-swap distinction (opening,
closing, and swapping one facility versus the `Θ(p)`-approximate swap search).[9]
Treat the strong/weak pair as folklore here, not as a theorem you can cite.

The no-free-lunch structure theorems are only weakly informative for this case.
NFL says performance must be averaged over problem classes;[15] it does not
imply anything *within* one instance about which move class helps. The useful
reading is negative: it blocks the claim that "some metaheuristic must work
here", so the burden of proof is on the move class, not on the search engine.

---

## 2. Move classes that provably escape 1-opt

The key structural fact, which I want to state precisely because it does the
real work: **a move escapes 1-opt iff it can change two nets' routes such that no
single-net re-optimisation of the *intermediate* state would produce the same
state.** Concretely, a compound move that (i) frees the union of resources used
by a set `S` of nets, (ii) re-decides the assignment of *all* of `S` jointly, and
(iii) accepts the joint decision as a unit, produces states that no prefix of
sequential per-net re-optimisation can reach — because any sequential order makes
the *first* net to be re-optimised see the others' old resources still blocked.
That is the formal content of "a 2-commodity transaction is not two sequential
reroutes", and it is exactly the corridor-transaction lead the other agents
raised. It is sound.

### (a) Corridor transactions / joint net-pair exchange — the best-supported lead

Ejection chains are the canonical machinery, and the framing is exact rather than
analogical. Glover's definition: compound sequences of moves "leading from one
solution to another, by linked steps in which changes in selected elements cause
other elements to be 'ejected from' their current state, position or value
assignment", built to "generate a neighborhood of compound moves", with the
explicit aim of generating "moves not available to customary neighborhood search
approaches".[4] The QAP application reports exactly the effect at issue — the
ejection chain neighbourhood grows **multiplicatively** while the effort to find
its best move grows only **additively**, a "combinatorial leverage effect", with
"significant improvement in solution quality … in comparison to the traditional
swap neighborhood".[5]

**Does it apply here?** Partially, with a precise caveat that must not be
dropped. The ejection-chain mechanism is representation-independent: net `n` is
an element with a "position" (its route), and ejecting it frees resources that
the next element can claim. That transfers cleanly. What does **not** transfer is
the *evaluation*: the M3D objective is a sum of root-to-sink delays over nets with
**per-net** (not per-path) vertex capacity, so a chain step has to be scored on
the true sum-of-sink-delays objective, and the chain must terminate in an
*exactly* recomputed joint state rather than a flow proxy. Both are implementable
at `N=62..104`. I flag as `[unverified]` the frequent claim in the routing
literature that ejection chains specifically appear in VLSI global routing — the
survey I read covers move-based heuristics, rip-up/reroute, multicommodity flow
and hierarchical methods in detail,[1] and ejection chains are **not** among the
families it lists for global routing (it lists simulated annealing, simulated
evolution, genetic algorithms, and tabu search).[1] The "Li, Chu, Wong ejection
chain" attribution in the task brief did **not** verify against any source I could
reach; I recommend the parent agent drop it rather than pass it on. The
attributions I *did* verify from the survey's own bibliography are Ting & Tien
1983, Nair 1987, and Sechen & Sangiovanni-Vincentelli 1986 (TimberWolf3.2).

### (b) SA over a non-1-opt state space

This is where Timberwolf matters, and the mechanism is the opposite of what the
brief assumes. The survey describes the package precisely: for each net "a set of
**candidate routing trees** is created … Each move implies a switch from one tree
to another for a net", with the cost being the *global* total overflow, and the
net to change chosen from a cell boundary where overflow exists.[1] The crucial
structural point: Timberwolf's move is a **switch to a precomputed alternative
tree** — it does **not** re-optimise the net. A move is accepted on the global
objective, not on the moving net's own re-optimised delay. So the operator is not
`E`-closed, and SA over it is not a re-parameterisation of the closed search.

**Would it fail here, and why?** Partly for a reason specific to M3D and worth
stating because it is the honest objection: Timberwolf's cost is *overflow*,
which is a **shared, global, saturating** signal. The M3D objective is a
**sum of private per-net delays** with a hard disjointness constraint, so a
net's contribution to the objective is nearly decoupled from everyone else's
once the disjointness constraint is satisfied. Global-overflow SA works because
reducing one net's overflow is *not* locally evaluable — that is exactly what the
"second-order congestion" example in PathFinder is designed to show.[2] In M3D
the coupling is only through the disjointness constraint, so the landscape has
*less* incentive to coordinate and *more* opportunity for the SA to degenerate
into independent single-net hill-climbing. This is a genuine reason Timberwolf
transfers worse here than its reputation suggests, and it is the strongest
argument against simply "anneal the joint assignment".

### (c) Large compound moves / k-exchange

Helsgaun's generalisation of the Lin–Kernighan "k-opt submoves" is the precise
theoretical statement that a *sequence* of restricted improving sub-moves
reaches states outside any fixed-size k-opt neighbourhood.[13] This is the
right citation for "compound moves beat k-exchange", and it is worth being
careful about the direction: LK's power comes from a **variable-depth** walk that
accepts improving sub-moves under a restricted, cheap evaluation and *only then*
inspects the result. That is precisely a mechanism that a flat plateau destroys —
see §4.

### (d) Layer-span (z) restructuring

`[unverified]` I found no citation in the global-routing literature treating
layer-band re-assignment as a discrete move class outside the searched
neighbourhood. Cong et al.'s provably-good bounded-radius construction is a
*single-net* method, and it explicitly says the wire cost using a naive Prim-analogue
"can be an unbounded factor worse than optimal" for one extreme of the
delay/length trade-off.[12] It is not a multi-net move class, and it is not
layer restructuring. **I have no verified support for this lead.** What the
survey does contain is a related, genuinely joint idea: Ting & Tien's *closed
loop* analysis, where a saturated set of boundaries forming a loop can only be
relieved by a net that **crosses the loop twice** — a structural condition
single-crossing nets cannot fix, so the cure is a class of moves selected by a
global combinatorial argument rather than by rerouting.[1] Our contention is
continuous, not loop-structured, so this does not transfer directly; but it is
the best example I found in the literature of a *structurally identified* set of
joint moves, and I cite it as such.

---

## 3. What actually works for global routing (and the one decisive number)

The survey's own bottom line is useful and blunt: for a simple, reasonably
effective approach use rip-up-and-reroute; for hard cases use multicommodity flow;
"Even though there is no completely satisfactory answer to the most basic
congestion-driven global routing problem…".[1]

- **Negotiated congestion (PathFinder).** Each node's cost is
  `c_n = (b_n + h_n)·p_n` — base delay, a **history** term, and a
  present-occupancy term — and nets negotiate by rerouting until no resources are
  shared.[2] The mechanism relevant to us: `h_n` **permanently** raises the cost
  of a chronically contended vertex, which is a *non-myopic* signal that ordinary
  per-net shortest-path rerouting does not carry. This is the single most
  directly transferable idea I found, and it is cheap. But flag honestly: the
  objective it optimises is overflow+delay with a *soft* capacity, whereas M3D
  has **hard** per-net disjointness. It does not apply as-is.
- **Rip-up-and-reroute** is "surprisingly effective and has long been the most
  commonly used global routing method in industry", and is combinable as
  post-processing.[1] Our own reference solution is exactly this, and it is
  already 1-opt-exhausted — so this line is closed to us.
- **The contest result that matters most.** MAIZEROUTER, winner of the ISPD 2007
  Global Routing Contest, "abandons popular algorithms such as
  multicommodity-flow-based techniques, ILP formulations, and congestion-driven
  Steiner tree generation", and instead rests on **edge-based local surgery**:
  *extreme edge shifting*, which relocates one tree edge **arbitrarily far**
  outside the current Steiner topology, "so long as the appropriate routing
  segments are added to connect it to the points of origin (forming a 'C'-shaped
  detour)", and *edge retraction*, its wirelength-reducing counterpart.[3] Zero
  overflow on all ten ISPD'98 instances, 7.5× faster than BoxRouter, 2.02%
  shorter wirelength, 2.92% shorter than FastRoute 2.0.[3]

That is the answer to Q2's fifth question — **a reported case of a global router
beating a 1-opt-exhausted incumbent.** The move class is *not* reroute, *not*
exchange, and *not* a joint solve. It is: take one segment of one net, move it
somewhere far away, and reconnect — accepting a *worse per-net shape* to relieve a
global condition, never re-optimising the net. Note the paper says this explicitly:
the algorithm "focuses only on individual segments … and will not explicitly
attempt to manipulate or re-route the entire tree of any net (as would typically
be done in Rip-up-and-reroute)".[3] This is the escape our closed neighbourhood
forbids by construction, and it is implementable in hours.

---

## 4. Why barrier-crossing fails on this plateau, and whether plateau-walking is plausible

The SA agent's evidence — 57% of single-net reroutes change the vertex set at
**zero** cost, 31–38k uphill moves accepted per case, never landing better — is
the signature of a **flat, large, connected neutral set**, not of a rugged
landscape. Three points from the literature, then a verdict.

**Why SA specifically fails.** The Metropolis rule accepts an uphill move with
probability `e^(-ΔC/T)`, and on a flat plateau with many *neutral* moves, the
"temperature" that matters for crossing a barrier is set by the barrier height,
while the search is spending essentially all its accepted moves traversing
zero-cost moves. A search that accepts 31–38k uphill moves and still never lands
better is not failing to accept moves — it is failing because *every* direction it
can reach is 1-opt. That is not a tuning problem, and more uphill moves would not
help: the reachable set is the fixed-point set of `E`, which is closed (§1). This
is the sharpest available argument that the SA result is structural.

**The standard remedies, and which survive the closedness constraint.**
- *Neutral-network / plateau walking.* VEGAS is built for exactly this
  landscape: its main feature "is to consider the whole evaluated solutions of a
  neutral network rather than the last accepted solution", and it is "designed to
  escape from plateaus based on the evolvability of solutions".[7] NILS, its
  scheduling counterpart, likewise "allows neutral walks to move on the
  plateaus" and finds improving solutions where a classical iterated local
  search does not.[8] This is real, working, and directly on our 57% statistic.
  **Caveat that decides the case:** both papers evaluate on flowshop scheduling
  and NK landscapes — *not* routing, and *not* a sum-of-sink-delays objective with
  hard disjointness. On a symmetric-cost product grid with V-shaped layer
  profiles, a neutral move of one net is a change of *which* equal-cost shortest
  path is used, and the crucial structural point is that these equal-cost paths
  are massively degenerate. If the neutral set of a net is a connected component
  that does not alter its interaction with any other net, walking it changes
  nothing about the optimum. **That is a falsifiable prediction and I recommend
  testing it directly** (§6).
- *Condensation.* The k-SAT condensation transition is the physics-derived
  picture of exactly this: below a critical constraint-density threshold solutions
  form exponentially many clusters, and search gets trapped in one.[14] Whether
  M3D's plateau has that structure is an open empirical question, not a
  literature result.
- *Tabu on the plateau.* Tabu search's answer to plateau cycling is
  **intensification/diversification**: "during an intensification stage the search
  focuses on examining neighbors of elite solutions" while diversification
  "encourages the search process to examine unvisited regions and to generate
  solutions that differ in various significant ways from those seen
  before".[11] The move mechanism is explicitly *not* the ordinary one —
  "neighbors" here has "a broader meaning … by either grafting together
  components of good solution or by using modified evaluation strategies".[11]
  Tabu is therefore **compatible** with a closed neighbourhood only if the tabu
  move is itself outside it; otherwise it just cycles 1-opt points.
- *Population / crossover.* Escape comes from combining components of distinct
  solutions, i.e. from recombination, not from intensification of one
  trajectory. Feasibility-preserving recombination is the hard part here, since
  the joint state must remain vertex-disjoint across all nets.
- *Restarts.* Only useful with genuine diversification; undiversified restarts
  return to the same 1-opt point.

**Is a plateau-walking method plausible at all here?** My honest answer:
**as a way to escape 1-opt, no — the closedness argument in §1 is a proof, not a
preference, and it bounds every method in this family at zero gain. As a way to
reach the *unexplored* part of the neutral set where a different joint assignment
is available, possibly yes, but only conditionally** — specifically, only if the
neutral moves are *interaction-changing*. That is an empirical question and §6
gives the experiment. Literature support for the conditional yes is genuine
(VEGAS/NILS improve on real scheduling instances), so I would not rule it out —
but it is a hypothesis with a cheap test, not a plan.

---

## 5. The trap, stated once so nobody walks into it

For every method above, the objective/constraint mismatch is the same and is
worth writing in one place:

| method | its objective / constraint | M3D's | verdict |
|---|---|---|---|
| PathFinder negotiation | soft congestion penalty, `h_n` history | **hard** per-net vertex disjointness | mechanism transferable, cost function not |
| Timberwolf SA | **global** total overflow | sum of **private** per-net sink delays | the decoupling is why it transfers worse than its reputation |
| Ting & Tien loop moves | loop-structured congestion | continuous contention at z=2,3 | structurally identified, not directly applicable |
| ejection chains (TSP/QAP) | tour adjacency / assignment | vertex-disjoint routing trees | mechanism transfers; the evaluation must be the true sum-of-sink-delays |
| multicommodity flow / LP | fractional flow, per-path capacity | per-**net** capacity | the swarm already found this relaxation weak; do not revisit |
| Cong et al. bounded radius | single-net, total wire cost + radius | multi-net, sum of sink delays | not a multi-net move class |

---

## 6. Two experiments this survey implies, in priority order

1. **The interaction-changing-neutrality test** (decides whether plateau walking
   can pay). Take a 1-opt solution. Enumerate the zero-delay single-net
   reroutes. Partition them by whether the rerouted net's *set of vertices
   adjacent to another net's vertices* changed. If the zero-delay set is
   dominated by moves that preserve every inter-net interaction, then the
   neutral component is dynamically inert and VEGAS/NILS-style walking provably
   cannot help — which would convert the last open plateau hypothesis into a
   closed one. If a meaningful fraction are interaction-changing, there is a real
   neutral corridor to walk and the plateau-walking route becomes live. This
   experiment directly tests the assumption in §4 and is cheap.
2. **C-detour surgery, transplanted from MAIZEROUTER.** Implement
   *extreme-edge-shifting* on the M3D graph: take one tree edge of one net,
   relocate it **outside** its current topology, reconnect with two parallel
   segments, and accept on the **global** sum-of-sink-delays objective. By
   construction this move class is not expressible as a sequence of per-net
   re-optimisations (§2, §3), which is the only kind that can help here given
   the closedness proof. Its M3D-specific cost function is `c(cell) =` congestion
   of `cell` w.r.t. its z-band, with a logistic shape, mirroring the paper's
   incremental `O(l·window)` scan.

I want to be explicit that experiment 1 is the higher-information one: it can
kill the plateau-walking hypothesis cheaply, whereas experiment 2 is a bet that
local segment surgery is the right escape regardless.

---

## Sources

[1] https://people.ece.umn.edu/~sachin/jnl/integration01.pdf
[2] https://cecs.uci.edu/~papers/compendium94-03/papers/1995/fpga95/pdffiles/6a.pdf
[3] https://cecs.uci.edu/~papers/aspdac08/pdf/p226_3A-1.pdf
[4] https://leeds-faculty.colorado.edu/glover/fred%20pubs/266%20-%20TSP%20-%20Ejection%20Chains%20DAM%201996.pdf
[5] http://leeds-faculty.colorado.edu/glover/fred%20pubs/401%20-%20Ejection%20Chain%20for%20QAP%20-%20w%20Cesar%20%26%20Tabitha%20-%20Networks.pdf
[6] https://backend.orbit.dtu.dk/ws/files/5293785/Pisinger.pdf
[7] https://arxiv.org/pdf/1207.4626
[8] https://arxiv.org/pdf/1207.4450
[9] https://arxiv.org/pdf/0809.2554.pdf
[10] https://web.stanford.edu/~yyye/CFLP-MOR2.pdf
[11] https://leeds-faculty.colorado.edu/glover/fred%20pubs/297%20-%20TS%20-%20chapter%20in%20Handbook%20of%20Combinatorial%20Optimization%20V3.pdf
[12] https://www.cs.virginia.edu/~robins/papers/Provably_Good_Performance-Driven_Global_Routing.pdf
[13] https://www2.seas.gwu.edu/~simhaweb/champalg/tsp/papers/Helsgaun2.pdf
[14] https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.APPROX-RANDOM.2016.22
[15] https://www.cs.ubc.ca/~hutter/earg/papers07/00585893.pdf
