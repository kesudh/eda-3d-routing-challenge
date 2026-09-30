"""Driver: dual-guided primal routing + checker-verified scoring."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from m3d.checker import check  # noqa: E402
from m3d.model import Instance, Submission  # noqa: E402

from bound import DualProblem  # noqa: E402
from primal import Router, order_nets, route_all, verts_to_submission  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="benchmarks_hard")
    ap.add_argument("--cases", default=None)
    ap.add_argument("--dual-iters", type=int, default=250)
    ap.add_argument("--outdir", default="submissions/lagrangian/hard")
    args = ap.parse_args()

    suite = json.load(open(os.path.join(args.suite, "suite.json")))
    os.makedirs(args.outdir, exist_ok=True)
    tot = 0
    for c in suite["cases"]:
        name = c["name"]
        if args.cases and name not in args.cases.split(","):
            continue
        t0 = time.time()
        inst = Instance.load(os.path.join(args.suite, c["instance_file"]))
        prob = DualProblem(inst, rounds=0)
        floor = prob.floor()
        best_val, mu = prob.ascent(iters=args.dual_iters)
        # collapse the per-pair prices into a per-net vertex price
        prices = {}
        for p in prob.pairs:
            if mu[p.idx]:
                prices.setdefault(p.net, {})
                for v, val in mu[p.idx].items():
                    prices[p.net][v] = prices[p.net].get(v, 0.0) + val
        router = Router(inst, prob)
        order = order_nets(router)
        best = None
        best_delay = None
        w = 4.0
        while w < 4000.0:
            verts = route_all(router, prices, order, w)
            if verts is not None:
                sub = verts_to_submission(inst, verts)
                res = check(inst, sub)
                if res.legal and (best_delay is None or res.total_delay < best_delay):
                    best, best_delay = sub, res.total_delay
            w *= 1.6
        if best is not None:
            best.save(os.path.join(args.outdir, f"{name}.sol.json"))
        print(f"{name}: floor={floor:.0f} dual={best_val:.1f} "
              f"primal={best_delay} baseline={c['baseline_total']} "
              f"[{time.time()-t0:.0f}s]", flush=True)
        if best_delay:
            tot += best_delay


if __name__ == "__main__":
    main()
