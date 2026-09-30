"""Head-to-head: policy-guided LNS vs random LNS at EQUAL evaluation budget.

This is the only comparison that matters for "can a NN help". Ranking quality
(Spearman) is worthless if following the ranking does not produce a better
final solution. So: run the same LNS loop, same number of candidate evaluations
per step, same seeds, differing only in how the winning move is chosen.

Reported per (case, ranker): mean and best final total delay over N restarts,
and how far below the PR#3 reference it gets. Lower is better.
"""
import argparse
import json
import os
import random
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "F:/eda3d-wt/nn-policy")

import spike as SP  # noqa: E402
from spike_lib import Case, MLP, spt_delay  # noqa: E402


def lns_loop(case, edges, cur, spt, rank_fn, steps, rng, cand):
    """LNS with a fixed candidate budget per step. Returns (total, evals)."""
    edges = {k: list(v) for k, v in edges.items()}
    cur = dict(cur)
    total = sum(cur.values())
    evals = 0
    for _ in range(steps):
        occ = SP.occupancy(case, edges)
        vbn = SP.verts_by_net(edges)
        cands = []
        for _ in range(cand):
            s = SP.sample_move(case, vbn, rng)
            if s is None:
                continue
            move, order = s
            r = SP.eval_move(case, occ, cur, move, order, spt)
            evals += 1
            if r is None:
                continue
            delta, newE = r
            cands.append((move, delta, newE, makeX(case, occ, move, cur, spt)))
        if not cands:
            break
        sc = rank_fn(np.array([c[3] for c in cands]))
        i = int(np.argmax(sc))
        move, delta, newE, _ = cands[i]
        if delta >= -0.5:
            break
        for n in move:
            edges[n] = newE[n]
            cur[n] = case.net_delay(n, newE[n])
        total += delta
    return total, evals


