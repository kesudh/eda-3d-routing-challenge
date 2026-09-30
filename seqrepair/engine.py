"""Sequential repair / steepest-descent group routing over the M3D grid.

Ground truth is m3d/checker.py.  Everything here is written to agree with it
exactly, and verify_state() re-derives the score through the real checker and
exits 3 on disagreement.

Key facts this implementation relies on (measured elsewhere in the project):
  * Given fixed obstacles, a net's optimal route IS its shortest-path tree.
    There is no per-net Steiner gain.
  * So a single-net *equal-delay* move cannot change the total by itself.  All
    gain is in the JOINT assignment: net A vacates cells at +0 (plateau) or at
    exactly the +2 delay quantum, which lets net B reach a cheaper tree.
  * Only PARENT edges may be emitted, deduplicated (checker rule 3:
    |E| == |V|-1).
  * Capacity is per-NET (checker line 205 stores a set), so a net's own trunk
    is free and rule 4 conflicts only across distinct nets.
"""
from __future__ import annotations

import heapq
import json
import os
import random
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from m3d.model import Instance, Submission, NetRoute, canon_edge  # noqa: E402
from m3d.checker import check  # noqa: E402

Vertex = Tuple[int, int, int]
Edge = Tuple[Vertex, Vertex]

BIGPENALTY = 10_000


class Grid:
    """Flat integer vertex indexing plus precomputed adjacency with delays."""

    def __init__(self, inst: Instance):
        self.inst = inst
        self.W, self.H, self.L = inst.width, inst.height, inst.layers
        self.WH = self.W * self.H
        self.N = self.WH * self.L
        self.adj: List[List[Tuple[int, int]]] = [[] for _ in range(self.N)]
        ld = inst.layer_delay
        vd = inst.via_delay
        for z in range(self.L):
            for y in range(self.H):
                for x in range(self.W):
                    u = self.idx(x, y, z)
                    a = self.adj[u]
                    if x + 1 < self.W:
                        a.append((u + 1, ld[z]))
                    if y + 1 < self.H:
                        a.append((u + self.W, ld[z]))
                    if z + 1 < self.L:
                        a.append((u + self.WH, vd))
        # The graph is UNDIRECTED.  The loop above only emits the +x/+y/+z
        # direction, which would make Dijkstra monotone (it could never travel
        # down, left, or down a layer).  Mirror every edge.
        for u in range(self.N):
            a = self.adj[u]
            for v, w in list(a):
                if u < v:
                    self.adj[v].append((u, w))

    def idx(self, x: int = 0, y: int = 0, z: int = 0) -> int:
        return (z * self.H + y) * self.W + x

    def dec(self, i: int) -> Vertex:
        z, r = divmod(i, self.WH)
        y, x = divmod(r, self.W)
        return (x, y, z)

    def xyz(self, v: Vertex) -> int:
        return self.idx(v[0], v[1], v[2])


def dijkstra(g: Grid, src: int, blocked: bytearray, penalty: Optional[Dict[int, int]] = None,
             rand: Optional[Sequence[int]] = None):
    """Dijkstra with per-vertex penalty P (avoids those vertices) and a random
    tie-break offset.  Returns (dist, parent).

    Costs are  c(u,v) = w(u,v) + penalty.get(v, 0).  With penalty=None this is
    the true shortest-path field; with a penalty it finds the tree that best
    avoids the penalised vertices (bounded-uphill moves).
    """
    INF = float("inf")
    dist = [INF] * g.N
    par = [-1] * g.N
    dist[src] = 0
    adj = g.adj
    if rand is None:
        rand = ZERO_RAND
        use_rand = False
    else:
        use_rand = True
    heap = [(rand[src] if use_rand else 0, src)]
    pen_get = penalty.get if penalty is not None else None
    while heap:
        key, u = heapq.heappop(heap)
        du = key - (rand[u] if use_rand else 0)
        if du > dist[u]:
            continue
        for v, w in adj[u]:
            if blocked[v]:
                continue
            nd = du + w + (0 if pen_get is None else pen_get(v, 0))
            if nd < dist[v]:
                dist[v] = nd
                par[v] = u
                heapq.heappush(heap, (nd + (rand[v] if use_rand else 0), v))
    return dist, par


