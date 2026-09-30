"""3D routing-grid helpers shared by the baseline router.

Vertices are packed into a single integer id ``vid = (z*height + y)*width + x`` so
the router can use fast dict/set lookups and integer heaps. Edge keys are the
ordered pair ``(min(vid), max(vid))``.
"""
from __future__ import annotations

from typing import Iterator, List, Tuple

from .model import Instance, Vertex


class Grid:
    def __init__(self, inst: Instance):
        self.w = inst.width
        self.h = inst.height
        self.l = inst.layers
        self.layer_delay = list(inst.layer_delay)
        self.via_delay = inst.via_delay
        self.wh = self.w * self.h

    # -- id <-> coordinate ---------------------------------------------------
    def vid(self, v: Vertex) -> int:
        x, y, z = v
        return (z * self.h + y) * self.w + x

    def coord(self, vid: int) -> Vertex:
        z, r = divmod(vid, self.wh)
        y, x = divmod(r, self.w)
        return (x, y, z)

    # -- neighbours ----------------------------------------------------------
    def neighbors(self, vid: int) -> Iterator[Tuple[int, int]]:
        """Yield ``(neighbor_vid, edge_delay)`` for every legal move from ``vid``."""
        z, r = divmod(vid, self.wh)
        y, x = divmod(r, self.w)
        ld = self.layer_delay[z]
        if x + 1 < self.w:
            yield vid + 1, ld
        if x - 1 >= 0:
            yield vid - 1, ld
        if y + 1 < self.h:
            yield vid + self.w, ld
        if y - 1 >= 0:
            yield vid - self.w, ld
        if z + 1 < self.l:
            yield vid + self.wh, self.via_delay
        if z - 1 >= 0:
            yield vid - self.wh, self.via_delay


def edge_delay(grid: Grid, u: Vid, v: Vid) -> int:
    """Delay of the 3D edge between adjacent vertices u and v (packed vids)."""
    w, h = grid.w, grid.h
    du, ru = divmod(u, w * h)
    dv, rv = divmod(v, w * h)
    if du != dv:
        return grid.via_delay
    y1, x1 = divmod(ru, w)
    y2, x2 = divmod(rv, w)
    if abs(x1 - x2) + abs(y1 - y2) != 1:
        raise ValueError(f"{grid.coord(u)} and {grid.coord(v)} are not adjacent")
    return grid.layer_delay[du]


def edge_key(a: int, b: int) -> Tuple[int, int]:
    return (a, b) if a < b else (b, a)
