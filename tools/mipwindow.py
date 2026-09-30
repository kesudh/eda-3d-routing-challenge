"""Exact MIP window optimisation of nets for the M3D hard tier.

Hypothesis under test: PR#3's window size (8 nets, solved exactly with HiGHS) is
the binding constraint, not exactness. This module builds a *provably exact*
min-cost-flow MIP for a window of nets and solves it to proven optimality.

Exact model (per window)
------------------------
Fixed: every net outside the window keeps PR#3's route. Their edges and vertices
are hard obstacles. Let W = window nets, and UB = PR#3's summed delay over W.

For each net n in W and each directed edge e=(u,v) in a candidate set S_n:
    z[n,e] in {0,1}   net n uses directed edge e
    f[n,e] in Z>=0   integer units of sink-flow carried on e  (0..K_n, K_n=|sinks|)
    y[n,v] in {0,1}   net n occupies vertex v

Constraints:
  (1) flow balance per net: out_f - in_f = 1 at each sink, = -K_n at the
      driver, 0 at any other vertex of net n.  K_n unit flows, one per sink.
  (2) linking:   z[n,e] <= f[n,e] <= K_n * z[n,e]   (a used tree edge carries
      at least one sink's flow)
  (3) occupancy:  y[n,v] >= z[n,e] for every e incident to v
  (4) vertex capacity: sum_n y[n,v] <= 1   (at most one net per 3D vertex)
  (5) edge capacity:   z[n,E] + z[n,rev(E)] <= 1  (at most one net per 3D edge)

Objective:  min sum_{n,e} delay(e) * f[n,e]
  == the checker's sum of sink delays, because the min-cost flow of net n
     decomposes into K_n driver->sink paths, their union is a tree, and each
     tree edge is charged delay(e) once per sink behind it.  All delays are
     positive, so a minimum-cost flow contains no cycle and the union is a
     connected acyclic tree -- a legal route.

Safe candidate-set pruning (makes "proven optimal" a statement about the true
window optimum, not just the restricted one):
  Let A_n(u) = min delay path driver->u and B_n(v) = min delay path
  v->any sink of n, both computed on the graph with *fixed* obstacles only
  (window nets mutually free).  Any legal tree of n that uses directed edge
  (u,v) has total cost >= A_n(u) + delay(u,v) + B_n(v).  Hence, when searching
  only for solutions of cost <= UB-1, an edge with that bound > UB-1 cannot
  appear in any improving solution and may be dropped without losing the
  optimum.  So: if the restricted model's optimum is <= UB-1 it *is* the true
  window optimum; if it is > UB-1, no improvement exists.

This is a genuine multi-commodity integer program -- the objective is a genuine
multicommodity cost, not a relaxation.
"""
from __future__ import annotations

import argparse
import heapq
import json
import os
import subprocess
import sys
import time
from typing import Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import m3d.model as M
from m3d.checker import check
from m3d.grid import Grid, edge_delay

Vid = int  # (z*h + y)*w + x


# --------------------------------------------------------------------------- #
# instance / solution loading
# --------------------------------------------------------------------------- #
def load_instance(case: str) -> M.Instance:
    d = json.load(open(f"benchmarks_hard/{case}.json"))
    return M.Instance.from_dict(d)


def load_pr3(case: str) -> M.Submission:
    txt = subprocess.run(
        ["git", "show", f"pr3:submissions/hard/pathfinder_lns/{case}.sol.json"],
        capture_output=True, text=True, check=True).stdout
    return M.Submission.from_dict(json.loads(txt))


# --------------------------------------------------------------------------- #
# routing graph with obstacles
# --------------------------------------------------------------------------- #
class RGraph:
    """Grid plus a set of blocked vertices; yields (v, delay) arcs."""

    def __init__(self, grid: Grid, blocked: Set[Vid]):
        self.g = grid
        self.blocked = blocked
        self.wh = grid.wh
        self.n = grid.w * grid.h * grid.l

    def nbrs(self, u: Vid) -> List[Tuple[Vid, int]]:
        out = []
        for v, d in self.g.neighbors(u):
            if v not in self.blocked:
                out.append((v, d))
        return out

    def delay(self, u: Vid, v: Vid) -> int:
        return edge_delay(self.g, u, v)


