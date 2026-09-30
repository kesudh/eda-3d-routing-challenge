"""structure-blueprint: what does a near-optimal (PR#3) hard-tier solution LOOK LIKE?

The other agents are trying to beat 1.3813 by building routers. This asks a
different question: what makes the 1.38 solutions structurally different from
the 1.05-1.23 ones? A good blueprint is worth as much as a marginal gain.

Measures, per net:
  - fanout, XY span, same-die vs cross-die
  - mean/min layer z actually used, and whether high-fanout nets dive deeper
  - per-sink detour vs the pins-only free distance, and what characterises it
  - adjacency to other nets (corridor clustering)
Then compares the resulting picture against the repo's own reference routers.
"""
import os, sys, json, collections, statistics, math
sys.path.insert(0, r"F:\eda-3d-routing-challenge")
import importlib.util

def load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

INF = 1 << 60


class Inst:
    pass


def enc(i, c):
    return (c[2] * i.height + c[1]) * i.width + c[0]


def dec(i, v):
    W = i.width
    return (v % W, (v // W) % i.height, v // (W * i.height))


def net_geom(i, net, edges):
    """Return per-net structural facts from a legal edge list."""
    vs = set()
    for (a, b) in edges:
        vs.add(enc(i, a)); vs.add(enc(i, b))
    adj = collections.defaultdict(list)
    for (a, b) in edges:
        va, vb = enc(i, a), enc(i, b)
        adj[va].append(vb); adj[vb].append(va)
    return vs, adj


def bfs_delay(i, src, adj):
    d = {src: 0}
    q = collections.deque([src])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in d:
                d[v] = d[u] + i.edge_delay(dec(i, u), dec(i, v))
                q.append(v)
    return d


def free_dist(i, net, other_pins):
    """Shortest driver->sink delay avoiding other nets' pins (the floor)."""
    p2v = {p.id: enc(i, p.vertex()) for p in i.pins}
    ld, vd = i.layer_delay, i.via_delay
    W, H, L = i.width, i.height, i.layers
    WH = W * H
    blocked = set(other_pins)
    for pid in net.pins():
        blocked.discard(p2v[pid])
    src = p2v[net.driver]
    d = {src: 0}
    pq = [(0, src)]
    sinks = [p2v[s] for s in net.sinks]
    sset = set(sinks)
    while pq and sset:
        dd, u = heapq_pop(pq)
        if dd > d.get(u, INF):
            continue
        if u in sset:
            sset.discard(u)
        z, r = divmod(u, WH); y, x = divmod(r, W)
        for v, wg in (((u + 1) if x + 1 < W else -1, ld[z]),
                      ((u - 1) if x > 0 else -1, ld[z]),
                      ((u + W) if y + 1 < H else -1, ld[z]),
                      ((u - W) if y > 0 else -1, ld[z]),
                      ((u + WH) if z + 1 < L else -1, vd),
                      ((u - WH) if z > 0 else -1, vd)):
            if v < 0 or v in blocked:
                continue
            nd = dd + wg
            if nd < d.get(v, INF):
                d[v] = nd
                heapq_push(pq, (nd, v))
    return {s: d.get(s, 0) for s in sinks}, p2v


import heapq
heapq_pop = heapq.heappop
heapq_push = heapq.heappush


def analyze(i, routes, label):
    p2v = {p.id: enc(i, p.vertex()) for p in i.pins}
    p2n = {}
    for n in i.nets:
        for pid in n.pins():
            p2n[pid] = n.id
    allpins = {p2v[p.id] for p in i.pins}
    rows = []
    occ = {}
    for r in routes:
        vs, adj = net_geom(i, next(n for n in i.nets if n.id == r.net), r.edges)
        for v in vs:
            occ[v] = r.net
    for n in i.nets:
        edges = next(r.edges for r in routes if r.net == n.id)
        vs, adj = net_geom(i, n, edges)
        dist = bfs_delay(i, p2v[n.driver], adj)
        delay = sum(dist[p2v[s]] for s in n.sinks)
        other = {p2v[p.id] for p in i.pins if p2n[p.id] != n.id}
        fd, _ = free_dist(i, n, other)
        detours = [dist[p2v[s]] - fd[p2v[s]] for s in n.sinks]
        co = [dec(i, v) for v in vs]
        zs = [c[2] for c in co]
        xs = [c[0] for c in co]; ys = [c[1] for c in co]
        dd = i.pin_by_id()[n.driver]
        cross = any(i.pin_by_id()[s].die != dd.die for s in n.sinks)
        rows.append(dict(net=n.id, fanout=len(n.sinks), delay=delay,
                         floor=sum(fd.values()),
                         detour=sum(detours), maxdetour=max(detours),
                         meanz=statistics.mean(zs), minz=min(zs), maxz=max(zs),
                         spanxy=(max(xs) - min(xs)) + (max(ys) - min(ys)),
                         cross=cross, nverts=len(vs)))
    return rows, occ


def main():
    sys.path.insert(0, r"F:\eda-3d-routing-challenge")
    from m3d.model import Instance, Submission
    suite = r"F:\eda-3d-routing-challenge\benchmarks_hard"
    sol = sys.argv[1] if len(sys.argv) > 1 else \
        r"C:\Users\gkesu\AppData\Local\hermes\cache\scratch\pr3"
    case = sys.argv[2] if len(sys.argv) > 2 else "case_09"
    i = Instance.load(os.path.join(suite, case + ".json"))
    sub = Submission.load(os.path.join(sol, case + ".sol.json"))
    print(f"=== {case}  layer_delay={i.layer_delay} via={i.via_delay} ===")
    print(f"{label if False else 'PR#3'} nets={len(i.nets)} "
          f"total_delay={sum(1 for _ in ())}")
    rows, occ = analyze(i, sub.routes, "pr3")

    tot = sum(r["delay"] for r in rows)
    print(f"total delay {tot}   floor {sum(r['floor'] for r in rows)}   "
          f"detour {sum(r['detour'] for r in rows)} "
          f"({100.0*sum(r['detour'] for r in rows)/tot:.1f}%)")

    print("\n-- by fanout --")
    for fo in sorted({r["fanout"] for r in rows}):
        g = [r for r in rows if r["fanout"] == fo]
        print(f"  fanout={fo:2d} n={len(g):3d} delay={statistics.mean(r['delay'] for r in g):7.1f} "
              f"per-sink={statistics.mean(r['delay']/fo for r in g):6.1f} "
              f"meanz={statistics.mean(r['meanz'] for r in g):4.2f} "
              f"minz={statistics.mean(r['minz'] for r in g):4.2f} "
              f"spanxy={statistics.mean(r['spanxy'] for r in g):5.1f} "
              f"detour/sink={statistics.mean(r['detour']/fo for r in g):6.1f}")

    print("\n-- cross-die vs same-die --")
    for cross in (True, False):
        g = [r for r in rows if r["cross"] == cross]
        if not g: continue
        print(f"  cross={cross!s:5s} n={len(g):3d} per-sink={statistics.mean(r['delay']/r['fanout'] for r in g):6.1f} "
              f"meanz={statistics.mean(r['meanz'] for r in g):4.2f} "
              f"detour/sink={statistics.mean(r['detour']/r['fanout'] for r in g):6.1f}")

    print("\n-- dive rule: does mean z track XY span? --")
    buckets = [(0, 10), (10, 20), (20, 30), (30, 45), (45, 70), (70, 999)]
    for lo, hi in buckets:
        g = [r for r in rows if lo <= r["spanxy"] < hi]
        if not g: continue
        print(f"  spanXY [{lo:3d},{hi:3d}) n={len(g):3d} meanz={statistics.mean(r['meanz'] for r in g):4.2f} "
              f"minz={statistics.mean(r['minz'] for r in g):4.2f} "
              f"per-sink={statistics.mean(r['delay']/r['fanout'] for r in g):6.1f} "
              f"detour/sink={statistics.mean(r['detour']/r['fanout'] for r in g):6.1f}")

    print("\n-- correlation of mean z with fanout / spanxy --")
    def corr(a, b):
        ma, mb = statistics.mean(a), statistics.mean(b)
        num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        da = math.sqrt(sum((x - ma) ** 2 for x in a)); db = math.sqrt(sum((y - mb) ** 2 for y in b))
        return num / (da * db) if da and db else 0.0
    mz = [r["meanz"] for r in rows]
    print(f"  corr(meanz, fanout) = {corr(mz, [r['fanout'] for r in rows]):+.3f}")
    print(f"  corr(meanz, spanxy) = {corr(mz, [r['spanxy'] for r in rows]):+.3f}")
    print(f"  corr(detour/sink, fanout) = {corr([r['detour']/r['fanout'] for r in rows], [r['fanout'] for r in rows]):+.3f}")
    print(f"  corr(detour/sink, spanxy) = {corr([r['detour']/r['fanout'] for r in rows], [r['spanxy'] for r in rows]):+.3f}")

    print("\n-- layer vertex occupancy by this solution --")
    W, H, L = i.width, i.height, i.layers
    for z in range(L):
        n = sum(1 for v in occ if dec(i, v)[2] == z)
        print(f"  z={z} delay={i.layer_delay[z]:2d} occupied={n:5d} / {W*H} = {100.0*n/(W*H):5.1f}%")

    print("\n-- worst-detour nets (where the money is) --")
    for r in sorted(rows, key=lambda r: -r["detour"])[:10]:
        print(f"  net {r['net']:3d} fanout={r['fanout']} delay={r['delay']:5d} "
              f"floor={r['floor']:5d} detour={r['detour']:4d} maxdet={r['maxdetour']:3d} "
              f"spanxy={r['spanxy']:3d} meanz={r['meanz']:.2f} cross={r['cross']}")


if __name__ == "__main__":
    main()
