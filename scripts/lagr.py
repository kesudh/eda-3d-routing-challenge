"""Lagrangian / LP-dual lower bound for M3D routing (vertex-capacity relaxation).

Formulation (exactly matching the challenge objective and the checker's legality
rules):

  For every (net n, sink s) pair the checker's delay is the tree distance from
  n's driver to s, so

      OPT  =  min over legal routings of  sum_{n,s} delay(driver_n -> sink_s)

  A legal routing gives, for each (n,s), a path inside n's tree; the tree's
  distance is <= that path's length, and the union of the shortest-path-tree
  branches reproduces the tree distances. Hence OPT is *identical* to

      OPT = min over path systems {(P_{n,s})} whose paths are pairwise
            vertex-disjoint across different nets, of sum_{n,s} len(P_{n,s})

  Relaxing "pairwise vertex-disjoint" to "sum of (n,s) paths through v <= 1" for
  every vertex v gives an LP whose dual is

      D(lambda) = sum_{n,s} min over paths P ( len(P) + sum_{v in P} lam_v )
                  - sum_v lam_v ,     lam >= 0                (nodes priced)

  which is a *valid lower bound* on OPT for every lam >= 0 (weak duality), and
  equals the pins-only bound at lam = 0.  The relaxation additionally honours
  the "no routing through another net's pin" rule, which makes it strictly
  stronger than the plain flow LP.
"""
from __future__ import annotations

import heapq
import json
import os
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from m3d.model import Instance  # noqa: E402


