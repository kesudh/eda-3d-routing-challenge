"""Directed zero-cost SPT re-selection.

The random-proposal search wastes almost all of its time: it re-picks a
tie-break for a net that was never actually in the way. The directed move
generator instead does the following, which is the whole point of the seam:

  1. find a net m whose sinks are DETOURED relative to the free graph
     (free = blocked only by foreign pins);
  2. walk a free-optimal path to its worst sink and locate the FIRST vertex v
     on that path that is occupied by some OTHER net n;
  3. re-select n's SPT with v forbidden -> v is released at ZERO cost to n,
     because we only ever choose among TIGHT predecessors, so n's sink delays
     (and hence its contribution to the objective) are unchanged;
  4. 1-opt sweep so every other net -- m included -- can exploit the freed room;
  5. accept only on a STRICT total-delay improvement.

The seam is real and enumerable: on benchmarks_hard a net that re-selects its
SPT can release a vertex that another net's optimal path was waiting for.
"""
from __future__ import annotations

import heapq
import os
import random
import sys
import time
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spt_search as S

INF = float("inf")


# --------------------------------------------------------------------------- #
def free_dist(g, src, blk):
    """Dijkstra blocked only by foreign pins (no net ownership)."""
    dist = {src: 0}
    h = [(0, src)]
    adj = g.adj
    while h:
        d, u = heapq.heappop(h)
        if u in dist and dist[u] < d:
            continue
        for (v, w) in adj[u]:
            if blk[v]:
                continue
            nd = d + w
            dv = dist.get(v)
            if dv is None or nd < dv:
                dist[v] = nd
                heapq.heappush(h, (nd, v))
    return dist


def blockers(st: S.State, g: S.Graph, net_idx: int):
    """Yield (sink, blocking_vertex, blocking_net) pairs that stand between a
    net and its free optimum, ordered by how much delay they cost."""
    net = st.nets[net_idx]
    src = net["driver"]
    blk = bytearray(g.n)
    for v, owner in st.pin_owner.items():
        if owner != net_idx:
            blk[v] = 1
    fd = free_dist(g, src, blk)
    out = []
    occ = st.occ_v
    for s in net["sinks"]:
        if s not in fd:
            continue
        detour = st.ndelay[net_idx] - fd[s]
        if detour <= 0:
            continue
        # walk one free-optimal path src->s, find the first occupied vertex
        v = s
        path = [v]
        seen = {v}
        while v != src:
            dv = fd[v]
            for (u, w) in g.adj[v]:
                if u in fd and fd[u] + w == dv and u not in seen:
                    seen.add(u)
                    path.append(u)
                    v = u
                    break
            else:
                break
        for u in path:                      # path is sink -> src
            o = occ[u]
            if o >= 0 and o != net_idx:
                out.append((detour, s, u, o))
                break
    out.sort(key=lambda t: -t[0])
    return out


def release(st: S.State, g: S.Graph, victim: int, forbid, log=None):
    """Re-select `victim`'s SPT while refusing to occupy any vertex in
    `forbid` (a set). Returns (ok, delay_before, verts_after).

    Cost is guaranteed unchanged: only TIGHT predecessors are ever considered,
    so every chosen tree is a genuine SPT of the same distance function.
    """
    before = st.ndelay[victim]
    old_verts = set(st.r_verts[victim])
    st.ripup(victim)
    costs = [0.0] * g.n
    BIG = 1e6
    for v in forbid:
        costs[v] = BIG
    d = S.reroute(st, victim, costs)
    kept = len(old_verts & st.r_verts[victim])
    if d != before:
        # Cannot happen with tight-only selection; guard anyway.
        return False, before, before, 0
    return True, before, d, len(old_verts) - len(st.r_verts[victim])


# --------------------------------------------------------------------------- #
def optimize_case(g, nets, po, st, seconds, seed=0, log=print,
                  max_victims=3):
    """Directed search. Returns the best total found (state left at best)."""
    t0 = time.time()
    rng = random.Random(seed)
    n = st.nv
    fanout = [len(x["sinks"]) for x in nets]
    order = list(range(n))

    best_total = st.total
    best_snap = st.snap()

    iters = 0
    improves = 0
    rejects = 0
    no_blocker = 0

    while time.time() - t0 < seconds:
        iters += 1
        pre = st.snap()
        pre_total = st.total

        # ---- pick a detoured victim net, low-fanout first (they pay most) ----
        # rank nets by per-sink detour, descending, and bias to low fanout
        ranked = []
        for m in range(n):
            if fanout[m] == 0:
                continue
            bl = blockers(st, g, m)
            if bl:
                ranked.append((bl[0][0] / fanout[m], m, bl))
        if not ranked:
            no_blocker += 1
            break
        ranked.sort(key=lambda t: -t[0])
        k = min(max_victims, len(ranked))
        pick = ranked[rng.randrange(k)]
        _rank, m, bl = pick

        # ---- try to release the top few blockers of m ----
        moved = False
        forb = set()
        for (_d, _s, v, o) in bl[:4]:
            forb.add(v)
        victims = sorted({o for (_d, _s, _v, o) in bl[:4]})
        for vic in victims:
            ok, before, d, freed = release(st, g, vic, forb)
            if not ok or freed <= 0:
                continue
            moved = True
        if not moved:
            st.restore(pre)
            rejects += 1
            continue

        # ---- 1-opt sweep: everyone, lex tie-break (each to own optimum) ----
        rng.shuffle(order)
        for q in order:
            st.ripup(q)
            S.reroute(st, q, None)
        st.total = sum(st.ndelay)

        if st.total < best_total:
            best_total = st.total
            best_snap = st.snap()
            improves += 1
            log(f"    [it {iters}] IMPROVE {pre_total} -> {st.total} "
                f"(victim net {m}, released {len(forb)} blockers)")
        else:
            st.restore(pre)
            rejects += 1

    st.restore(best_snap)
    log(f"    iters={iters} improves={improves} rejects={rejects} "
        f"no_blocker={no_blocker} best={best_total} "
        f"elapsed={time.time()-t0:.1f}s")
    return best_total
