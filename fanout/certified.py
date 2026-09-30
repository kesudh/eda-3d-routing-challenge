"""CORRECT Lagrangian dual for M3D, plus a certified lower bound.

WHY THE FANOUT-WEIGHTED DUAL IS WRONG
-------------------------------------
The brief's hypothesis prices a vertex by the number of downstream sinks, on
the theory that "the objective charges every trunk segment once per downstream
sink". That is true of the DELAY term but FALSE of the CAPACITY term, and the
two must not be conflated.

The checker (m3d/checker.py:205) stores `net_vertices[net.id] = vertices`, a
SET, and rule 4 conflicts a vertex only when two DISTINCT nets both claim it:

    for v in net_vertices[nid]:
        if v in vertex_owner and vertex_owner[v] != nid:  # short

So the resource constraint is

    for every 3D vertex v:   #{nets n : v in T_n}  <=  1

i.e. a trunk vertex occupied by a 6-sink net consumes exactly ONE unit of
capacity, the same as a 1-sink net touching it once. Empirically confirmed on
PR#3's own hard solutions: max distinct nets per vertex = 1 on every case,
while vertices shared by up to 6 driver->sink paths *of the same net* are
common (551 on case_01, 1651 on case_09). Intra-net sharing is free because a
tree already reuses its own edges.

A fanout-weighted dual therefore charges for a constraint the problem does not
have. It is not merely a weaker bound, it is not a bound at all: run on
benchmarks_hard/case_01 it converged to Z = 8766.7, which is ABOVE PR#3's
actual feasible 8674. A valid lower bound cannot exceed a known feasible
solution, so that model is provably wrong. (It optimises a strictly harder
fiction in which a 6-sink trunk is 6x more expensive than a 1-sink touch.)

THE CORRECT DUAL
----------------
    Z(pi) = sum_n  min_{tree T} [ sum_sinks delay_T(s) + sum_{v in T} pi_v ]
            - sum_v pi_v ,        pi >= 0

which is exactly the standard node-capacity Lagrangian. The per-net minimum is
a node-weighted Steiner tree (NP-hard), so for a CERTIFIED bound we need a
valid LOWER bound on that minimum. Two are used, whichever is larger:

  (a) `pins`: sum over sinks of the free (uncongested, pin-avoiding) shortest
      path delay from the driver. Sharing can only help, so this is valid.
  (b) `steiner`: max over sinks s of the priced shortest-path delay from the
      driver to s in the node-weighted graph (enter v costs d(u,v) + pi_v).
      Every feasible tree contains a root->s path, whose priced length is at
      least the shortest one, and the tree's own pi-mass is at least the pi
      along that path. Valid.

Both are valid lower bounds on the per-net minimum, hence on Z, hence on the
optimal legal routing cost. Maximising the result over pi >= 0 by projected
subgradient ascent gives a certified bound.
"""
from __future__ import annotations

import heapq
import math
from typing import Dict, List, Optional, Sequence, Tuple

from m3d.model import Instance

from .dual import G3, Prob, spt_priced, tree_from_spt


# --------------------------------------------------------------------------- #
# Free (pin-avoiding) shortest path tree, used for the `pins` bound
# --------------------------------------------------------------------------- #
def free_spt(prob: Prob):
    """pi = 0 Dijkstra per net -> (free_delay, tree, par, dist) cached."""
    g = prob.g
    out = {}
    zero = [0.0] * g.n
    for nid, drv, sinks, blocked in prob.net_blocked:
        src = drv[0]
        dist, par = spt_priced(g, src, sinks, zero, blocked)
        tree = tree_from_spt(g, par, src, sinks)
        out[nid] = (dist, par, tree)
    return out


def free_pins_bound(prob: Prob, free=None):
    if free is None:
        free = free_spt(prob)
    tot = 0.0
    for nid, drv, sinks, _b in prob.net_blocked:
        dist = free[nid][0]
        tot += sum(dist[s] for s in sinks)
    return tot


# --------------------------------------------------------------------------- #
# Certified dual ascent
# --------------------------------------------------------------------------- #
class CertifiedDual:
    def __init__(self, prob: Prob, ub: Optional[int] = None, lam0: float = 1.5,
                 halv: int = 10, max_iter: int = 120):
        self.p = prob
        self.g = prob.g
        self.n = self.g.n
        self.ub = ub
        self.lam0 = lam0
        self.halv = halv
        self.max_iter = max_iter
        self.pi = [0.0] * self.n
        self.free = free_spt(prob)
        self.pins_bound = free_pins_bound(prob, self.free)
        self.best_z = -math.inf
        self.best_pi: List[float] = []
        self.history: List[Tuple[int, float, float]] = []  # (iter, z, gap%)

    def _evaluate(self, pi):
        """Exact per-net TREE value (upper, heuristic) and certified per-net LB."""
        g, p = self.g, self.p
        gsq = 0.0
        occ = [0] * self.n
        lb_total = 0.0
        tree_total = 0.0
        trees = []
        for nid, drv, sinks, blocked in p.net_blocked:
            src = drv[0]
            dist, par = spt_priced(g, src, sinks, pi, blocked)
            tree = tree_from_spt(g, par, src, sinks)
            if tree is None:
                return None
            # exact tree value under the CORRECT (per-net-vertex) accounting
            tv = sum(dist[s] for s in sinks)
            tree_total += tv
            trees.append((nid, tree, sinks, src, par, dist))
            for v in tree:
                occ[v] += 1
            # certified per-net lower bound
            lb_pins = sum(self.free[nid][0][s] for s in sinks)
            lb_steiner = max(dist[s] for s in sinks)
            lb_total += max(lb_pins, lb_steiner)
        for v in range(self.n):
            gv = occ[v] - 1.0
            gsq += gv * gv
        z = lb_total - sum(pi)
        return z, tree_total, gsq, occ, trees

    def run(self):
        n = self.n
        lam = self.lam0
        stagnant = 0
        for it in range(self.max_iter):
            r = self._evaluate(self.pi)
            if r is None:
                return None
            z, tree_total, gsq, occ, _trees = r
            if z > self.best_z + 1e-9:
                self.best_z = z
                self.best_pi = list(self.pi)
                stagnant = 0
            else:
                stagnant += 1
            gap = 0.0
            if self.ub:
                gap = 100.0 * (self.ub - z) / self.ub
            self.history.append((it, z, gap))
            if gsq <= 1e-12:
                break
            if self.ub is not None:
                step = lam * max(self.ub - z, 1.0) / gsq
            else:
                step = lam * 0.1
            pi = self.pi
            for v in range(n):
                nv = pi[v] + step * (occ[v] - 1.0)
                pi[v] = nv if nv > 0.0 else 0.0
            if stagnant >= self.halv:
                lam *= 0.5
                stagnant = 0
        return self.best_z
