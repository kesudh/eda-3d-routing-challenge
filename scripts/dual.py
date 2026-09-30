"""Correct Lagrangian dual bound for M3D routing (vertex-capacity relaxation).

Model
-----
The checker charges, per net n, the tree distance from its driver to each sink
and forbids two DIFFERENT nets from sharing a vertex or edge.  A single net may
reuse its own vertices across its own branches (that is what a Steiner tree is),
so the capacity constraint is *per net*, not per (net, sink) pair.

    OPT = min over vertex-disjoint-across-nets path systems of sum_{n,s} d_{T_n}(s)

Valid relaxation (LP).  For every (net, sink) pair give the unit of flow its own
path variable, and let y[n,v] >= 0 be a "net n uses vertex v" variable:

    min    sum_{n,s} sum_P len(P) * f^s_{n,P}
    s.t.   f^s_{n,P} >= 0,  y[n,v] >= 0
           sum_P f^s_{n,P} = 1                             (one path per sink)
           f^s_{n,v} <= y[n,v]                             (flow implies use)
           sum_n y[n,v] <= 1                               (one net per vertex)

Any legal routing maps to a feasible LP point of the same cost (route each sink
along its tree path, set y=1 on the tree's vertices), so LP_opt <= OPT.  Hence
every value of the dual below is a certified lower bound.

Dual
----
Relax sum_n y[n,v] <= 1 with lam_v >= 0, and f^s_{n,v} <= y[n,v] with
mu^s_{n,v} >= 0.  Minimising over y gives a finite value only when
lam_v >= sum_s mu^s_{n,v} for every net, and the best choice is
lam_v = max_n sum_s mu^s_{n,v} (it only appears as -sum_v lam_v).  Minimising
over f leaves, per (n, s), a shortest path in the graph whose node weights are
mu^s:

    D(mu) = sum_{n,s} minpath_P ( len(P) + sum_{v in P} mu^s_{n,v} )
            - sum_v max_n sum_s mu^s_{n,v}                     mu >= 0

D is concave in mu (min of linear functions, minus a max), D(0) is exactly the
pins-only floor, and every evaluated point is a valid bound.  Maximised by
projected subgradient ascent; the step direction is
    dD/dmu^s_{n,v} = 1[v on the chosen path of (n,s)] - 1[n is argmax at v].
"""
from __future__ import annotations

import heapq
import json
import os
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from m3d.model import Instance  # noqa: E402

INF = float("inf")


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

    def vid(self, x, y, z):
        return (z * self.h + y) * self.w + x


class Pair:
    """One (net, sink) demand: a unit of flow from driver to sink."""
    __slots__ = ("net", "sink", "src", "dst", "idx", "blocked")

    def __init__(self, net, sink, src, dst, idx, blocked):
        self.net = net
        self.sink = sink
        self.src = src
        self.dst = dst
        self.idx = idx            # index into the per-pair price array
        self.blocked = blocked    # other nets' pins are forbidden


class Dual:
    """Evaluator / optimiser for D(mu)."""

    def __init__(self, g: Graph, pairs: List[Pair]):
        self.g = g
        self.pairs = pairs
        self.n = g.n
        self.dist = [0.0] * g.n
        self.stamp = [0] * g.n
        self.pred = [0] * g.n
        self.tick = 0

    def evaluate(self, mu: List[List[float]], want_paths: bool = False):
        """Return D(mu); optionally also the per-pair path-vertex incidences."""
        g, pairs = self.g, self.pairs
        dist, stamp, pred = self.dist, self.stamp, self.pred
        adj = g.adj
        total = 0.0
        paths: List[List[int]] = [] if want_paths else None
        tick = self.tick
        for p in pairs:
            tick += 1
            w = mu[p.idx]
            src = p.src
            dist[src] = 0.0
            stamp[src] = tick
            heap = [(0.0, src)]
            blocked = p.blocked
            while heap:
                d, u = heapq.heappop(heap)
                if d > dist[u] or stamp[u] != tick:
                    continue
                if u == p.dst:
                    break
                for v, c in adj[u]:
                    if v in blocked:
                        continue
                    ndv = d + c + w[v]
                    if stamp[v] != tick:
                        stamp[v] = tick
                        dist[v] = ndv
                        pred[v] = u
                        heapq.heappush(heap, (ndv, v))
                    elif ndv < dist[v]:
                        dist[v] = ndv
                        pred[v] = u
                        heapq.heappush(heap, (ndv, v))
            total += dist[p.dst]
            if want_paths:
                v = p.dst
                chain = []
                while v != src:
                    chain.append(v)
                    v = pred[v]
                paths.append(chain)
        self.tick = tick
        # - sum_v max_n sum_s mu^s_{n,v}
        best = {}
        for p in pairs:
            w = mu[p.idx]
            b = best.get(p.dst)
            cur = best
            for v in ([p.dst] if paths is None else paths[pairs.index(p)]):
                pass
        # recompute lambda properly below
        best = self._lambdas(mu, paths)
        total -= sum(best.values())
        return total, paths

    def _lambdas(self, mu, paths=None):
        """lam_v = max_n sum_s mu^s_{n,v} (over pairs actually on a path)."""
        acc: Dict[int, float] = {}
        if paths is None:
            for p in self.pairs:
                w = mu[p.idx]
                acc[p.dst] = max(acc.get(p.dst, 0.0), w[p.dst])
            return acc
        for p, chain in zip(self.pairs, paths):
            w = mu[p.idx]
            for v in chain:
                a = acc.get(v, 0.0)
                if w[v] > a:
                    acc[v] = w[v]
        return acc


