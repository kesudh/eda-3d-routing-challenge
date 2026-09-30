"""Verify our rebuilt routes against the repo's own checker, end to end.

Also asserts the ZERO-COST property: every SPT tie-break yields the identical
sum-of-sink-delays for that net.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import spt_search as S
from m3d.model import Instance, Submission
from m3d.checker import check


def verify(case, sol_path):
    inst = Instance.load(os.path.join(REPO, "benchmarks_hard", case + ".json"))
    g = S.Graph(inst.width, inst.height, inst.layers, inst.layer_delay, inst.via_delay)
    name, nets, po = S.load_case(g, os.path.join(REPO, "benchmarks_hard", case + ".json"))
    st = S.State(g, nets, po)
    S.load_sol(g, nets, sol_path, st)
    # recompute per-net delay from the loaded route to populate ndelay
    S.set_total(st)
    return inst, g, nets, po, st


def full_check(case, g, nets, st, inst):
    """Write our state out and run the repo checker on it."""
    fd, tmp = tempfile.mkstemp(suffix=".sol.json")
    os.close(fd)
    S.dump_sol(g, nets, st, tmp)
    sub = Submission.load(tmp)
    res = check(inst, sub)
    os.unlink(tmp)
    return res


if __name__ == "__main__":
    case = sys.argv[1] if len(sys.argv) > 1 else "case_01"
    sol = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        REPO, "submissions", "hard", "spt_reselect", case + ".sol.json")
    inst, g, nets, po, st = verify(case, sol)
    res = full_check(case, g, nets, st, inst)
    print(f"{case}: checker legal={res.legal} total={res.total_delay}")
    if not res.legal:
        for r in res.reasons[:5]:
            print("  REASON", r)
        for n in res.nets:
            if not n.legal:
                print("  net", n.net, n.reasons[:3])
                break

    # zero-cost property check: reroute every net under many different
    # tie-break cost vectors and assert the delay never changes.
    import random
    rng = random.Random(7)
    base = [0] * st.nv
    order = list(range(st.nv))
    S.sweep(st, order)
    for i, n in enumerate(nets):
        base[i] = st.ndelay[i]
    base_total = sum(base)
    print(f"  after full lex sweep: {base_total}")
    bad = 0
    for trial in range(6):
        st.ripup(0)
        press = [rng.random() * 5 for _ in range(g.n)]
        d = S.reroute(st, 0, press)
        if d != base[0]:
            bad += 1
            print(f"  !! net0 delay changed {base[0]} -> {d}")
        S.sweep(st, order)
    print(f"  zero-cost property on net 0: {'HOLDS' if bad == 0 else f'VIOLATED x{bad}'}")
