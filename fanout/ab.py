"""A/B of congestion-pricing policies on the repo's known-converging kernel.

m3d/negotiated.py already certifies legal routings on the hard tier, so it is
the right substrate: the experiment here is purely "which per-vertex price
function", holding the routing kernel fixed. Policies compared:

  plain      : vertex price = history + presence            (repo default)
  fanout     : price x the net's fanout, i.e. the EXACT linear downstream-sink
               marginal applied as a routing heuristic (the brief's ask)
  sinks^-0.5 : PR#3's decaying surrogate, for reference
  outer      : layer price making z=2,3 dear for LOW-fanout nets so they
               escape to the sparse outer layers (z=1,4 ~40% full, z=0,5 ~16%)

The tree kernel is the repo's multi-source SPT grow, so per-net routing is
exact given the obstacle set (established fact #2) and the only thing that
varies between runs is the price.
"""
from __future__ import annotations

import heapq
import os
import time
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from m3d.checker import check
from m3d.model import Instance, NetRoute, Submission

from .dual import Prob


class PricedRouter:
    def __init__(self, inst: Instance, policy: str = "plain",
                 max_iters: int = 60, hist_fac: float = 0.5,
                 pres_fac0: float = 0.5, pres_mult: float = 1.7,
                 outer_pen: float = 0.0, order: str = "hard_first"):
        self.p = Prob(inst)
        self.g = self.p.g
        self.n = self.g.n
        self.policy = policy
        self.max_iters = max_iters
        self.hist_fac = hist_fac
        self.pres_fac0 = pres_fac0
        self.pres_mult = pres_mult
        self.outer_pen = outer_pen
        self.order = order

        self.src = {t[0]: t[1][0] for t in self.p.net_blocked}
        self.sinks = {t[0]: t[2] for t in self.p.net_blocked}
        self.nb = {t[0]: t[3] for t in self.p.net_blocked}
        self.fan = {t[0]: len(t[2]) for t in self.p.net_blocked}
        self.h = [0.0] * self.n
        self.owners_v: Dict[int, Set[int]] = defaultdict(set)
        self.owners_e: Dict[Tuple[int, int], Set[int]] = defaultdict(set)
        self.routes: Dict[int, Tuple[Set[int], Set[Tuple[int, int]]]] = {}
        zl = self.g.zlayer
        self.pen = [0.0] * self.n
        for v in range(self.n):
            z = zl[v]
            self.pen[v] = outer_pen * (1.0 if z in (1, 4) else
                                       (2.0 if z in (2, 3) else 0.25))
        if order == "hard_first":
            self.order_list = [t[0] for t in sorted(
                self.p.net_blocked, key=lambda t: (-len(t[2]), t[0]))]
        else:
            self.order_list = [t[0] for t in self.p.net_blocked]

    # -- price function ----------------------------------------------------- #
    def _scale(self, nid):
        f = self.fan[nid]
        if self.policy == "fanout":
            return float(f)                        # exact linear marginal
        if self.policy == "sinks^-0.5":
            return f ** -0.5                       # PR#3's surrogate
        return 1.0

    # -- routing kernel (repo multi-source SPT grow) ----------------------- #
    def _route_net(self, nid, pres_fac):
        """Return (vertex set, EDGE set).

        Only genuine parent edges are returned. Emitting every adjacency inside
        the vertex set is WRONG: a shortest path to the next sink can run past
        a vertex that an earlier branch already claimed, which adds an extra
        edge and turns the tree into a cycle (the checker then rejects the net
        with "not a tree: V vertices but V edges").
        """
        g, h, ov = self.g, self.h, self.owners_v
        sc = self._scale(nid)
        outer = (self.policy == "outer" and self.outer_pen > 0.0)
        vp = None
        if outer:
            # low-fanout nets get the bigger push outward
            f = 1.0 + 1.0 / max(self.fan[nid], 1)
            vp = [x * f for x in self.pen]
        blocked = self.nb[nid]
        src = self.src[nid]
        tree: Set[int] = {src}
        edges: Set[Tuple[int, int]] = set()
        remaining = set(self.sinks[nid])
        n = self.n
        while remaining:
            dist = [float("inf")] * n
            prev = [-1] * n
            pq = [(0.0, s) for s in tree]
            for s in tree:
                dist[s] = 0.0
            heapq.heapify(pq)
            found = None
            while pq:
                d, u = heapq.heappop(pq)
                if d > dist[u]:
                    continue
                if u in remaining:
                    found = u
                    break
                for v, w in g.nbr[u]:
                    if blocked[v] or v in tree:
                        continue
                    c = sc * (h[v] + pres_fac * len(ov.get(v, ())))
                    if vp is not None:
                        c += vp[v]
                    nd = d + w + c
                    if nd < dist[v]:
                        dist[v] = nd
                        prev[v] = u
                        heapq.heappush(pq, (nd, v))
            if found is None:
                return None
            # walk the parent chain back to the existing tree, adding real edges
            cur = found
            while cur not in tree:
                p = prev[cur]
                if p == -1:
                    return None
                edges.add((cur, p) if cur < p else (p, cur))
                tree.add(cur)
                cur = p
            remaining.discard(found)
        return tree, edges

    def _add(self, nid, t):
        for v in t[0]:
            self.owners_v[v].add(nid)
        for e in t[1]:
            self.owners_e[e].add(nid)
        self.routes[nid] = t

    def _remove(self, nid):
        t = self.routes.pop(nid)
        for v in t[0]:
            s = self.owners_v[v]
            s.discard(nid)
            if not s:
                del self.owners_v[v]
        for e in t[1]:
            s = self.owners_e[e]
            s.discard(nid)
            if not s:
                del self.owners_e[e]

    def run(self):
        pres_fac = self.pres_fac0
        for nid in self.order_list:
            r = self._route_net(nid, pres_fac)
            if r is None:
                return None
            self._add(nid, r)
        for it in range(self.max_iters):
            bad = [v for v, o in self.owners_v.items() if len(o) > 1]
            bade = [e for e, o in self.owners_e.items() if len(o) > 1]
            if not bad and not bade:
                break
            affected = set()
            for v in bad:
                self.h[v] += self.hist_fac * (len(self.owners_v[v]) - 1)
                affected |= self.owners_v[v]
            for e in bade:
                # an edge conflict is always also a vertex conflict (both
                # endpoints are shared), so vertex pricing resolves it too
                affected |= self.owners_e[e]
            pres_fac = min(pres_fac * self.pres_mult, 1e6)
            for nid in self.order_list:
                if nid not in affected:
                    continue
                self._remove(nid)
                r = self._route_net(nid, pres_fac)
                if r is None:
                    return None
                self._add(nid, r)
        if any(len(o) > 1 for o in self.owners_v.values()):
            return None
        if any(len(o) > 1 for o in self.owners_e.values()):
            return None
        return self.routes

    # -- output ------------------------------------------------------------- #
    def submission(self, routes=None):
        routes = routes if routes is not None else self.routes
        g = self.g
        out = []
        for nid, (t, e) in sorted(routes.items()):
            out.append(NetRoute(net=nid,
                                edges=[(g.coord(a), g.coord(b)) for (a, b) in e]))
        return Submission(instance=self.p.inst.name, routes=out)


def run_case(path, policy, outdir=None, **kw):
    inst = Instance.load(path)
    t0 = time.process_time()
    rt = PricedRouter(inst, policy=policy, **kw)
    routes = rt.run()
    cpu = time.process_time() - t0
    if routes is None:
        return None, cpu
    sub = rt.submission(routes)
    r = check(inst, sub)
    if not r.legal:
        return ("ILLEGAL", r.reasons[:2]), cpu
    if outdir:
        os.makedirs(outdir, exist_ok=True)
        sub.save(os.path.join(outdir, f"{inst.name}.sol.json"))
    return r.total_delay, cpu
