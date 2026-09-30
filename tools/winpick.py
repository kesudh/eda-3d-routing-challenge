"""Window selection strategies + the iterate-and-report driver."""
from __future__ import annotations

import os
import random
import sys
from typing import Dict, List, Sequence, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from m3d.model import Instance
from m3d.grid import Grid
from mipwindow import Vid, tree_delay


def window_nets(inst: Instance, routes, grid: Grid, window: int,
                strategy: str, seed: int) -> List[int]:
    nets = sorted(inst.nets, key=lambda n: n.id)
    ids = [n.id for n in nets]
    pv = inst.pin_vertex()
    if window >= len(ids):
        return ids
    if strategy == "seeded":
        return sorted(random.Random(seed).sample(ids, window))
    if strategy == "big":
        sc = sorted(((tree_delay(routes[n.id], grid, n, pv), n.id) for n in nets),
                    reverse=True)
        return sorted(i for _, i in sc[:window])
    if strategy == "contended":
        # nets crossing the most (vertex,edge) incidences in the congested
        # middle layers z=2,3 -- where hard is 81-90% occupied
        occ23: Set[Vid] = set()
        for nid, es in routes.items():
            for (u, v) in es:
                if grid.coord(u)[2] in (2, 3): occ23.add(u)
                if grid.coord(v)[2] in (2, 3): occ23.add(v)
        sc = []
        for n in nets:
            touch = sum(1 for (u, v) in routes[n.id] if u in occ23 or v in occ23)
            sc.append((touch, tree_delay(routes[n.id], grid, n, pv), n.id))
        sc.sort(reverse=True)
        return sorted(i for _, _, i in sc[:window])
    if strategy == "region":
        # every net touching a spatial box centred in the middle of the die
        g = grid
        cx, cy = g.w // 2, g.h // 2
        rad = max(3, min(g.w, g.h) // 5)
        box: Set[Vid] = set()
        for z in range(g.l):
            for y in range(max(0, cy - rad), min(g.h, cy + rad + 1)):
                for x in range(max(0, cx - rad), min(g.w, cx + rad + 1)):
                    box.add(g.vid((x, y, z)))
        keep = [n.id for n in nets
                if any(u in box or v in box for (u, v) in routes[n.id])]
        keep.sort()
        if not keep:
            return ids[:window]
        step = max(1, len(keep) // window)
        return sorted(keep[::step][:window])
    raise ValueError(strategy)
