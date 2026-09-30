"""Baseline harness: load PR#5, verify against the checker, run 1-opt to fixpoint."""
from __future__ import annotations
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from m3d.model import Instance
from seqrepair.engine import Grid, State, verify_state, dijkstra, extract_tree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(case):
    inst = Instance.load(os.path.join(ROOT, "benchmarks_hard", f"{case}.json"))
    g = Grid(inst)
    st = State(inst, g)
    st.load_submission(os.path.join(ROOT, "work", "pr5_hard", f"{case}.sol.json"))
    return inst, g, st


def net_opt(st, g, nid, rand=None):
    """Exact per-net optimum = shortest-path tree given other nets fixed."""
    net = st.nets[nid]
    blocked = st.blocked_mask(nid)
    src = g.xyz(st.pin_vertex[net.driver])
    sinks = [g.xyz(st.pin_vertex[s]) for s in net.sinks]
    dist, par = dijkstra(g, src, blocked, None, rand)
    return extract_tree(g, par, src, sinks, dist)


if __name__ == "__main__":
    cases = sys.argv[1:] or [f"case_0{i}" for i in range(1, 10)]
    tot = 0
    for c in cases:
        t0 = time.time()
        inst, g, st = load(c)
        ok, tot_c = verify_state(st, c)
        base = tot_c
        # 1-opt to fixpoint, strictly delay-descending
        moved = 0
        for sweep in range(30):
            ch = 0
            for n in inst.nets:
                v, e, sd = net_opt(st, g, n.id)
                if v is None:
                    continue
                nd = sum(sd)
                if nd < st.delay[n.id]:
                    st._commit(n.id, v, e, nd)
                    ch += 1
            moved += ch
            if ch == 0:
                break
        ok2, tot2 = verify_state(st, c + "-1opt")
        print(f"{c}: pr5={base} after_1opt={tot2} nets_moved={moved} "
              f"sweeps={sweep+1} t={time.time()-t0:.1f}s", flush=True)
        tot += tot2
    print(f"TOTAL {tot}")
