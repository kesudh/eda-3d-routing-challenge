"""Basin-diversity probe: does a different CONSTRUCTION ORDER reach a different
1-opt fixed point than PR#3's?

Rationale: the move set is closed because the evaluation operator E (apply each
net's exact per-net optimum in turn) is idempotent. That blocks every search
AROUND a given basin. It does NOT block a different construction order, which
lands in a different basin. This script measures the distribution of basins.
"""
import os, sys, heapq, random, time, collections
sys.path.insert(0, r"F:\eda-3d-routing-challenge")
os.chdir(r"F:\eda-3d-routing-challenge")
from m3d.model import Instance

INF = 1 << 60


class Case:
    def __init__(self, path):
        self.i = Instance.load(path)
        i = self.i
        self.W, self.H, self.L = i.width, i.height, i.layers
        self.WH = self.W * self.H
        self.enc = lambda c: (c[2] * self.H + c[1]) * self.W + c[0]
        self.dec = lambda v: (v % self.W, (v // self.W) % self.H, v // self.WH)
        self.pv = {p.id: self.enc(p.vertex()) for p in i.pins}
        self.pin_of = {}
        for n in i.nets:
            for pid in n.pins():
                self.pin_of[pid] = n.id
        self.pinv = {self.pv[p.id]: p.id for p in i.pins}
        self.NET = {n.id: n for n in i.nets}
        self.other_pin_cache = {}

    def other_pins(self, nid):
        if nid not in self.other_pin_cache:
            self.other_pin_cache[nid] = {
                v for v, pid in self.pinv.items() if self.pin_of[pid] != nid
            }
        return self.other_pin_cache[nid]

    def nbrs(self, v):
        z, r = divmod(v, self.WH)
        y, x = divmod(r, self.W)
        d = self.i.layer_delay
        via = self.i.via_delay
        W, H, L = self.W, self.H, self.L
        if x + 1 < W:
            yield v + 1, d[z]
        if x > 0:
            yield v - 1, d[z]
        if y + 1 < H:
            yield v + W, d[z]
        if y > 0:
            yield v - W, d[z]
        if z + 1 < L:
            yield v + self.WH, via
        if z > 0:
            yield v - self.WH, via

    def spt(self, nid, blocked, jitter=None):
        """Dijkstra from driver avoiding `blocked` and other nets' pins.
        Returns dist dict (None if unreachable)."""
        n = self.NET[nid]
        src = self.pv[n.driver]
        op = self.other_pins(nid)
        d = {src: 0.0}
        pq = [(0.0, src)]
        while pq:
            dd, u = heapq.heappop(pq)
            if dd != d.get(u):
                continue
            for v, wg in self.nbrs(u):
                if v in op or v in blocked:
                    continue
                nd = dd + wg + (jitter.get(v, 0.0) if jitter else 0.0)
                if nd < d.get(v, INF) - 1e-9:
                    d[v] = nd
                    heapq.heappush(pq, (nd, v))
        return d

    def tree(self, nid, d, src):
        """Build the route by walking each sink back to the driver along tight edges.
        Returns (vertex set, true integer delay) or None."""
        n = self.NET[nid]
        verts = set()
        delay = 0
        EPS = 1e-6
        BIG = float("inf")
        for s in n.sinks:
            t = self.pv[s]
            if t not in d:
                return None
            cur = t
            guard = 0
            while True:
                verts.add(cur)
                if cur == src:
                    break
                guard += 1
                if guard > 4 * (self.W * self.H * self.L):
                    return None
                # Among TIGHT predecessors (d[u]+w <= d[cur]+EPS) take the one
                # with the smallest key. With soft congestion penalties d is not
                # a consistent labelling, so strict equality strands the walk.
                step = None
                best = BIG
                for u, wg in self.nbrs(cur):
                    if u not in d:
                        continue
                    key = d[u] + wg
                    if key <= d[cur] + EPS and key < best:
                        best = key
                        step = (u, wg)
                if step is None:
                    return None
                verts.add(step[0])
                delay += step[1]
                cur = step[0]
        return verts, delay

    def place(self, nid, occ, jitter=None):
        d = self.spt(nid, occ, jitter)
        if not d:
            return None
        t = self.tree(nid, d, self.pv[self.NET[nid].driver])
        if t is None:
            return None
        return t[0], t[1]

    def build(self, order, jitter=None):
        """Greedy sequential construction. No backtracking: an unlucky order can
        strand a later net, which is itself a finding."""
        occ = set()
        routes = {}
        tot = 0
        for nid in order:
            r = self.place(nid, occ, jitter)
            if r is None:
                return None, None
            v, dl = r
            if v & occ:
                return None, None
            occ |= v
            routes[nid] = (v, dl)
            tot += dl
        return routes, tot

    def one_opt(self, routes):
        """Reroute each net to its exact optimum with others frozen; repeat to fixpoint."""
        occ = set()
        for v, _ in routes.values():
            occ |= v
        improved = True
        rounds = 0
        while improved:
            improved = False
            rounds += 1
            for nid in list(routes):
                v, d0 = routes[nid]
                occ -= v
                r = self.place(nid, occ, None)
                if r is not None and r[1] < d0:
                    routes[nid] = (r[0], r[1])
                    occ |= r[0]
                    improved = True
                    continue
                occ |= v
        return routes, sum(d for _, d in routes.values()), rounds


def main():
    targets = {"case_01": 8674, "case_05": 15311, "case_09": 21476}
    c = Case("benchmarks_hard/case_01.json")
    bbox = {}
    for nid, n in c.NET.items():
        xs = [c.dec(c.pv[pid])[0] for pid in n.pins()]
        ys = [c.dec(c.pv[pid])[1] for pid in n.pins()]
        bbox[nid] = (max(xs) - min(xs)) + (max(ys) - min(ys))
    ids = sorted(c.NET)
    cfgs = [
        ("bbox_desc", sorted(ids, key=lambda k: (-bbox[k], k))),
        ("bbox_asc", sorted(ids, key=lambda k: (bbox[k], k))),
        ("netid_asc", ids),
        ("fanout_desc", sorted(ids, key=lambda k: (-len(c.NET[k].sinks), k))),
        ("fanout_asc", sorted(ids, key=lambda k: (len(c.NET[k].sinks), k))),
        ("fanout_then_bbox",
         sorted(ids, key=lambda k: (-len(c.NET[k].sinks), -bbox[k], k))),
    ]
    rng = random.Random(7)
    for s in range(6):
        cfgs.append((f"random_{s}", rng.sample(ids, len(ids))))

    print("case_01 -- construction diversity -> 1-opt fixed points")
    print(f"PR#3 = {targets['case_01']}   (greedy construction has no backtracking;")
    print(" INFEASIBLE = that net order stranded a net, which is a real result)")
    print(f"\n{'configuration':<18}{'construct':>10}{'1-opt':>8}   note")
    t0 = time.time()
    res = []
    for nm, od in cfgs:
        r, tot = c.build(od)
        if r is None:
            res.append((nm, None, None, "greedy-infeasible"))
            continue
        ro, to, rounds = c.one_opt(dict((k, (set(v), d)) for k, (v, d) in r.items()))
        res.append((nm, tot, to, f"{rounds} rounds"))
    for nm, cc, t, note in res:
        print(f"{nm:<18}{(cc if cc is not None else '-'):>10}"
              f"{(t if t is not None else '-'):>8}   {note}")
    fin = [t for _, _, t, _ in res if t is not None]
    print(f"\ndistinct 1-opt fixed points: {sorted(set(fin))}")
    if fin:
        print(f"best {min(fin)}  vs PR#3 {targets['case_01']}"
              f"  (delta {min(fin) - targets['case_01']:+d})")
    print(f"elapsed {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
