"""UPPER BOUND on the zero-cost SPT re-selection seam.

measure_seam.py showed only ~1.3% of blocking vertices can be released by an
equal-cost SPT re-selection of their owner (97-100% of the rest sit on the
owner's unique shortest path -- there is no alternative tree that avoids them).

This script takes the maximally favourable interpretation of that residual:
for every net, choose the SPT that occupies the FEWEST vertices (which releases
every choice vertex simultaneously, in the globally most favourable direction),
then run a full 1-opt sweep. If even that does not beat the incumbent, the seam
is closed.

Variants tried, all strictly zero-cost per net:
  minverts  - tie-break to minimise the vertex count of the net's own SPT
  minmid    - tie-break to minimise occupancy of the contended middle layers
  maxouter  - tie-break to maximise occupancy of the slack outer layers
  random    - random tight-DAG tie-break (restarts)
"""
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import spt_search as S
import spt_directed as D
from m3d.model import Instance, Submission
from m3d.checker import check

CASES = ["case_%02d" % i for i in range(1, 10)]
BASE = {"case_01": 8674, "case_02": 13230, "case_03": 11086, "case_04": 13095,
        "case_05": 15311, "case_06": 19882, "case_07": 21433, "case_08": 21620,
        "case_09": 21476}


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


def make_costs(g, variant, rng):
    if variant == "minverts":
        return [1.0] * g.n                       # every vertex costs 1
    if variant == "minmid":
        c = []
        for v in range(g.n):
            z = g.zof[v]
            c.append(0.0 if z in (2, 3) else 1.0)
        return c
    if variant == "maxouter":
        c = []
        for v in range(g.n):
            z = g.zof[v]
            c.append(0.0 if z in (1, 4) else 1.0)
        return c
    if variant == "random":
        return [rng.random() for _ in range(g.n)]
    raise ValueError(variant)


def run(case, variant, seed=0, sweeps=3):
    inst, g, nets, po, st = load(case)
    start = st.total
    rng = random.Random(seed)
    best = start
    for s in range(sweeps):
        order = list(range(st.nv))
        rng.shuffle(order)
        for n in order:
            st.ripup(n)
            S.reroute(st, n, make_costs(g, variant, rng))
        for _ in range(3):
            for n in list(range(st.nv)):
                st.ripup(n)
                S.reroute(st, n, None)
        st.total = sum(st.ndelay)
        best = min(best, st.total)
    return start, best


if __name__ == "__main__":
    variants = sys.argv[1].split(",") if len(sys.argv) > 1 else \
        ["minverts", "minmid", "maxouter", "random"]
    cases = sys.argv[2].split(",") if len(sys.argv) > 2 else CASES
    grand_start = grand_best = 0
    for v in variants:
        gs = gb = 0
        print(f"--- variant {v} ---")
        for c in cases:
            a, b = run(c, v)
            gs += a
            gb += b
            flag = "  <-- IMPROVED" if b < a else ""
            print(f"  {c}: {a} -> {b}{flag}")
        print(f"  TOTAL {gs} -> {gb}  ({100.0*(gs-gb)/gs:+.3f}%)")
        grand_start += gs
        grand_best += gb
    print()
    print(f"PR#3 = 145807 / 1.381266. Best achieved = {grand_best}")
