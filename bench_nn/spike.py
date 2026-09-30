"""Run the LNS move-selection feasibility spike on one hard case.

Two regimes, because they answer different questions:

  regime A "local_optimum": start from PR#3's own solution for hard/case_01. It
      is a capacity-1 hard 1-opt local optimum, so almost no single
      rip-up-and-reroute move improves. This measures the size of the prize a
      move-selection policy could ever capture from that state.

  regime B "perturbed": first degrade the solution with a few random rip-ups
      (the state an LNS loop is actually in mid-search, when improving moves DO
      exist), then sample moves. This is the ONLY regime where a learned
      move-selection policy has anything to select, so it is the decisive one.

For each candidate move we compute the TRUE resulting total delay by rerouting
exactly (Dijkstra per net, other nets' vertices blocked) -- an exact label, not
an estimate. Features are cheap aggregates available before the move runs.

Rankers compared, all on identical candidate sets:
  * random,
  * hand heuristics (max detour, max net count, max delay),
  * a small numpy MLP (torch is NOT installed on this host; numpy MLP is the
    accepted substitute).

Metrics: Spearman vs true improvement, top-k precision, and -- most importantly
-- a greedy descent using each ranker, reporting the final total delay reached.
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

from spike_lib import Case, MLP, make_features, reroute, spearman, spt_delay  # noqa: E402

FEATURE_NAMES = [
    "n_nets", "n_sinks", "delay_sum", "delay_per_sink", "detour_sum",
    "detour_mean", "detour_max", "mid_layer_frac_mean", "mid_layer_frac_max",
]


def occupancy(case, edges_by_net):
    occ = {}
    for nid, E in edges_by_net.items():
        for a, b in E:
            occ[a] = nid
            occ[b] = nid
    return occ


def net_delays(case, edges_by_net):
    return {nid: case.net_delay(nid, E) for nid, E in edges_by_net.items()}


def verts_by_net(edges_by_net):
    return {nid: {v for e in E for v in e} for nid, E in edges_by_net.items()}


def sample_move(case, vbn, rng):
    """An LNS neighbourhood: nets touching a random box around a middle-layer seed."""
    z = rng.randrange(1, case.L - 1)
    x = rng.randrange(case.W)
    y = rng.randrange(case.H)
    box = rng.choice([1, 2, 3, 4, 6])
    grp = set()
    for nid, vs in vbn.items():
        for v in vs:
            if abs(v[0] - x) <= box and abs(v[1] - y) <= box and abs(v[2] - z) <= 1:
                grp.add(nid)
                break
    if not grp:
        return None
    if len(grp) > 12:
        grp = set(rng.sample(sorted(grp), 12))
    move = sorted(grp)
    order = move[:]
    rng.shuffle(order)
    return move, order


def eval_move(case, occ, cur, move, order, spt_cache):
    newE, ok = reroute(case, move, occ, order)
    if not ok:
        return None
    old_d = sum(cur[n] for n in move)
    new_d = sum(case.net_delay(n, newE[n]) for n in move)
    return float(new_d - old_d), newE


def build_dataset(case, edges, cur, spt_cache, n_moves, rng, label):
    occ = occupancy(case, edges)
    vbn = verts_by_net(edges)
    recs = []
    t0 = time.perf_counter()
    while len(recs) < n_moves:
        s = sample_move(case, vbn, rng)
        if s is None:
            continue
        move, order = s
        r = eval_move(case, occ, cur, move, order, spt_cache)
        if r is None:
            recs.append({"ok": False, "X": None, "delta": None, "move": move})
            continue
        delta, _ = r
        X = make_features(case, occ, move, cur, spt_cache)
        recs.append({"ok": True, "X": X.tolist(), "delta": delta, "move": move,
                     "order": order})
    dt = time.perf_counter() - t0
    good = [r for r in recs if r["ok"]]
    d = np.array([r["delta"] for r in good])
    print(f"[{label}] {len(recs)} moves ({len(good)} feasible) in {dt:.1f}s "
          f"= {dt / max(1, len(recs)) * 1000:.0f} ms/move-eval")
    print(f"[{label}] true delta: mean {d.mean():.1f} median {np.median(d):.1f} "
          f"min {d.min():.0f} max {d.max():.0f}  improving {int((d < -0.5).sum())}/{len(d)}")
    return recs, dt


def ranker_table(name, scores, y, extra=None):
    k = min(10, len(y))
    top = np.argsort(-scores)[:k]
    r = {
        "ranker": name,
        "spearman": spearman(scores, y),
        "topk": k,
        "topk_precision": float((y[top] > 0.5).mean()),
        "y_of_top1": float(y[top[0]]),
        "best_available": float(y.max()),
        "mean_top1_gap": float(y.max() - y[top[0]]),
    }
    if extra:
        r.update(extra)
    return r


def greedy_descent(case, edges, cur, spt_cache, rank_fn, steps, rng, cand=14):
    """`steps` LNS iterations; each evaluates `cand` candidate moves exactly and
    applies the one the ranker scores highest. Returns the final total delay."""
    edges = {k: list(v) for k, v in edges.items()}
    cur = dict(cur)
    total = sum(cur.values())
    applied = 0
    for _ in range(steps):
        occ = occupancy(case, edges)
        vbn = verts_by_net(edges)
        cands = []
        for _ in range(cand):
            s = sample_move(case, vbn, rng)
            if s is None:
                continue
            move, order = s
            r = eval_move(case, occ, cur, move, order, spt_cache)
            if r is None:
                continue
            delta, newE = r
            cands.append((move, order, delta, newE,
                          make_features(case, occ, move, cur, spt_cache)))
        if not cands:
            break
        Xc = np.array([c[4] for c in cands])
        sc = rank_fn(Xc)
        i = int(np.argmax(sc))
        move, order, delta, newE, _ = cands[i]
        if delta >= -0.5:
            break            # no improving move in the sampled neighbourhood
        for n in move:
            edges[n] = newE[n]
            cur[n] = case.net_delay(n, newE[n])
        total += delta
        applied += 1
    return total, applied


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="F:/eda3d-wt/nn-policy/benchmarks_hard/case_01.json")
    ap.add_argument("--sol", required=True)
    ap.add_argument("--moves", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--steps", type=int, default=10)
    ap.add_argument("--perturb", type=int, default=14,
                    help="random nets ripped+rerouted to create a non-1-opt state")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "spike_result.json"))
    args = ap.parse_args()

    case = Case(args.case, args.sol)
    print(f"loaded {case.W}x{case.H}x{case.L} verts={case.N} nets={len(case.net_ids)}")

    from m3d.model import Instance, Submission  # type: ignore
    from m3d.checker import check
    res = check(Instance.from_dict(json.load(open(args.case))),
                Submission.from_dict(json.load(open(args.sol))))
    print(f"m3d/checker.py: legal={res.legal} total_delay={res.total_delay}")
    if not res.legal:
        print("REASON:", res.reasons[:3])
        return 1

    edges = {nid: list(E) for nid, E in case.sol_edges.items()}
    cur = net_delays(case, edges)
    base_total = sum(cur.values())

    t0 = time.perf_counter()
    spt_cache = {nid: spt_delay(case, nid) for nid in case.net_ids}
    lb = sum(v for v in spt_cache.values() if v is not None)
    print(f"PR#3 total delay = {base_total}; pins-only SPT bound = {lb:.0f} "
          f"({(base_total / lb - 1) * 100:.1f}% above) [{time.perf_counter() - t0:.1f}s]")

    rng = random.Random(args.seed)
    nprng = np.random.default_rng(args.seed)

    # ---------------- regime A: from PR#3's 1-opt optimum ----------------
    print("\n=== regime A: moves from PR#3's own (1-opt optimal) solution ===")
    recsA, dtA = build_dataset(case, edges, cur, spt_cache, args.moves, rng, "A")

    # ---------------- regime B: perturbed state ---------------------------
    print(f"\n=== regime B: state degraded by {args.perturb} random rip-ups "
          f"(mid-LNS state, improving moves exist) ===")
    pedges = {k: list(v) for k, v in edges.items()}
    pcur = net_delays(case, pedges)
    pocc = occupancy(case, pedges)
    pverts = verts_by_net(pedges)
    prng = random.Random(args.seed + 500)
    applied = 0
    for _ in range(args.perturb):
        s = sample_move(case, pverts, prng)
        if s is None:
            continue
        move, order = s
        r = eval_move(case, pocc, pcur, move, order, spt_cache)
        if r is None:
            continue
        _, newE = r
        for n in move:
            pedges[n] = newE[n]
        pcur = net_delays(case, pedges)
        pocc = occupancy(case, pedges)
        pverts = verts_by_net(pedges)
        applied += 1
    ptotal = sum(pcur.values())
    print(f"perturbed state: {applied} rip-ups applied, total = {ptotal} "
          f"(PR#3 was {base_total}, i.e. {ptotal - base_total:+d})")
    recsB, dtB = build_dataset(case, pedges, pcur, spt_cache, args.moves, rng, "B")

    # ---------------- ranking experiments --------------------------------
    out = {
        "case": os.path.basename(args.case),
        "checker_legal": res.legal,
        "pr3_total_delay": base_total,
        "pins_only_bound": lb,
        "pr3_pct_above_bound": (base_total / lb - 1) * 100,
        "moves_per_regime": args.moves,
        "eval_ms_per_move_A": dtA / max(1, len(recsA)) * 1000,
        "eval_ms_per_move_B": dtB / max(1, len(recsB)) * 1000,
        "feature_names": FEATURE_NAMES,
        "regimes": {},
    }

    for label, recs, start_total in (("A_local_optimum", recsA, base_total),
                                     ("B_perturbed", recsB, ptotal)):
        good = [r for r in recs if r["ok"]]
        d = np.array([r["delta"] for r in good])
        X = np.array([r["X"] for r in good])
        y = -d
        mu, sd = X.mean(0), X.std(0) + 1e-9
        Xs = (X - mu) / sd
        print(f"\n--- {label}: {len(good)} feasible moves, "
              f"{int((d < -0.5).sum())} improving ---")

        rand_scores = nprng.normal(size=(300, len(y)))
        rows = [
            ranker_table("hand:max_detour_sum", X[:, 4], y),
            ranker_table("hand:max_net_count", X[:, 0], y),
            ranker_table("hand:max_delay_sum", X[:, 2], y),
        ]
        mlp = MLP(Xs.shape[1], d_h=32, seed=1)
        t_train = time.perf_counter()
        mlp.fit(Xs, y, epochs=1500, batch=32, seed=2)
        t_train = time.perf_counter() - t_train
        sc = mlp(Xs)
        t0s = time.perf_counter()
        reps = 2000
        for _ in range(reps):
            mlp(Xs[:64])
        t_score = (time.perf_counter() - t0s) / reps
        rows.append(ranker_table("mlp_h32_e1500_in_sample", sc, y,
                                 {"train_s": t_train, "score_batch64_s": t_score}))

        print(f"{'ranker':26s} {'spearman':>9s} {'top10prec':>10s} {'y(top1)':>9s} "
              f"{'best':>8s} {'gap':>8s}")
        for r in rows:
            print(f"{r['ranker']:26s} {r['spearman']:9.3f} {r['topk_precision']:10.3f} "
                  f"{r['y_of_top1']:9.1f} {r['best_available']:8.1f} {r['mean_top1_gap']:8.1f}")
        rs = [spearman(s, y) for s in rand_scores]
        rp = [float((y[np.argsort(-s)[:10]] > 0.5).mean()) for s in rand_scores]
        r1 = [float(y[np.argmax(s)]) for s in rand_scores]
        print(f"{'random (mean of 300)':26s} {np.mean(rs):9.3f} {np.mean(rp):10.3f} "
              f"{np.mean(r1):9.1f}")

        # honest held-out split
        idx = np.random.default_rng(11).permutation(len(y))
        tr, te = idx[: len(y) // 2], idx[len(y) // 2:]
        m2 = MLP(Xs.shape[1], d_h=32, seed=1)
        m2.fit(Xs[tr], y[tr], epochs=1500, batch=32, seed=2)
        sc2 = m2(Xs[te])
        ho = {
            "mlp_spearman": spearman(sc2, y[te]),
            "random_spearman_mean": float(np.mean(
                [spearman(s, y[te]) for s in nprng.normal(size=(300, len(te)))])),
            "hand_detour_spearman": spearman(X[te, 4], y[te]),
            "hand_netcount_spearman": spearman(X[te, 0], y[te]),
            "y_test_best": float(y[te].max()),
            "y_test_mlp_top1": float(y[te][int(np.argmax(sc2))]),
            "y_test_hand_top1": float(y[te][int(np.argmax(X[te, 4]))]),
            "y_test_random_top1_mean": float(np.mean(
                [y[te][int(np.argmax(s))] for s in nprng.normal(size=(300, len(te)))])),
        }
        print("  held-out (train half / test half):")
        for k, v in ho.items():
            print(f"    {k:30s} {v:9.3f}")

        out["regimes"][label] = {
            "start_total": start_total,
            "feasible_moves": len(good),
            "improving_moves": int((d < -0.5).sum()),
            "delta_mean": float(d.mean()),
            "delta_min": float(d.min()),
            "rankers": rows,
            "random_spearman_mean": float(np.mean(rs)),
            "random_topk_precision_mean": float(np.mean(rp)),
            "random_y_top1_mean": float(np.mean(r1)),
            "heldout": ho,
        }

    # ---------------- greedy descent comparison --------------------------
    print("\n=== greedy descent from the perturbed state: final total delay ===")
    goodB = [r for r in recsB if r["ok"]]
    Xb = np.array([r["X"] for r in goodB])
    yb = -np.array([r["delta"] for r in goodB])
    mbmu, mbsd = Xb.mean(0), Xb.std(0) + 1e-9
    mbfit = MLP(Xb.shape[1], d_h=32, seed=1)
    mbfit.fit((Xb - mbmu) / mbsd, yb, epochs=1500, batch=32, seed=2)

    rankers = {
        "random": lambda Xc: nprng.normal(size=len(Xc)),
        "hand:max_detour_sum": lambda Xc: Xc[:, 4],
        "hand:max_net_count": lambda Xc: Xc[:, 0],
        "mlp": lambda Xc: mbfit((Xc - mbmu) / mbsd),
    }
    descent = {}
    for name, fn in rankers.items():
        finals, apps = [], []
        for s in range(3):
            rr = random.Random(1000 + s)
            f, a = greedy_descent(case, pedges, pcur, spt_cache, fn, args.steps, rr)
            finals.append(f)
            apps.append(a)
        print(f"  {name:22s} start {ptotal} -> finals {['%.0f' % f for f in finals]} "
              f"mean {np.mean(finals):.1f}  moves applied {apps}")
        descent[name] = {"start": ptotal, "finals": finals,
                         "mean_final": float(np.mean(finals)), "applied": apps}
    out["greedy_descent_perturbed"] = descent
    out["greedy_descent_steps"] = args.steps

    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
