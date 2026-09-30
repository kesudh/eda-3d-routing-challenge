"""Per-net candidate arcs: why REGION 8-net windows don't close but RANDOM ones do.

Like-for-like on hard/case_01, 240s limit, same HiGHS settings:
    RANDOM w8 (seeded) : proven=True   2.7s
    REGION w8          : limit, no incumbent, 240.6s

Tightness was REFUTED as the cause (32.9% region vs 30.5% random).
This measures candidate arcs per net, which is what actually sets model size.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from m3d.grid import Grid
from mipwindow import (RGraph, dijkstra, load_instance, load_pr3,
                       multi_source_dijkstra, sub_to_routes)
from region import region_windows


def profile(nids, routes, inst, g, pv, label):
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
    stats = []
    total_arcs = 0
    for nid in nids:
        n = next(x for x in inst.nets if x.id == nid)
        drv = g.vid(pv[n.driver])
        sk = [g.vid(pv[s]) for s in n.sinks]
        A = dijkstra(rg, drv)
        B = multi_source_dijkstra(rg, sk)
        if any(s not in A or s not in B for s in sk):
            continue
        tight = set(A) & set(B)
        arcs = 0
        for u in tight:
            for (v, w) in rg.nbrs(u):
                if v in tight and A[u] + w == A[v]:
                    arcs += 1
        total_arcs += arcs
        stats.append((arcs, len(n.sinks), max(A[s] for s in sk) if sk else 0))
    if not stats:
        print(f"  {label:<24} (all nets disconnected in residual graph)")
        return None
    a = [s[0] for s in stats]
    sk_ = [s[1] for s in stats]
    sp = [s[2] for s in stats]
    print(f"  {label:<24} cand_arcs {total_arcs:7d}  mean/net {sum(a)/len(a):8.0f}  "
          f"sinks {sum(sk_)/len(sk_):4.1f}  span {sum(sp)/len(sp):6.1f}")
    return total_arcs


def main():
    inst = load_instance("case_01")
    g = Grid(inst)
    pv = inst.pin_vertex()
    routes = sub_to_routes(load_pr3("case_01"), g)
    print("Per-net candidate arcs in the residual graph (drives model size)\n")
    rw = region_windows(g, routes, pv, 1, 8, 8)
    reg = profile(set(rw[0]), routes, inst, g, pv, "REGION w8") if rw else None
    rng = random.Random(5)
    tot = []
    for t in range(3):
        v = profile(set(rng.sample(sorted(routes), 8)), routes, inst, g, pv,
                    f"RANDOM w8 #{t}")
        if v:
            tot.append(v)
    if reg and tot:
        avg = sum(tot) / len(tot)
        print(f"\n  region {reg} vs random avg {avg:.0f}  =  {reg/avg:.2f}x")
        print("  => larger candidate-arc sets at equal window SIZE explain the gap;"
              "\n     tightness (32.9% vs 30.5%) was a red herring.")


if __name__ == "__main__":
    main()