ZERO_RAND: List[int] = []


def extract_tree(g: Grid, par: Sequence[int], src: int, sinks: Sequence[int],
                 dist: Sequence[float]):
    """Walk parent pointers back from every sink; emit DEDUPLICATED parent
    edges only.  Returns (vertex_set, edge_list, per-sink tree delay).

    Trap guard: emitting every adjacency edge inside the vertex set is WRONG and
    yields |E| > |V|-1, which the checker rejects.
    """
    need = bytearray(g.N)
    stack = [src]
    need[src] = 1
    for s in sinks:
        if not need[s]:
            need[s] = 1
            stack.append(s)
    while stack:
        u = stack.pop()
        p = par[u]
        if u != src and p >= 0 and not need[p]:
            need[p] = 1
            stack.append(p)
    verts = []
    edges = []
    seen_e = set()
    for v in range(g.N):
        if not need[v]:
            continue
        verts.append(v)
        if v == src:
            continue
        p = par[v]
        if p < 0:
            # unreachable (dist == inf): no parent was ever relaxed
            return None, None, None
        e = (p, v) if p < v else (v, p)
        if e not in seen_e:
            seen_e.add(e)
            edges.append(e)
    # exact tree delay per sink, by BFS over the emitted edges (unique path)
    tadj: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
    for a, b in edges:
        w = _w(g, a, b)
        tadj[a].append((b, w))
        tadj[b].append((a, w))
    dmap = {src: 0}
    dq = [src]
    while dq:
        u = dq.pop()
        for v, w in tadj[u]:
            if v not in dmap:
                dmap[v] = dmap[u] + w
                dq.append(v)
    sdelays = []
    for s in sinks:
        if s not in dmap:
            return None, None, None
        sdelays.append(dmap[s])
    assert len(verts) == len(edges) + 1, (len(verts), len(edges))
    return verts, edges, sdelays


_W_CACHE: Dict[Tuple[int, int, int], Dict[Tuple[int, int], int]] = {}


def _w(g: Grid, a: int, b: int) -> int:
    """Real (unpenalised) delay of an adjacent pair, via the instance itself.

    Never hand-roll this: a y-step changes the flat index by W, not 1, and
    getting that wrong silently turns an in-layer step into a via.
    """
    key = (g.W, g.H, g.L)
    d = _W_CACHE.get(key)
    if d is None:
        d = {}
        _W_CACHE[key] = d
    v = d.get((a, b))
    if v is None:
        v = g.inst.edge_delay(g.dec(a), g.dec(b))
        d[(a, b)] = v
        d[(b, a)] = v
    return v