def build(inst: Instance):
    """Pairs = (net, sink) demands with other nets' pins blocked."""
    g = Graph(inst)
    pin_v = inst.pin_vertex()
    v2p = inst.vertex_to_pin()
    p2n = inst.pin_to_net()
    foreign = {p2n[pid] for pid in v2p}
    blocked_by_net = {}
    for net in inst.nets:
        blocked = {g.vid(*v) for v, pid in v2p.items() if p2n[pid] != net.id}
        blocked_by_net[net.id] = blocked
    pairs = []
    for net in inst.nets:
        src = g.vid(*pin_v[net.driver])
        for s in net.sinks:
            pairs.append(Pair(net.id, s, src, g.vid(*pin_v[s]), len(pairs),
                              blocked_by_net[net.id]))
    return g, pairs


def pins_only(du: Dual) -> float:
    return du.evaluate([[0.0] * du.n for _ in du.pairs])[0]


def subgradient(du: Dual, iters: int = 400, alpha0: float = 1.0,
                verbose: bool = False, time_cap: float = None):
    """Projected subgradient ascent on D(mu)."""
    import time
    t0 = time.time()
    n = du.n
    P = len(du.pairs)
    mu = [[0.0] * n for _ in range(P)]
    cur, paths = du.evaluate(mu, want_paths=True)
    best_val, best_mu = cur, [row[:] for row in mu]
    alpha = alpha0
    for it in range(iters):
        # gradient: 1[v on path] - 1[pair's net is the argmax at v]
        acc = {}
        for p, chain in zip(du.pairs, paths):
            w = mu[p.idx]
            for v in chain:
                a = acc.get(v)
                if a is None or w[v] > a[0]:
                    acc[v] = (w[v], p.net)
        grad = [[0.0] * n for _ in range(P)]
        gnorm = 0.0
        for p, chain in zip(du.pairs, paths):
            row = grad[p.idx]
            net = p.net
            for v in chain:
                val = w_owner = 0.0
                top_net = acc[v][1]
                row[v] += 1.0 if net != top_net else 0.0
            for v in range(n):
                if grad[p.idx][v]:
                    gnorm += grad[p.idx][v] ** 2
        if gnorm <= 0:
            break
        step = alpha / (gnorm ** 0.5)
        for p in range(P):
            row, mrow = grad[p], mu[p]
            for v in range(n):
                gv = row[v]
                if gv:
                    nv = mrow[v] + step * gv
                    mrow[v] = nv if nv > 0.0 else 0.0
        cur, paths = du.evaluate(mu, want_paths=True)
        if cur > best_val:
            best_val, best_mu = cur, [row[:] for row in mu]
        alpha *= 0.99
        if verbose and it % 25 == 0:
            print(f"  it {it:4d} D={cur:10.1f} best={best_val:10.1f} "
                  f"|g|={gnorm**0.5:8.1f} t={time.time()-t0:.0f}s", flush=True)
        if time_cap and time.time() - t0 > time_cap:
            break
    return best_val, best_mu


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="benchmarks_hard")
    ap.add_argument("--iters", type=int, default=400)
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
        g, pairs = build(inst)
        du = Dual(g, pairs)
        pin = pins_only(du)
        sp = os.path.join(args.upper, f"{name}.sol.json")
        upper = c["baseline_total"]
        if os.path.exists(sp):
            from m3d.checker import check
            from m3d.model import Submission
            upper = check(inst, Submission.load(sp)).total_delay
        val, mu = subgradient(du, iters=args.iters, alpha0=1.0,
                              verbose=args.verbose, time_cap=args.time_cap)
        print(f"{name}: pins={pin:.0f} bound={val:.1f} upper={upper} "
              f"gap={(upper-val)/upper*100:.2f}%", flush=True)
        out[name] = {"pins_only": pin, "bound": val, "upper": upper}
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        json.dump(out, open(args.out, "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
