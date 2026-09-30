"""The only way a move-selection policy can add value: PRUNE candidates.

In the head-to-head, every candidate move was evaluated exactly and the policy
only chose among already-computed results -- so the policy saved nothing. A
policy earns its keep only if it can rank candidates BEFORE the expensive exact
evaluation and skip most of them.

Test: at a fixed total evaluation budget, compare
  (a) evaluate all `cand` candidates exactly, pick the best  -> upper bound
  (b) score all `cand` candidates with the policy (cheap), evaluate only the
      top-`keep`, pick the best of those                    -> what a policy buys
at equal numbers of EXACT evaluations, i.e. equal inner-loop work.

If (b) ~ (a), pruning with a learned ranker is worth its cost. If (b) << (a),
the exact evaluation is cheap enough that you should just do all of them, and a
learned ranker has nothing to contribute.
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
from spike_lib import Case, MLP, make_features, spt_delay  # noqa: E402


def train_policy(case_name, scratch, repo, moves, seed=7):
    ci = f"{repo}/benchmarks_hard/{case_name}.json"
    cs = f"{scratch}/pr3_{case_name.replace('case_', 'case')}.json"
    case = Case(ci, cs)
    edges = {nid: list(E) for nid, E in case.sol_edges.items()}
    spt = {nid: spt_delay(case, nid) for nid in case.net_ids}
    Xs, ys = [], []
    for rep in range(4):
        pe = {k: list(v) for k, v in edges.items()}
        pc = SP.net_delays(case, pe)
        po = SP.occupancy(case, pe)
        pv = SP.verts_by_net(pe)
        pr = random.Random(700 + rep)
        for _ in range(6):
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
        for _ in range(moves // 4):
            s = SP.sample_move(case, pv, pr)
            if s is None:
                continue
            mv, od = s
            r = SP.eval_move(case, po, pc, mv, od, spt)
            if r is None:
                continue
            delta, _ = r
            Xs.append(make_features(case, po, mv, pc, spt))
            ys.append(-delta)
    X = np.array(Xs)
    y = np.array(ys)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    m = MLP(X.shape[1], d_h=32, seed=1)
    m.fit((X - mu) / sd, y, epochs=2000, batch=32, seed=2)
    return m, mu, sd, len(y)


def run(case, edges, cur, spt, m, mu, sd, steps, cand, keep, rng, prune):
    """prune=True: score all cand, evaluate only top-keep. prune=False: evaluate all."""
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
            cands.append((move, order))
        if not cands:
            break
        if prune is None:                      # random control at the same budget
            idx = list(rng.sample(range(len(cands)), min(keep, len(cands))))
        elif prune:
            Xc = np.array([make_features(case, occ, mv, cur, spt) for mv, _ in cands])
            sc = m((Xc - mu) / sd)
            idx = list(np.argsort(-sc)[:keep])
        else:
            idx = list(range(len(cands)))
        best = None
        for i in idx:
            move, order = cands[i]
            r = SP.eval_move(case, occ, cur, move, order, spt)
            evals += 1
            if r is None:
                continue
            delta, newE = r
            if best is None or delta < best[0]:
                best = (delta, move, newE)
        if best is None or best[0] >= -0.5:
            break
        delta, move, newE = best
        for n in move:
            edges[n] = newE[n]
            cur[n] = case.net_delay(n, newE[n])
        total += delta
    return total, evals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--moves-train", type=int, default=400)
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--cand", type=int, default=14)
    ap.add_argument("--restarts", type=int, default=6)
    ap.add_argument("--perturb", type=int, default=25)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "prune_result.json"))
    a = ap.parse_args()
    scratch = os.environ.get("HERMES_SCRATCH",
                             "C:/Users/gkesu/AppData/Local/hermes/cache/scratch")
    repo = "F:/eda3d-wt/nn-policy"

    m, mu, sd, ntr = train_policy("case_01", scratch, repo, a.moves_train)
    print(f"policy: trained on case_01, n={ntr}")

    out = {"steps": a.steps, "cand": a.cand, "restarts": a.restarts, "cases": {}}
    for name in ("case_01", "case_05", "case_09"):
        case = Case(f"{repo}/benchmarks_hard/{name}.json",
                    f"{scratch}/pr3_{name.replace('case_', 'case')}.json")
        edges = {nid: list(E) for nid, E in case.sol_edges.items()}
        pr3 = sum(SP.net_delays(case, edges).values())
        spt = {nid: spt_delay(case, nid) for nid in case.net_ids}
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
        print(f"\n{name}: PR#3 {pr3}, common start {start}, cand={a.cand}")

        res = {}
        # full evaluation of all candidates
        f, e = [], []
        for s in range(a.restarts):
            x, ev = run(case, pe, pc, spt, m, mu, sd, a.steps, a.cand, a.cand,
                        random.Random(4000 + s), prune=False)
            f.append(x)
            e.append(ev)
        res["evaluate_all"] = {"mean_final": float(np.mean(f)), "best_final": float(np.min(f)),
                               "mean_evals": float(np.mean(e))}
        print(f"  evaluate_all (oracle over {a.cand})      mean {np.mean(f):9.1f} "
              f"best {np.min(f):9.1f}  evals {np.mean(e):5.0f}")

        # pruning with the policy: same number of exact evaluations
        for keep in (1, 2, 4, 7):
            f, e = [], []
            t0 = time.perf_counter()
            for s in range(a.restarts):
                x, ev = run(case, pe, pc, spt, m, mu, sd, a.steps, a.cand, keep,
                            random.Random(4000 + s), prune=True)
                f.append(x)
                e.append(ev)
            dt = time.perf_counter() - t0
            res[f"policy_prune_keep{keep}"] = {
                "mean_final": float(np.mean(f)), "best_final": float(np.min(f)),
                "mean_evals": float(np.mean(e)), "wall_s": dt}
            print(f"  policy_prune top-{keep:<2d}                 mean {np.mean(f):9.1f} "
                  f"best {np.min(f):9.1f}  evals {np.mean(e):5.0f}  {dt:5.1f}s")

        # random pruning at the same budget, as the control
        for keep in (2, 4):
            f, e = [], []
            for s in range(a.restarts):
                x, ev = run(case, pe, pc, spt, m, mu, sd, a.steps, a.cand, keep,
                            random.Random(4000 + s), prune=None)
                f.append(x)
                e.append(ev)
            res[f"random_prune_keep{keep}"] = {
                "mean_final": float(np.mean(f)), "best_final": float(np.min(f)),
                "mean_evals": float(np.mean(e))}
            print(f"  random_prune keep {keep} (control)      mean {np.mean(f):9.1f} "
                  f"best {np.min(f):9.1f}  evals {np.mean(e):5.0f}")
        out["cases"][name] = {"pr3": pr3, "start": start, "res": res}

    with open(a.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
