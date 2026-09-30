"""ARBITER: run EXACT 2-net corridor transactions on the heaviest contending
pairs, using the mip-window agent's already-validated MIP builder.

A 2-net transaction is the minimal instance of lead (a): the MIP optimises both
nets JOINTLY as an integer multicommodity flow, so it explores every exchange of
assignments between them, including states where BOTH nets end non-SPT --
exactly the states a per-net reroute provably cannot express.

The W=8 MIPs took 9-90 s and reached 17k-100k vars.  A W=2 model should be
~50x smaller, so hundreds of pairs are affordable.  If the transaction finds
delta > 0 anywhere, lead (a) is live and we have an improvement.  If it returns
delta 0 / infeasible on the heaviest pairs, that is a rigorous proof that those
transactions are dead, at negligible cost.

Usage: pairtx.py <case> [n_pairs] [detour]
"""
import os, sys, json, time, itertools, collections

MW = r"F:\eda3d-wt\mip-window"
# the mip-window worktree carries a PATCHED m3d/grid.py (adds edge_delay);
# it MUST win over the main repo's copy, so insert it LAST (path[0] wins).
sys.path.insert(0, r"F:\eda-3d-routing-challenge")
sys.path.insert(0, os.path.join(MW, "tools"))
sys.path.insert(0, MW)

from m3d.model import Instance, Submission
from m3d.grid import Grid
from mipbuild import WindowMIP
from mipwindow import sub_to_routes

HARD = r"F:\eda-3d-routing-challenge\benchmarks_hard"
PR3 = os.path.join(MW, "runs", "sub_pr3_baseline")


def enc(i, c): return (c[2] * i.height + c[1]) * i.width + c[0]


def net_delay_from_edges(inst, grid, routes, net):
    """Recompute a net's delay from its flat-vid edge list (checker-identical)."""
    from mipwindow import tree_delay
    pv = inst.pin_vertex()
    return tree_delay(routes[net.id], grid, net, pv)


def main():
    case = sys.argv[1] if len(sys.argv) > 1 else "case_01"
    npairs = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    detour = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    tl = float(os.environ.get("TL", "60"))

    inst = Instance.load(os.path.join(HARD, case + ".json"))
    sub = Submission.load(os.path.join(PR3, case + ".sol.json"))
    grid = Grid(inst)
    routes = sub_to_routes(sub, grid)   # flat Vid edges, as the MIP expects
    nets = {n.id: n for n in inst.nets}
    delay = {i: net_delay_from_edges(inst, grid, routes, nets[i]) for i in routes}
    tot = sum(delay.values())
    print(f"{case}: PR#3 total {tot}, {len(routes)} nets, delay validated")

    # contending pairs: middle-layer (z=2,3) Chebyshev proximity <= 3
    WH = inst.width * inst.height
    mid = {}
    for i, e in routes.items():
        vs = set()
        for (a, b) in e: vs.add(a); vs.add(b)   # already flat vids
        mid[i] = {v for v in vs if (v // WH) in (2, 3)}
    pairs = []
    for a, b in itertools.combinations(sorted(routes), 2):
        ma, mb = mid[a], mid[b]
        if not ma or not mb: continue
        hit = False
        for v in ma:
            r = v % WH; x, y = r % inst.width, r // inst.width
            for u in mb:
                ru = u % WH
                if abs(x - ru % inst.width) <= 3 and abs(y - ru // inst.width) <= 3:
                    hit = True; break
            if hit: break
        if hit: pairs.append((a, b))
    pairs.sort(key=lambda p: -(delay[p[0]] + delay[p[1]]))
    print(f"  {len(pairs)} contending pairs; running exact MIP on the "
          f"{min(npairs,len(pairs))} heaviest (detour={detour}, tl={tl}s)")

    t0 = time.time()
    proven = infeas = better = timeout = 0
    deltas = []
    for k, (a, b) in enumerate(pairs[:npairs]):
        try:
            mip = WindowMIP(inst, grid, routes, [a, b], time_limit=tl,
                            threads=4, detour=(None if detour == 0 else detour))
            mip.build()
            out = mip.solve()
            nvars = out.get("n_vars")
        except Exception as e:
            print(f"   pair ({a},{b}) ERROR {e}"); continue
        st = out.get("status")
        if st == "infeasible":
            proven += 1
        elif st == "optimal" or st == "feasible":
            c = out.get("best_cost")
            if c is not None and c < mip.ub - 0.5:
                better += 1; deltas.append(mip.ub - c)
                print(f"   *** IMPROVEMENT pair ({a},{b}): {mip.ub} -> {c} "
                      f"(delta {mip.ub-c})")
            else:
                infeas += 1
        else:
            timeout += 1
        if (k + 1) % 10 == 0:
            print(f"   [{a},{b}] vars={nvars} arcs={out.get('n_arcs')} raw={out.get('raw_status')} {out.get('solve_s',0):.1f}s")
            print(f"   ...{k+1}/{min(npairs,len(pairs))} proven={proven} "
                  f"better={better} open/timeout={timeout} "
                  f"elapsed={time.time()-t0:.0f}s")
    print(f"DONE {case}: {min(npairs,len(pairs))} exact 2-net transactions, "
          f"proven-infeasible={proven}, improved={better}, open={timeout}, "
          f"wall={time.time()-t0:.0f}s")
    if deltas:
        print("  DELTAS FOUND:", deltas)


if __name__ == "__main__":
    main()
