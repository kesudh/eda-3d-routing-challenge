"""Exact min-cost multicommodity-flow MIP for a window of M3D nets.

Model, objective identity with the checker's sum-of-sink-delays, and the proof
that the candidate-set pruning preserves the true window optimum are documented
in tools/mipwindow.py.  This file is the concrete HiGHS build.
"""
from __future__ import annotations

import os
import sys
import time
from typing import Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import highspy
from m3d.model import Instance
from m3d.grid import Grid

from mipwindow import (RGraph, Vid, dijkstra, multi_source_dijkstra, tree_delay)

INF = highspy.kHighsInf


class WindowMIP:
    """Exact optimum of a window of nets with all other nets frozen.

    We search only for a strictly better window (cost <= UB-1).  If the MIP is
    infeasible, PR#3's assignment of those nets is proven window-optimal.
    """

    def __init__(self, inst: Instance, grid: Grid,
                 routes: Dict[int, List[Tuple[Vid, Vid]]],
                 window: Sequence[int], time_limit: float = 120.0,
                 threads: int = 8, verbose: bool = False,
                 detour: Optional[int] = None):
        self.inst, self.grid, self.routes = inst, grid, routes
        self.win = list(window)
        self.tl, self.threads, self.verbose = time_limit, threads, verbose
        # detour=None -> proof mode: caps provably dominate every improving
        #   solution, so INFEASIBLE is a rigorous proof of window optimality.
        # detour=D   -> search mode: net n may exceed its own shortest-path-tree
        #   cost by at most D.  Much smaller model; an INFEASIBLE answer is then
        #   only a proof of "no better solution within detour budget D".
        self.detour = detour
        self.pv = inst.pin_vertex()
        self.nets = {n.id: n for n in inst.nets}
        self.win_nets = [self.nets[i] for i in self.win]
        self.win_set = set(self.win)
        self.per_net_ub = {i: tree_delay(routes[i], grid, self.nets[i], self.pv)
                           for i in self.win}
        self.ub = sum(self.per_net_ub.values())
        # only solutions strictly better than the incumbent are of interest
        self.target = self.ub - 1
        self.pin_vid = {}
        for n in self.win_nets:
            s = {grid.vid(self.pv[n.driver])}
            s |= {grid.vid(self.pv[k]) for k in n.sinks}
            self.pin_vid[n.id] = s
        self.build_time = 0.0
        self.n_arcs = self.n_rows = self.n_vars = 0
        self.cand: List[List[Tuple[Vid, Vid, int]]] = []
        self.status = "unbuilt"
        self.sol_values = None

    # ------------------------------------------------------------------ #
    def build(self) -> Dict:
        g, inst, routes = self.grid, self.inst, self.routes
        pv = self.pv
        t0 = time.time()

        fixed_v: Set[Vid] = set()
        for nid, es in routes.items():
            if nid in self.win_set:
                continue
            for (u, v) in es:
                fixed_v.add(u); fixed_v.add(v)
        for n in inst.nets:
            if n.id in self.win_set:
                continue
            fixed_v.add(g.vid(pv[n.driver]))
            for s in n.sinks:
                fixed_v.add(g.vid(pv[s]))
        rg = RGraph(g, fixed_v)

        # Candidate arcs per net, pruned to arcs that can lie on a path whose
        # total (driver->sink) delay is within the net's own budget.
        #
        # Safe per-net budget: in any solution of total window cost <= target,
        # net n's own cost is <= target - sum_{m != n} lb(m), where lb(m) is m's
        # own shortest-path-tree cost in the *unconstrained-by-window* graph
        # (a valid lower bound for m regardless of what the other window nets
        # do, since removing vertices can only lengthen m's paths).  So arc
        # (u,v) with A_n(u) + delay(u,v) + B_n(v) > cap_n cannot appear in any
        # improving solution, and dropping it cannot lose the optimum.
        cand: List[List[Tuple[Vid, Vid, int]]] = []
        lbs: List[int] = []
        Ds: List[Tuple[Dict[Vid, int], Dict[Vid, int]]] = []
        for n in self.win_nets:
            drv = g.vid(pv[n.driver])
            sk = [g.vid(pv[k]) for k in n.sinks]
            A = dijkstra(rg, drv)
            B = multi_source_dijkstra(rg, sk)
            for s in sk:
                if s not in A or s not in B:
                    return {"status": "infeasible", "ub": self.ub,
                            "reason": f"net {n.id} disconnected in fixed obstacles"}
            Ds.append((A, B))
            lbs.append(sum(A[s] for s in sk))
        self.lbs = lbs

        for i, n in enumerate(self.win_nets):
            A, B = Ds[i]
            if self.detour is None:
                cap = self.target - (sum(lbs) - lbs[i])
            else:
                cap = lbs[i] + self.detour
            es = []
            for u, du in A.items():
                for v, d in rg.nbrs(u):
                    bv = B.get(v)
                    if bv is None:
                        continue
                    if du + d + bv > cap:
                        continue
                    es.append((u, v, d))
            cand.append(es)
        self.cand = cand
        n_arcs = sum(len(c) for c in cand)
        if n_arcs == 0:
            return {"status": "infeasible", "ub": self.ub, "reason": "empty candidate set"}

        # per-net local vertex indexing
        vidx: List[Dict[Vid, int]] = []
        for i, n in enumerate(self.win_nets):
            d: Dict[Vid, int] = {}
            for (u, v, _x) in cand[i]:
                if u not in d: d[u] = len(d)
                if v not in d: d[v] = len(d)
            for x in self.pin_vid[n.id]:
                if x not in d: d[x] = len(d)
            vidx.append(d)
        allv: List[Vid] = []
        gvid: Dict[Vid, int] = {}
        for d in vidx:
            for x in d:
                if x not in gvid:
                    gvid[x] = len(allv); allv.append(x)
        self.allv, self.gvid, self.vidx = allv, gvid, vidx

        off_z, o = [], 0
        for c in cand: off_z.append(o); o += len(c)
        off_f, o = [], 0
        for c in cand: off_f.append(o); o += len(c)
        off_y, o = [], 0
        for d in vidx: off_y.append(o); o += len(d)
        tot_y = o
        self.off_z, self.off_f, self.off_y = off_z, off_f, off_y
        z0, f0, y0 = 0, n_arcs, 2 * n_arcs
        nv = 2 * n_arcs + tot_y
        self.z0, self.f0, self.y0 = z0, f0, y0

        h = highspy.Highs()
        h.setOptionValue("output_flag", bool(self.verbose))
        h.setOptionValue("threads", self.threads)
        h.setOptionValue("time_limit", self.tl)
        h.setOptionValue("mip_rel_gap", 0.0)
        h.setOptionValue("mip_abs_gap", 0.0)
        self.h = h

        allidx = np.arange(nv, dtype=np.int32)
        h.addVars(nv, np.zeros(nv), np.full(nv, INF))
        cost = np.zeros(nv)
        cost[f0:f0 + n_arcs] = np.array([float(d) for c in cand for (_u, _v, d) in c])
        h.changeColsCost(nv, allidx, cost)
        lo = np.zeros(nv)
        up = np.ones(nv)
        for i, c in enumerate(cand):
            K = len(self.win_nets[i].sinks)
            up[f0 + off_f[i]: f0 + off_f[i] + len(c)] = float(K)
        h.changeColsBounds(nv, allidx, lo, up)
        h.changeColsIntegrality(nv, allidx,
                                np.array([highspy.HighsVarType.kInteger] * nv))

        # -- rows ---------------------------------------------------------- #
        rlo: List[float] = []
        rup: List[float] = []
        starts: List[int] = [0]
        idxs: List[int] = []
        vals: List[float] = []

        def add(lb, ub_, terms):
            rlo.append(lb); rup.append(ub_)
            for c, v in terms:
                idxs.append(c); vals.append(v)
            starts.append(len(idxs))

        self._rows(add, cand, vidx, off_z, off_f, off_y, z0, f0, y0, allv, gvid)
        nrows = len(rlo)
        h.addRows(nrows, np.array(rlo), np.array(rup), len(idxs),
                  np.array(starts, dtype=np.int32),
                  np.array(idxs, dtype=np.int32), np.array(vals))
        self.build_time = time.time() - t0
        self.n_arcs, self.n_rows, self.n_vars = n_arcs, nrows, nv
        return {"status": "built", "ub": self.ub, "target": self.target,
                "n_arcs": n_arcs, "n_rows": nrows, "n_vars": nv,
                "build_s": self.build_time,
                "arcs_per_net": [len(c) for c in cand]}

    # ------------------------------------------------------------------ #
    def _rows(self, add, cand, vidx, off_z, off_f, off_y, z0, f0, y0, allv, gvid):
        """add(lower, upper, [(col, coef), ...]) -- a row is
             lower <= sum coef*x <= upper.
        """
        g = self.grid
        NEG = -highspy.kHighsInf

        # (1) linking: z <= f <= K*z, i.e. 0 <= f - z  and  f - K*z <= 0
        for i, n in enumerate(self.win_nets):
            K = len(n.sinks)
            for a in range(len(cand[i])):
                zc, fc = z0 + off_z[i] + a, f0 + off_f[i] + a
                add(0.0, INF, [(fc, 1.0), (zc, -1.0)])        # f - z >= 0
                add(NEG, 0.0, [(fc, 1.0), (zc, -float(K))])  # f - K*z <= 0

        # (2) flow conservation.
        # The driver supplies K units.  Each of the K sinks must ABSORB one unit,
        # so the constraint at a sink is in - out >= 1, not = 1: a sink may sit
        # on the path to another sink and legitimately transit flow (in=2,
        # out=1).  Since total supply is K and the K sinks absorb at least 1
        # each, every sink absorbs exactly 1 and no circulation can remain, so
        # the flow decomposes into exactly K driver->sink paths.
        for i, n in enumerate(self.win_nets):
            K = len(n.sinks)
            # Row coefficients for "in - out" at each vertex: +1 on each arc's
            # head (it enters), -1 on each arc's tail (it leaves).
            terms_at: Dict[Vid, List[Tuple[int, float]]] = {}
            for a, (u, v, _d) in enumerate(cand[i]):
                fv = f0 + off_f[i] + a
                terms_at.setdefault(u, []).append((fv, -1.0))
                terms_at.setdefault(v, []).append((fv, 1.0))
            sink_v = {g.vid(self.pv[s]) for s in n.sinks}
            drv = g.vid(self.pv[n.driver])
            for vtx, terms in terms_at.items():
                if vtx == drv:
                    add(-float(K), -float(K), terms)   # in - out = -K
                elif vtx in sink_v:
                    add(1.0, INF, terms)               # in - out >= 1
                else:
                    add(0.0, 0.0, terms)               # in - out = 0

        # (3) occupancy: y[n,v] >= z[n,e] for every e incident to v, so a net
        #     marks a vertex as its own exactly when it uses an arc there.
        for i in range(len(self.win_nets)):
            for a, (u, v, _d) in enumerate(cand[i]):
                zc = z0 + off_z[i] + a
                for x in (u, v):
                    add(0.0, INF, [(y0 + off_y[i] + vidx[i][x], 1.0), (zc, -1.0)])

        # (4) vertex capacity (at most one net per 3D vertex) + pin exclusivity
        #     (checker rules 4 and 5).  A net owns a vertex iff it has an
        #     incident arc or a pin there, which is exactly what y tracks.
        for x in allv:
            users = [i for i in range(len(self.win_nets)) if x in vidx[i]]
            if len(users) < 2:
                continue
            pin_users = [i for i in users
                         if x in self.pin_vid[self.win_nets[i].id]]
            if pin_users:
                keep = pin_users[0]
                # y[keep,v] <= 1 and y[i,v] = 0 for the others
                add(NEG, 1.0, [(y0 + off_y[i] + vidx[i][x],
                                 1.0 if i == keep else 0.0) for i in users])
                for i in users:
                    if i == keep:
                        continue
                    terms = [(z0 + off_z[i] + a, 1.0) for a, (u, v, _d)
                             in enumerate(cand[i]) if u == x or v == x]
                    add(NEG, 0.0, terms)
            else:
                add(NEG, 1.0, [(y0 + off_y[i] + vidx[i][x], 1.0) for i in users])

        # (5) total window cost <= target.  Prunes the search, and makes an
        #     infeasible answer a proof that no better assignment exists.
        add(NEG, float(self.target),
            [(f0 + off_f[i] + a, float(d)) for i, c in enumerate(cand)
             for a, (_u, _v, d) in enumerate(c)])

    # ------------------------------------------------------------------ #
    def solve(self) -> Dict:
        h = self.h
        t0 = time.time()
        h.run()
        name = h.modelStatusToString(h.getModelStatus())
        info = h.getInfo()
        self.solve_s = time.time() - t0
        self.status = name
        res = {"ub": self.ub, "lns_cost": self.ub, "raw_status": name,
               "solve_s": self.solve_s, "build_s": self.build_time,
               "n_arcs": self.n_arcs, "n_rows": self.n_rows,
               "n_vars": self.n_vars}
        if name == "Infeasible":
            self.sol_values = None
            res.update(status="infeasible", best_cost=None, proven=True,
                       note="proved: no window assignment of cost <= ub-1 exists")
            return res
        self.sol_values = self.extract()
        if name == "Optimal":
            res.update(status="optimal", proven=True,
                       best_cost=int(round(info.objective_function_value)))
        else:
            obj = float(info.objective_function_value)
            res.update(status="limit", proven=False,
                       best_cost=(int(round(obj))
                                  if (self.sol_values is not None
                                      and obj != float("inf")) else None),
                       mip_gap=getattr(info, "mip_gap", None))
        if res.get("best_cost") is not None:
            res["delta"] = self.ub - res["best_cost"]
            res["gap_pct"] = 100.0 * res["delta"] / self.ub if self.ub else 0.0
        return res

    # ------------------------------------------------------------------ #
    def extract(self) -> Optional[Dict[int, List[Tuple[Vid, Vid]]]]:
        val = list(self.h.getSolution().col_value)
        f0 = self.f0
        routes: Dict[int, List[Tuple[Vid, Vid]]] = {}
        for i, n in enumerate(self.win_nets):
            fb = f0 + self.off_f[i]
            used = set()
            for a, (u, v, _d) in enumerate(self.cand[i]):
                if val[fb + a] > 0.5:
                    used.add((u, v) if u < v else (v, u))
            routes[n.id] = sorted(used)
        return routes

    def refine_routes(self, routes) -> Dict[int, List[Tuple[Vid, Vid]]]:
        """Reduce each net's used-arc set to a BFS tree from the driver.  A
        min-cost flow with positive delays contains no cycle, so this preserves
        the sink delays; applied as a safety net regardless."""
        g, pv = self.grid, self.pv
        out = {}
        for n in self.win_nets:
            adj: Dict[Vid, List[Vid]] = {}
            for (u, v) in routes[n.id]:
                adj.setdefault(u, []).append(v)
                adj.setdefault(v, []).append(u)
            drv = g.vid(pv[n.driver])
            seen, order, tree = {drv}, [drv], []
            qi = 0
            while qi < len(order):
                u = order[qi]; qi += 1
                for v in adj.get(u, ()):
                    if v not in seen:
                        seen.add(v)
                        tree.append((u, v) if u < v else (v, u))
                        order.append(v)
            out[n.id] = tree
        return out
