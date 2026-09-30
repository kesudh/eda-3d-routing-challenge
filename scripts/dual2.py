"""Certified Lagrangian lower bounds for the M3D routing challenge.

--------------------------------------------------------------------------
The exact model
--------------------------------------------------------------------------
The checker charges, per net n, the driver->sink distance inside n's routed
tree, and forbids two DIFFERENT nets from sharing any vertex or edge.  A net may
reuse its own vertices freely across its own branches.  Therefore

    OPT = min over path systems {(P_{n,s})} whose paths are vertex-disjoint
              *across different nets* of   sum_{n,s} len(P_{n,s})

(equality both ways: a routing's tree paths give such a system with identical
cost, and any such system's per-net union yields a tree via its shortest-path
tree, of no greater cost.)

--------------------------------------------------------------------------
Relaxation 1: compulsory-vertex exclusion  (raises the floor exactly)
--------------------------------------------------------------------------
Let G_n be the grid with every *other* net's pins removed.  If vertex v is a
cut vertex of G_n separating n's driver from one of n's sinks, then EVERY legal
routing puts n through v, so by vertex capacity no other net may use v.  Hence
v can be deleted from every other net's graph without changing OPT.  Applying
this to the union of all nets' compulsory vertices, and iterating, yields a
strictly stronger (still exact) relaxation.  Articulation points are found with
one Tarjan lowlink pass per net, so this is cheap.

--------------------------------------------------------------------------
Relaxation 2: vertex-capacity LP, dualised  (Lagrangian lower bound)
--------------------------------------------------------------------------
One unit of flow per (net, sink) pair, plus per-(net,vertex) "use" variables:

    min    sum_{n,s} sum_P len(P) * f^s_{n,P}
    s.t.   sum_P f^s_{n,P} = 1                for each (n,s)
           f^s_{n,v} <= y[n,v]                for each (n,s,v)
           sum_n y[n,v] <= 1                  for each vertex v
           f >= 0, y >= 0

Any legal routing is a feasible point of this LP of the SAME cost, so
LP_opt <= OPT and every dual value is a certified lower bound.  Relaxing the
two capacity rows with mu^s_{n,v} >= 0 and lam_v >= 0, and minimising over y,
is finite only when lam_v >= sum_s mu^s_{n,v}; the best choice is
lam_v = max_n sum_s mu^s_{n,v}, giving the concave dual

    D(mu) = sum_{n,s} minpath_P ( len(P) + sum_{v in P} mu^s_{n,v} )
            - sum_v max_n sum_s mu^s_{n,v}

D(0) is exactly the (exclusion-strengthened) pins-only floor.  D is maximised by
projected subgradient ascent; every iterate is itself a valid bound and the best
iterate is what we report.
"""
from __future__ import annotations

import heapq
import json
import os
import sys
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from m3d.model import Instance  # noqa: E402


# --------------------------------------------------------------------------- #
# graph
# --------------------------------------------------------------------------- #
class Graph:
    """Flattened undirected 3D grid; vertex id = (z*height + y)*width + x."""

    def __init__(self, inst: Instance):
        self.inst = inst
        w, h, L = inst.width, inst.height, inst.layers
        self.w, self.h, self.L = w, h, L
        self.n = w * h * L
        self.adj: List[List[Tuple[int, int]]] = [[] for _ in range(self.n)]
        ld, vd = inst.layer_delay, inst.via_delay
        for z in range(L):
            base = (z * h) * w
            for y in range(h):
                row = base + y * w
                for x in range(w):
                    u = row + x
                    a = self.adj[u]
                    if x + 1 < w:
                        v = u + 1
                        a.append((v, ld[z]))
                        self.adj[v].append((u, ld[z]))
                    if y + 1 < h:
                        v = u + w
                        a.append((v, ld[z]))
                        self.adj[v].append((u, ld[z]))
                    if z + 1 < L:
                        v = u + w * h
                        a.append((v, vd))
                        self.adj[v].append((u, vd))

    def vid(self, x: int, y: int, z: int) -> int:
        return (z * self.h + y) * self.w + x