class Graph:
    """Flattened 3D grid: vertex id = (z*height + y)*width + x."""

    def __init__(self, inst: Instance):
        self.inst = inst
        w, h, L = inst.width, inst.height, inst.layers
        self.w, self.h, self.L = w, h, L
        self.n = w * h * L
        self.adj: List[List[Tuple[int, int]]] = [[] for _ in range(self.n)]
        ld = inst.layer_delay
        vd = inst.via_delay
        for z in range(L):
            base = (z * h) * w
            for y in range(h):
                for x in range(w):
                    u = base + y * w + x
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

    def xyz(self, v: int):
        x = v % self.w
        y = (v // self.w) % self.h
        z = v // (self.w * self.h)
        return (x, y, z)


class NetData:
    __slots__ = ("nid", "driver", "sinks", "blocked", "nblocked", "targets")

    def __init__(self, nid, driver, sinks, blocked):
        self.nid = nid
        self.driver = driver
        self.sinks = sinks
        self.blocked = blocked      # set of vertex ids forbidden (other nets' pins)
        self.nblocked = blocked     # same object, alias kept for clarity
        self.targets = set(sinks)


class Solver:
    """Array-based repeated Dijkstra over the whole grid, one source per net.

    Keeps a stamped distance array so no per-iteration allocation is needed.
    """

    def __init__(self, g: Graph, nets: List[NetData]):
        self.g = g
        self.nets = nets
        n = g.n
        self.dist = [0.0] * n
        self.stamp = [0] * n
        self.pred = [0] * n
        self.tick = 0
        # flatten adjacency into CSR-ish lists of (nbr, cost)
        self.adj = g.adj
        self.INF = 1e30

    def solve(self, lam: List[float], want_loads: bool):
        g = self.g
        nets = self.nets
        dist = self.dist
        stamp = self.stamp
        pred = self.pred
        adj = self.adj
        loads = [0] * g.n if want_loads else None
        total = 0.0
        push, pop = heapq.heappush, heapq.heappop
        tick = self.tick
        for nd in nets:
            tick += 1
            src = nd.driver
            dstamp = stamp
            dist[src] = lam[src]
            stamp[src] = tick
            heap = [(lam[src], src)]
            blocked = nd.blocked
            targets = nd.targets
            nleft = len(targets)
            while heap and nleft:
                d, u = pop(heap)
                if d > dist[u] or stamp[u] != tick:
                    continue
                if u in targets:
                    nleft -= 1
                    if not nleft:
                        break
                for v, c in adj[u]:
                    if v in blocked:
                        continue
                    ndv = d + c + lam[v]
                    if stamp[v] != tick:
                        stamp[v] = tick
                        dist[v] = ndv
                        pred[v] = u
                        push(heap, (ndv, v))
                    elif ndv < dist[v]:
                        dist[v] = ndv
                        pred[v] = u
                        push(heap, (ndv, v))
            for s in nd.sinks:
                total += dist[s]
            if want_loads:
                for s in nd.sinks:
                    v = s
                    while v != src:
                        loads[v] += 1
                        v = pred[v]
        self.tick = tick
        total -= sum(lam)
        return total, loads


def build(inst: Instance) -> Tuple[Graph, List[NetData]]:
    g = Graph(inst)
    pin_v = inst.pin_vertex()
    v2p = inst.vertex_to_pin()
    p2n = inst.pin_to_net()
    nets = []
    for net in inst.nets:
        own = {pin_v[p] for p in net.pins()}
        blocked = set()
        for v, pid in v2p.items():
            if p2n[pid] != net.id:
                blocked.add(g.vid(*v))
        nets.append(NetData(net.id, g.vid(*pin_v[net.driver]),
                            [g.vid(*pin_v[s]) for s in net.sinks], blocked))
    return g, nets


INF = float("inf")


def pins_only(sv: Solver) -> float:
    """D(0): the shortest-path (pins-only) floor."""
    return sv.solve([0.0] * sv.g.n, False)[0]


def subgradient_ascent(sv: Solver, upper: float, iters: int = 300,
                       alpha0: float = 2.0, verbose: bool = False,
                       lam0: List[float] = None, time_cap: float = None,
                       decay: float = 0.995):
    """Polyak subgradient ascent on the vertex-capacity multipliers.

    D(lambda) is concave piecewise-linear in lambda, so a projected
    subgradient step with the Polyak step size (upper - D) / |g|^2 ascends it.
    Every iterate is itself a certified lower bound; we keep the best.
    """
    import time
    g = sv.g
    t_start = time.time()
    lam = list(lam0) if lam0 is not None else [0.0] * g.n
    cur, loads = sv.solve(lam, True)
    best_val, best_lam = cur, list(lam)
    alpha = alpha0
    for it in range(iters):
        gnorm = 0.0
        for l in loads:
            if l:
                d = l - 1.0
                gnorm += d * d
        if gnorm <= 0.0:
            break
        step = alpha * (upper - cur) / gnorm
        for v in range(g.n):
            l = lam[v] + step * (loads[v] - 1.0)
            lam[v] = l if l > 0.0 else 0.0
        cur, loads = sv.solve(lam, True)
        if cur > best_val:
            best_val, best_lam = cur, list(lam)
        alpha *= decay
        if verbose and it % 25 == 0:
            print(f"  it {it:4d} D={cur:10.1f} best={best_val:10.1f} "
                  f"|g|^2={gnorm:8.0f} support={sum(1 for x in lam if x > 0)} "
                  f"t={time.time() - t_start:.0f}s", flush=True)
        if time_cap and time.time() - t_start > time_cap:
            break
    return best_val, best_lam


def prune_and_polish(sv: Solver, lam: List[float], upper: float,
                     rounds: int = 6, iters: int = 60, alpha0: float = 1.0):
    """Drop multiplier entries that no priced shortest path actually uses, then
    re-ascend on the tightened support.  Keeps the dual sparse, which is what
    makes the bound tight here (many equal-length grid routes per pair)."""
    val = sv.solve(lam, False)[0]
    for _ in range(rounds):
        _, loads = sv.solve(lam, True)
        newlam = [lam[v] if loads[v] > 0 else 0.0 for v in range(sv.g.n)]
        val2, newlam = subgradient_ascent(sv, upper, iters=iters,
                                         alpha0=alpha0, lam0=newlam)
        if val2 <= val:
            break
        val, lam = val2, newlam
    return val, lam


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="benchmarks_hard")
    ap.add_argument("--iters", type=int, default=300)
    ap.add_argument("--time-cap", type=float, default=None)
    ap.add_argument("--upper", default="base/pr3_hard")
    ap.add_argument("--out", default="results/bound_hard.json")
    ap.add_argument("--cases", default=None)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    suite = json.load(open(os.path.join(args.suite, "suite.json")))
    out = {}
    if os.path.exists(args.out):
        out = json.load(open(args.out))
    for c in suite["cases"]:
        name = c["name"]
        if args.cases and name not in args.cases.split(","):
            continue
        inst = Instance.load(os.path.join(args.suite, c["instance_file"]))
        g, nets = build(inst)
        sv = Solver(g, nets)
        pin = pins_only(sv)
        # PR#3 delay as the Polyak upper bound on OPT
        sp = os.path.join(args.upper, f"{name}.sol.json")
        upper = None
        if os.path.exists(sp):
            from m3d.checker import check
            from m3d.model import Submission
            upper = check(inst, Submission.load(sp)).total_delay
        if upper is None:
            upper = c["baseline_total"]
        val, lam = subgradient_ascent(sv, upper, iters=args.iters,
                                      alpha0=2.0, verbose=args.verbose,
                                      time_cap=args.time_cap)
        val, lam = prune_and_polish(sv, lam, upper, rounds=4, iters=80,
                                    alpha0=1.0)
        nnz = sum(1 for x in lam if x > 0)
        print(f"{name}: pins={pin:.0f} bound={val:.1f} upper={upper} "
              f"gap={(upper-val)/upper*100:.2f}% support={nnz}", flush=True)
        out[name] = {"pins_only": pin, "bound": val, "upper": upper,
                     "support": nnz, "max_lam": max(lam)}
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        json.dump(out, open(args.out, "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
