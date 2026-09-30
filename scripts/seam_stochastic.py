"""Stochastic confirmation: many random tight-DAG tie-breaks, full 1-opt
sweeps, keep only strict improvements. This is the 'local search' version of
the hypothesis, run for real rather than argued about."""
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import spt_search as S
from m3d.model import Instance
from m3d.checker import check

CASES = ["case_%02d" % i for i in range(1, 10)]


def load(case):
    inst = Instance.load(os.path.join(REPO, "benchmarks_hard", case + ".json"))
    g = S.Graph(inst.width, inst.height, inst.layers,
                inst.layer_delay, inst.via_delay)
    name, nets, po = S.load_case(g, os.path.join(REPO, "benchmarks_hard", case + ".json"))
    st = S.State(g, nets, po)
    S.load_sol(g, nets, os.path.join(
        REPO, "submissions", "hard", "spt_reselect", case + ".sol.json"), st)
    S.sweep(st, list(range(st.nv)))
    return inst, g, nets, po, st


def main(seconds=30.0, seed=0):
    gs = gb = 0
    for case in CASES:
        inst, g, nets, po, st = load(case)
        start = st.total
        best = start
        best_snap = st.snap()
        rng = random.Random(seed)
        t0 = time.time()
        it = 0
        while time.time() - t0 < seconds:
            it += 1
            pre = st.snap()
            # random zero-cost re-selection of a random subset of nets
            for n in range(st.nv):
                if rng.random() < 0.35:
                    st.ripup(n)
                    S.reroute(st, n, [rng.random() for _ in range(g.n)])
            for _ in range(2):
                for n in range(st.nv):
                    st.ripup(n)
                    S.reroute(st, n, None)
            st.total = sum(st.ndelay)
            if st.total < best:
                best = st.total
                best_snap = st.snap()
            else:
                st.restore(pre)
        st.restore(best_snap)
        gs += start
        gb += best
        print(f"{case}: {start} -> {best}  ({it} trials)")
    print()
    print(f"stochastic: PR#3={gs}  ours={gb}  delta={gb-gs:+d}")


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 30.0,
         int(sys.argv[2]) if len(sys.argv) > 2 else 0)
