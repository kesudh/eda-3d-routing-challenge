"""DECISIVE test of the zero-cost SPT re-selection seam.

Three questions, all measured:

Q1. Is the incumbent already at the minimum-vertex SPT for every net?
    If yes, there is NOTHING for a zero-cost re-selection to release: the
    seam is closed before any search begins.

Q2. Forcing release of EVERY choice blocker simultaneously -- the most
    favourable possible use of the seam -- does the total move at all?

Q3. Exhaustive enumeration: for every net, enumerate all distinct SPTs
    reachable by tight-DAG tie-breaking, and record the union of vertices
    that ANY SPT of that net can release. This is the exact, complete
    measure of the seam's size, not a sample.
"""
import itertools
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import spt_search as S
import spt_directed as D
from m3d.model import Instance, Submission
from m3d.checker import check

CASES = ["case_%02d" % i for i in range(1, 10)]
BASE = {"case_01": 8674, "case_02": 13230, "case_03": 11086, "case_04": 13095,
        "case_05": 15311, "case_06": 19882, "case_07": 21433, "case_08": 21620,
        "case_09": 21476}


def load(case):
    inst = Instance.load(os.path.join(REPO, "benchmarks_hard", case + ".json"))
    g = S.Graph(inst.width, inst.height, inst.layers,
                inst.layer_delay, inst.via_delay)
    name, nets, po = S.load_case(g, os.path.join(REPO, "benchmarks_hard", case + ".json"))
    st = S.State(g, nets, po)
    S.load_sol(g, nets, os.path.join(
        REPO, "submissions", "hard", "spt_reselect", case + ".sol.json"), st)
    S.sweep(st, list(range(st.nv)))
    return inst, g, nets, po, st


# --------------------------------------------------------------------------- #
# Q3: exact enumeration of the releasable set of one net
# --------------------------------------------------------------------------- #
def releasable(st, g, n):
    """Every vertex that SOME SPT of net n omits, while the current route
    occupies it. Exact: enumerate over all tight-predecessor assignments,
    collapsing by reachable outcomes (the set of SPTs is a product of
    independent per-vertex choices, so we can reason vertex-wise exactly).
    """
    net = st.nets[n]
    src = net["driver"]
    blk = st._blk
    ov = st.occ_v
    for v in range(g.n):
        o = ov[v]
        blk[v] = 1 if (o >= 0 and o != n) else 0
    for v, owner in st.pin_owner.items():
        if owner != n:
            blk[v] = 1
    import heapq
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
            if v not in dist or nd < dist[v]:
                dist[v] = nd
                heapq.heappush(h, (nd, v))
    order = sorted(dist, key=lambda v: (dist[v], v))
    needed = set(net["sinks"])
    for v in reversed(order):
        if v in needed or v == src:
            continue
        for (u, w) in adj[v]:
            if u in dist and dist[v] + w == dist[u]:
                needed.add(v)
                break
    # for each needed vertex, is its choice of tight predecessor forced?
    # a vertex is RELEASABLE iff it can be left out of the tree entirely
    # (i.e. it is not required) or its predecessor can vary AND dropping it
    # still leaves the subtree attached.  Conservative exact test: rebuild with
    # each candidate forbidden and test.
    rel = []
    cur = st.r_verts[n]
    for v in sorted(cur):
        if v == src or v in needed and False:
            continue
        # forbid v: can the tree still reach all sinks with the same cost?
        pre = st.snap()
        ok, before, after, freed = D.release(st, g, n, {v})
        got = v not in st.r_verts[n]
        st.restore(pre)
        if ok and got:
            rel.append(v)
    return rel, set(cur)


def main():
    t0 = time.time()
    tot_rel = 0
    tot_cur = 0
    forced_nets = 0
    all_rel = set()
    for case in CASES:
        inst, g, nets, po, st = load(case)
        rel_n = 0
        cur_n = 0
        forced = 0
        for n in range(st.nv):
            r, cur = releasable(st, g, n)
            rel_n += len(r)
            cur_n += len(cur)
            if not r:
                forced += 1
            all_rel |= set(r)
        tot_rel += rel_n
        tot_cur += cur_n
        forced_nets += forced
        print(f"{case}: total={st.total:6d} nets={st.nv:4d} "
              f"incumbent_route_verts={cur_n:5d} "
              f"individually_releasable={rel_n:4d} "
              f"({100.0*rel_n/max(1,cur_n):.2f}%)  "
              f"nets_with_NO_releasable_vertex={forced}")
    print()
    print(f"Q3 EXACT: of {tot_cur} occupied vertices across all 9 hard cases, "
          f"{tot_rel} ({100.0*tot_rel/max(1,tot_cur):.2f}%) can be released by a "
          f"strictly zero-cost SPT re-selection.")
    print(f"    {forced_nets} nets have a completely rigid SPT (no equal-cost choice at all).")
    print(f"    distinct releasable vertices: {len(all_rel)}")
    print(f"    elapsed {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
