"""Exact fanout-aware congestion pricing + Lagrangian dual ascent for M3D.

Key theoretical point
---------------------
The objective charges every trunk vertex ONCE PER DOWNSTREAM SINK. For a net
with tree T and driver r, the true marginal congestion usage of vertex v is

    cnt_T(v) = #{sinks s : v lies on the r->s path in T}

so the *exact* congestion cost of a net's tree under per-vertex duals pi is

    sum_v pi_v * cnt_T(v)  =  sum_{sinks s} sum_{v in path(r->s)} pi_v

The right-hand side is a sum of per-sink path costs, each path paying pi_v on
ENTERING v. That makes the per-net Lagrangian subproblem a single-source
shortest-path problem in the node-weighted graph (enter-v cost = d(u,v) +
pi_v), and its optimum is EXACTLY the shortest-path tree:

    * lower bound: for any tree T, each r->s path in T has priced length
      >= D(s) (the Dijkstra distance), so sum_s priced(T,s) >= sum_s D(s);
    * upper bound: the Dijkstra SPT realises priced length exactly D(s) for
      every sink.

So `net_cost_lagrangian` is exact, not a heuristic, and therefore the dual

    Z(pi) = sum_nets sum_sinks D_n(s)  -  sum_v pi_v        (pi >= 0)

is a CERTIFIED lower bound on the optimal legal routing cost, and pi -> cnt
is an exact subgradient. PR#3's `sinks^-0.5` scalar is a crude approximation
of exactly this node-weighted SPT; here it is exact and optimised by dual
ascent.
"""
from __future__ import annotations

import heapq
import math
from typing import Dict, List, Optional, Sequence, Tuple

from m3d.model import Instance


# --------------------------------------------------------------------------- #
# Grid
# --------------------------------------------------------------------------- #
class G3:
    __slots__ = ("w", "h", "l", "wh", "n", "ld", "vd", "nbr", "zlayer")

    def __init__(self, inst: Instance):
        self.w, self.h, self.l = inst.width, inst.height, inst.layers
        self.ld = list(inst.layer_delay)
        self.vd = inst.via_delay
        self.wh = self.w * self.h
        self.n = self.wh * self.l
        w, h, l, ld, vd = self.w, self.h, self.l, self.ld, self.vd
        nbr: List[Tuple[Tuple[int, int], ...]] = []
        zlayer = [0] * self.n
        for z in range(l):
            base = z * self.wh
            zdelay = ld[z]
            for y in range(h):
                row = base + y * w
                for x in range(w):
                    v = row + x
                    zlayer[v] = z
                    a: List[Tuple[int, int]] = []
                    if x + 1 < w:
                        a.append((v + 1, zdelay))
                    if x > 0:
                        a.append((v - 1, zdelay))
                    if y + 1 < h:
                        a.append((v + w, zdelay))
                    if y > 0:
                        a.append((v - w, zdelay))
                    if z + 1 < l:
                        a.append((v + self.wh, vd))
                    if z > 0:
                        a.append((v - self.wh, vd))
                    nbr.append(tuple(a))
        self.nbr = nbr
        self.zlayer = zlayer

    def coord(self, v: int) -> Tuple[int, int, int]:
        z, r = divmod(v, self.wh)
        y, x = divmod(r, self.w)
        return (x, y, z)


# --------------------------------------------------------------------------- #
# Instance wrapper: pins, nets, forbidden vertices
# --------------------------------------------------------------------------- #
class Prob:
    def __init__(self, inst: Instance):
        self.inst = inst
        self.g = G3(inst)
        g = self.g
        self.pin_vid = {}
        for p in inst.pins:
            self.pin_vid[p.id] = (p.z * g.h + p.y) * g.w + p.x
        self.nets: List[Tuple[int, List[int], List[int]]] = []
        for n in inst.nets:
            self.nets.append((n.id, [self.pin_vid[n.driver]],
                              [self.pin_vid[s] for s in n.sinks]))
        # pin vertex -> owning net (checker's rule 5: a route may not pass
        # through a pin of another net)
        self.pin_owner: Dict[int, int] = {}
        for nid, drv, sinks in self.nets:
            for v in [drv[0]] + sinks:
                self.pin_owner[v] = nid
        self.nets_by_id = {nid: (drv, sinks) for nid, drv, sinks in self.nets}
        self.all_pins = sorted(self.pin_owner.keys())
        # per-net blocked mask: every pin that is NOT this net's own pin.
        self.net_blocked: List[Tuple[int, List[int], List[int], bytearray]] = []
        for nid, drv, sinks in self.nets:
            m = bytearray(self.g.n)
            for v, o in self.pin_owner.items():
                if o != nid:
                    m[v] = 1
            self.net_blocked.append((nid, drv, sinks, m))


