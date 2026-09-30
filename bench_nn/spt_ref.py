"""Python reference for the exact inner loop of an M3D router.

For each net, one single-source Dijkstra from the driver over the whole 3D grid
with every OTHER net's pin vertices blocked, then sum the distance to each sink.
That distance sum IS the net's shortest-path-tree delay (an SPT from one source
has exactly the per-sink shortest-path distances), so this is simultaneously:

  * the exact per-net optimum given fixed obstacles, and
  * the pins-only lower bound of the sum-of-sink-delays objective, when summed
    over nets (no capacity-1 coupling, so no joint solution can do better).

Used to validate the C++ microbenchmark (bench_nn/dijk_bench.cpp) and to size
the inner loop from the Python side.
"""
import heapq
import json
import os
import sys
import time


def spt_per_net(inst):
    """Return {net_id: spt_delay} plus the elapsed seconds."""
    W, H, L = inst["grid"]["width"], inst["grid"]["height"], inst["grid"]["layers"]
    ld = inst["delay"]["layer_delay"]
    via = inst["delay"]["via_delay"]
    pv = {p["id"]: (p["x"], p["y"], p["z"]) for p in inst["pins"]}
    v2p = {(p["x"], p["y"], p["z"]): p["id"] for p in inst["pins"]}
    p2n = {}
    for n in inst["nets"]:
        for p in list(n["sinks"]) + [n["driver"]]:
            p2n[p] = n["id"]

    t0 = time.perf_counter()
    per_net = {}
    for n in inst["nets"]:
        nid = n["id"]
        driver = pv[n["driver"]]
        sinks = [pv[s] for s in n["sinks"]]
        dist = {driver: 0}
        pq = [(0, driver)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, d):
                continue
            x, y, z = u
            nb = []
            if x + 1 < W:
                nb.append(((x + 1, y, z), ld[z]))
            if x > 0:
                nb.append(((x - 1, y, z), ld[z]))
            if y + 1 < H:
                nb.append(((x, y + 1, z), ld[z]))
            if y > 0:
                nb.append(((x, y - 1, z), ld[z]))
            if z + 1 < L:
                nb.append(((x, y, z + 1), via))
            if z > 0:
                nb.append(((x, y, z - 1), via))
            for v, w in nb:
                o = v2p.get(v)
                if o is not None and p2n[o] != nid:
                    continue
                nd = d + w
                if nd < dist.get(v, 1 << 30):
                    dist[v] = nd
                    heapq.heappush(pq, (nd, v))
        missing = [s for s in sinks if s not in dist]
        if missing:
            raise RuntimeError(f"net {nid}: {len(missing)} sinks unreachable")
        per_net[nid] = sum(dist[s] for s in sinks)
    return per_net, time.perf_counter() - t0


def main(paths):
    for p in paths:
        inst = json.load(open(p))
        per, secs = spt_per_net(inst)
        tot = sum(per.values())
        nsinks = sum(len(n["sinks"]) for n in inst["nets"])
        nn = len(inst["nets"])
        print(
            f"{os.path.basename(p)}: pins-only SPT bound={tot} nets={nn} sinks={nsinks} "
            f"mean_sink_delay={tot / nsinks:.2f} py={secs:.2f}s "
            f"({secs / nn * 1e6:.0f} us/net, {nn / secs:.1f} nets/s)"
        )


if __name__ == "__main__":
    main(sys.argv[1:])
