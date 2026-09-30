"""Cross-case generalisation test for the LNS move-selection policy.

Train the numpy MLP move ranker on hard/case_01 and test it, UNSEEN, on
hard/case_05 and hard/case_09. This is the decisive question for a learned
policy on a 9-case tier: does a ranker trained on one instance transfer to a
different grid, net count and congestion pattern?

Also measures the raw inference cost of the policy (numpy MLP forward pass over a
candidate batch) against the cost of EXACTLY evaluating one candidate move, which
is the thing the policy is trying to avoid.
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
from spike_lib import Case, MLP, spearman, spt_delay  # noqa: E402

FEATURES = SP.FEATURE_NAMES


def prepare(case_path, sol_path, moves, seed, perturb):
    case = Case(case_path, sol_path)
    edges = {nid: list(E) for nid, E in case.sol_edges.items()}
    cur = SP.net_delays(case, edges)
    base = sum(cur.values())
    spt = {nid: spt_delay(case, nid) for nid in case.net_ids}
    lb = sum(v for v in spt.values() if v is not None)
    rng = random.Random(seed)
    recsA, _ = SP.build_dataset(case, edges, cur, spt, moves, rng, "A")

    pedges = {k: list(v) for k, v in edges.items()}
    pcur = SP.net_delays(case, pedges)
    pocc = SP.occupancy(case, pedges)
    pverts = SP.verts_by_net(pedges)
    prng = random.Random(seed + 500)
    for _ in range(perturb):
        s = SP.sample_move(case, pverts, prng)
        if s is None:
            continue
        move, order = s
        r = SP.eval_move(case, pocc, pcur, move, order, spt)
        if r is None:
            continue
        _, newE = r
        for n in move:
            pedges[n] = newE[n]
        pcur = SP.net_delays(case, pedges)
        pocc = SP.occupancy(case, pedges)
        pverts = SP.verts_by_net(pedges)
    ptotal = sum(pcur.values())
    recsB, dtB = SP.build_dataset(case, pedges, pcur, spt, moves, rng, "B")
    return case, base, lb, recsA, recsB, ptotal, dtB


def xy(recs):
    good = [r for r in recs if r["ok"]]
    X = np.array([r["X"] for r in good])
    y = -np.array([r["delta"] for r in good])
    return X, y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--moves", type=int, default=500)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--perturb", type=int, default=40)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "crosscase_result.json"))
    a = ap.parse_args()

    scratch = os.environ.get("HERMES_SCRATCH",
                            "C:/Users/gkesu/AppData/Local/hermes/cache/scratch")
    repo = "F:/eda3d-wt/nn-policy"
    cases = {
        "case_01": (f"{repo}/benchmarks_hard/case_01.json", f"{scratch}/pr3_case01.json"),
        "case_05": (f"{repo}/benchmarks_hard/case_05.json", f"{scratch}/pr3_case05.json"),
        "case_09": (f"{repo}/benchmarks_hard/case_09.json", f"{scratch}/pr3_case09.json"),
    }

    data = {}
    for name, (ci, cs) in cases.items():
        print(f"\n########## {name} ##########")
        case, base, lb, rA, rB, ptot, dtB = prepare(ci, cs, a.moves, a.seed, a.perturb)
        print(f"{name}: PR#3 {base}, pins-only LB {lb:.0f} ({(base / lb - 1) * 100:.1f}% above), "
              f"perturbed {ptot}")
        data[name] = {"case": case, "base": base, "lb": lb, "A": rA, "B": rB,
                      "ptot": ptot, "dtB": dtB, "spt": {nid: spt_delay(case, nid)
                                                        for nid in case.net_ids}}

    results = {}
    for regime in ("A", "B"):
        print(f"\n=== cross-case transfer, regime {regime} ===")
        Xtr, ytr = xy(data["case_01"][regime])
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        m = MLP(Xtr.shape[1], d_h=32, seed=1)
        t0 = time.perf_counter()
        m.fit((Xtr - mu) / sd, ytr, epochs=1500, batch=32, seed=2)
        t_train = time.perf_counter() - t0
        print(f"trained on case_01 regime {regime}: n={len(ytr)} in {t_train:.2f}s")
        for name in ("case_01", "case_05", "case_09"):
            Xte, yte = xy(data[name][regime])
            sc = m((Xte - mu) / sd)
            nprng = np.random.default_rng(5)
            rs = [spearman(s, yte) for s in nprng.normal(size=(300, len(yte)))]
            rp = [float((yte[np.argsort(-s)[:10]] > 0.5).mean())
                  for s in nprng.normal(size=(300, len(yte)))]
            r1 = [float(yte[np.argmax(s)]) for s in nprng.normal(size=(300, len(yte)))]
            hs = spearman(Xte[:, 4], yte)
            hp = float((yte[np.argsort(-Xte[:, 4])[:10]] > 0.5).mean())
            h1 = float(yte[int(np.argmax(Xte[:, 4]))])
            print(f"  {name}: n={len(yte):4d} improving={int((yte > 0.5).sum()):4d}  "
                  f"MLP rho={spearman(sc, yte):6.3f} (random {np.mean(rs):6.3f})  "
                  f"MLP top10prec={float((yte[np.argsort(-sc)[:10]] > 0.5).mean()):.3f} "
                  f"(random {np.mean(rp):.3f})  "
                  f"MLP y(top1)={float(yte[np.argmax(sc)]):8.1f} "
                  f"(random {np.mean(r1):8.1f}, hand {h1:8.1f})")
            results[f"{regime}_{name}"] = {
                "n": len(yte),
                "improving": int((yte > 0.5).sum()),
                "mlp_spearman": spearman(sc, yte),
                "random_spearman": float(np.mean(rs)),
                "mlp_top10prec": float((yte[np.argsort(-sc)[:10]] > 0.5).mean()),
                "random_top10prec": float(np.mean(rp)),
                "mlp_y_top1": float(yte[np.argmax(sc)]),
                "random_y_top1": float(np.mean(r1)),
                "hand_y_top1": h1,
                "hand_spearman": hs,
                "hand_top10prec": hp,
                "best_available": float(yte.max()),
            }

    # ---- inference cost vs exact move-evaluation cost -------------------
    print("\n=== inference cost vs exact move evaluation ===")
    case1 = data["case_01"]["case"]
    spt1 = data["case_01"]["spt"]
    Xtr, ytr = xy(data["case_01"]["B"])
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    m = MLP(Xtr.shape[1], d_h=32, seed=1)
    m.fit((Xtr - mu) / sd, ytr, epochs=1500, batch=32, seed=2)
    for bs in (1, 14, 64, 512):
        Xb = np.tile((Xtr[:1] - mu) / sd, (bs, 1))
        reps = 20000 // max(1, bs) + 10
        t0 = time.perf_counter()
        for _ in range(reps):
            m(Xb)
        dt = (time.perf_counter() - t0) / reps
        print(f"  MLP forward pass, batch {bs:4d}: {dt * 1e6:8.1f} us  "
              f"({dt / bs * 1e6:.2f} us/candidate)")
    per_move_ms = data["case_01"]["dtB"] / max(1, a.moves)
    print(f"  exact evaluation of ONE candidate move (python): {per_move_ms:.1f} ms")
    print(f"  exact evaluation of ONE candidate move (C++ A*, from dijk_bench): "
          f"0.112-0.198 ms/net x ~{np.mean(Xtr[:, 1]):.1f} nets/move "
          f"= {0.112 * np.mean(Xtr[:, 1]):.2f}-{0.198 * np.mean(Xtr[:, 1]):.2f} ms/move")

    out = {
        "moves_per_case": a.moves,
        "perturb": a.perturb,
        "pr3": {k: data[k]["base"] for k in data},
        "pins_only_lb": {k: data[k]["lb"] for k in data},
        "transfer": results,
        "exact_move_eval_ms_python": per_move_ms,
    }
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
