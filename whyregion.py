"""Why do REGION windows not close when RANDOM windows of the same size do?

The earlier random 8-net windows closed in 9-221 CPU-s. An 8-net region window
(48,710 vars) hit a 240s limit with no feasible incumbent. Hypothesis: a region
window concentrates on the contended z=2,3 layers where many more shortest paths
are TIED, so the branch-and-bound tree is much larger for the same variable count.

Metric: TIGHTNESS = fraction of residual-graph arcs lying on a shortest path.
Higher tightness => more equally-optimal alternatives => bigger search tree.
"""
import os
import random
import sys

# IMPORT-ORDER TRAP (documented in mip-window/findings.md §7): mipwindow.py needs
# edge_delay from m3d.grid, which only exists in THIS worktree's patched copy.
# The main repo's m3d/ must never win. Put the worktree first, before chdir.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"F:\eda-3d-routing-challenge\benchmarks_hard")

from m3d.grid import Grid
from mipwindow import (RGraph, dijkstra, load_instance, load_pr3,
                       multi_source_dijkstra, sub_to_routes)
from region import region_windows


def tightness(nids, routes, inst, g, pv, label):
    fixed = set()
    for nid, es in routes.items():
        if nid in nids:
            continue
        for (u, v) in es:
            fixed.add(u)
            fixed.add(v)
    for n in inst.nets:
        if n.id in nids:
            continue
        fixed.add(g.vid(pv[n.driver]))
        for s in n.sinks:
            fixed.add(g.vid(pv[s]))
    rg = RGraph(g, fixed)
    # global tightness w.r.t. one representative source is not meaningful across
    # nets; measure per window net and average.
    tot_t = tot_r = 0
    for nid in nids:
        n = next(x for x in inst.nets if x.id == nid)
        drv = g.vid(pv[n.driver])
        sk = [g.vid(pv[s]) for s in n.sinks]
        A = dijkstra(rg, drv)
        if any(s not in A for s in sk):
            continue
        for u in A:
            for (v, w) in rg.nbrs(u):
                tot_r += 1
                if v in A and A[u] + w == A[v]:
                    tot_t += 1
    pct = 100.0 * tot_t / max(tot_r, 1)
    print(f"  {label:<28} tight arcs {tot_t:6d}/{tot_r:6d} = {pct:5.1f}%")
    return pct


def main():
    inst = load_instance("case_01")
    g = Grid(inst)
    pv = inst.pin_vertex()
    routes = sub_to_routes(load_pr3("case_01"), g)

    print("TIGHTNESS of the residual graph (fraction of arcs on a shortest path)")
    print("Higher tightness = more tied alternatives = larger B&B tree.\n")

    rw = region_windows(g, routes, pv, 1, 8, 8)
    res = []
    if rw:
        res.append(("REGION w8 (z=2,3 crowded)",
                    tightness(set(rw[0]), routes, inst, g, pv,
                              "REGION w8 (z=2,3 crowded)")))
    rng = random.Random(5)
    alln = sorted(routes)
    for t in range(3):
        s = set(rng.sample(alln, 8))
        res.append((f"RANDOM w8 #{t}",
                    tightness(s, routes, inst, g, pv, f"RANDOM w8 #{t}")))

    if res:
        avg_reg = res[0][1]
        avg_rnd = sum(v for _, v in res[1:]) / max(len(res) - 1, 1)
        print(f"\n  region avg {avg_reg:.1f}%   random avg {avg_rnd:.1f}%")
        if avg_reg > avg_rnd:
            print("  => region windows ARE tighter, so the same variable count hides")
            print("     a much larger search tree. That explains no incumbent at 240s.")
        else:
            print("  => tightness does NOT explain it; something else (obstacle")
            print("     fragmentation / disconnected residual components) is at work.")


if __name__ == "__main__":
    main()