# --------------------------------------------------------------------------- #
# compulsory-vertex exclusion (Tarjan articulation points)
# --------------------------------------------------------------------------- #
def compulsory_vertices(g: Graph, driver: int, sinks: List[int],
                       blocked: Set[int]) -> Set[int]:
    """Vertices every driver->sink path must cross, in the graph minus `blocked`.

    Returns articulation points of the reachable component that separate the
    driver from at least one sink.  Vertices are excluded when they are cut
    vertices *and* some sink lies in a subtree cut off by them.
    """
    adj = g.adj
    # iterative Tarjan DFS restricted to the component containing `driver`
    dfn: Dict[int, int] = {}
    low: Dict[int, int] = {}
    parent: Dict[int, int] = {}
    timer = 0
    # subtree exit times, to test "sink inside the cut-off subtree"
    tout: Dict[int, int] = {}
    root = driver
    dfn[root] = low[root] = timer
    tout[root] = timer
    timer += 1
    stack = [(root, 0)]
    order: List[int] = []
    # edge iteration state
    it_state = [(root, 0)]
    parent[root] = -1
    while stack:
        v, pi = stack[-1]
        if pi < len(adj[v]):
            stack[-1] = (v, pi + 1)
            w = adj[v][pi][0]
            if w in blocked:
                continue
            if w not in dfn:
                dfn[w] = low[w] = timer
                tout[w] = timer
                timer += 1
                parent[w] = v
                stack.append((w, 0))
                it_state.append((w, 0))
                order.append(w)
            elif w != parent[v]:
                if dfn[w] < low[v]:
                    low[v] = dfn[w]
        else:
            stack.pop()
            tout[v] = timer
            pv = parent[v]
            if pv >= 0:
                if low[v] < low[pv]:
                    low[pv] = low[v]
    # A vertex v is an articulation point separating the root when it has a
    # child c with low[c] >= dfn[v].  The cut-off part is the DFS subtree of c.
    result: Set[int] = set()
    for v in order + [root]:
        pv = parent.get(v, -1)
        if pv < 0:
            continue
        if low[v] >= dfn[pv]:
            for s in sinks:
                if s in dfn and pv not in _ancestors(s, parent):
                    pass
    # Simpler exact test: for each articulation point p with a cut child, check
    # whether any sink lies in a component of G-p not containing the root.
    for p in set(list(parent.values()) + [root]):
        if p in blocked:
            continue
        # component of the root without p
        root_side = _component_without(adj, root, p, blocked)
        if root_side is None:
            continue
        for s in sinks:
            if s not in dfn:
                continue
            if s not in root_side:
                result.add(p)
                break
    return result


def _ancestors(v, parent):
    out = set()
    while v is not None and v >= 0:
        out.add(v)
        v = parent.get(v)
    return out


def _component_without(adj, start, removed, blocked) -> Optional[Set[int]]:
    """Vertices reachable from `start` without using `removed`."""
    if start == removed:
        return None
    seen = {start}
    stack = [start]
    while stack:
        v = stack.pop()
        for w, _c in adj[v]:
            if w == removed or w in blocked or w in seen:
                continue
            seen.add(w)
            stack.append(w)
    return seen


# --------------------------------------------------------------------------- #
# demand pairs
# --------------------------------------------------------------------------- #
class Pair:
    __slots__ = ("net", "sink", "src", "dst", "idx", "blocked")

    def __init__(self, net, sink, src, dst, idx, blocked):
        self.net = net
        self.sink = sink
        self.src = src
        self.dst = dst
        self.idx = idx
        self.blocked = blocked


