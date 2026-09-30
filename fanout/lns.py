"""Joint multi-net LNS on top of PR#3's solutions.

Established fact #1 (independently re-verified here: 0 of 62 / 0 of 104 nets
move under exact per-net reroute to fixpoint) says no PER-NET congestion price
can improve PR#3's hard solutions: given the other nets as hard obstacles,
every net is already at its exact optimum. Pricing only steers the INITIAL
construction, and PR#3's construction already reaches a 1-fixed point.

So the only remaining lever is a move that changes SEVERAL nets at once. This
module rips up a set of nets and reroutes the set JOINTLY, in a chosen order,
with the rest of the design as hard obstacles, then runs a 1-opt fixpoint over
the ripped set. Accept only if the checker's total strictly improves.

The set is chosen to attack the measured residual: low-fanout nets walled into
middle-layer pockets (case_09 nets 28, 14, 95, 80, 7, 33, ~500 delay), plus
every net whose current route touches the region those nets need.
"""
from __future__ import annotations

import heapq
import time
from typing import Dict, List, Optional, Sequence, Set, Tuple

from m3d.checker import check
from m3d.model import Instance, NetRoute, Submission

from .dual import Prob
from .reopt import load_state, net_delay, spt_with_obstacles


def state_delay(inst, g, routes, src, sinks) -> Optional[int]:
    tot = 0
    for nid, (vs, es) in routes.items():
        d = net_delay(inst, g, vs, es, src[nid], sinks[nid])
        if d is None:
            return None
        tot += d
    return tot


def joint_ripup(inst: Instance, p: Prob, routes, rip: Set[int], order_key,
                fixed_rounds: int = 3):
    """Reroute the nets in `rip` jointly; return new routes or None if illegal."""
    g = p.g
    n = g.n
    src = {t[0]: t[1][0] for t in p.net_blocked}
    sinks = {t[0]: t[2] for t in p.net_blocked}
    new = dict(routes)
    for nid in rip:
        new[nid] = ({src[nid]}, set())
    for _ in range(fixed_rounds):
        for nid in sorted(rip, key=order_key):
            vs, es = new[nid]
            blocked = bytearray(n)
            for other, (ovs, _oes) in new.items():
                if other == nid:
                    continue
                for v in ovs:
                    blocked[v] = 1
            r = spt_with_obstacles(g, src[nid], sinks[nid], blocked)
            if r is None:
                return None
            new[nid] = r
    return new


def check_routes(inst, g, routes):
    sub = Submission(instance=inst.name, routes=[
        NetRoute(net=k, edges=[(g.coord(a), g.coord(b)) for a, b in e])
        for k, (v, e) in sorted(routes.items())])
    return check(inst, sub)
