"""Feasibility spike: can a small learned model pick better LNS moves than random
or a hand heuristic on an M3D hard-tier case?

Setup
-----
Start from PR#3's own solution for hard/case_01 (a capacity-1 solution that is
already a hard 1-opt local optimum). A "move" = rip up a set of nets and reroute
them exactly (Dijkstra per net, other nets' vertices blocked) in a given order.

For each candidate move we compute the TRUE resulting total delay, i.e. a label.
Features are cheap aggregates of the move (fanout, current delay, detour vs the
pins-only SPT, layer occupancy around the net, etc.) -- the kind of thing a
policy net could plausibly see.

Then we ask the only question that matters for "can a NN help": does a small
numpy MLP trained on these (features -> delta) rank moves better than
(a) random and (b) a hand heuristic? Measured as top-k precision and as the
mean true delta of the move the ranker selects.

Honesty rules baked in: no torch dependency, deterministic seeds, every number
printed is measured here.
"""
import argparse
import heapq
import json
import os
import random
import sys
import time

import numpy as np

SCRATCH = os.environ.get("TMPDIR", "C:/Users/gkesu/AppData/Local/hermes/cache/scratch")


# --------------------------------------------------------------------------- #
# instance / solution loading
# --------------------------------------------------------------------------- #
class Case:
    def __init__(self, inst_path, sol_path):
        d = json.load(open(inst_path))
        self.W, self.H, self.L = d["grid"]["width"], d["grid"]["height"], d["grid"]["layers"]
        self.ld = d["delay"]["layer_delay"]
        self.via = d["delay"]["via_delay"]
        self.N = self.W * self.H * self.L
        self.pv = {p["id"]: (p["x"], p["y"], p["z"]) for p in d["pins"]}
        self.v2p = {v: p for p, v in self.pv.items()}
        self.nets = {n["id"]: n for n in d["nets"]}
        self.net_ids = sorted(self.nets)
        self.pin_net = {}
        for nid, n in self.nets.items():
            for p in [n["driver"]] + list(n["sinks"]):
                self.pin_net[p] = nid
        sol = json.load(open(sol_path))
        # occupancy: vertex -> net, from the PR#3 submission
        self.sol_edges = {
            r["net"]: [(tuple(e[0]), tuple(e[1])) for e in r["edges"]]
            for r in sol["routes"]
        }

    def vid(self, v):
        x, y, z = v
        return (z * self.H + y) * self.W + x

    def net_pins_v(self, nid):
        n = self.nets[nid]
        return [self.pv[n["driver"]]] + [self.pv[s] for s in n["sinks"]]

    def net_delay(self, nid, edge_set):
        """Sum of driver->sink delays over a net's edge set (BFS on the tree)."""
        adj = {}
        for a, b in edge_set:
            w = self.via if a[2] != b[2] else self.ld[a[2]]
            adj.setdefault(a, []).append((b, w))
            adj.setdefault(b, []).append((a, w))
        drv = self.pv[self.nets[nid]["driver"]]
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
        return sum(dist[self.pv[s]] for s in self.nets[nid]["sinks"])


def _iter_edges(r):
    return r["edges"]


# --------------------------------------------------------------------------- #
# exact reroute of a set of nets with all other nets' vertices blocked
# --------------------------------------------------------------------------- #
def reroute(case, rip, occ, order, vcost=None):
    """rip: list of net ids to remove. occ: dict vertex->net for the rest.
    Returns (new_edges_by_net, ok). new edges replace the ripped nets' edges.
    vcost: optional dict vertex->extra cost (for negotiated-style reroute).
    """
    blocked = set(occ)
    for nid in rip:
        for e in case.sol_edges[nid]:
            blocked.discard(e[0])
            blocked.discard(e[1])
    # other nets' pins stay blocked
    for nid in rip:
        for p in [case.nets[nid]["driver"]] + list(case.nets[nid]["sinks"]):
            if case.pin_net[p] != nid:
                blocked.add(case.pv[p])
    out = {}
    newocc = dict(occ)
    for nid in order:
        pins = case.net_pins_v(nid)
        E = _dijkstra_tree(case, pins, blocked, vcost)
        if E is None:
            return None, False
        out[nid] = E
        for e in E:
            blocked.add(e[0])
            blocked.add(e[1])
            newocc[e[0]] = nid
            newocc[e[1]] = nid
    return out, True


