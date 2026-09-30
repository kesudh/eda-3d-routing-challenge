"""Sequential repair driver.

Per iteration:
  1. starved nets = nets above their obstacle-free optimum
  2. contested cells in the cheap middle layers that those nets want but do not
     own, tagged with the victim net that currently holds them
  3. evaluate EVERY transaction -- single-cell, whole-cluster, and the
     zero-cost plateau -- and keep the single best strictly-improving one
     (STEEPEST descent, not first-improvement)
  4. commit it, re-verify through m3d/checker.py, continue
  5. global 1-opt to fixpoint (expected no-op; we check)
  6. stop when nothing improves or the budget runs out

evaluate()/plateau() are pure, so a rejected candidate cannot corrupt state.
"""
from __future__ import annotations
import argparse, json, os, random, sys, time
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seqrepair.baseline import load
from seqrepair.search import Solver
from seqrepair.engine import verify_state

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PEN = (2, 4, 8, 16, 64, 256)


def one_opt(st, sv):
    moved = 0
    for _ in range(20):
        ch = 0
        for n in sv.nets:
            v, e, sd = sv.reroute(n, sv.mask_for(n))
            if v is None:
                continue
            nd = sum(sd)
            if nd < st.delay[n]:
                st._commit(n, v, e, nd)
                ch += 1
        moved += ch
        if ch == 0:
            break
    return moved


def cluster_moves(tri):
    byAB = defaultdict(set)
    for A, B, c in tri:
        byAB[(A, B)].add(c)
    return [(A, B, tuple(sorted(cs))) for (A, B), cs in byAB.items()]


def descend(st, sv, case, max_iters, budget, plateau_trials, rng):
    t0 = time.time()
    base = st.total()
    iters = evals = committed = 0
    hist = Counter()
    best_hist = None
    while iters < max_iters and time.time() - t0 < budget:
        iters += 1
        starved = sv.starved()
        if not starved:
            break
        tri = sv.contested(starved)
        best = None

        # (a) single-cell and (b) whole-cluster forced-cell transactions
        for A, B, cs in [(A, B, (c,)) for A, B, c in tri] + cluster_moves(tri):
            for pen in PEN:
                r = sv.evaluate(A, cs, pen)
                evals += 1
                if r is None:
                    hist["inapplicable"] += 1
                    continue
                d = r["net_delta"]
                hist["improve" if d < 0 else "equal" if d == 0 else "worse"] += 1
                if d < 0 and (best is None or d < best[0]):
                    best = (d, A, B, len(cs), pen, r)
                break

        # (c) zero-cost plateau: randomised equal-delay tie-breaking
        victims = sorted({A for A, _, _ in tri})
        for _ in range(plateau_trials):
            A = rng.choice(victims)
            rv = sv.randvec(rng)
            r = sv.plateau(A, rv)
            evals += 1
            if r is None:
                hist["plateau_noop"] += 1
                continue
            d = r["net_delta"]
            hist["plateau_gain" if d < 0 else "plateau_flat"] += 1
            if d < 0 and (best is None or d < best[0]):
                best = (d, A, -1, 0, 0, r)

        if best is None:
            best_hist = dict(hist)
            break
        d, A, B, nc, pen, r = best
        sv.apply(r["commits"])
        committed += 1
        cur = st.total()
        assert cur == base + d, (cur, base, d)
        base = cur
        verify_state(st, f"{case}-iter{iters}")
        print(f"  [{case}] iter {iters}: A={A} B={B} cells={nc} pen={pen} "
              f"cost={r['cost']} gain={r['gain']} nets={r['n_nets']} "
              f"-> {base}", flush=True)
    return base, {"iters": iters, "evals": evals, "committed": committed,
                  "histogram": best_hist or dict(hist),
                  "secs": round(time.time() - t0, 1)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", nargs="*", default=None)
    ap.add_argument("--max-iters", type=int, default=30)
    ap.add_argument("--budget", type=float, default=900.0)
    ap.add_argument("--plateau", type=int, default=200)
    ap.add_argument("--cost-cap", type=float, default=12)
    ap.add_argument("--seed", type=int, default=12345)
    a = ap.parse_args()
    cases = a.cases or [f"case_0{i}" for i in range(1, 10)]
    rng = random.Random(a.seed)
    grand = 0
    summary = []
    for c in cases:
        inst, g, st = load(c)
        sv = Solver(inst, g, st)
        sv.cost_cap = a.cost_cap
        base0 = st.total()
        bt, stats = descend(st, sv, c, a.max_iters, a.budget, a.plateau, rng)
        mv = one_opt(st, sv)
        _, final = verify_state(st, c + "-final")
        print(f"{c}: pr5={base0} -> {final}  (1opt_moved={mv})  {stats}", flush=True)
        summary.append({"case": c, "pr5": base0, "final": final, "stats": stats})
        grand += final
    print(f"\nTOTAL {grand}   (target to beat 145305)")
    with open(os.path.join(ROOT, "work", "descent_summary.json"), "w") as fh:
        json.dump(summary, fh, indent=1)
