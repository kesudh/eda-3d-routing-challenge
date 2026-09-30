"""Test the structure-blueprint's actionable claim: can the walled-in single-sink
nets be rescued?

Blueprint finding: on hard case_09 six 1-sink nets each have ONE sink sitting
72-96 delay worse than its free distance - boxed into pockets of z=2,3 that
higher-priority nets consumed. If those sinks can be rescued at acceptable cost,
that is a concrete, enumerable attack surface.

This script:
  1. identifies every net/sink whose detour exceeds a threshold,
  2. checks whether a strictly cheaper route exists for that net when the
     CURRENT board is held fixed except that the net is allowed to push
     others' *pressure* (i.e. is the pin truly walled in, or is it just
     locally suboptimal?),
  3. reports how much delay is theoretically addressable.

This is diagnostic only - it does not attempt a full legal routing.
"""
import os, sys, json, heapq, collections
sys.path.insert(0, r"F:\eda-3d-routing-challenge")
from m3d.model import Instance, Submission

INF = 1 << 60


def enc(i, c):
    return (c[2] * i.height + c[1]) * i.width + c[0]


def dec(i, v):
    W = i.width
    return (v % W, (v // W) % i.height, v // (W * i.height))


def dij_free(i, src, blocked, p2v):
    ld, vd = i.layer_delay, i.via_delay
    W, H, L = i.width, i.height, i.layers
    WH = W * H
    d = {src: 0}
    pq = [(0, src)]
    while pq:
        dd, u = heapq.heappop(pq)
        if dd > d.get(u, INF):
            continue
        z, r = divmod(u, WH); y, x = divmod(r, W)
        for v, wg in (((u + 1) if x + 1 < W else -1, ld[z]),
                      ((u - 1) if x > 0 else -1, ld[z]),
                      ((u + W) if y + 1 < H else -1, ld[z]),
                      ((u - W) if y > 0 else -1, ld[z]),
                      ((u + WH) if z + 1 < L else -1, vd),
                      ((u - WH) if z > 0 else -1, vd)):
            if v < 0 or (v in blocked and v != src):
                continue
            nd = dd + wg
            if nd < d.get(v, INF):
                d[v] = nd
                heapq.heappush(pq, (nd, v))
    return d


def main():
    suite = r"F:\eda-3d-routing-challenge\benchmarks_hard"
    sol = sys.argv[1] if len(sys.argv) > 1 else \
        r"C:\Users\gkesu\AppData\Local\hermes\cache\scratch\pr3"
    cases = sys.argv[2].split(",") if len(sys.argv) > 2 else ["case_09"]

    grand_addr = 0
    for case in cases:
        i = Instance.load(os.path.join(suite, case + ".json"))
        sub = Submission.load(os.path.join(sol, case + ".sol.json"))
        p2v = {p.id: enc(i, p.vertex()) for p in i.pins}
        p2n = {}
        for n in i.nets:
            for pid in n.pins():
                p2n[pid] = n.id
        pinv = {p2v[p.id]: p.id for p in i.pins}
        occ = {}
        netv = {}
        nete = {}
        for r in sub.routes:
            vs, es = set(), set()
            for (a, b) in r.edges:
                va, vb = enc(i, a), enc(i, b)
                vs.add(va); vs.add(vb); es.add((min(va, vb), max(va, vb)))
            netv[r.net] = vs; nete[r.net] = es
            for v in vs:
                occ[v] = r.net

        total = 0
        rows = []
        for n in i.nets:
            adj = collections.defaultdict(list)
            for (a, b) in nete[n.id]:
                adj[a].append(b); adj[b].append(a)
            dist = {p2v[n.driver]: 0}
            q = collections.deque([p2v[n.driver]])
            while q:
                u = q.popleft()
                for v in adj[u]:
                    if v not in dist:
                        dist[v] = dist[u] + i.edge_delay(dec(i, u), dec(i, v))
                        q.append(v)
            cur = {s: dist[p2v[s]] for s in n.sinks}
            # floor: only other nets' PINS blocked
            otherpins = {p2v[p.id] for p in i.pins if p2n[p.id] != n.id}
            d = dij_free(i, p2v[n.driver], otherpins, p2v)
            fl = {s: d.get(p2v[s], 0) for s in n.sinks}
            # floor2: all other nets' CURRENT routes blocked too
            blocked2 = set(otherpins)
            for v, o in occ.items():
                if o != n.id:
                    blocked2.add(v)
            d2 = dij_free(i, p2v[n.driver], blocked2, p2v)
            fl2 = {s: d2.get(p2v[s], 0) for s in n.sinks}
            tot = sum(cur.values())
            total += tot
            for s in n.sinks:
                rows.append((n.id, s, len(n.sinks), cur[s], fl[s], fl2[s],
                             cur[s] - fl[s], cur[s] - fl2[s]))

        # addressable = sum over sinks of (current - floor2) = what a perfect
        # re-assignment with this exact net set could in principle recover
        addr = sum(r[6] for r in rows)
        # "walled-in" = detour concentrated in a single sink
        walled = [r for r in rows if r[3] - r[4] >= 40 and r[2] == 1]
        print(f"=== {case}: total {total}, "
              f"sum(sink detour vs pins-floor) = {addr} ({100.0*addr/total:.1f}%)")
        print(f"    1-sink nets with a single sink >=40 detour: {len(walled)}")
        for r in sorted(walled, key=lambda r: -r[6])[:12]:
            n = next(nn for nn in i.nets if nn.id == r[0])
            print(f"      net {r[0]:3d} sink {r[1]:3d} cur={r[3]:4d} "
                  f"pinsfloor={r[4]:4d} detour={r[6]:4d}  "
                  f"(with others' routes removed: {r[5]:4d})")
        # how much is recoverable if ONLY the worst sinks were fixed
        top = sorted(rows, key=lambda r: -r[6])[:10]
        print(f"    top-10 worst sinks hold {sum(r[6] for r in top)} delay "
              f"({100.0*sum(r[6] for r in top)/total:.1f}% of total)")
        grand_addr += addr

    print(f"\nacross cases: total addressable-vs-pins-floor = {grand_addr}")


if __name__ == "__main__":
    main()
