"""Sequential repair: steepest descent over TRANSACTIONAL group moves.

Why transactions and not single-net moves
-----------------------------------------
Given fixed obstacles a net's optimum IS its shortest-path tree, so a single-net
reroute can never change the total: it is either a no-op (already optimal) or
strictly worse.  PR#5's "sequential repair" must therefore mean a *transaction*:
net A gives up cells (possibly at a delay cost) and net B picks them up for a
larger gain.  The move class is

    (A, contested cell c) -> reroute A with c penalised
                          -> collect the gain of every net that can now reach a
                             cheaper tree

and we commit the single best strictly-improving transaction, then continue to
the next net.  This is the disciplined version of the random-restart move
class: the search is aimed at cells a *specific* starved net actually wants,
instead of hopping to a random point of an SPT face.

The zero-cost half of the neighbourhood (the plateau) comes from equal-delay
tie-breaking; the bounded-uphill half from the measured +2 delay quantum.

evaluate() is PURE: it never mutates State, so there is no rollback path that
could corrupt the incumbent.
"""
from __future__ import annotations

import os
import random
import sys
from typing import Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from seqrepair.engine import Grid, State, dijkstra, extract_tree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NEG = float("inf")


class Solver:
    def __init__(self, inst, g: Grid, st: State):
        self.inst = inst
        self.g = g
        self.st = st
        self.nets = {n.id: n for n in inst.nets}
        self.pv = st.pin_vertex
        self.src: Dict[int, int] = {}
        self.sinks: Dict[int, List[int]] = {}
        self.foreign_mask: Dict[int, bytearray] = {}
        for n in inst.nets:
            nid = n.id
            self.src[nid] = g.xyz(self.pv[n.driver])
            self.sinks[nid] = [g.xyz(self.pv[s]) for s in n.sinks]
            b = bytearray(g.N)
            for v, o in st.pin_owner.items():
                if o != nid:
                    b[v] = 1
            self.foreign_mask[nid] = b
        # Ideal (obstacle-free) SPT per net: the cells this net *wants*.  Static
        # -- it depends only on foreign pins.
        self.ideal: Dict[int, Tuple[frozenset, object]] = {}
        for n in inst.nets:
            nid = n.id
            d, par = dijkstra(g, self.src[nid], self.foreign_mask[nid])
            v, e, sd = extract_tree(g, par, self.src[nid], self.sinks[nid], d)
            self.ideal[nid] = (frozenset(v) if v else frozenset(),
                               sum(sd) if sd else NEG)
        # reverse index: cell -> nets whose ideal tree wants it
        self.wanters: Dict[int, List[int]] = {}
        for nid, (vs, _) in self.ideal.items():
            for v in vs:
                self.wanters.setdefault(v, []).append(nid)
        self.mid_layers = {z for z in range(g.L)
                           if inst.layer_delay[z] == min(inst.layer_delay)}
        # Bound on a victim's delay cost per transaction.  The measured quantum
        # is +2 per SINK, so a fanout-6 net pays up to 12 to give up one cell;
        # the default caps just above that.  Raised by experiments to test
        # whether dearer transactions ever repay.
        self.cost_cap = 12

    # -- primitives --------------------------------------------------------
    def reroute(self, nid: int, blocked: bytearray,
                penalty: Optional[Dict[int, int]] = None,
                rand: Optional[Sequence[float]] = None):
        d, par = dijkstra(self.g, self.src[nid], blocked, penalty, rand)
        return extract_tree(self.g, par, self.src[nid], self.sinks[nid], d)

    def mask_for(self, nid: int, replace: Optional[Tuple[int, frozenset]] = None) -> bytearray:
        """Blocked mask for net nid.  If `replace` = (A, newA_cells), net A's
        current footprint is ignored and newA_cells is used instead."""
        b = bytearray(self.foreign_mask[nid])
        st = self.st
        if replace is not None:
            A, newset = replace
            oldA = st.tree[A][0] if A in st.tree else ()
            for v in oldA:
                if st.vowner.get(v) == A:
                    continue
                b[v] = 1
            for v in newset:
                if st.pin_owner.get(v) == nid:
                    continue
                b[v] = 1
            for v, o in st.vowner.items():
                if o != nid and o != A:
                    b[v] = 1
            return b
        for v, o in st.vowner.items():
            if o != nid:
                b[v] = 1
        return b

    # -- candidate generation ---------------------------------------------
    def starved(self) -> List[Tuple[int, int]]:
        """(net, gap): gap = current delay - ideal obstacle-free delay.
        Only these nets can GAIN; every other net is already at its optimum."""
        out = []
        for nid in self.nets:
            _, ideal_d = self.ideal[nid]
            if ideal_d == NEG:
                continue
            gap = self.st.delay[nid] - ideal_d
            if gap > 0:
                out.append((nid, gap))
        out.sort(key=lambda t: (-t[1], t[0]))
        return out

    def contested(self, starved_nets) -> List[Tuple[int, int, int]]:
        """(victim A, starved B, cell): A owns a cell that B's ideal tree wants.

        Restricted to the cheap middle layers, where contention actually lives.
        """
        g = self.g
        out = []
        for B, _gap in starved_nets:
            ivs = self.ideal[B][0]
            if not ivs:
                continue
            for c in ivs:
                if (c // g.WH) not in self.mid_layers:
                    continue
                A = self.st.vowner.get(c)
                if A is None or A == B:
                    continue
                if self.st.pin_owner.get(c) == A:
                    continue          # a net can never give up its own pin
                out.append((A, B, c))
        return out

    # -- the transaction ---------------------------------------------------
    def evaluate(self, A: int, cells: Sequence[int], penalty: float,
                 rand: Optional[Sequence[float]] = None):
        """Pure evaluation.  Reroute A with `cells` penalised, then measure the
        gain of every net that can now reach a cheaper tree.

        Returns a result dict, or None if the transaction is inapplicable.
        """
        st = self.st
        old_A_delay = st.delay[A]
        old_A_cells = frozenset(st.tree[A][0])

        blocked = self.mask_for(A)
        for c in cells:                      # A must not keep using them
            if self.st.pin_owner.get(c) != A:
                blocked[c] = 1
        pen = {c: penalty for c in cells
               if self.st.pin_owner.get(c) != A}
        v, e, sd = self.reroute(A, blocked, penalty=pen, rand=rand)
        if v is None:
            return None
        new_A_delay = sum(sd)
        new_A_cells = frozenset(v)
        if new_A_cells == old_A_cells:
            return None
        freed = old_A_cells - new_A_cells
        if not freed:
            return None
        cost = new_A_delay - old_A_delay
        if cost > self.cost_cap:             # bounded; quantum is +2 per sink
            return None

        touched: Set[int] = set()
        for c in freed:
            for C in self.wanters.get(c, ()):
                if C != A:
                    touched.add(C)
        commits = {A: (v, e, new_A_delay)}
        gain = 0
        for C in sorted(touched):
            bl = self.mask_for(C, replace=(A, new_A_cells))
            v2, e2, sd2 = self.reroute(C, bl)
            if v2 is None:
                continue
            nd = sum(sd2)
            if nd < st.delay[C]:
                gain += st.delay[C] - nd
                commits[C] = (v2, e2, nd)
        return {"net_delta": cost - gain, "commits": commits, "cost": cost,
                "gain": gain, "freed": len(freed), "n_nets": len(commits)}

    def apply(self, commits):
        for nid, (v, e, d) in commits.items():
            self.st._commit(nid, v, e, d)

    # -- plateau move: equal-delay tie-breaking that happens to free a cell ---
    def plateau(self, A: int, rand: Sequence[float]):
        """Reroute A with a randomised tie-break and NO forced cell.  By
        construction the delay is unchanged (same shortest-path tree, different
        parent choices among tight arcs), so this is the zero-cost half of the
        neighbourhood.  Returns the same result dict as evaluate()."""
        st = self.st
        old_A_delay = st.delay[A]
        old_A_cells = frozenset(st.tree[A][0])
        blocked = self.mask_for(A)
        v, e, sd = self.reroute(A, blocked, None, rand)
        if v is None:
            return None
        new_A_delay = sum(sd)
        new_A_cells = frozenset(v)
        if new_A_cells == old_A_cells:
            return None
        if new_A_delay != old_A_delay:
            return None            # plateau only: never accept a cost here
        freed = old_A_cells - new_A_cells
        if not freed:
            return None
        touched: Set[int] = set()
        for c in freed:
            for C in self.wanters.get(c, ()):
                if C != A:
                    touched.add(C)
        commits = {A: (v, e, new_A_delay)}
        gain = 0
        for C in sorted(touched):
            bl = self.mask_for(C, replace=(A, new_A_cells))
            v2, e2, sd2 = self.reroute(C, bl)
            if v2 is None:
                continue
            nd = sum(sd2)
            if nd < st.delay[C]:
                gain += st.delay[C] - nd
                commits[C] = (v2, e2, nd)
        return {"net_delta": -gain, "commits": commits, "cost": 0,
                "gain": gain, "freed": len(freed), "n_nets": len(commits)}

    def randvec(self, rng) -> List[float]:
        """Small random offsets for Dijkstra tie-breaking.  Must be << 1 so it
        only ever breaks exact ties, never changes which paths are shortest."""
        return [rng.random() * 0.5 for _ in range(self.g.N)]
