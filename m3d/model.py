"""Data model, delay profile, and JSON (de)serialization for the 3D routing challenge.

The stack is a simplified hybrid-bonded 3D one (the package name ``m3d`` is
historical). Two dies (bottom = die 0, top = die 1) share a
vertical stack of ``layers`` routing layers indexed by z in ``0..layers-1``.

Routing graph
-------------
A vertex is an integer triple ``(x, y, z)`` with ``0 <= x < width``,
``0 <= y < height``, ``0 <= z < layers``. Legal moves (undirected edges):

* an in-layer step: change x or y by exactly 1, same z; cost = ``layer_delay[z]``;
* a via: change z by exactly 1, same (x, y); cost = ``via_delay``.

No diagonal moves, no skipped layers. Bottom-die pins live on layer ``z = 0``;
top-die pins live on layer ``z = layers - 1``.

All delays are positive integers and are stored explicitly in every instance so
scoring is deterministic and independent of any recomputed profile.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Sequence, Tuple

Vertex = Tuple[int, int, int]  # (x, y, z)
Edge = Tuple[Vertex, Vertex]   # unordered pair of adjacent vertices

BOTTOM_DIE = 0
TOP_DIE = 1

INSTANCE_FORMAT = "m3d-instance"
SUBMISSION_FORMAT = "m3d-submission"
RESULT_FORMAT = "m3d-result"
FORMAT_VERSION = 1


# --------------------------------------------------------------------------- #
# Delay profile
# --------------------------------------------------------------------------- #
def layer_delay_profile(layers: int, center_delay: int, slope: int) -> List[int]:
    """Return the per-layer, per-edge delay list.

    The profile is symmetric about the middle of the stack, lowest in the middle
    and highest near either die. Using ``|2z - (layers - 1)|`` keeps every value
    an exact integer and perfectly symmetric for both odd and even ``layers``::

        delay[z] = center_delay + slope * |2*z - (layers - 1)|

    * odd ``layers``: the single middle layer gets exactly ``center_delay``;
    * even ``layers``: the two middle layers tie at ``center_delay + slope``.

    All values are >= 1 as long as ``center_delay >= 1`` and ``slope >= 0``.
    """
    if layers < 1:
        raise ValueError("layers must be >= 1")
    if center_delay < 1:
        raise ValueError("center_delay must be >= 1")
    if slope < 0:
        raise ValueError("slope must be >= 0")
    return [center_delay + slope * abs(2 * z - (layers - 1)) for z in range(layers)]


# --------------------------------------------------------------------------- #
# Instance structures
# --------------------------------------------------------------------------- #
@dataclass
class Cell:
    id: int
    die: int          # BOTTOM_DIE or TOP_DIE
    x: int            # lower-left vertex x of the footprint
    y: int            # lower-left vertex y of the footprint
    w: int            # footprint width in vertices (occupies x .. x+w-1)
    h: int            # footprint height in vertices (occupies y .. y+h-1)


@dataclass
class Pin:
    id: int
    cell: int
    die: int
    x: int
    y: int
    z: int            # 0 for bottom die, layers-1 for top die

    def vertex(self) -> Vertex:
        return (self.x, self.y, self.z)


@dataclass
class Net:
    id: int
    driver: int              # pin id
    sinks: List[int]         # pin ids (>= 1)

    def pins(self) -> List[int]:
        return [self.driver] + list(self.sinks)


@dataclass
class Instance:
    name: str
    width: int
    height: int
    layers: int
    layer_delay: List[int]
    via_delay: int
    cells: List[Cell]
    pins: List[Pin]
    nets: List[Net]
    params: Dict = field(default_factory=dict)
    seed: int = 0
    master_seed: int = 0

    # -- convenience indices -------------------------------------------------
    def pin_by_id(self) -> Dict[int, Pin]:
        return {p.id: p for p in self.pins}

    def pin_vertex(self) -> Dict[int, Vertex]:
        return {p.id: p.vertex() for p in self.pins}

    def vertex_to_pin(self) -> Dict[Vertex, int]:
        return {p.vertex(): p.id for p in self.pins}

    def pin_to_net(self) -> Dict[int, int]:
        m: Dict[int, int] = {}
        for net in self.nets:
            for pid in net.pins():
                m[pid] = net.id
        return m

    def in_bounds(self, v: Vertex) -> bool:
        x, y, z = v
        return 0 <= x < self.width and 0 <= y < self.height and 0 <= z < self.layers

    def edge_delay(self, u: Vertex, v: Vertex) -> int:
        """Delay of a *legal* edge. Raises ValueError on an illegal move."""
        (ux, uy, uz), (vx, vy, vz) = u, v
        dx, dy, dz = abs(ux - vx), abs(uy - vy), abs(uz - vz)
        if dz == 0 and dx + dy == 1:
            return self.layer_delay[uz]
        if dx == 0 and dy == 0 and dz == 1:
            return self.via_delay
        raise ValueError(f"illegal move between {u} and {v}")

    # -- JSON ---------------------------------------------------------------
    def to_dict(self) -> Dict:
        return {
            "format": INSTANCE_FORMAT,
            "version": FORMAT_VERSION,
            "name": self.name,
            "grid": {"width": self.width, "height": self.height, "layers": self.layers},
            "delay": {"layer_delay": list(self.layer_delay), "via_delay": self.via_delay},
            "cells": [asdict(c) for c in self.cells],
            "pins": [asdict(p) for p in self.pins],
            "nets": [{"id": n.id, "driver": n.driver, "sinks": list(n.sinks)} for n in self.nets],
            "params": self.params,
            "seed": self.seed,
            "master_seed": self.master_seed,
        }

    @staticmethod
    def from_dict(d: Dict) -> "Instance":
        if d.get("format") != INSTANCE_FORMAT:
            raise ValueError(f"not an {INSTANCE_FORMAT} document")
        g = d["grid"]
        delay = d["delay"]
        return Instance(
            name=d["name"],
            width=g["width"],
            height=g["height"],
            layers=g["layers"],
            layer_delay=list(delay["layer_delay"]),
            via_delay=delay["via_delay"],
            cells=[Cell(**c) for c in d["cells"]],
            pins=[Pin(**p) for p in d["pins"]],
            nets=[Net(id=n["id"], driver=n["driver"], sinks=list(n["sinks"])) for n in d["nets"]],
            params=d.get("params", {}),
            seed=d.get("seed", 0),
            master_seed=d.get("master_seed", 0),
        )

    def save(self, path: str) -> None:
        with open(path, "w") as fh:
            json.dump(self.to_dict(), fh, indent=1, sort_keys=False)

    @staticmethod
    def load(path: str) -> "Instance":
        with open(path, encoding="utf-8-sig") as fh:
            return Instance.from_dict(json.load(fh))


# --------------------------------------------------------------------------- #
# Submission structures
# --------------------------------------------------------------------------- #
def canon_edge(u: Vertex, v: Vertex) -> Edge:
    """Return an edge as an ordered pair (smaller vertex first) for dedup/hashing."""
    return (u, v) if tuple(u) <= tuple(v) else (v, u)


class SubmissionFormatError(ValueError):
    """A submission file is not a well-formed m3d-submission document."""


def _vertex(v, where: str) -> Vertex:
    # coordinates must be JSON integers: no floats (which int() would silently
    # truncate, e.g. -0.9 -> 0), no booleans, no numeric strings
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        raise SubmissionFormatError(f"{where}: a vertex must be [x, y, z], got {v!r}")
    for c in v:
        if type(c) is not int:
            raise SubmissionFormatError(f"{where}: coordinates must be integers, got {c!r}")
    return tuple(v)


@dataclass
class NetRoute:
    net: int
    edges: List[Edge]


@dataclass
class Submission:
    instance: str
    routes: List[NetRoute]

    def to_dict(self) -> Dict:
        return {
            "format": SUBMISSION_FORMAT,
            "version": FORMAT_VERSION,
            "instance": self.instance,
            "routes": [
                {"net": r.net, "edges": [[list(a), list(b)] for (a, b) in r.edges]}
                for r in self.routes
            ],
        }

    @staticmethod
    def from_dict(d: Dict) -> "Submission":
        if not isinstance(d, dict) or d.get("format") != SUBMISSION_FORMAT:
            raise SubmissionFormatError(f"not an {SUBMISSION_FORMAT} document")
        if not isinstance(d.get("routes"), list):
            raise SubmissionFormatError("'routes' must be a list")
        routes = []
        for i, r in enumerate(d["routes"]):
            if (not isinstance(r, dict) or type(r.get("net")) is not int
                    or not isinstance(r.get("edges"), list)):
                raise SubmissionFormatError(
                    f"routes[{i}]: expected {{\"net\": <int>, \"edges\": [...]}}")
            edges = []
            for j, e in enumerate(r["edges"]):
                where = f"routes[{i}].edges[{j}]"
                if not isinstance(e, (list, tuple)) or len(e) != 2:
                    raise SubmissionFormatError(f"{where}: an edge must be a pair of vertices")
                edges.append((_vertex(e[0], where), _vertex(e[1], where)))
            routes.append(NetRoute(net=r["net"], edges=edges))
        return Submission(instance=d.get("instance", ""), routes=routes)

    def save(self, path: str) -> None:
        with open(path, "w") as fh:
            json.dump(self.to_dict(), fh, indent=1)

    @staticmethod
    def load(path: str) -> "Submission":
        # utf-8-sig: accept files written with a byte-order mark (common on Windows)
        with open(path, encoding="utf-8-sig") as fh:
            return Submission.from_dict(json.load(fh))
