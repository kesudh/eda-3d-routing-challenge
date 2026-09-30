"""Driver: exact MIP window optimisation of the M3D hard tier.

Iterates windows over the current best routing, converting every MIP solution
back to a legal edge list and verifying it with the repo's own checker before
accepting it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from m3d.checker import check
from m3d.grid import Grid
from m3d.model import Instance

from mipwindow import (load_instance, load_pr3, sub_to_routes, routes_to_sub,
                       tree_delay, routes_legal_tree)
from mipbuild import WindowMIP
from winpick import window_nets

CASES = [f"case_0{i}" for i in range(1, 10)]


def case_delay(inst: Instance, routes) -> int:
    pv = inst.pin_vertex()
    return sum(tree_delay(routes[n.id], inst_grid[id(inst)], n, pv) for n in inst.nets)


_inst_grid: Dict[int, Grid] = {}
inst_grid = _inst_grid


def total_delay(inst: Instance, grid: Grid, routes) -> int:
    pv = inst.pin_vertex()
    return sum(tree_delay(routes[n.id], grid, n, pv) for n in inst.nets)


def solve_case(case: str, args) -> Dict:
    inst = load_instance(case)
    grid = Grid(inst)
    _inst_grid[id(inst)] = grid
    base = load_pr3(case)
    routes = sub_to_routes(base, grid)

    # sanity: PR#3's own routes must be a legal screen-pass and match the target
    ok, why = routes_legal_tree(inst, grid, routes, inst.nets)
    chk = check(inst, routes_to_sub(inst, grid, routes))
    start_total = chk.total_delay
    log = {"case": case, "pr3_total": start_total, "pr3_legal": chk.legal,
           "pr3_screen": ok, "pr3_why": why, "nets": len(inst.nets),
           "grid": [inst.width, inst.height, inst.layers], "rounds": []}

    best_routes = {k: list(v) for k, v in routes.items()}
    best_total = start_total
    cpu0 = time.process_time()
    wall0 = time.time()
    for rnd in range(args.rounds):
        strat = args.strategy if rnd == 0 else args.strategy2
        w = window_nets(inst, best_routes, grid, args.window, strat, args.seed + rnd)
        m = WindowMIP(inst, grid, best_routes, w, time_limit=args.time_limit,
                      threads=args.threads, verbose=args.verbose,
                      detour=(args.detour or None))
        b = m.build()
        if b.get("status") == "infeasible":
            log["rounds"].append({"round": rnd, "window": w, "strategy": strat,
                                  "status": "infeasible", "reason": b.get("reason"),
                                  "lns_cost": m.ub})
            continue
        r = m.solve()
        rec = {"round": rnd, "window": w, "strategy": strat, "n_win": len(w),
               **{k: v for k, v in r.items()}}
        if m.sol_values is not None and r.get("best_cost") is not None:
            cand = dict(best_routes)
            refined = m.refine_routes(m.sol_values)
            newr = {k: list(v) for k, v in best_routes.items()}
            newr.update(refined)
            ok2, why2 = routes_legal_tree(inst, grid, newr,
                                          [inst_nets_by_id(inst, i) for i in w])
            sub2 = routes_to_sub(inst, grid, newr)
            c2 = check(inst, sub2)
            rec["legal_after"] = c2.legal
            rec["legal_reasons"] = c2.reasons[:3]
            rec["screen"] = ok2
            rec["screen_why"] = why2
            rec["total"] = c2.total_delay
            if c2.legal and c2.total_delay is not None and c2.total_delay < best_total:
                best_routes = newr
                best_total = c2.total_delay
                rec["ACCEPTED"] = True
        log["rounds"].append(rec)
        if best_total == start_total and rnd >= 1 and args.early_stop:
            pass
    log["best_total"] = best_total
    log["delta_vs_pr3"] = start_total - best_total
    log["cpu_s"] = time.process_time() - cpu0
    log["wall_s"] = time.time() - wall0
    return {"log": log, "inst": inst, "grid": grid,
            "sub": routes_to_sub(inst, grid, best_routes)}


_nets_cache: Dict[int, Dict] = {}


def inst_nets_by_id(inst: Instance, i: int):
    if id(inst) not in _nets_cache:
        _nets_cache[id(inst)] = {n.id: n for n in inst.nets}
    return _nets_cache[id(inst)][i]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="all")
    ap.add_argument("--window", type=int, default=8)
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--time-limit", type=float, default=120.0, dest="time_limit")
    ap.add_argument("--strategy", default="seeded")
    ap.add_argument("--strategy2", default="contended")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--out", default="")
    ap.add_argument("--detour", type=int, default=0, help="0 = proof mode")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    cases = CASES if args.cases == "all" else args.cases.split(",")
    outdir = args.out or f"runs/w{args.window}_{args.strategy}"
    os.makedirs(outdir, exist_ok=True)
    rpath = os.path.join(outdir, "results.json")
    # resume: keep results already computed so a killed run loses nothing
    results = {}
    tot_pr3 = tot_best = 0
    if os.path.exists(rpath):
        try:
            prev = json.load(open(rpath))
            results = prev.get("results", {})
            for c, log in results.items():
                tot_pr3 += log["pr3_total"]
                tot_best += log["best_total"]
        except Exception:
            results = {}
    for c in cases:
        if c in results:
            print(f"{c}: cached pr3={results[c]['pr3_total']} "
                  f"best={results[c]['best_total']} delta="
                  f"{results[c]['delta_vs_pr3']}")
            continue
        r = solve_case(c, args)
        log = r["log"]
        if log["best_total"] < log["pr3_total"]:
            with open(os.path.join(outdir, f"{c}.sol.json"), "w") as fh:
                json.dump(r["sub"].to_dict(), fh)
        results[c] = log
        tot_pr3 += log["pr3_total"]
        tot_best += log["best_total"]
        with open(rpath, "w") as fh:      # flush after every case
            json.dump({"args": vars(args), "results": results,
                       "tot_pr3": tot_pr3, "tot_best": tot_best}, fh, indent=1)
        print(f"{c}: pr3={log['pr3_total']} best={log['best_total']} "
              f"delta={log['delta_vs_pr3']} cpu={log['cpu_s']:.1f}s", flush=True)
        for rd in log["rounds"]:
            print(f"   r{rd['round']} {rd['strategy']:>10} n={rd.get('n_win')} "
                  f"status={rd.get('status')} lns={rd.get('lns_cost')} "
                  f"mip={rd.get('best_cost')} proven={rd.get('proven')} "
                  f"gap%={rd.get('gap_pct')} solve={rd.get('solve_s', 0):.1f}s",
                  flush=True)
    print(f"TOTAL pr3={tot_pr3} best={tot_best} delta={tot_pr3 - tot_best}")


if __name__ == "__main__":
    main()
