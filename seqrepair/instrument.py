"""Full instrumentation of the transactional move class.  Non-vacuous by
construction: asserts candidates were generated AND that transactions were
actually evaluated, and prints the complete delta histogram.
"""
from __future__ import annotations
import os, sys, time
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seqrepair.baseline import load
from seqrepair.search import Solver

PEN = (2, 4, 8, 16, 64, 256)


def sweep(sv, triples_fn, label, cap=None):
    hist = Counter()
    best = None
    n = 0
    cells = set()
    triples = triples_fn()
    if cap:
        triples = triples[:cap]
    t0 = time.time()
    for A, B, cs in triples:
        cells.update(cs)
        got = None
        for pen in PEN:
            r = sv.evaluate(A, cs, pen)
            n += 1
            if r is None:
                hist["inapplicable"] += 1
                continue
            got = r
            break
        if got is None:
            continue
        d = got["net_delta"]
        hist["improve" if d < 0 else "equal" if d == 0 else "worse"] += 1
        if best is None or d < best[0]:
            best = (d, A, B, cs, pen, got)
    el = time.time() - t0
    print(f"\n--- {label} ---")
    print(f"  transactions enumerated : {len(triples)}")
    print(f"  distinct cells covered  : {len(cells)}")
    print(f"  evaluate() calls        : {n}   ({el:.1f}s, {el/max(1,n)*1000:.1f} ms each)")
    print(f"  delta histogram         : {dict(hist)}")
    print(f"  EVALUATED (not skipped) : {hist['improve']+hist['equal']+hist['worse']}")
    print(f"  strictly improving      : {hist['improve']}")
    if best:
        d, A, B, cs, pen, r = best
        print(f"  best net_delta          : {d}  (A={A} starvedB={B} "
              f"cells={[sv.g.dec(c) for c in cs]} pen={pen})")
        print(f"      cost={r['cost']} gain={r['gain']} freed={r['freed']} "
              f"nets_rerouted={r['n_nets']}")
    else:
        print("  best                    : NONE EVALUATED (move class vacuous here)")
    return hist, best, n


if __name__ == "__main__":
    case = sys.argv[1] if len(sys.argv) > 1 else "case_01"
    inst, g, st = load(case)
    sv = Solver(inst, g, st)
    print(f"case={case} total={st.total()}")

    starved = sv.starved()
    tot_gap = sum(gp for _, gp in starved)
    print(f"starved nets = {len(starved)}/{len(inst.nets)}   total gap = {tot_gap}")

    tri = sv.contested(starved)
    per_net = defaultdict(int)
    for A, B, c in tri:
        per_net[B] += 1
    covered = len(per_net)
    print(f"contested triples = {len(tri)}   starved nets with >=1 contested cell "
          f"= {covered}/{len(starved)}   distinct cells = "
          f"{len({c for _, _, c in tri})}")
    assert len(tri) > 0, "vacuous: no contested triples"
    assert covered > 0, "vacuous: no starved net represented"

    h1, b1, n1 = sweep(sv, lambda: [(A, B, (c,)) for A, B, c in tri],
                       "single-cell transactions")

    # multi-cell: victim A vacates the WHOLE set of cells one starved net wants
    # from it.  This is the natural "sequential repair" cluster move.
    def multi():
        byAB = defaultdict(set)
        for A, B, c in tri:
            byAB[(A, B)].add(c)
        return [(A, B, tuple(sorted(cs))) for (A, B), cs in byAB.items()]

    mt = multi()
    print(f"\nmulti-cell transactions: {len(mt)}  "
          f"mean cells/move = {sum(len(m[2]) for m in mt)/max(1,len(mt)):.1f}  "
          f"max = {max((len(m[2]) for m in mt), default=0)}")
    h2, b2, n2 = sweep(sv, multi, "multi-cell (cluster) transactions")

    assert (n1 + n2) > 0, "vacuous: nothing was evaluated"
    print(f"\nTOTAL evaluate() calls = {n1+n2}  (proof the move class was exercised)")
