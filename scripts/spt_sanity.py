"""Sanity: load PR#3, verify our own delay model matches the repo checker,
verify a lex-rebuild is a true zero-cost re-selection, and time one sweep."""
import json
import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spt_search as S

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from m3d.model import Instance, Submission
from m3d.checker import check


def main(case="case_01"):
    inst = Instance.load(os.path.join(REPO, "benchmarks_hard", case + ".json"))
    g = S.Graph(inst.width, inst.height, inst.layers,
                inst.layer_delay, inst.via_delay)
    name, nets, pin_owner = S.load_case(g, os.path.join(REPO, "benchmarks_hard", case + ".json"))
    sol = os.path.join(REPO, "submissions", "hard", "spt_reselect", case + ".sol.json")
    st = S.State(g, nets, pin_owner)
    S.load_sol(g, nets, sol, st)
    S.set_total(st)
    print("my total       :", st.total)

    res = check(inst, Submission.load(sol))
    print("checker total  :", res.total_delay, "legal", res.legal)

    # verify our r_verts/r_edges reconstruct the checker's view
    bad = 0
    for i, n in enumerate(nets):
        exp = set()
        for (a, b) in st.r_edges[i]:
            exp.add(a); exp.add(b)
        exp.add(n["driver"])
        for s in n["sinks"]:
            exp.add(s)
        if exp != st.r_verts[i]:
            bad += 1
    print("vertex-mismatch nets:", bad)

    # time a dijkstra
    t = time.time()
    st.ripup(0)
    d = S.reroute(st, 0, None)
    print(f"one reroute (lex): {time.time()-t:.3f}s  delay={d} (was {st.ndelay[0]})")
    t = time.time()
    st.ripup(0)
    press = S.make_pressure(g, st, 2.0, 1.0, 0.5)
    d2 = S.reroute(st, 0, press)
    print(f"one reroute (press): {time.time()-t:.3f}s delay={d2} (lex was {d})  verts {len(st.r_verts[0])}")
    t = time.time()
    S.sweep(st, list(range(st.nv)))
    print(f"full sweep: {time.time()-t:.2f}s total={st.total}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "case_01")