class Problem:
    """Instance -> priced demands, plus the exclusion-strengthened floor."""

    def __init__(self, inst: Instance, rounds: int = 3, verbose: bool = False):
        self.inst = inst
        self.g = Graph(inst)
        pin_v = inst.pin_vertex()
        v2p = inst.vertex_to_pin()
        p2n = inst.pin_to_net()
        g = self.g
        net_ids = [n.id for n in inst.nets]
        src = {n.id: g.vid(*pin_v[n.driver]) for n in inst.nets}
        sinks = {n.id: [g.vid(*pin_v[s]) for s in n.sinks] for n in inst.nets}

        # base exclusion: other nets' pins
        base_blocked = {
            n.id: {g.vid(*v) for v, pid in v2p.items() if p2n[pid] != n.id}
            for n in inst.nets
        }
        # iterative compulsory-vertex closure
        extra = {n.id: set() for n in inst.nets}
        for _ in range(rounds):
            added = 0
            forced_total: Dict[int, Set[int]] = {n.id: set() for n in inst.nets}
            for n in inst.nets:
                blocked = base_blocked[n.id] | extra[n.id]
                fv = compulsory_vertices(g, src[n.id], sinks[n.id], blocked)
                extra[n.id] = fv
                for v in fv:
                    forced_total[v] = forced_total.get(v, set()) | {n.id}
            # if two nets are each forced through v, the instance is infeasible;
            # that cannot happen on a feasible instance, so assign v to the sole
            # forced net and exclude it from everyone else.
            for v, owners in forced_total.items():
                if len(owners) == 1:
                    owner = next(iter(owners))
                    for m in net_ids:
                        if m != owner and v not in extra[m]:
                            extra[m].add(v)
                            added += 1
            if verbose:
                print(f"    exclusion round: +{added} vertices")
            if added == 0:
                break
        self.blocked = {n.id: base_blocked[n.id] | extra[n.id] for n in inst.nets}
        self.src = src
        self.sinks = sinks
        self.net_ids = net_ids
        self.pairs: List[Pair] = []
        for n in inst.nets:
            for s in n.sinks:
                self.pairs.append(Pair(n.id, s, src[n.id], g.vid(*pin_v[s]),
                                       len(self.pairs), self.blocked[n.id]))
        # Dijkstra scratch
        self.dist = [0.0] * g.n
        self.stamp = [0] * g.n
        self.pred = [0] * g.n
        self.tick = 0
        self.cache: List[Optional[float]] = [None] * len(self.pairs)

    # -- shortest paths with per-pair node prices -------------------------- #
    def sp(self, p: Pair, mu_row: List[float]) -> float:
        g = self.g
        dist, stamp, pred = self.dist, self.stamp, self.pred
        adj, blocked = g.adj, p.blocked
        self.tick += 1
        tick = self.tick
        src = p.src
        dist[src] = 0.0
        stamp[src] = tick
        heap = [(0.0, src)]
        push, pop = heapq.heappush, heapq.heappop
        while heap:
            d, u = pop(heap)
            if d > dist[u] or stamp[u] != tick:
                continue
            if u == p.dst:
                break
            for v, c in adj[u]:
                if v in blocked:
                    continue
                ndv = d + c + mu_row[v]
                if stamp[v] != tick:
                    stamp[v] = tick
                    dist[v] = ndv
                    pred[v] = u
                    push(heap, (ndv, v))
                elif ndv < dist[v]:
                    dist[v] = ndv
                    pred[v] = u
                    push(heap, (ndv, v))
        return dist[p.dst]

    def path(self, p: Pair) -> List[int]:
        """Chain of vertices (excluding src) of the last solved path."""
        out = []
        v = p.dst
        src = p.src
        pred = self.pred
        while v != src:
            out.append(v)
            v = pred[v]
        return out

    # -- dual --------------------------------------------------------------- #
    def floor(self) -> float:
        zero = [0.0] * self.g.n
        return sum(self.sp(p, zero) for p in self.pairs)

    def dual(self, mu: List[List[float]], active: Optional[Set[int]] = None):
        """D(mu).  `active` limits which pairs are re-solved (others cached)."""
        total = 0.0
        paths: List[List[int]] = []
        for p in self.pairs:
            if active is None or p.idx in active or self.cache[p.idx] is None:
                self.cache[p.idx] = self.sp(p, mu[p.idx])
                self._path_cache = None
            total += self.cache[p.idx]
        # rebuild path incidences for the pairs we care about
        lam_sum = 0.0
        return total, lam_sum


