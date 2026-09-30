"""Certified Lagrangian lower bounds for the M3D routing challenge.

--------------------------------------------------------------------------
Exact model
--------------------------------------------------------------------------
The checker charges, per net n, the driver->sink distance inside n's routed
tree, and forbids two DIFFERENT nets from sharing any vertex or edge.  A net may
reuse its own vertices freely across its own branches.  Hence

    OPT = min over path systems {(P_{n,s})} whose paths are vertex-disjoint
              *across different nets* of  sum_{n,s} len(P_{n,s})

Equality holds both ways: a routing's tree paths give such a system with
identical cost, and any such system's per-net union contains a shortest-path
tree of no greater cost.

--------------------------------------------------------------------------
Strengthening A: compulsory-vertex exclusion  (raises the floor exactly)
--------------------------------------------------------------------------
Let G_n be the grid with every *other* net's pins removed.  If vertex v is a
cut vertex of G_n separating n's driver from one of n's sinks, then EVERY legal
routing puts net n through v, so by vertex capacity no other net may use v.
Deleting v from every other net's graph therefore preserves OPT exactly.
This is iterated to a fixed point.

--------------------------------------------------------------------------
Strengthening B: vertex-capacity LP, dualised (the Lagrangian bound)
--------------------------------------------------------------------------
One unit of flow per (net, sink) pair plus per-(net,vertex) "use" variables:

    min    sum_{n,s} sum_P len(P) * f^s_{n,P}
    s.t.   sum_P f^s_{n,P} = 1                 for each (n,s)
           f^s_{n,v} <= y[n,v]                 for each (n,s,v)
           sum_n y[n,v] <= 1                   for each vertex v
           f >= 0, y >= 0

Any legal routing is a feasible point of this LP with the SAME cost (route each
sink along its tree path; set y=1 on the tree's vertices), so LP_opt <= OPT and
every dual value is a certified lower bound.  Relaxing the two capacity rows by
mu^s_{n,v} >= 0 and lam_v >= 0 and minimising over y >= 0 is finite only when
lam_v >= sum_s mu^s_{n,v}; since lam enters only as -sum_v lam_v the best choice
is lam_v = max_n sum_s mu^s_{n,v}, giving the concave dual

    D(mu) = sum_{n,s} minpath_P ( len(P) + sum_{v in P} mu^s_{n,v} )
            - sum_v max_n sum_s mu^s_{n,v} ,        mu >= 0

D(0) is exactly the strengthened pins-only floor.  D is concave, so projected
subgradient ascent converges; every iterate is itself a valid bound and the best
iterate is reported.  A subgradient is

    dD/dmu^s_{n,v} = 1[v on the chosen path of (n,s)] - 1[n attains the max at v]
"""
from __future__ import annotations

import heapq
import json
import os
import sys
import time
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from m3d.model import Instance  # noqa: E402


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
# Strengthening A: compulsory vertices
# --------------------------------------------------------------------------- #
def _component_without(adj, start: int, removed: int,
                       blocked: Set[int]) -> Optional[Set[int]]:
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


def compulsory_vertices(g: Graph, driver: int, sinks: List[int],
                       blocked: Set[int]) -> Set[int]:
    """Vertices every driver->sink path crosses, in the graph minus `blocked`.

    Exactly the cut vertices that separate the driver from at least one sink.
    """
    adj = g.adj
    # Tarjan articulation points (iterative, root = driver)
    dfn: Dict[int, int] = {driver: 0}
    low: Dict[int, int] = {driver: 0}
    parent: Dict[int, int] = {driver: -1}
    timer = 1
    stack = [(driver, 0)]
    cut: Set[int] = set()
    while stack:
        v, i = stack[-1]
        if i < len(adj[v]):
            stack[-1] = (v, i + 1)
            w = adj[v][i][0]
            if w in blocked or w == parent[v]:
                continue
            if w in dfn:
                if dfn[w] < low[v]:
                    low[v] = dfn[w]
            else:
                dfn[w] = low[w] = timer
                timer += 1
                parent[w] = v
                stack.append((w, 0))
        else:
            stack.pop()
            pv = parent[v]
            if pv >= 0 and low[v] >= dfn[pv]:
                cut.add(pv)
    if not cut:
        return set()
    reach = [s for s in sinks if s in dfn]
    out: Set[int] = set()
    for v in cut:
        comp = _component_without(adj, driver, v, blocked)
        if comp is None:
            continue
        for s in reach:
            if s not in comp:
                out.add(v)
                break
    # a net's own pins are always available to it
    out -= set(sinks)
    return out


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


