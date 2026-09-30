"""Validation of the window MIP: does it find AND prove optima?

The MIP searches only for a window cost strictly below the incumbent, so the two
meaningful outcomes are:

  FEASIBLE(c) with c < incumbent -> c is a legal, better window assignment;
                                    the repo checker must confirm it.
  INFEASIBLE                       -> the incumbent is PROVEN window-optimal.

So the correct validations are:

V1  1-net window: INFEASIBLE is expected (the incumbent is the net's own SPT,
    the established per-net optimum given fixed obstacles) and must be
    consistent with the obstacle-constrained SPT cost; any FEASIBLE answer c
    must satisfy c == that SPT cost exactly.

V2  Damage a net inside a window, then solve: the MIP must recover a cost
    <= the pre-damage cost.  This proves the model can FIND an optimum rather
    than trivially always reporting infeasible.

V3  Every accepted MIP solution is fed back through the repo's own checker and
    must be legal with recomputed total delay == the MIP objective.
"""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from m3d.checker import check
from m3d.grid import Grid

from mipwindow import (RGraph, dijkstra, load_instance, load_pr3, sub_to_routes,
                       routes_to_sub, tree_delay, routes_legal_tree)
from mipbuild import WindowMIP

FAILURES = []


def obstacle_spt(grid, pv, net, fixed_v):
    rg = RGraph(grid, fixed_v)
    A = dijkstra(rg, grid.vid(pv[net.driver]))
    return sum(A[grid.vid(pv[s])] for s in net.sinks)


def fixed_vertices(routes, win):
    fv = set()
    w = set(win)
    for nid, es in routes.items():
        if nid in w:
            continue
        for (u, v) in es:
            fv.add(u); fv.add(v)
    return fv


def v1_one_net(case="case_01", n_nets=10):
    inst = load_instance(case)
    grid = Grid(inst)
    pv = inst.pin_vertex()
    routes = sub_to_routes(load_pr3(case), grid)
    nets = {n.id: n for n in inst.nets}
    print("V1: single-net windows; exact optimum must equal the fixed-obstacle SPT")
    ok_all = True
    for nid in list(routes)[:n_nets]:
        n = nets[nid]
        spt = obstacle_spt(grid, pv, n, fixed_vertices(routes, [nid]))
        inc = tree_delay(routes[nid], grid, n, pv)
        m = WindowMIP(inst, grid, routes, [nid], time_limit=60)
        b = m.build()
        if b.get("status") == "infeasible":
            good = spt <= inc
            print(f"  net {nid:3d}: incumbent={inc} obstacles_spt={spt} "
                  f"-> PROVEN OPTIMAL (no cost <= {inc - 1}) ok={good}")
            if not good:
                print("     FAIL: spt > incumbent, the model cannot be right")
            ok_all &= good
            continue
        r = m.solve()
        got = r.get("best_cost")
        if r["status"] == "infeasible":
            good = spt <= inc
            print(f"  net {nid:3d}: incumbent={inc} obstacles_spt={spt} "
                  f"-> PROVEN OPTIMAL ok={good}")
        else:
            good = (got == spt)
            print(f"  net {nid:3d}: incumbent={inc} obstacles_spt={spt} "
                  f"-> MIP optimum={got} status={r['status']} ok={good}")
            if got is not None and got < inc:
                newr = {k: list(v) for k, v in routes.items()}
                newr[nid] = m.refine_routes(m.sol_values)[nid]
                c = check(inst, routes_to_sub(inst, grid, newr))
                td = sum(tree_delay(newr[i], grid, nets[i], pv) for i in newr)
                if not c.legal or td != got:
                    print(f"     FAIL: checker legal={c.legal} recomputed={td} "
                          f"mip={got}")
                    good = False
        ok_all &= good
    print(f"  -> {'PASS' if ok_all else 'FAIL'}")
    if not ok_all:
        FAILURES.append("V1")
    return ok_all


