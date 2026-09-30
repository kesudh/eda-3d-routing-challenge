"""MAIZEROUTER-style extreme edge shifting, adapted to M3D.

Source: Moffitt et al., "MAIZEROUTER: Engineering an Effective Global Router",
ASPDAC 2008 (https://cecs.uci.edu/~papers/aspdac08/pdf/p226_3A-1.pdf). Reported:
full routability on all ten instances, 7.5x faster than BoxRouter, 2.02% shorter
wirelength than BoxRouter and 2.92% shorter than FastRoute 2.0.

The move: relocate ONE tree edge far outside the current Steiner/connection
topology, reconnect, and score on the GLOBAL objective -- crucially it never
re-optimises the net. That is why it escapes our closed move class: the
evaluation operator E (apply each net's exact per-net optimum) is idempotent,
so anything that ends in per-net re-optimisation lands back on a 1-opt point.

Adaptation note (honest): MAIZEROUTER targets overflow repair in a soft-
congestion global router. Ours has HARD per-net capacity and PR#3's solution is
already legal, so there is no overflow to repair. The analog is contention
relief, so each compound move is:
  1. pick net A and one edge e of its tree lying in the contended middle layers;
  2. cut e and reconnect A's two components by the cheapest LEGAL reconnection
     -- deliberately accepting a locally-worse tree for A;
  3. run 1-opt to fixpoint so every OTHER net reclaims the freed space;
  4. accept only if the GLOBAL total strictly improves.

Step 3 is the compound part: a plain edge relocation cannot help here on its own,
because A's own delay rises and nothing else moves.
"""
from __future__ import annotations

import collections
import heapq
import json
import os
import sys
import time

sys.path.insert(0, r"F:\eda-3d-routing-challenge")
os.chdir(r"F:\eda-3d-routing-challenge")

from m3d.model import Instance, Submission

INF = float("inf")


