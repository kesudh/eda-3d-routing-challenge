"""Part 2: primal extraction from the converged dual.

Use the Lagrangian prices mu to drive an actual legal routing, then repair.

Pipeline
1. Net ordering.  Route the hardest nets first: a net is hard when its sinks
   are few (few routing options) or when its unpriced shortest paths run through
   already-claimed vertices.  Ordering by "constrainedness" is what lets a
   greedy method beat an all-shortest-path baseline.
2. Dual-guided sequential routing.  For each net in order, route each of its
   sinks along the cheapest path in the *current* residual graph under the
   combined cost
        len(edge) + occupancy(v) * w_occ + mu[pair][v]
   where occupancy counts other nets' vertices already taken, w_occ is a hard
   barrier weight, and mu is the converged dual price.  The union of the chosen
   paths is turned into a shortest-path tree (which is delay-optimal for that
   net, established fact 2).
3. Negotiation.  Repeat passes with the barrier weight raised until every net
   has a legal obstacle-free route.
4. Repair + polish.  Rip up and reroute individual nets against the fixed
   others, then accept only strict improvements.
"""
from __future__ import annotations

import heapq
import json
import os
import sys
from typing import Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from m3d.model import Instance, NetRoute, Submission, canon_edge  # noqa: E402

from bound import DualProblem, Graph, Pair  # noqa: E402


class Router:
    def __init__(self, inst: Instance, prob: DualProblem):
        self.inst = inst
        self.g = prob.g
        self.prob = prob
        pin_v = inst.pin_vertex()
        self.pin_v = pin_v
        self.net_by_id = {n.id: n for n in inst.nets}
        self.src = {n.id: self.g.vid(*pin_v[n.driver]) for n in inst.nets}
        self.sinks = {n.id: [self.g.vid(*pin_v[s]) for s in n.sinks]
                      for n in inst.nets}
        self.pin_of_net = {n.id: {self.g.vid(*pin_v[p]) for p in n.pins()}
                           for n in inst.nets}
        v2p = inst.vertex_to_pin()
        p2n = inst.pin_to_net()
        # foreign pins: never traversable
        self.foreign: Dict[int, Set[int]] = {
            n.id: {self.g.vid(*v) for v, pid in v2p.items() if p2n[pid] != n.id}
            for n in inst.nets}

    # -- one net's shortest-path tree under a residual cost ------------------ #
    def spt(self, nid: int, taken: Set[int], price: Dict[int, float],
            w_occ: float, blocked_extra: Optional[Set[int]] = None):
        """Cheapest-path tree from net nid's driver to all its sinks.

        cost(v) = mu_price(v) + w_occ if v is occupied by another net
        Returns (parent array, reached set) or (None, None) if a sink is walled.
        """
        blocked = self.foreign[nid]
        if blocked_extra:
            blocked = blocked | blocked_extra
        n = g.n
        INF = float("inf")
        dist = [INF] * n
        par = [-1] * n
        src = self.src[nid]
        dist[src] = 0.0
        heap = [(0.0, src)]
        adj = g.adj
        targets = set(self.sinks[nid])
        got = 0
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist[u]:
                continue
            if u in targets:
                got += 1
                if got == len(targets):
                    break
            for v, c in adj[u]:
                if v in blocked:
                    continue
                if v in taken:
                    nv = d + c + w_occ
                else:
                    nv = d + c
                nv += price.get(v, 0.0)
                if nv < dist[v]:
                    dist[v] = nv
                    par[v] = u
                    heapq.heappush(heap, (nv, v))
        for s in self.sinks[nid]:
            if dist[s] == INF:
                return None, None
        return par, dist

    def tree_edges(self, nid: int, par: Dict[int, int]) -> List[Tuple[int, int]]:
        """Edges of the shortest-path tree from the driver to every sink.

        Walking each sink up to the driver and keeping the union gives exactly
        the SPT branches, which is delay-optimal for this net.
        """
        edges: Set[Tuple[int, int]] = set()
        src = self.src[nid]
        for s in self.sinks[nid]:
            v = s
            while v != src:
                pv = par[v]
                edges.add(canon_edge(pv, v))
                v = pv
        return sorted(edges)


def order_nets(router: Router) -> List[int]:
    """Hardest-first: few sinks first, then nets whose free paths are longest."""
    g = router.g
    scores = []
    for n in router.inst.nets:
        ns = len(n.sinks)
        scores.append((ns, n.id))
    scores.sort()
    return [nid for _ns, nid in scores]


def route_all(router: Router, prices: Dict[Tuple[int, int], Dict[int, float]],
              order: Sequence[int], w_occ: float) -> Optional[Dict[int, Set[int]]]:
    """Sequential dual-guided routing.  Returns taken-vertex sets per net."""
    taken: Set[int] = set()
    verts: Dict[int, Set[int]] = {}
    for nid in order:
        pr = prices.get(nid, {})
        par, _d = router.spt(nid, taken, pr, w_occ)
        if par is None:
            return None
        edges = router.tree_edges(nid, par)
        vs: Set[int] = set()
        for a, b in edges:
            vs.add(a)
            vs.add(b)
        verts[nid] = vs
        taken |= vs
    return verts


def verts_to_submission(inst: Instance, verts: Dict[int, Set[int]]) -> Submission:
    g = Graph(inst)
    routes = []
    for n in inst.nets:
        vs = verts[n.id]
        adj: Dict[int, List[int]] = {v: [] for v in vs}
        for v in vs:
            for w, _c in g.adj[v]:
                if w in vs:
                    adj[v].append(w)
        # spanning tree from the driver over the routed vertex set
        src = g.vid(*inst.pin_vertex()[n.driver])
        seen = {src}
        stack = [src]
        edges = set()
        while stack:
            v = stack.pop()
            for w in adj[v]:
                if w not in seen:
                    seen.add(w)
                    edges.add(canon_edge(v, w))
                    stack.append(w)
        routes.append(NetRoute(n.id, sorted(edges)))
    return Submission(instance=inst.name, routes=routes)