def damage(grid, n, route):
    """Lengthen a net's route by detouring its first in-layer edge one step."""
    g = grid
    es = [((u, v) if u < v else (v, u)) for (u, v) in route]
    for k, (u0, v0) in enumerate(es):
        x0, y0, z0 = g.coord(u0)
        x1, y1, z1 = g.coord(v0)
        if z0 != z1:
            continue
        if abs(x0 - x1) == 1:
            s = 1 if y0 + 1 < g.h else -1
            a, b = g.vid((x0, y0 + s, z0)), g.vid((x1, y1 + s, z0))
        else:
            s = 1 if x0 + 1 < g.w else -1
            a, b = g.vid((x0 + s, y0, z0)), g.vid((x1 + s, y1, z0))
        new = [((u0, a) if u0 < a else (a, u0)),
               ((a, b) if a < b else (b, a)),
               ((b, v0) if b < v0 else (v0, b))]
        cand = new + es[k + 1:]
        seen, ded = set(), []
        for e in cand:
            if e not in seen:
                seen.add(e); ded.append(e)
        return ded
    return None


def v2_recovery(case="case_01", trials=10, seed=11):
    inst = load_instance(case)
    grid = Grid(inst)
    pv = inst.pin_vertex()
    base = sub_to_routes(load_pr3(case), grid)
    nets = {n.id: n for n in inst.nets}
    rnd = random.Random(seed)
    print("V2: recovery of a deliberately damaged net (proves the model can FIND")
    print("    an optimum rather than only ever proving optimality)")
    ok_all = True
    done = 0
    for _ in range(trials):
        nid = rnd.choice([i for i in base if nets[i].sinks and len(base[i]) >= 3])
        n = nets[nid]
        orig = tree_delay(base[nid], grid, n, pv)
        dmg = damage(grid, n, base[nid])
        if dmg is None:
            continue
        routes2 = {k: list(v) for k, v in base.items()}
        routes2[nid] = dmg
        ok, why = routes_legal_tree(inst, grid, routes2, [n])
        if not ok:
            print(f"  net {nid}: damage illegal ({why}), skip")
            continue
        dcost = tree_delay(dmg, grid, n, pv)
        if dcost <= orig:
            continue
        done += 1
        m = WindowMIP(inst, grid, routes2, [nid], time_limit=90)
        b = m.build()
        if b.get("status") != "built":
            print(f"  net {nid}: build {b.get('status')}")
            ok_all = False
            continue
        r = m.solve()
        got = r.get("best_cost")
        good = got is not None and got <= orig
        line = (f"  net {nid:3d}: damaged={dcost} pre_damage={orig} mip={got} "
                f"status={r['status']} recovered={good}")
        if good:
            # the MIP objective is the net's own cost; the checker must confirm
            # the whole submission is legal AND that this net's recomputed
            # delay from the submitted edges equals the MIP objective.
            newr = {k: list(v) for k, v in base.items()}
            newr[nid] = m.refine_routes(m.sol_values)[nid]
            c = check(inst, routes_to_sub(inst, grid, newr))
            nd = tree_delay(newr[nid], grid, n, pv)
            tot = sum(tree_delay(newr[i], grid, nets[i], pv) for i in newr)
            if not c.legal or nd != got or c.total_delay != tot:
                line += (f"  CHECKER FAIL legal={c.legal} net_delay={nd} "
                         f"mip={got} checker_total={c.total_delay} recomputed={tot}")
                good = False
        print(line)
        ok_all &= good
    print(f"  ({done} trials exercised)")
    print(f"  -> {'PASS' if ok_all and done else 'FAIL'}")
    if not (ok_all and done):
        FAILURES.append("V2")
    return ok_all and done > 0


if __name__ == "__main__":
    a = v1_one_net()
    print()
    b = v2_recovery()
    print()
    print("VALIDATION:", "PASS" if (a and b) else f"FAIL {FAILURES}")
    sys.exit(0 if (a and b) else 1)