def makeX(case, occ, move, cur, spt):
    from spike_lib import make_features
    return make_features(case, occ, move, cur, spt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--moves-train", type=int, default=500)
    ap.add_argument("--train-case", default="case_01")
    ap.add_argument("--steps", type=int, default=25)
    ap.add_argument("--cand", type=int, default=14)
    ap.add_argument("--restarts", type=int, default=8)
    ap.add_argument("--perturb", type=int, default=25)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "headtohead_result.json"))
    a = ap.parse_args()

    scratch = os.environ.get("HERMES_SCRATCH",
                             "C:/Users/gkesu/AppData/Local/hermes/cache/scratch")
    repo = "F:/eda3d-wt/nn-policy"
    cases = {
        "case_01": (f"{repo}/benchmarks_hard/case_01.json", f"{scratch}/pr3_case01.json"),
        "case_05": (f"{repo}/benchmarks_hard/case_05.json", f"{scratch}/pr3_case05.json"),
        "case_09": (f"{repo}/benchmarks_hard/case_09.json", f"{scratch}/pr3_case09.json"),
    }

    # ---- train the policy on the training case only ---------------------
    ci, cs = cases[a.train_case]
    tcase = Case(ci, cs)
    tedges = {nid: list(E) for nid, E in tcase.sol_edges.items()}
    tcur = SP.net_delays(tcase, tedges)
    tspt = {nid: spt_delay(tcase, nid) for nid in tcase.net_ids}
    trng = random.Random(7)
    # training data from PERTURBED states of the training case only
    Xs, ys = [], []
    for rep in range(4):
        pe = {k: list(v) for k, v in tedges.items()}
        pc = SP.net_delays(tcase, pe)
        po = SP.occupancy(tcase, pe)
        pv = SP.verts_by_net(tcase and pe)
        pr = random.Random(700 + rep)
        for _ in range(6):
            s = SP.sample_move(tcase, pv, pr)
            if s is None:
                continue
            mv, od = s
            r = SP.eval_move(tcase, po, pc, mv, od, tspt)
            if r is None:
                continue
            _, newE = r
            for n in mv:
                pe[n] = newE[n]
            pc = SP.net_delays(tcase, pe)
            po = SP.occupancy(tcase, pe)
            pv = SP.verts_by_net(pe)
        for _ in range(a.moves_train // 4):
            s = SP.sample_move(tcase, pv, pr)
            if s is None:
                continue
            mv, od = s
            r = SP.eval_move(tcase, po, pc, mv, od, tspt)
            if r is None:
                continue
            delta, _ = r
            Xs.append(makeX(tcase, po, mv, pc, tspt))
            ys.append(-delta)
    Xtr = np.array(Xs)
    ytr = np.array(ys)
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    m = MLP(Xtr.shape[1], d_h=32, seed=1)
    t0 = time.perf_counter()
    m.fit((Xtr - mu) / sd, ytr, epochs=2000, batch=32, seed=2)
    print(f"policy trained on {a.train_case} only: n={len(ytr)} samples, "
          f"{Xtr.shape[1]} features, 32 hidden units, {time.perf_counter() - t0:.2f}s")
    print(f"training label: improvement (higher = better move); "
          f"{(ytr > 0.5).sum()}/{len(ytr)} improving")

    out = {"train_case": a.train_case, "train_n": len(ytr),
           "steps": a.steps, "cand": a.cand, "restarts": a.restarts,
           "cases": {}}

    for name, (ci, cs) in cases.items():
        case = Case(ci, cs)
        edges = {nid: list(E) for nid, E in case.sol_edges.items()}
        cur = SP.net_delays(case, edges)
        pr3 = sum(cur.values())
        spt = {nid: spt_delay(case, nid) for nid in case.net_ids}
        lb = sum(v for v in spt.values() if v is not None)

        # starting state: a fixed degraded state, identical for every ranker
        pe = {k: list(v) for k, v in edges.items()}
        pc = SP.net_delays(case, pe)
        po = SP.occupancy(case, pe)
        pv = SP.verts_by_net(pe)
        pr = random.Random(31337)
        for _ in range(a.perturb):
            s = SP.sample_move(case, pv, pr)
            if s is None:
                continue
            mv, od = s
            r = SP.eval_move(case, po, pc, mv, od, spt)
            if r is None:
                continue
            _, newE = r
            for n in mv:
                pe[n] = newE[n]
            pc = SP.net_delays(case, pe)
            po = SP.occupancy(case, pe)
            pv = SP.verts_by_net(pe)
        start = sum(pc.values())
        print(f"\n{name}: PR#3 {pr3}, LB {lb:.0f}, common start state {start}")

        rankers = {
            "random": lambda Xc, _r=random.Random(9): np.array(
                [_r.random() for _ in range(len(Xc))]),
            "hand:max_detour_sum": lambda Xc: Xc[:, 4],
            "hand:max_net_count": lambda Xc: Xc[:, 0],
            "mlp_policy": lambda Xc: m((Xc - mu) / sd),
        }
        res = {}
        for rname, fn in rankers.items():
            finals, evals = [], []
            t0 = time.perf_counter()
            for s in range(a.restarts):
                f, e = lns_loop(case, pe, pc, spt, fn, a.steps, random.Random(4000 + s), a.cand)
                finals.append(f)
                evals.append(e)
            dt = time.perf_counter() - t0
            res[rname] = {"finals": finals, "mean_final": float(np.mean(finals)),
                          "best_final": float(np.min(finals)),
                          "mean_evals": float(np.mean(evals)),
                          "wall_s": dt}
            print(f"  {rname:20s} start {start} -> mean {np.mean(finals):9.1f} "
                  f"best {np.min(finals):9.1f}  ({np.mean(finals) - pr3:+9.1f} vs PR#3) "
                  f"evals {np.mean(evals):5.0f}  {dt:5.1f}s")
        out["cases"][name] = {"pr3": pr3, "lb": lb, "start": start, "rankers": res}

    with open(a.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
