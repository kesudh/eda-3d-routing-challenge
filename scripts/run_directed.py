"""Run the directed zero-cost SPT re-selection over benchmarks_hard."""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import spt_search as S
import spt_directed as D
from m3d.model import Instance
from m3d.checker import check

CASES = ["case_%02d" % i for i in range(1, 10)]
BASE = {"case_01": 8674, "case_02": 13230, "case_03": 11086, "case_04": 13095,
        "case_05": 15311, "case_06": 19882, "case_07": 21433, "case_08": 21620,
        "case_09": 21476}


def run_case(case, seconds, seed, src_dir, out_dir, log=print):
    inst = Instance.load(os.path.join(REPO, "benchmarks_hard", case + ".json"))
    g = S.Graph(inst.width, inst.height, inst.layers,
                inst.layer_delay, inst.via_delay)
    name, nets, po = S.load_case(g, os.path.join(REPO, "benchmarks_hard", case + ".json"))
    st = S.State(g, nets, po)
    S.load_sol(g, nets, os.path.join(src_dir, case + ".sol.json"), st)
    # populate ndelay from the loaded route
    S.set_total(st)
    S.sweep(st, list(range(st.nv)))       # make sure we start at a 1-opt fixpoint
    start = st.total
    log(f"  {case}: start(after 1-opt sweep)={start}  target={BASE[case]}")
    best = D.optimize_case(g, nets, po, st, seconds, seed=seed, log=log)
    os.makedirs(out_dir, exist_ok=True)
    S.dump_sol(g, nets, st, os.path.join(out_dir, case + ".sol.json"))
    return start, best


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--cases", default="case_01")
    ap.add_argument("--src", default=os.path.join(REPO, "submissions", "hard", "spt_reselect"))
    ap.add_argument("--out", default=os.path.join(REPO, "submissions", "hard", "spt_reselect"))
    a = ap.parse_args()
    for c in a.cases.split(","):
        run_case(c, a.seconds, a.seed, a.src, a.out)
