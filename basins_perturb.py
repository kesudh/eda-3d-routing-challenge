"""Basin diversity via PERTURB + RE-CLOSE, not from-scratch construction.

Why this replaces the negotiator: a from-scratch PathFinder never converged
(60 iterations, still overlapping), so it could not answer the basin question.
But the question is not really "can I build a good router from scratch" -- it is
"is PR#3's 1-opt fixed point a DOMINANT attractor, or are there other basins?"

That is answerable by perturbing PR#3's solution and re-running 1-opt to
fixpoint. If every perturbation lands back on 8674, PR#3 is a dominant
attractor. If some land strictly below, there are other basins and one of them
is better.

Perturbations used (all preserve legality -- every net keeps a valid tree):
  - force a net onto an alternative equal-cost SPT (zero-cost plateau move)
  - rip up k nets and reroute them in a random order
  - swap which of two free alternatives a net takes
"""
import collections
import os
import random
import sys
import time

sys.path.insert(0, r"F:\eda-3d-routing-challenge")
os.chdir(r"F:\eda-3d-routing-challenge")
sys.path.insert(0, r"F:\eda3d-wt\_shared")

from basins import Case, INF


def load_pr3_routes(c: Case, case="case_01"):
    import json
    import subprocess
    from m3d.model import Submission
    out = subprocess.run(
        ["git", "show", f"pr3:submissions/hard/pathfinder_lns/{case}.sol.json"],
        capture_output=True, text=True, cwd=r"F:\eda-3d-routing-challenge")
    sub = Submission.from_dict(json.loads(out.stdout))
    routes = {}
    for rt in sub.routes:
        vs = {c.enc(a) for a, _ in rt.edges} | {c.enc(b) for _a, b in rt.edges}
        routes[rt.net] = vs
    return routes


def one_opt_sets(c: Case, routes):
    """TRUE 1-opt: accept a net's new tree ONLY if its own delay strictly drops.

    Bug this replaces: the earlier version accepted ANY different vertex set
    (`r[0] != v`), including equal- or worse-delay reshuffles. That is not a
    1-opt at all, and scoring it produced a phantom 7838 vs PR#3's 8674 --
    the checker correctly rejected the resulting solution as illegal.
    A 1-opt must be delay-descending, and the incumbent is already a 1-opt
    fixed point (measured 0/62 nets improve), so this should be a no-op.
    """
    occ = set()
    for v in routes.values():
        occ |= v
    improved = True
    rounds = 0
    while improved:
        improved = False
        rounds += 1
        for nid in list(routes):
            v = routes[nid]
            occ -= v
            d = c.spt(nid, occ)
            cur_delay = None
            if all(c.pv[s] in d for s in c.NET[nid].sinks):
                cur_delay = sum(d[c.pv[s]] for s in c.NET[nid].sinks)
            t = c.tree(nid, d, c.pv[c.NET[nid].driver])
            if t is not None and cur_delay is not None:
                nv = t[0]
                # score the NEW tree against the other nets only -- no double count
                o2 = set()
                for k2, v2 in routes.items():
                    if k2 != nid:
                        o2 |= v2
                d2 = c.spt(nid, o2)
                if all(c.pv[s] in d2 for s in c.NET[nid].sinks):
                    new_delay = sum(d2[c.pv[s]] for s in c.NET[nid].sinks)
                    if new_delay < cur_delay and not (nv & o2):
                        routes[nid] = nv
                        occ |= nv
                        improved = True
                        continue
            occ |= v
    # honest total: score each net against the OTHERS only
    total = 0
    ok = True
    for nid, v in routes.items():
        o2 = set()
        for k2, v2 in routes.items():
            if k2 != nid:
                o2 |= v2
        d = c.spt(nid, o2)
        if not all(c.pv[s] in d for s in c.NET[nid].sinks):
            ok = False
            continue
        total += sum(d[c.pv[s]] for s in c.NET[nid].sinks)
    return routes, total, rounds, ok


def main():
    TARGET = 8674
    c = Case(r"F:\eda-3d-routing-challenge\benchmarks_hard\case_01.json")
    base = load_pr3_routes(c)
    # re-score PR#3's own solution through our engine as a self-check
    r0, tot0, _, ok0 = one_opt_sets(c, dict((k, set(v)) for k, v in base.items()))
    print(f"case_01: PR#3 = {tot0} (target {TARGET}) self-check={tot0 == TARGET}")
    if tot0 != TARGET:
        print("  ENGINE MISMATCH -- do not trust anything below")
        return

    rng = random.Random(3)
    results = []
    t0 = time.time()

    # --- A. rip up k nets, reroute in random order (k = 1..8)
    for k in (1, 2, 4, 8):
        for trial in range(6):
            cur = dict((k2, set(v)) for k2, v in base.items())
            occ = set()
            for v in cur.values():
                occ |= v
            victims = rng.sample(sorted(cur), min(k, len(cur)))
            for nid in victims:
                occ -= cur[nid]
            for nid in rng.sample(victims, len(victims)):
                r = c.place(nid, occ, None)
                if r is not None:
                    cur[nid] = r[0]
                    occ |= r[0]
            cur, tot, _, _ok = one_opt_sets(c, cur)
            results.append((f"rirup{k}#{trial}", tot))

    # --- B. force a net onto an alternative EQUAL-cost SPT (plateau move)
    n_alt = 0
    for nid in sorted(base):
        occ = set()
        for k2, v in base.items():
            if k2 != nid:
                occ |= v
        # jitter breaks ties inside the SPT search -> a different equal-cost tree
        jt = {v: rng.random() * 0.9 for v in range(c.W * c.H * c.L)}
        r = c.place(nid, occ, jt)
        if r is None:
            continue
        cur = dict((k2, set(v)) for k2, v in base.items())
        cur[nid] = r[0]
        cur, tot, _, _ok = one_opt_sets(c, cur)
        results.append((f"altSpt_net{nid}", tot))
        n_alt += 1

    # --- C. combined: plateau move + ripup of its neighbours
    for trial in range(8):
        cur = dict((k2, set(v)) for k2, v in base.items())
        nid = rng.choice(sorted(cur))
        occ = set()
        for k2, v in cur.items():
            if k2 != nid:
                occ |= v
        jt = {v: rng.random() * 0.9 for v in range(c.W * c.H * c.L)}
        r = c.place(nid, occ, jt)
        if r is None:
            continue
        cur[nid] = r[0]
        occ = set()
        for v in cur.values():
            occ |= v
        victims = rng.sample(sorted(cur), min(3, len(cur)))
        for vv in victims:
            occ -= cur[vv]
        for vv in rng.sample(victims, len(victims)):
            rr = c.place(vv, occ, None)
            if rr is not None:
                cur[vv] = rr[0]
                occ |= rr[0]
        cur, tot, _, _ok = one_opt_sets(c, cur)
        results.append((f"combo#{trial}", tot))

    vals = [t for _, t in results]
    below = [v for v in vals if v < TARGET]
    print(f"\nperturbations run: {len(vals)}   (alt-SPT nets tried: {n_alt})")
    print(f"distinct 1-opt fixed points reached: {sorted(set(vals))}")
    print(f"below PR#3 ({TARGET}): {len(below)}")
    if below:
        print(f"  BEST: {min(below)}   delta {TARGET - min(below):+d}")
    else:
        print("  -> PR#3 is a DOMINANT ATTRACTOR: every perturbation re-closes to 8674.")
    print(f"elapsed {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