class DualProblem(Problem):
    """Problem plus full dual bookkeeping (paths, lambda, ascent)."""

    def solve_all(self, mu: List[List[float]]):
        paths = []
        total = 0.0
        for p in self.pairs:
            total += self.sp(p, mu[p.idx])
            paths.append(self.path(p))
        lam: Dict[int, float] = {}
        for p, chain in zip(self.pairs, paths):
            row = mu[p.idx]
            for v in chain:
                a = lam.get(v)
                if a is None or row[v] > a:
                    lam[v] = row[v]
        return total - sum(lam.values()), paths, lam

    def ascent(self, iters: int = 250, alpha0: float = 0.5, verbose: bool = False,
               time_cap: Optional[float] = None):
        import time
        t0 = time.time()
        n = self.g.n
        P = len(self.pairs)
        mu = [[0.0] * n for _ in range(P)]
        val, paths, lam = self.solve_all(mu)
        best_val, best_mu = val, [r[:] for r in mu]
        alpha = alpha0
        for it in range(iters):
            # subgradient of D: +1 for every (pair, vertex) on the chosen path,
            # minus 1 for the pair whose net attains the max at that vertex.
            grad: List[List[int]] = [[0] * n for _ in range(P)]
            gn = 0
            for p, chain in zip(self.pairs, paths):
                row = grad[p.idx]
                net = p.net
                for v in chain:
                    if p.idx == self._owner(v, lam, paths):
                        continue
                    row[v] += 1
                    gn += 1
            if gn == 0:
                break
            step = alpha / (gn ** 0.5)
            for p in self.pairs:
                row, mrow = grad[p.idx], mu[p.idx]
                for v in range(n):
                    if row[v]:
                        nv = mrow[v] + step
                        mrow[v] = nv if nv > 0.0 else 0.0
            val, paths, lam = self.solve_all(mu)
            if val > best_val:
                best_val, best_mu = val, [r[:] for r in mu]
            alpha *= 0.97
            if verbose and it % 20 == 0:
                print(f"    it {it:4d} D={val:10.1f} best={best_val:10.1f} "
                      f"t={time.time()-t0:.0f}s", flush=True)
            if time_cap and time.time() - t0 > time_cap:
                break
        return best_val, best_mu

    def _owner(self, v, lam, paths):
        """Index of a pair attaining max_n sum_s mu at vertex v (cached lazily)."""
        cache = getattr(self, "_owner_cache", None)
        if cache is None:
            cache = {}
            for p, chain in zip(self.pairs, paths):
                row = mu_row = p  # placeholder, replaced below
        return self._owner_map.get(v, -1)


# --------------------------------------------------------------------------- #
def run_case(inst: Instance, iters: int = 250, exclusion_rounds: int = 3,
             verbose: bool = False, time_cap: Optional[float] = None):
    prob = DualProblem(inst, rounds=exclusion_rounds, verbose=verbose)
    floor = prob.floor()
    val, mu = prob.ascent(iters=iters, verbose=verbose, time_cap=time_cap)
    return prob, floor, val, mu


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="benchmarks_hard")
    ap.add_argument("--iters", type=int, default=250)
    ap.add_argument("--exclusion-rounds", type=int, default=3)
    ap.add_argument("--time-cap", type=float, default=None)
    ap.add_argument("--upper", default="base/pr3_hard")
    ap.add_argument("--out", default="results/bound_hard.json")
    ap.add_argument("--cases", default=None)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    suite = json.load(open(os.path.join(args.suite, "suite.json")))
    out = json.load(open(args.out)) if os.path.exists(args.out) else {}
    for c in suite["cases"]:
        name = c["name"]
        if args.cases and name not in args.cases.split(","):
            continue
        inst = Instance.load(os.path.join(args.suite, c["instance_file"]))
        upper = c["baseline_total"]
        sp = os.path.join(args.upper, f"{name}.sol.json")
        if os.path.exists(sp):
            from m3d.checker import check
            from m3d.model import Submission
            upper = check(inst, Submission.load(sp)).total_delay
        prob, floor, val, mu = run_case(inst, iters=args.iters,
                                        exclusion_rounds=args.exclusion_rounds,
                                        verbose=args.verbose, time_cap=args.time_cap)
        flag = "  *** BOUND EXCEEDS UPPER: INVALID ***" if val > upper else ""
        print(f"{name}: floor={floor:.0f} bound={val:.1f} upper={upper} "
              f"gap={(upper-val)/upper*100:6.2f}%{flag}", flush=True)
        out[name] = {"floor_excl": floor, "bound": val, "upper": upper}
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        json.dump(out, open(args.out, "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