def spt_priced(g: G3, src: int, targets: Sequence[int], pi: List[float],
               blocked: Optional[bytearray] = None):
    """Dijkstra SPT in the node-weighted graph (enter-v cost = d(u,v) + pi_v).

    Returns (dist, parent) restricted to vertices that can reach a target.
    dist is the exact priced root-path length. Stop as soon as all targets
    settled, but the SPT is exact regardless.
    """
    n = g.n
    INF = float("inf")
    dist = [INF] * n
    par = [-1] * n
    nbr = g.nbr
    tset = set(targets)
    dist[src] = 0.0
    pq = [(0.0, src)]
    left = len(tset)
    while pq and left:
        d, u = heapq.heappop(pq)
        if d > dist[u]:
            continue
        if u in tset:
            left -= 1
            if left == 0:
                break
        for v, w in nbr[u]:
            if blocked is not None and blocked[v]:
                continue
            nd = d + w + pi[v]
            if nd < dist[v]:
                dist[v] = nd
                par[v] = u
                heapq.heappush(pq, (nd, v))
    return dist, par


def tree_from_spt(g: G3, par: List[int], src: int, sinks: Sequence[int]):
    """Union of parent paths src->sink: the exact-optimal SPT pruned to sinks.

    Returns None only if some sink is genuinely unreachable from src.
    """
    tset = set()
    for s in sinks:
        c = s
        while True:
            if c in tset:
                break
            tset.add(c)
            if c == src:
                break
            c = par[c]
            if c == -1:
                return None
    return tset


# --------------------------------------------------------------------------- #
# Dual ascent
# --------------------------------------------------------------------------- #
class DualSolver:
    def __init__(self, prob: Prob, ub: Optional[int] = None,
                 lam0: float = 1.6, halv: int = 12, max_iter: int = 200):
        self.p = prob
        self.g = prob.g
        self.n = self.g.n
        self.ub = ub
        self.lam0 = lam0
        self.halv = halv
        self.max_iter = max_iter
        pi = [0.0] * self.n
        self.pi = pi
        # blocked = pins of other nets
        self.blocked = bytearray(self.n)
        for v, o in prob.pin_owner.items():
            self.blocked[v] = 1
        self.best_z = -math.inf
        self.best_pi: List[float] = []
        self.history: List[Tuple[int, float]] = []

    def _per_net(self, pi):
        """Return (total priced sink cost, cnt array, trees) with exact fanout counts."""
        g, p = self.g, self.p
        cnt = [0] * self.n
        total = 0.0
        trees = []
        for nid, drv, sinks, blocked in p.net_blocked:
            src = drv[0]
            dist, par = spt_priced(g, src, sinks, pi, blocked)
            tset = tree_from_spt(g, par, src, sinks)
            if tset is None:
                return None, None, None
            trees.append((nid, tset, sinks, src, par))
            total += sum(dist[s] for s in sinks)
        # downstream counts from the pruned trees
        for nid, tset, sinks, src, par in trees:
            # walk each sink to root, counting only tree vertices
            for s in sinks:
                c = s
                while c != -1:
                    cnt[c] += 1
                    if c == src:
                        break
                    c = par[c]
        return total, cnt, trees

    def run(self):
        n = self.n
        lam = self.lam0
        stagnant = 0
        for it in range(self.max_iter):
            total, cnt, _ = self._per_net(self.pi)
            if total is None:
                return None
            z = total - sum(self.pi)
            if z > self.best_z + 1e-9:
                self.best_z = z
                self.best_pi = list(self.pi)
                stagnant = 0
            else:
                stagnant += 1
            self.history.append((it, z))
            # subgradient: g_v = cnt(v) - 1
            gsq = 0.0
            gmax = 0.0
            for v in range(n):
                gv = cnt[v] - 1.0
                gsq += gv * gv
                if -gv > gmax:
                    gmax = -gv
            if gsq <= 1e-12:
                break
            # Polyak step toward the known upper bound
            if self.ub is not None:
                gap = max(self.ub - z, 1.0)
                step = lam * gap / gsq
            else:
                step = lam * gmax / (n * gmax + 1.0)
            pi = self.pi
            for v in range(n):
                nv = pi[v] + step * (cnt[v] - 1.0)
                pi[v] = nv if nv > 0.0 else 0.0
            if stagnant >= self.halv:
                lam *= 0.5
                stagnant = 0
        return self.best_z