class State:
    """Full routing state: per-net tree, per-vertex / per-edge owner, delays."""

    def __init__(self, inst: Instance, g: Grid):
        self.inst = inst
        self.g = g
        self.nets = {n.id: n for n in inst.nets}
        self.pin_vertex = inst.pin_vertex()
        self.vertex_to_pin = inst.vertex_to_pin()
        # foreign-pin mask: a vertex that is a pin of some net -> that pin's net
        self.pin_owner: Dict[int, int] = {}
        for p in inst.pins:
            self.pin_owner[g.xyz(p.vertex())] = p.cell  # placeholder, fixed below
        self.pin_owner = {}
        for n in inst.nets:
            for pid in n.pins():
                self.pin_owner[g.xyz(self.pin_vertex[pid])] = n.id
        self.tree: Dict[int, Tuple[List[int], List[Tuple[int, int]], int]] = {}
        self.delay: Dict[int, int] = {}
        self.vowner: Dict[int, int] = {}
        self.eowner: Dict[Tuple[int, int], int] = {}

    # -- construction ------------------------------------------------------
    def load_submission(self, path: str) -> None:
        sub = Submission.load(path)
        routes = {r.net: r for r in sub.routes}
        for n in self.inst.nets:
            edges_int = []
            for a, b in routes[n.id].edges:
                edges_int.append((self.g.xyz(a), self.g.xyz(b)))
            verts = self._verts_of(n, edges_int)
            verts = self._prune(n, verts, edges_int)
            sdel = self._sink_delays(n, verts, edges_int)
            self._commit(n.id, verts, edges_int, sum(sdel))

    def _verts_of(self, net, edges_int):
        vs = set()
        for a, b in edges_int:
            vs.add(a)
            vs.add(b)
        for pid in net.pins():
            vs.add(self.g.xyz(self.pin_vertex[pid]))
        return vs

    def _prune(self, net, verts, edges_int):
        """Drop non-pin leaves (never changes delay, frees capacity)."""
        adj = defaultdict(set)
        for a, b in edges_int:
            adj[a].add(b)
            adj[b].add(a)
        pins = {self.g.xyz(self.pin_vertex[p]) for p in net.pins()}
        rem = set(edges_int)
        changed = True
        cur = set(edges_int)
        while changed:
            changed = False
            deg = defaultdict(int)
            for a, b in cur:
                deg[a] += 1
                deg[b] += 1
            drop = [e for e in cur
                    if (deg[e[0]] == 1 and e[0] not in pins)
                    or (deg[e[1]] == 1 and e[1] not in pins)]
            if drop:
                changed = True
                for e in drop:
                    cur.discard(e)
        vs = set()
        for a, b in cur:
            vs.add(a)
            vs.add(b)
        vs |= pins
        return vs

    def _sink_delays(self, net, verts, edges_int) -> List[int]:
        src = self.g.xyz(self.pin_vertex[net.driver])
        tadj = defaultdict(list)
        for a, b in edges_int:
            w = _w(self.g, a, b)
            tadj[a].append((b, w))
            tadj[b].append((a, w))
        dmap = {src: 0}
        dq = [src]
        while dq:
            u = dq.pop()
            for v, w in tadj[u]:
                if v not in dmap:
                    dmap[v] = dmap[u] + w
                    dq.append(v)
        return [dmap[self.g.xyz(self.pin_vertex[s])] for s in net.sinks]

    def _commit(self, nid, verts, edges_int, total_delay):
        """Write a net's tree into the ownership maps."""
        old = self.tree.get(nid)
        if old is not None:
            for v in old[0]:
                self.vowner.pop(v, None)
            for e in old[1]:
                self.eowner.pop(e, None)
        for v in verts:
            self.vowner[v] = nid
        for e in edges_int:
            self.eowner[e] = nid
        self.tree[nid] = (list(verts), list(edges_int), total_delay)
        self.delay[nid] = total_delay

    # -- masks -------------------------------------------------------------
    def blocked_mask(self, nid: int) -> bytearray:
        """Vertices unusable by net nid: owned by another net, or another net's pin."""
        b = bytearray(self.g.N)
        for v, o in self.vowner.items():
            if o != nid:
                b[v] = 1
        for v, o in self.pin_owner.items():
            if o != nid:
                b[v] = 1
        return b

    def total(self) -> int:
        return sum(self.delay[n.id] for n in self.inst.nets)

    # -- verification ------------------------------------------------------
    def to_submission(self, path: Optional[str] = None) -> Submission:
        routes = []
        for n in self.inst.nets:
            verts, edges, _ = self.tree[n.id]
            out = []
            for a, b in edges:
                out.append((self.g.dec(a), self.g.dec(b)))
            routes.append(NetRoute(net=n.id, edges=out))
        sub = Submission(instance=self.inst.name, routes=routes)
        if path:
            sub.save(path)
        return sub


def verify_state(st: State, label: str = "") -> Tuple[bool, int]:
    """Ground-truth gate: re-derive legality + delay through m3d/checker.py.
    Exits 3 on any disagreement.  Returns (legal, checker_total)."""
    sub = st.to_submission()
    res = check(st.inst, sub)
    mine = st.total()
    if res.total_delay is None or not res.legal:
        print(f"[VERIFY FAIL {label}] checker says illegal: {res.reasons[:5]}", flush=True)
        sys.exit(3)
    if res.total_delay != mine:
        print(f"[VERIFY FAIL {label}] checker={res.total_delay} engine={mine}", flush=True)
        sys.exit(3)
    # per-net agreement too: a compensating pair of errors could hide in the sum
    for r in res.nets:
        if r.delay != st.delay[r.net]:
            print(f"[VERIFY FAIL {label}] net {r.net}: checker={r.delay} "
                  f"engine={st.delay[r.net]}", flush=True)
            sys.exit(3)
    return True, res.total_delay
