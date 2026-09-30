"""Test whether ANY improving move exists on top of PR#3's own solutions.

This is the decisive experiment. A congestion-pricing policy can only help if
it changes the routing in a way that lowers total delay. If PR#3's solutions are
already 1-optimal (the brief's established fact #1), then no per-net policy --
fanout-exact, sinks^-0.5, or otherwise -- can improve them, and the honest
conclusion is that pricing is not the lever.

Two moves are tested:

  1-opt      : rip up one net, reroute it optimally with all other nets fixed
               as hard obstacles. Repeat to fixpoint. (established fact #1)
  joint LNS  : rip up a SET of nets (the walled-in low-fanout nets plus every
               net boxing them in), reroute the set jointly under a chosen
               congestion price, keep only if total delay strictly improves.
"""
from __future__ import annotations

import heapq
import os
import time
from typing import Dict, List, Optional, Sequence, Set, Tuple

from m3d.checker import check
from m3d.model import Instance, NetRoute, Submission

from .dual import Prob


def load_state(inst: Instance, solpath: str):
    """Return (prob, routes, owners) where routes[nid] = (verts, edges)."""
    p = Prob(inst)
    g = p.g
    sub = Submission.load(solpath)
    routes: Dict[int, Tuple[Set[int], Set[Tuple[int, int]]]] = {}
    for r in sub.routes:
        vs = set()
        es = set()
        for a, b in r.edges:
            va = (a[2] * g.h + a[1]) * g.w + a[0]
            vb = (b[2] * g.h + b[1]) * g.w + b[0]
            vs.add(va); vs.add(vb)
            es.add((va, vb) if va < vb else (vb, va))
        routes[r.net] = (vs, es)
    return p, routes


def net_delay(inst: Instance, g, vs: Set[int], es: Set[Tuple[int, int]],
              src: int, sinks: Sequence[int]) -> Optional[int]:
    adj: Dict[int, List[Tuple[int, int]]] = {v: [] for v in vs}
    for a, b in es:
        w = inst.edge_delay(g.coord(a), g.coord(b))
        adj[a].append((b, w))
        adj[b].append((a, w))
    from collections import deque
    dist = {src: 0}
    q = deque([src])
    while q:
        u = q.popleft()
        for v, w in adj[u]:
            if v not in dist:
                dist[v] = dist[u] + w
                q.append(v)
    if any(s not in dist for s in sinks):
        return None
    return sum(dist[s] for s in sinks)


def spt_with_obstacles(g, src: int, sinks: Sequence[int],
                       blocked: bytearray):
    """Exact SPT (pure delay) avoiding `blocked` vertices."""
    n = g.n
    INF = float("inf")
    dist = [INF] * n
    par = [-1] * n
    tset = set(sinks)
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
        for v, w in g.nbr[u]:
            if blocked[v]:
                continue
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                par[v] = u
                heapq.heappush(pq, (nd, v))
    tree = {src}
    edges: Set[Tuple[int, int]] = set()
    for s in sinks:
        c = s
        while c not in tree:
            p = par[c]
            if p == -1:
                return None
            tree.add(c)
            edges.add((c, p) if c < p else (p, c))
            c = p
    return tree, edges
