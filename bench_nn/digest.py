"""Pre-digest an M3D instance JSON into the flat whitespace format the C++
microbenchmark reads: W H L via nNets, layer delays, then per net the pin count
and pin (x,y,z) vertex ids.

Vertex id packing must match m3d/grid.py: vid = (z*H + y)*W + x.
"""
import json
import sys


def digest(path, out):
    d = json.load(open(path))
    g = d["grid"]
    W, H, L = g["width"], g["height"], g["layers"]
    via = d["delay"]["via_delay"]
    ld = d["delay"]["layer_delay"]
    pv = {p["id"]: (p["x"], p["y"], p["z"]) for p in d["pins"]}
    nets = d["nets"]
    with open(out, "w") as f:
        f.write(f"{W} {H} {L} {via} {len(nets)}\n")
        f.write(" ".join(map(str, ld)) + "\n")
        for n in nets:
            pins = [n["driver"]] + list(n["sinks"])
            vids = [(pv[p][2] * H + pv[p][1]) * W + pv[p][0] for p in pins]
            f.write(str(len(vids)) + " " + " ".join(map(str, vids)) + "\n")
    return W, H, L, len(nets), sum(len(n["sinks"]) + 1 for n in nets)


if __name__ == "__main__":
    for name in sys.argv[1:]:
        print(name, digest(name, name.replace(".json", ".txt")))