class DualProblem:
    """Instance -> priced demands + dual evaluation and ascent."""

    def __init__(self, inst: Instance, rounds: int = 3, verbose: bool = False):
        self.inst = inst
        self.g = Graph(inst)
        g = self.g
        pin_v = inst.pin_vertex()
        v2p = inst.vertex_to_pin()
        p2n = inst.pin_to_net()
        self.net_ids = [n.id for n in inst.nets]
        self.src = {n.id: g.vid(*pin_v[n.driver]) for n in inst.nets}
        sinks = {n.id: [g.vid(*pin_v[s]) for s in n.sinks] for n in inst.nets}

        all_pins = {g.vid(*v) for v in v2p}
        pin_of_net = {n.id: {g.vid(*v) for v, pid in v2p.items()
                             if p2n[pid] == n.id} for n in inst.nets}
        base = {n.id: {g.vid(*v) for v, pid in v2p.items() if p2n[pid] != n.id}
                for n in inst.nets}
        forced = {n.id: set() for n in inst.nets}
        for r in range(rounds):
            owners: Dict[int, Set[int]] = {}
            for n in inst.nets:
                forced[n.id] = compulsory_vertices(
                    g, self.src[n.id], sinks[n.id], base[n.id] | forced[n.id])
                for v in forced[n.id] - pin_of_net[n.id]:
                    owners.setdefault(v, set()).add(n.id)
            added = 0
            for v, own in owners.items():
                if len(own) == 1:      # feasible instance => never >1
                    o = next(iter(own))
                    for m in self.net_ids:
                        if m == o or v in forced[m]:
                            continue
                        # a net always keeps its own pins
                        if v in pin_of_net[m]:
                            continue
                        forced[m].add(v)
                        added += 1
            if verbose:
                print(f"    exclusion round {r}: +{added} vertices", flush=True)
            if added == 0:
                break
        self.blocked = {n.id: base[n.id] | forced[n.id] for n in inst.nets}
        self.forced = forced

        self.pairs: List[Pair] = []
        for n in inst.nets:
            for s in n.sinks:
                self.pairs.append(Pair(n.id, s, self.src[n.id],
                                       g.vid(*pin_v[s]), len(self.pairs),
                                       self.blocked[n.id]))
        self.nets_of_pair: Dict[int, List[int]] = {}
        for p in self.pairs:
            self.nets_of_pair.setdefault(p.net, []).append(p.idx)

        # Dijkstra scratch
        self.dist = [0.0] * g.n
        self.stamp = [0] * g.n
        self.pred = [0] * g.n
        self.tick = 0
        self.sp_cache: List[float] = [0.0] * len(self.pairs)
        self.solved: Set[int] = set()

    # -- shortest paths with per-pair node prices -------------------------- #
    def sp_sparse(self, p: Pair, mu_row: Dict[int, float]) -> float:
        dist, stamp, pred = self.dist, self.stamp, self.pred
        adj, blocked = self.g.adj, p.blocked
        self.tick += 1
        tick = self.tick
        src, dst = p.src, p.dst
        dist[src] = 0.0
        stamp[src] = tick
        heap = [(0.0, src)]
        push, pop = heapq.heappush, heapq.heappop
        while heap:
            d, u = pop(heap)
            if d > dist[u] or stamp[u] != tick:
                continue
            if u == dst:
                break
            for v, c in adj[u]:
                if v in blocked:
                    continue
                ndv = d + c + mu_row.get(v, 0.0)
                if stamp[v] != tick:
                    stamp[v] = tick
                    dist[v] = ndv
                    pred[v] = u
                    push(heap, (ndv, v))
                elif ndv < dist[v]:
                    dist[v] = ndv
                    pred[v] = u
                    push(heap, (ndv, v))
        return dist[dst]

    def path_of(self, p: Pair) -> List[int]:
        out: List[int] = []
        v, src = p.dst, p.src
        pred = self.pred
        while v != src:
            out.append(v)
            v = pred[v]
        return out

    # -- dual --------------------------------------------------------------- #
    def floor(self) -> float:
        return sum(self.sp_sparse(p, {}) for p in self.pairs)

    def solve_all(self, mu: List[Dict[int, float]], dirty: Optional[Set[int]] = None):
        """Return (D(mu), paths, lam_owner).

        mu rows are SPARSE dicts {vertex: price}.  A pair with an all-zero row
        has the unpriced shortest path forever, so it is solved once and then
        cached; only priced pairs are re-solved each iteration.  This is what
        makes a few hundred ascent iterations affordable.
        """
        paths: List[List[int]] = []
        total = 0.0
        for p in self.pairs:
            row = mu[p.idx]
            if row or p.idx not in self.solved:
                self.sp_cache[p.idx] = self.sp_sparse(p, row)
                self.solved.add(p.idx)
            total += self.sp_cache[p.idx]
            paths.append(self.path_of(p))
        # lam_v = max over nets n of (sum of mu[p][v] over that net's pairs
        # whose chosen path contains v).  owner[v] is the argmax net.
        per_net: Dict[int, Dict[int, float]] = {}
        for p in self.pairs:
            row = mu[p.idx]
            if not row:
                continue
            d = per_net.setdefault(p.net, {})
            for v in row:
                if v in paths[p.idx]:
                    d[v] = d.get(v, 0.0) + row[v]
        lam_best: Dict[int, float] = {}
        owner: Dict[int, int] = {}
        lam_sum = 0.0
        for nid, d in per_net.items():
            for v, s_nv in d.items():
                if s_nv > lam_best.get(v, -1.0):
                    lam_best[v] = s_nv
                    owner[v] = nid
        for v, b in lam_best.items():
            lam_sum += b
        return total - lam_sum, paths, owner

    def ascent(self, iters: int = 250, alpha0: float = 1.0,
               verbose: bool = False, time_cap: Optional[float] = None):
        """Projected subgradient ascent on the concave D(mu).

        Only vertices that appear on some priced shortest path can ever carry a
        positive price, so mu stays sparse and every iterate is a valid bound.
        """
        t0 = time.time()
        P = len(self.pairs)
        mu: List[Dict[int, float]] = [{} for _ in range(P)]
        val, paths, owner = self.solve_all(mu)
        best_val, best_mu = val, [dict(r) for r in mu]
        alpha = alpha0
        for it in range(iters):
            grad: Dict[int, Dict[int, int]] = {}
            gn = 0
            for p in self.pairs:
                row = grad.setdefault(p.idx, {})
                net = p.net
                for v in paths[p.idx]:
                    if owner.get(v) == net:
                        continue
                    row[v] = row.get(v, 0) + 1
                    gn += 1
            if gn == 0:
                break
            step = alpha / (gn ** 0.5)
            for idx, row in grad.items():
                m = mu[idx]
                for v, gv in row.items():
                    nv = m.get(v, 0.0) + step * gv
                    if nv > 0.0:
                        m[v] = nv
                    else:
                        m.pop(v, None)
            val, paths, owner = self.solve_all(mu)
            if val > best_val:
                best_val, best_mu = val, [dict(r) for r in mu]
            alpha *= 0.97
            if verbose and it % 20 == 0:
                sup = sum(len(r) for r in mu)
                print(f"    it {it:4d} D={val:10.1f} best={best_val:10.1f} "
                      f"support={sup} t={time.time()-t0:.0f}s", flush=True)
            if time_cap and time.time() - t0 > time_cap:
                break
        return best_val, best_mu


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
        t0 = time.time()
        prob, floor, val, mu = run_case(
            inst, iters=args.iters, exclusion_rounds=args.exclusion_rounds,
            verbose=args.verbose, time_cap=args.time_cap)
        flag = "  *** BOUND > UPPER: INVALID ***" if val > upper else ""
        print(f"{name}: floor={floor:.0f} bound={val:.1f} upper={upper} "
              f"gap={(upper-val)/upper*100:6.2f}%{flag}  "
              f"[{time.time()-t0:.0f}s]", flush=True)
        out[name] = {"floor_excl": floor, "bound": val, "upper": upper}
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        json.dump(out, open(args.out, "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