class Router:
    def __init__(self, case: str):
        self.inst = Instance.load(f"benchmarks_hard/{case}.json")
        i = self.inst
        self.W, self.H, self.L = i.width, i.height, i.layers
        self.WH = self.W * self.H
        self.enc = lambda c: (c[2] * self.H + c[1]) * self.W + c[0]
        self.dec = lambda v: (v % self.W, (v // self.W) % self.H, v // self.WH)
        self.pv = {p.id: self.enc(p.vertex()) for p in i.pins}
        self.pin_of = {}
        for n in i.nets:
            for pid in n.pins():
                self.pin_of[pid] = n.id
        self.pinv = {self.pv[p.id]: p.id for p in i.pins}
        self.NET = {n.id: n for n in i.nets}
        self._op = {}

    def other_pins(self, nid):
        if nid not in self._op:
            self._op[nid] = {v for v, pid in self.pinv.items()
                             if self.pin_of[pid] != nid}
        return self._op[nid]

    def nbrs(self, v):
        z, r = divmod(v, self.WH)
        y, x = divmod(r, self.W)
        d = self.inst.layer_delay
        via = self.inst.via_delay
        W, H, L = self.W, self.H, self.L
        if x + 1 < W:
            yield v + 1, d[z]
        if x > 0:
            yield v - 1, d[z]
        if y + 1 < H:
            yield v + W, d[z]
        if y > 0:
            yield v - W, d[z]
        if z + 1 < L:
            yield v + self.WH, via
        if z > 0:
            yield v - self.WH, via

    # ---------------------------------------------------------------- routing
    def spt(self, nid, blocked):
        """Exact per-net optimum with `blocked` vertices removed."""
        n = self.NET[nid]
        src = self.pv[n.driver]
        op = self.other_pins(nid)
        d = {src: 0}
        pq = [(0, src)]
        while pq:
            dd, u = heapq.heappop(pq)
            if dd != d.get(u):
                continue
            for v, wg in self.nbrs(u):
                if v in op or v in blocked:
                    continue
                nd = dd + wg
                if nd < d.get(v, INF):
                    d[v] = nd
                    heapq.heappush(pq, (nd, v))
        return d

    def tree_from_d(self, nid, d, src):
        n = self.NET[nid]
        verts = set()
        edges = []
        delay = 0
        for s in n.sinks:
            t = self.pv[s]
            if t not in d:
                return None
            cur = t
            while True:
                verts.add(cur)
                if cur == src:
                    break
                step = None
                best = INF
                for u, wg in self.nbrs(cur):
                    if u not in d:
                        continue
                    key = d[u] + wg
                    if key < best:
                        best = key
                        step = (u, wg)
                if step is None:
                    return None
                verts.add(step[0])
                edges.append((step[0], cur))
                delay += step[1]
                cur = step[0]
        return verts, edges, delay

    def route(self, nid, blocked):
        d = self.spt(nid, blocked)
        if not d:
            return None
        t = self.tree_from_d(nid, d, self.pv[self.NET[nid].driver])
        return t

    def one_opt(self, routes):
        """Fixpoint: reroute every net to its exact optimum with others frozen."""
        occ = set()
        for v, _e, _d in routes.values():
            occ |= v
        improved = True
        while improved:
            improved = False
            for nid in list(routes):
                v, _e, d0 = routes[nid]
                occ -= v
                r = self.route(nid, occ)
                if r is not None and r[2] < d0:
                    routes[nid] = r
                    occ |= r[0]
                    improved = True
                    continue
                occ |= v
        return routes

    @staticmethod
    def total(routes):
        return sum(d for _v, _e, d in routes.values())


def load_pr3(r: Router, case):
    import subprocess
    out = subprocess.run(
        ["git", "show", f"pr3:submissions/hard/pathfinder_lns/{case}.sol.json"],
        capture_output=True, text=True, cwd=r"F:\eda-3d-routing-challenge")
    return Submission.from_dict(json.loads(out.stdout))


def sub_to_routes(r: Router, sub):
    routes = {}
    for rt in sub.routes:
        nid = rt.net
        vs = {r.enc(a) for a, _ in rt.edges} | {r.enc(b) for _a, b in rt.edges}
        edges = [(r.enc(a), r.enc(b)) for a, b in rt.edges]
        adj = collections.defaultdict(list)
        for u, v in edges:
            adj[u].append(v)
            adj[v].append(u)
        n = r.NET[nid]
        src = r.pv[n.driver]
        dist = {src: 0}
        q = collections.deque([src])
        while q:
            u = q.popleft()
            for v in adj[u]:
                if v not in dist:
                    dist[v] = dist[u] + r.inst.edge_delay(r.dec(u), r.dec(v))
                    q.append(v)
        delay = sum(dist[r.pv[s]] for s in n.sinks)
        routes[nid] = (vs, edges, delay)
    return routes


def edge_relocate(r: Router, routes, target_nets, budget_s, log):
    """One pass of extreme edge shifting over `target_nets`."""
    occ = set()
    for v, _e, _d in routes.values():
        occ |= v
    base = Router.total(routes)
    accepted = 0
    tried = 0
    t_end = time.time() + budget_s
    for nid in target_nets:
        if time.time() > t_end:
            break
        verts, edges, d0 = routes[nid]
        # candidate edges: those in the contended middle layers
        cand = [e for e in edges if r.dec(e[0])[2] in (2, 3) or r.dec(e[1])[2] in (2, 3)]
        for (u, v) in cand:
            if time.time() > t_end:
                break
            tried += 1
            # adjacency WITHOUT this edge -> two components
            adj = collections.defaultdict(list)
            for a, b in edges:
                if {a, b} == {u, v}:
                    continue
                adj[a].append(b)
                adj[b].append(a)
            src = r.pv[r.NET[nid].driver]
            # label components from the driver
            comp = {src: 0}
            q = collections.deque([src])
            while q:
                x = q.popleft()
                for y in adj[x]:
                    if y not in comp:
                        comp[y] = comp[x]
                        q.append(y)
            others = [x for x in verts if x not in comp]
            if not others:
                continue
            other_blocked = (occ - verts)
            # cheapest legal reconnection: any free vertex adjacent to both sides
            best = None
            a_side = [x for x in comp if x in verts]
            for x in a_side:
                for y, _wg in r.nbrs(x):
                    if y in comp or y in other_blocked:
                        continue
                    for z in others:
                        for z2, wg2 in r.nbrs(z):
                            if z2 == y:
                                w = _wg + wg2
                                if best is None or w < best[0]:
                                    best = (w, y)
            if best is None:
                continue
            newverts = set(verts) | {best[1]}
            newedges = [e for e in edges if {e[0], e[1]} != {u, v}]
            newedges.append((best[1], min(a_side, key=lambda x: 0)))  # placeholder
            # rebuild properly: connect the bridging vertex to both sides
            bridge = best[1]
            newedges = [e for e in edges if {e[0], e[1]} != {u, v}]
            for x in a_side:
                for y, _w in r.nbrs(x):
                    if y == bridge:
                        newedges.append((x, bridge))
                        break
            for z in others:
                for z2, _w in r.nbrs(z):
                    if z2 == bridge:
                        newedges.append((bridge, z2))
                        break
            # verify the tree reaches every sink
            adj2 = collections.defaultdict(list)
            for a, b in newedges:
                adj2[a].append(b)
                adj2[b].append(a)
            if any(r.pv[s] not in adj2 or r.pv[s] not in newverts for s in r.NET[nid].sinks):
                continue
            dist = {src: 0}
            q = collections.deque([src])
            while q:
                x = q.popleft()
                for y in adj2[x]:
                    if y not in dist:
                        dist[y] = dist[x] + r.inst.edge_delay(r.dec(x), r.dec(y))
                        q.append(y)
            if any(r.pv[s] not in dist for s in r.NET[nid].sinks):
                continue
            ndelay = sum(dist[r.pv[s]] for s in r.NET[nid].sinks)
            if ndelay >= d0:
                continue          # a plain relocation that costs A nothing is a 1-opt move
            # COMPOUND: A is now locally worse. Let everyone else re-optimise.
            trial = {k: (set(vv), list(e), dd) for k, (vv, e, dd) in routes.items()}
            trial[nid] = (newverts, newedges, ndelay)
            occ2 = set()
            for k, (vv, _e, _dd) in trial.items():
                occ2 |= vv
            occ2 -= newverts
            fixed = {k: (vv, e, dd) for k, (vv, e, dd) in trial.items() if k != nid}
            r.one_opt(fixed)
            newtot = sum(dd for _vv, _e, dd in fixed.values()) + ndelay
            if newtot < base:
                routes = dict(fixed)
                routes[nid] = (newverts, newedges, ndelay)
                occ = occ2 | newverts
                base = Router.total(routes)
                accepted += 1
                log.append(f"  ACCEPT net {nid} edge {(r.dec(u), r.dec(v))}: "
                           f"{d0}->{ndelay}, total {base}")
    return routes, accepted, tried


def main():
    case = "case_01"
    TARGET = 8674
    r = Router(case)
    routes = sub_to_routes(r, load_pr3(r, case))
    base = Router.total(routes)
    print(f"{case}: PR#3 total {base} (target {TARGET})")
    # verify we reproduce it
    assert base == TARGET, f"failed to reproduce PR#3: {base} != {TARGET}"
    log = []
    t0 = time.time()
    budget = 240.0
    # target the fanout-1 nets that carry 65% of the excess
    fan = {n.id: len(n.sinks) for n in r.inst.nets}
    tgt = sorted([k for k in routes if fan[k] == 1])
    print(f"targeting {len(tgt)} fanout-1 nets, budget {budget:.0f}s")
    cur = dict(routes)
    for sweep in range(3):
        if time.time() - t0 > budget:
            break
        cur, acc, tried = edge_relocate(r, cur, tgt, budget - (time.time() - t0), log)
        print(f"sweep {sweep}: tried {tried}, accepted {acc}, total {Router.total(cur)}"
              f"  ({time.time()-t0:.0f}s)")
        if not acc:
            break
    tot = Router.total(cur)
    print(f"\nFINAL {case}: {base} -> {tot}   delta {base - tot:+d}")
    print(f"vs PR#3 {TARGET}: {tot - TARGET:+d}")
    for line in log[:20]:
        print(line)
    return cur


if __name__ == "__main__":
    main()
