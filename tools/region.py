"""Region-constrained exact windows: solve the set of nets touching a spatial
box in the contended middle layers (z=2,3) exactly, rather than a random sample.

Motivation: on the hard tier z=2,3 run 81-90% occupied, so the contention that
costs delay is spatially local.  A window of every net that *touches* a small
contended region should therefore be a far stronger neighbourhood than the same
number of nets sampled at random.

Obstacle handling: nets outside the window keep their current routes and are
hard obstacles in the MIP (their vertices are blocked and their pins are
forbidden).  That is exactly the formulation in tools/mipbuild.py, so a region
window can reroute its nets *through* space vacated by nothing -- it cannot
displace an outside net.  This is reported explicitly in the log.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from m3d.checker import check
from m3d.grid import Grid

from mipwindow import (Vid, load_instance, load_pr3, sub_to_routes, routes_to_sub,
                       tree_delay, routes_legal_tree)
from mipbuild import WindowMIP

CASES = [f"case_0{i}" for i in range(1, 10)]


def congested_verts(grid: Grid, routes, radius: int = 2) -> List[Vid]:
    """Vertices in the middle layers that sit in a CROWDED neighbourhood.

    Note carefully: the challenge gives every 3D vertex and edge to at most one
    net, so two nets can never share a vertex -- measuring "shared" vertices
    always returns zero and is useless.  Contention is instead *crowding*:
    a vertex is expensive to use when many other nets already occupy the
    vertices right next to it.  So we count, for each vertex used in z=2,3,
    how many distinct OTHER nets occupy vertices within a Chebyshev radius.
    """
    owner: Dict[Vid, int] = {}
    for nid, es in routes.items():
        for (u, v) in es:
            owner.setdefault(u, nid)
            owner.setdefault(v, nid)
    g = grid
    out = []
    for x in owner:
        cx, cy, cz = g.coord(x)
        if cz not in (2, 3):
            continue
        cnt = 0
        for dz in (-radius, 0, radius):
            z = cz + dz
            if not (0 <= z < g.l):
                continue
            for dy in range(-radius, radius + 1):
                y = cy + dy
                if not (0 <= y < g.h):
                    continue
                for dx in range(-radius, radius + 1):
                    xx = cx + dx
                    if not (0 <= xx < g.w):
                        continue
                    o = owner.get(g.vid((xx, y, z)))
                    if o is not None and o != owner[x]:
                        cnt += 1
        if cnt:
            out.append((cnt, x))
    out.sort(reverse=True)
    return [x for _c, x in out]


def region_windows(grid: Grid, routes, pv, n_windows: int,
                   min_nets: int, max_nets: int, zs=(2, 3)) -> List[List[int]]:
    """Tile the congested vertices into a few spatial boxes and return, for each,
    the set of nets touching it (capped at max_nets)."""
    hot = congested_verts(grid, routes)
    if not hot:
        return []
    g = grid
    # cluster the hot vertices by (x,y) proximity via a simple grid of boxes
    cell = max(2, min(g.w, g.h) // 8)
    boxes: Dict[Tuple[int, int], Set[Vid]] = {}
    for x in hot:
        cx, cy, _cz = g.coord(x)
        key = (cx // cell, cy // cell)
        boxes.setdefault(key, set()).add(x)

    out = []
    for key in sorted(boxes, key=lambda k: -len(boxes[k])):
        if len(out) >= n_windows:
            break
        bx, by = key
        x0, x1 = bx * cell, bx * cell + cell - 1
        y0, y1 = by * cell, by * cell + cell - 1
        region: Set[Vid] = set()
        for z in range(g.l):
            for y in range(max(0, y0), min(g.h, y1 + 1)):
                for x in range(max(0, x0), min(g.w, x1 + 1)):
                    region.add(g.vid((x, y, z)))
        touch = {nid for nid, es in routes.items()
                 if any(u in region or v in region for (u, v) in es)}
        touch = sorted(touch)
        if len(touch) < min_nets:
            continue
        out.append(touch[:max_nets])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="case_01")
    ap.add_argument("--time-limit", type=float, default=600.0, dest="time_limit")
    ap.add_argument("--n-windows", type=int, default=4, dest="n_windows")
    ap.add_argument("--min-nets", type=int, default=4, dest="min_nets")
    ap.add_argument("--max-nets", type=int, default=10, dest="max_nets")
    ap.add_argument("--detour", type=int, default=0)
    ap.add_argument("--threads", type=int, default=20)
    ap.add_argument("--out", default="runs/region")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    summary = {}
    for case in args.cases.split(","):
        inst = load_instance(case)
        grid = Grid(inst)
        pv = inst.pin_vertex()
        base = sub_to_routes(load_pr3(case), grid)
        nets = {n.id: n for n in inst.nets}
        chk = check(inst, routes_to_sub(inst, grid, base))
        best = {k: list(v) for k, v in base.items()}
        best_total = chk.total_delay
        wins = region_windows(grid, best, pv, args.n_windows,
                              args.min_nets, args.max_nets)
        log = {"case": case, "pr3_total": best_total,
               "outside_window_obstacles": True,
               "n_hot_verts": len(congested_verts(grid, best)),
               "windows": []}
        cpu0 = time.process_time()
        for wi, w in enumerate(wins):
            m = WindowMIP(inst, grid, best, w, time_limit=args.time_limit,
                          threads=args.threads, detour=(args.detour or None))
            b = m.build()
            rec = {"window": wi, "n_nets": len(w),
                   "build": {k: b.get(k) for k in ("status", "n_arcs", "n_vars",
                                                   "n_rows", "build_s",
                                                   "arcs_per_net")}}
            if b.get("status") == "built":
                r = m.solve()
                rec.update({k: v for k, v in r.items() if k != "ub"})
                if m.sol_values is not None and r.get("best_cost") is not None:
                    newr = {k: list(v) for k, v in best.items()}
                    newr.update(m.refine_routes(m.sol_values))
                    wnets = [nets[i] for i in w]
                    ok, why = routes_legal_tree(inst, grid, newr, wnets)
                    c2 = check(inst, routes_to_sub(inst, grid, newr))
                    rec["screen"] = ok; rec["screen_why"] = why
                    rec["legal"] = c2.legal
                    rec["total"] = c2.total_delay
                    if c2.legal and c2.total_delay < best_total:
                        best = newr
                        best_total = c2.total_delay
                        rec["ACCEPTED"] = True
            log["windows"].append(rec)
            st = rec.get("status")
            print(f"{case} w{wi} n={rec['n_nets']} ub={rec.get('lns_cost')} "
                  f"status={st} proven={rec.get('proven')} "
                  f"mip={rec.get('best_cost')} gap={rec.get('mip_gap')} "
                  f"vars={rec['build'].get('n_vars')} "
                  f"solve={rec.get('solve_s', 0):.1f}s", flush=True)
        final = check(inst, routes_to_sub(inst, grid, best))
        log["best_total"] = final.total_delay
        log["legal"] = final.legal
        log["delta"] = best_total and (chk.total_delay - final.total_delay)
        log["cpu_s"] = time.process_time() - cpu0
        summary[case] = log
        print(f"{case}: pr3={chk.total_delay} best={final.total_delay} "
              f"legal={final.legal} cpu={log['cpu_s']:.1f}s", flush=True)
        if final.total_delay < chk.total_delay:
            with open(os.path.join(args.out, f"{case}.sol.json"), "w") as fh:
                json.dump(routes_to_sub(inst, grid, best).to_dict(), fh)
    with open(os.path.join(args.out, "results.json"), "w") as fh:
        json.dump({"args": vars(args), "summary": summary}, fh, indent=1)
    print("TOTALS:", {c: (v["pr3_total"], v["best_total"]) for c, v in summary.items()})


if __name__ == "__main__":
    main()
