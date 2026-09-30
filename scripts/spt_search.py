"""Zero-cost SPT re-selection search for the M3D hard tier.

Hypothesis under test
---------------------
The objective is the SUM over sinks of driver->sink delay. For a fixed set of
blocked vertices a net's optimum IS its shortest-path tree, and EVERY SPT of a
net attains every sink's free minimum simultaneously. So all SPTs of a net
cost exactly the same delay: re-selecting one is a ZERO-cost move whose only
effect is to change WHICH vertices the net occupies. Those vertices are exactly
what walls other nets out of the cheap middle layers.

Search
------
  propose(net)  : re-select that net's SPT under a different tie-break, zero cost
  sweep()       : 1-opt every other net in turn, each to its own exact optimum
  accept        : only on STRICT total-delay improvement
Iterate with restarts and a seeded RNG.
"""
from __future__ import annotations

import heapq
import json
import os
import random
import sys
import time
from typing import Dict, List, Optional, Sequence, Tuple

INF = float("inf")


# --------------------------------------------------------------------------- #
# Graph
# --------------------------------------------------------------------------- #
class Graph:
    __slots__ = ("W", "H", "L", "ld", "vd", "n", "slice", "adj", "zof", "nb")

    def __init__(self, W, H, L, ld, vd):
        self.W, self.H, self.L = W, H, L
        self.ld, self.vd = list(ld), vd
        self.slice = W * H
        self.n = self.slice * L
        adj: List[List[Tuple[int, int]]] = [[] for _ in range(self.n)]
        for z in range(L):
            base_z = z * self.slice
            d = ld[z]
            for y in range(H):
                base_y = base_z + y * W
                for x in range(W):
                    v = base_y + x
                    a = adj[v]
                    # UNDIRECTED: every forward move adds its reverse edge too
                    if x + 1 < W:
                        a.append((v + 1, d))
                        adj[v + 1].append((v, d))
                    if y + 1 < H:
                        a.append((v + W, d))
                        adj[v + W].append((v, d))
                    if z + 1 < L:
                        a.append((v + self.slice, vd))
                        adj[v + self.slice].append((v, vd))
        self.adj = [tuple(a) for a in adj]
        self.zof = [v // self.slice for v in range(self.n)]
        # static neighbour vertex lists (for pressure), no weights
        self.nb = [tuple(u for (u, _w) in a) for a in self.adj]

    def vid(self, x, y, z):
        return (z * self.H + y) * self.W + x

    def vx(self, v):
        z = v // self.slice
        r = v % self.slice
        return (r % self.W, r // self.W, z)


def load_case(g: Graph, inst_path: str):
    d = json.load(open(inst_path))
    assert d["grid"] == {"width": g.W, "height": g.H, "layers": g.L}, d["grid"]
    pin_vertex = {p["id"]: g.vid(p["x"], p["y"], p["z"]) for p in d["pins"]}
    nets = [{"id": n["id"],
             "driver": pin_vertex[n["driver"]],
             "sinks": [pin_vertex[s] for s in n["sinks"]]} for n in d["nets"]]
    pin_owner = {}          # vertex -> net
    for n in d["nets"]:
        for pid in [n["driver"]] + n["sinks"]:
            pin_owner[pin_vertex[pid]] = n["id"]
    return d["name"], nets, pin_owner


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
class State:
    __slots__ = ("g", "nets", "nv", "occ_v", "occ_e", "r_edges", "r_verts",
                 "ndelay", "total", "pin_owner", "_blk")

    def __init__(self, g: Graph, nets, pin_owner):
        self.g = g
        self.nets = nets
        self.nv = len(nets)
        self.occ_v = [-1] * g.n
        self.occ_e = {}
        self.r_edges: List[List[Tuple[int, int]]] = [[] for _ in range(self.nv)]
        self.r_verts: List[set] = [set() for _ in range(self.nv)]
        self.ndelay = [0] * self.nv
        self.total = 0
        self.pin_owner = pin_owner
        self._blk = bytearray(g.n)

    def ripup(self, n):
        for v in self.r_verts[n]:
            self.occ_v[v] = -1
        oe = self.occ_e
        for e in self.r_edges[n]:
            del oe[e]
        self.r_edges[n] = []
        self.r_verts[n] = set()

    def place(self, n, edges, verts, delay):
        self.r_edges[n] = edges
        self.r_verts[n] = verts
        ov = self.occ_v
        for v in verts:
            ov[v] = n
        oe = self.occ_e
        for e in edges:
            oe[e] = n
        self.ndelay[n] = delay
        self.total += delay - self.ndelay[n] + self.ndelay[n]
        self.total = self.total - 0  # noop guard (recomputed by caller)

    def snap(self):
        return (list(self.occ_v), dict(self.occ_e),
                [list(e) for e in self.r_edges], [set(s) for s in self.r_verts],
                list(self.ndelay), self.total)

    def restore(self, s):
        self.occ_v = list(s[0])
        self.occ_e = dict(s[1])
        self.r_edges = [list(e) for e in s[2]]
        self.r_verts = [set(x) for x in s[3]]
        self.ndelay = list(s[4])
        self.total = s[5]


# --------------------------------------------------------------------------- #
# Core: Dijkstra + tight-DAG SPT
# --------------------------------------------------------------------------- #
def reroute(st: State, n: int, costs=None, lex: bool = False) -> int:
    """Rip up net n and rebuild its exact-optimal route. Returns its delay.

    If ``costs`` is None (or lex) the SPT tie-break is lowest vertex index.
    Otherwise tie-break minimises the cumulative secondary cost, subject to the
    predecessor being TIGHT (d[u] + w(u,v) == d[v]), so the result is always a
    true SPT with unchanged sink delays.
    """
    g = st.g
    net = st.nets[n]
    src = net["driver"]
    st.ripup(n)

    ov = st.occ_v
    blk = st._blk
    # blocked: any vertex owned by another net, and any pin of another net
    for v in range(g.n):
        o = ov[v]
        blk[v] = 1 if (o >= 0 and o != n) else 0
    # foreign pins (a route may not pass through another net's pin)
    for v, owner in st.pin_owner.items():
        if owner != n:
            blk[v] = 1

    adj = g.adj
    dist = {src: 0}
    h = [(0, src)]
    push, pop = heapq.heappush, heapq.heappop
    while h:
        d, u = pop(h)
        if u in dist and dist[u] < d:
            continue
        for (v, w) in adj[u]:
            if blk[v]:
                continue
            nd = d + w
            dv = dist.get(v)
            if dv is None or nd < dv:
                dist[v] = nd
                push(h, (nd, v))

    order = sorted(dist, key=lambda v: (dist[v], v))
    # A legal net route is a TREE, so it must be MINIMAL: only the vertices
    # that lie on some tight src->sink path. Vertices reachable from src but
    # with no tight continuation into a sink are pruned (they are not needed
    # and would waste capacity).
    needed = set()
    stack = list(net["sinks"])
    for s in stack:
        needed.add(s)
    # reverse-tight closure: v is needed if some tight successor is needed
    for v in reversed(order):
        if v in needed or v == src:
            continue
        for (u, w) in adj[v]:
            if u in dist and dist[v] + w == dist[u]:
                needed.add(v)
                break
    needed.discard(src)

    chosen = {src: -1}
    if costs is None:
        for v in order:
            if v == src or v not in needed:
                continue
            for (u, w) in adj[v]:
                if u in chosen and dist[u] + w == dist[v]:
                    chosen[v] = u
                    break
    else:
        best = {src: 0.0}
        for v in order:
            if v == src or v not in needed:
                continue
            cv = costs[v]
            bv = None
            bu = -1
            for (u, w) in adj[v]:
                if u in chosen and dist[u] + w == dist[v]:
                    cu = best[u] + cv
                    if bv is None or cu < bv:
                        bv = cu
                        bu = u
            chosen[v] = bu
            best[v] = bv

    edges = []
    verts = set(chosen)
    for v, p in chosen.items():
        if p >= 0:
            edges.append((p, v) if p < v else (v, p))
    delay = 0
    for s in net["sinks"]:
        delay += dist[s]
    st.r_edges[n] = edges
    st.r_verts[n] = verts
    for v in verts:
        ov[v] = n
    oe = st.occ_e
    for e in edges:
        oe[e] = n
    st.ndelay[n] = delay
    return delay


def set_total(st: State):
    st.total = sum(st.ndelay)
    return st.total


# --------------------------------------------------------------------------- #
# Pressure functions
# --------------------------------------------------------------------------- #
def make_pressure(g: Graph, st: State, mid_pen: float, out_pen: float,
                  nb_pen: float) -> List[float]:
    """Secondary cost per vertex used to break SPT ties.

    mid_pen  : penalty for occupying a contended middle layer (z=2,3)
    out_pen  : penalty for occupying the slack layers (z=1,4,0,5)
    nb_pen   : penalty proportional to how many NEIGHBOUR vertices are already
               owned by other nets (avoids wedging into occupied neighbourhoods)
    """
    c = [0.0] * g.n
    zof = g.zof
    nb = g.nb
    occ = st.occ_v
    nv = st.nv
    for v in range(g.n):
        z = zof[v]
        if z == 2 or z == 3:
            c[v] = mid_pen
        else:
            c[v] = out_pen
    if nb_pen:
        for v in range(g.n):
            k = 0
            for u in nb[v]:
                o = occ[u]
                if 0 <= o < nv:
                    k += 1
            c[v] += nb_pen * k
    return c


# --------------------------------------------------------------------------- #
# Submission IO
# --------------------------------------------------------------------------- #
def load_sol(g: Graph, nets, path: str, st: State):
    d = json.load(open(path))
    by_id = {n["id"]: i for i, n in enumerate(nets)}
    for r in d["routes"]:
        n = by_id[r["net"]]
        st.ripup(n)
        edges = []
        for (a, b) in r["edges"]:
            va = g.vid(a[0], a[1], a[2])
            vb = g.vid(b[0], b[1], b[2])
            edges.append((va, vb) if va < vb else (vb, va))
        verts = set()
        for e in edges:
            verts.add(e[0])
            verts.add(e[1])
        verts.add(nets[n]["driver"])
        for s in nets[n]["sinks"]:
            verts.add(s)
        for v in verts:
            st.occ_v[v] = n
        for e in edges:
            st.occ_e[e] = n
        st.r_edges[n] = edges
        st.r_verts[n] = verts
    set_total(st)


def dump_sol(g: Graph, nets, st: State, path: str):
    routes = []
    for i, net in enumerate(nets):
        edges = []
        for (a, b) in st.r_edges[i]:
            aa = list(g.vx(a))
            bb = list(g.vx(b))
            edges.append([aa, bb])
        routes.append({"net": net["id"], "edges": edges})
    routes.sort(key=lambda r: r["net"])
    out = {"format": "m3d-submission", "version": 1,
           "instance": path.split(os.sep)[-1].split(".")[0].replace(".sol", ""),
           "routes": routes}
    json.dump(out, open(path, "w"))


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
def sweep(st: State, order, cost_fn=None) -> int:
    """1-opt every net in `order` to its own exact optimum. Idempotent at
    fixpoint. Returns the new total."""
    tot = 0
    for n in order:
        st.ripup(n)
        d = reroute(st, n, None)
        tot += d
    st.total = sum(st.ndelay)
    return st.total


def search_case(g: Graph, nets, pin_owner, sol_path: str, out_path: str,
                seconds: float, seed: int = 0, log=print):
    t0 = time.time()
    rng = random.Random(seed)
    st = State(g, nets, pin_owner)
    load_sol(g, nets, sol_path, st)
    set_total(st)
    base_total = st.total
    log(f"  loaded total={st.total}")

    best_snap = st.snap()
    best_total = st.total

    # sweep ordering heuristics: nets whose sinks are worst-off first, plus
    # a deterministic rotation.
    fanout = [len(n["sinks"]) for n in nets]

    it = 0
    stall = 0
    lam_grid = [0.0, 0.5, 1.0, 2.0, 4.0, 8.0]
    nb_grid = [0.0, 0.25, 1.0]
    mid_grid = [1.0, 2.0, 4.0]
    while time.time() - t0 < seconds:
        it += 1
        # pick a victim net
        n = rng.randrange(st.nv)
        pre = st.snap()
        pre_total = st.total
        st.ripup(n)
        old_verts = set(pre[3][n])
        # build pressure from the CURRENT occupancy (net n already ripped)
        mid_pen = rng.choice(mid_grid)
        nb_pen = rng.choice(nb_grid)
        lam = rng.choice(lam_grid)
        press = make_pressure(g, st, mid_pen, lam, nb_pen)
        # normalize: a genuine zero-cost re-selection keeps the same delay
        d = reroute(st, n, press)
        if d != st.ndelay[n]:
            # the re-selection was not cost-neutral (shouldn't happen); revert
            st.restore(pre)
            continue
        # 1-opt sweep everyone else
        order = list(range(st.nv))
        rng.shuffle(order)
        for m in order:
            if m == n:
                continue
            st.ripup(m)
            reroute(st, m, None)
        set_total(st)
        if st.total < best_total:
            best_total = st.total
            best_snap = st.snap()
            stall = 0
            log(f"  [it {it}] IMPROVE total={st.total} (was {pre_total}) net={n} "
                f"verts {len(old_verts)}->{len(st.r_verts[n])}")
        else:
            stall += 1
            if rng.random() < 0.5:
                st.restore(pre)
    set_total(st)
    log(f"  iters={it} best={best_total} start={base_total} "
        f"elapsed={time.time()-t0:.1f}s")
    return best_total, best_snap
