"""Convert an m3d instance + an initial submission into the flat text format the
C++ SA engine reads. Kept tiny on purpose: the engine has no JSON parser.

Format (whitespace separated, '#' starts a comment):

I <W> <H> <L> <via_delay>
D <d0> <d1> ... <d_{L-1}>
P <nPins>
C <count>            # `count` pin records follow
  <pinId> <x> <y> <z> <netId>
N <nNets>
  <netId> <driverPin> <nsinks> <s1> ... <sN>
E <nRouted>          # initial route block; 0 == start from empty
  <netId> <nEdges> <nDelay>
  <u> <v>            # nEdges lines, vertex ids as linear (z*H+y)*W+x
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def vid(x: int, y: int, z: int, W: int, H: int) -> int:
    return (z * H + y) * W + x


def main() -> None:
    inst_path, init_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    inst = json.loads(Path(inst_path).read_text())
    W = inst["grid"]["width"]
    H = inst["grid"]["height"]
    L = inst["grid"]["layers"]
    layer_delay = inst["delay"]["layer_delay"]
    via = inst["delay"]["via_delay"]

    pin_to_net = {}
    for n in inst["nets"]:
        for p in [n["driver"]] + list(n["sinks"]):
            pin_to_net[p] = n["id"]

    out = [
        f"# from {inst_path} init={init_path}",
        f"I {W} {H} {L} {via}",
        "D " + " ".join(str(v) for v in layer_delay),
        f"P {len(inst['pins'])}",
        f"C {len(inst['pins'])}",
    ]
    for p in inst["pins"]:
        out.append(f"  {p['id']} {p['x']} {p['y']} {p['z']} {pin_to_net[p['id']]}")
    out.append(f"N {len(inst['nets'])}")
    for n in inst["nets"]:
        out.append(f"  {n['id']} {n['driver']} {len(n['sinks'])} "
                   + " ".join(str(s) for s in n["sinks"]))

    if init_path and init_path != "-":
        sub = json.loads(Path(init_path).read_text())
        out.append(f"E {len(sub['routes'])}")
        for r in sub["routes"]:
            es = [(vid(a[0], a[1], a[2], W, H), vid(b[0], b[1], b[2], W, H))
                  for a, b in r["edges"]]
            out.append(f"  {int(r['net'])} {len(es)}")
            for u, v in es:
                out.append(f"  {u} {v}")
    else:
        out.append("E 0")

    Path(out_path).write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