def dijkstra(g: RGraph, src: Vid) -> Dict[Vid, int]:
    dist = {src: 0}
    hq = [(0, src)]
    while hq:
        d, u = heapq.heappop(hq)
        if d > dist.get(u, 1 << 60):
            continue
        for v, w in g.nbrs(u):
            nd = d + w
            if nd < dist.get(v, 1 << 60):
                dist[v] = nd
                heapq.heappush(hq, (nd, v))
    return dist


def multi_source_dijkstra(g: RGraph, srcs: Sequence[Vid]) -> Dict[Vid, int]:
    dist: Dict[Vid, int] = {}
    hq = []
    for s in srcs:
        dist[s] = 0
        heapq.heappush(hq, (0, s))
    while hq:
        d, u = heapq.heappop(hq)
        if d > dist.get(u, 1 << 60):
            continue
        for v, w in g.nbrs(u):
            nd = d + w
            if nd < dist.get(v, 1 << 60):
                dist[v] = nd
                heapq.heappush(hq, (nd, v))
    return dist


# --------------------------------------------------------------------------- #
# solution <-> internal representation
# --------------------------------------------------------------------------- #
def sub_to_routes(sub: M.Submission, grid: Grid) -> Dict[int, List[Tuple[Vid, Vid]]]:
    out = {}
    for r in sub.routes:
        es = []
        for (u, v) in r.edges:
            us, vs = grid.vid(u), grid.vid(v)
            es.append((us, vs) if us < vs else (vs, us))
        out[r.net] = es
    return out


def routes_to_sub(inst: M.Instance, grid: Grid,
                  routes: Dict[int, List[Tuple[Vid, Vid]]]) -> M.Submission:
    rs = []
    for net in inst.nets:
        es = [(tuple(grid.coord(u)), tuple(grid.coord(v)))
              for (u, v) in routes[net.id]]
        rs.append(M.NetRoute(net=net.id, edges=es))
    return M.Submission(instance=inst.name, routes=rs)


def tree_delay(edges: Sequence[Tuple[Vid, Vid]], grid: Grid, net, pv: Dict) -> int:
    """Sum of sink delays of a tree given as edges, via BFS from the driver."""
    adj: Dict[Vid, List[Tuple[Vid, int]]] = {}
    for (u, v) in edges:
        d = edge_delay(grid, u, v)
        adj.setdefault(u, []).append((v, d))
        adj.setdefault(v, []).append((u, d))
    drv = grid.vid(pv[net.driver])
    dist = {drv: 0}
    q = [drv]
    while q:
        nq = []
        for u in q:
            for v, w in adj.get(u, ()):
                if v not in dist:
                    dist[v] = dist[u] + w
                    nq.append(v)
        q = nq
    return sum(dist[grid.vid(pv[s])] for s in net.sinks)


def routes_legal_tree(inst: M.Instance, grid: Grid,
                      routes: Dict[int, List[Tuple[Vid, Vid]]],
                      nets: Sequence[M.Net]) -> Tuple[bool, str]:
    pv = inst.pin_vertex()
    """Cheap local legality screen: connected, acyclic, all pins, no dup verts/edges."""
    seen_v: Dict[Vid, int] = {}
    seen_e: Dict[Tuple[Vid, Vid], int] = {}
    for net in nets:
        es = routes[net.id]
        adj: Dict[Vid, List[Vid]] = {}
        vs = set()
        for (u, v) in es:
            if (u, v) in seen_e:
                return False, f"edge dup net {net.id}"
            seen_e[(u, v)] = net.id
            for x in (u, v):
                if x in seen_v and seen_v[x] != net.id:
                    return False, f"vertex conflict at {grid.coord(x)}"
                seen_v[x] = net.id
            adj.setdefault(u, []).append(v)
            adj.setdefault(v, []).append(u)
            vs.add(u)
            vs.add(v)
        pins = [grid.vid(pv[net.driver])] + [grid.vid(pv[s]) for s in net.sinks]
        for p in pins:
            if p not in vs:
                return False, f"net {net.id} misses pin {grid.coord(p)}"
        # connectivity + acyclicity
        start = pins[0]
        seen = {start}
        st = [start]
        while st:
            u = st.pop()
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    st.append(v)
        if seen != vs:
            return False, f"net {net.id} disconnected"
        if len(es) != len(vs) - 1:
            return False, f"net {net.id} has cycle ({len(es)} edges, {len(vs)} verts)"
    return True, ""