def _dijkstra_tree(case, pins, blocked, vcost):
    """Exact SPT from pins[0] avoiding `blocked`. Returns the edge list, or None
    if some sink is unreachable. Delays are positive, so the SPT's driver->sink
    tree paths ARE the shortest distances, which is what the objective charges.
    """
    W, H, L, ld, via = case.W, case.H, case.L, case.ld, case.via
    drv = pins[0]
    dist = {drv: 0}
    prev = {}
    heap = [(0, drv)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, d):
            continue
        x, y, z = u
        nb = []
        if x + 1 < W: nb.append(((x + 1, y, z), ld[z]))
        if x > 0: nb.append(((x - 1, y, z), ld[z]))
        if y + 1 < H: nb.append(((x, y + 1, z), ld[z]))
        if y > 0: nb.append(((x, y - 1, z), ld[z]))
        if z + 1 < L: nb.append(((x, y, z + 1), via))
        if z > 0: nb.append(((x, y, z - 1), via))
        for v, w in nb:
            if v in blocked:
                continue
            nd = d + w + (vcost.get(v, 0) if vcost else 0)
            if nd < dist.get(v, 1 << 30):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))
    edges = []
    for s in pins[1:]:
        if s not in dist:
            return None
        cur = s
        while cur != drv:
            p = prev[cur]
            edges.append((p, cur))
            cur = p
    return edges


# --------------------------------------------------------------------------- #
# features
# --------------------------------------------------------------------------- #
def spt_delay(case, nid, extra_blocked=frozenset()):
    E = _dijkstra_tree(case, case.net_pins_v(nid), set(extra_blocked), None)
    if E is None:
        return None
    return case.net_delay(nid, E)


def make_features(case, occ, move_nets, cur_delays, spt_cache):
    """Cheap, per-move aggregate features available BEFORE running the move."""
    W, H, L = case.W, case.H, case.L
    f = []
    nsink = 0
    delay_sum = 0
    detour_sum = 0
    detour_max = 0
    mid_occ = []   # fraction of net vertices on the two middle layers
    for nid in move_nets:
        n = case.nets[nid]
        k = len(n["sinks"])
        nsink += k
        d = cur_delays[nid]
        delay_sum += d
        s = spt_cache.get(nid)
        if s is not None:
            det = d - s
            detour_sum += det
            detour_max = max(detour_max, det)
        vs = set()
        for a, b in case.sol_edges[nid]:
            vs.add(a); vs.add(b)
        mid = sum(1 for v in vs if 1 <= v[2] <= L - 2)
        mid_occ.append(mid / max(1, len(vs)))
    f += [
        len(move_nets),
        nsink,
        delay_sum,
        delay_sum / max(1, nsink),
        detour_sum,
        detour_mean := detour_sum / max(1, nsink),
        detour_max,
        float(np.mean(mid_occ)) if mid_occ else 0.0,
        float(np.max(mid_occ)) if mid_occ else 0.0,
    ]
    return np.array(f, dtype=np.float64)


# --------------------------------------------------------------------------- #
# numpy MLP
# --------------------------------------------------------------------------- #
class MLP:
    def __init__(self, d_in, d_h=32, seed=0):
        rng = np.random.default_rng(seed)
        self.W1 = rng.normal(0, 0.5, (d_in, d_h))
        self.b1 = np.zeros(d_h)
        self.W2 = rng.normal(0, 0.5, (d_h, 1))
        self.b2 = np.zeros(1)
        self.lr = 0.01

    def __call__(self, X):
        h = np.tanh(X @ self.W1 + self.b1)
        return (h @ self.W2 + self.b2).ravel()

    def fit(self, X, y, epochs=400, batch=32, seed=0, l2=1e-3):
        rng = np.random.default_rng(seed)
        n = len(X)
        for ep in range(epochs):
            idx = rng.permutation(n)
            for i in range(0, n, batch):
                j = idx[i:i + batch]
                xb, yb = X[j], y[j]
                h = np.tanh(xb @ self.W1 + self.b1)
                p = (h @ self.W2 + self.b2).ravel()
                err = 2 * (p - yb) / len(j)
                gW2 = h.T @ err[:, None]
                gb2 = np.array([err.sum()])
                dh = (err[:, None] @ self.W2.T) * (1 - h ** 2)
                gW1 = xb.T @ dh
                gb1 = dh.sum(0)
                self.W1 -= self.lr * (gW1 + l2 * self.W1)
                self.b1 -= self.lr * gb1
                self.W2 -= self.lr * (gW2 + l2 * self.W2)
                self.b2 -= self.lr * gb2
        return self


def spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean(); rb -= rb.mean()
    den = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / den) if den else 0.0
