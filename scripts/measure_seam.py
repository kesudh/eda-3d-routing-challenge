"""MEASUREMENT: can zero-cost SPT re-selection ever release a blocking vertex?

For every (detoured net m, free-optimal path, blocking vertex v owned by net o)
triple we ask: does net o have ANY shortest path tree that avoids v?

  * v is FORCED  -> every SPT of o contains v. Re-selecting o's SPT is a
                    ZERO-cost move that CANNOT release v. The seam is dead
                    for this triple.
  * v is CHOICE  -> some SPT of o avoids v at identical cost. The seam is live.

We test this directly by forbidding v in o's SPT selection and checking the
delay is unchanged while v is actually released.
"""
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

CASES = ["case_%02d" % i for i in range(1, 10)]


def main():
    grand = dict(triples=0, forced=0, choice=0, detour_sum=0,
                 forced_detour=0, choice_detour=0)
    for case in CASES:
        inst = Instance.load(os.path.join(REPO, "benchmarks_hard", case + ".json"))
        g = S.Graph(inst.width, inst.height, inst.layers,
                    inst.layer_delay, inst.via_delay)
        name, nets, po = S.load_case(g, os.path.join(REPO, "benchmarks_hard", case + ".json"))
        st = S.State(g, nets, po)
        S.load_sol(g, nets, os.path.join(
            REPO, "submissions", "hard", "spt_reselect", case + ".sol.json"), st)
        S.sweep(st, list(range(st.nv)))
        tot = sum(st.ndelay)
        f = c = 0
        fd = cd = 0
        seen_pairs = set()
        for m in range(st.nv):
            bl = D.blockers(st, g, m)
            for (det, _s, v, o) in bl:
                key = (m, v, o)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                pre = st.snap()
                ok, before, after, freed = D.release(st, g, o, {v})
                released = v not in st.r_verts[o]
                st.restore(pre)
                if ok and released:
                    c += 1
                    cd += det
                else:
                    f += 1
                    fd += det
        grand["triples"] += f + c
        grand["forced"] += f
        grand["choice"] += c
        grand["forced_detour"] += fd
        grand["choice_detour"] += cd
        print(f"{case}: total={tot:6d}  blocker-triples={f+c:5d}  "
              f"FORCED={f:5d} ({100.0*f/max(1,f+c):5.1f}%)  "
              f"CHOICE={c:5d} ({100.0*c/max(1,f+c):5.1f}%)  "
              f"detour behind CHOICE={cd}")
    g = grand
    print()
    print(f"TOTAL: triples={g['triples']} forced={g['forced']} choice={g['choice']} "
          f"({100.0*g['choice']/max(1,g['triples']):.2f}% releasable)")
    print(f"detour behind forced = {g['forced_detour']}, behind choice = {g['choice_detour']}")


if __name__ == "__main__":
    main()
