"""FINAL decisive test: force-release EVERY releasable vertex simultaneously.

This is the most favourable possible use of the zero-cost SPT re-selection
seam, applied globally rather than one net at a time:

  for each net n:
      forbid, in n's SPT selection, every vertex that some other SPT of n
      could omit. This releases the UNION of all choice vertices n owns, at
      provably ZERO delay cost to n.
  then run a full 1-opt sweep so every remaining net can exploit the room.

If the total does not move, the seam is closed and the result is a clean
negative.
"""
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


def releasable_set(st, g, n):
    """Vertices owned by n that some zero-cost SPT of n can omit."""
    cur = set(st.r_verts[n])
    rel = []
    for v in sorted(cur):
        pre = st.snap()
        ok, before, after, freed = D.release(st, g, n, {v})
        got = v not in st.r_verts[n]
        st.restore(pre)
        if ok and got:
            rel.append(v)
    return rel


def main():
    gs = gb = 0
    for case in CASES:
        inst, g, nets, po, st = load(case)
        start = st.total
        # global maximal release
        released_total = 0
        changed = 0
        for n in range(st.nv):
            rel = releasable_set(st, g, n)
            if not rel:
                continue
            before = len(st.r_verts[n])
            ok, b, a, freed = D.release(st, g, n, set(rel))
            if ok and freed != 0:
                changed += 1
                released_total += max(0, before - len(st.r_verts[n]))
        after_release = sum(st.ndelay)
        # full 1-opt sweep
        for _ in range(3):
            for n in range(st.nv):
                st.ripup(n)
                S.reroute(st, n, None)
        st.total = sum(st.ndelay)
        gs += start
        gb += st.total
        print(f"{case}: {start} -> release({changed} nets, {released_total} verts) "
              f"-> sweep = {st.total}   (delta {st.total-start:+d})")
    print()
    print(f"MAXIMAL zero-cost release + full 1-opt sweep:")
    print(f"  PR#3 = {gs} / 1.381266")
    print(f"  ours = {gb}")
    print(f"  delta = {gb-gs:+d} ({100.0*(gb-gs)/gs:+.4f}%)")


if __name__ == "__main__":
    main()
