// sa.cpp -- Simulated annealing / threshold-accepting router for the M3D challenge.
//
// Hypothesis under test: replacing the strict-descent accept rule with a
// metaheuristic (SA over JOINT multi-net moves) beats a pure 1-opt descent LNS
// on the hard tier.
//
// Model
// -----
// A net's route is always the union of shortest paths from its driver to its
// sinks in the currently-free subgraph (a pruned SPT). That is exactly optimal
// for sum-of-sink-delay given the blocked-vertex set, so the only decision
// variables are:
//   (a) which nets are ripped up together,
//   (b) in what order they are re-inserted (who yields to whom),
//   (c) how equal-cost shortest-path ties are broken.
// (b) and (c) are the real search space; the incumbent is a hard 1-opt optimum
// so nothing improves under strict descent -- the point of SA is to pay an
// uphill toll now to unlock a cheaper basin later.
//
// Rip-up + re-insert in a random order leaves every net outside the ripped set
// untouched, so the cost delta is exact and local.
//
// Build: clang++ -O2 -std=c++20 -o sa.exe sa.cpp
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <climits>
#include <cmath>
#include <string>
#include <vector>
#include <algorithm>
#include <unordered_map>

// ------------------------------------------------------------------ RNG ----
struct Rng {
    uint64_t s;
    explicit Rng(uint64_t seed = 88172645463325252ULL) : s(seed ? seed : 1) {}
    inline uint64_t next() { uint64_t x = s; x ^= x << 13; x ^= x >> 7; x ^= x << 17; return s = x; }
    inline uint32_t u32() { return (uint32_t)(next() >> 32); }
    inline double unit() { return (next() >> 11) * (1.0 / 9007199254740992.0); }
    inline int below(int n) { return n <= 1 ? 0 : (int)(u32() % (uint32_t)n); }
};
static Rng RNG;

// ----------------------------------------------------------------- model ----
static int W, H, L, VIA, NV, MAXW, NBUCK;
static std::vector<int> LD, nbr, vx, vy, vz;

static int nPins, nNets;
static std::vector<int> pinV, pinNet, vPin;

struct Net {
    int drv = 0;
    std::vector<int> sinks;
    int delay = 0;
    std::vector<int> verts;
    std::vector<std::pair<int, int>> edges;
};
static std::vector<Net> nets;

static std::vector<int> vowner;
static std::vector<int> d_dist, d_ver, d_par, s_ver;   // Dijkstra scratch
static std::vector<int> t_mark, t_ver;                 // SPT pruning scratch
static uint32_t gver = 0;
static std::vector<int> bucket[64];
static long long g_total = 0;

static inline int vid(int x, int y, int z) { return (z * H + y) * W + x; }
static inline int edge_w(int a, int b) { return (vz[a] == vz[b]) ? LD[vz[a]] : VIA; }

static void build_adj() {
    nbr.assign((size_t)NV * 6, -1);
    vx.resize(NV); vy.resize(NV); vz.resize(NV);
    for (int z = 0; z < L; z++)
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                int v = vid(x, y, z);
                vx[v] = x; vy[v] = y; vz[v] = z;
                int d = 0;
                if (x + 1 < W) nbr[(size_t)v * 6 + d++] = v + 1;
                if (x - 1 >= 0) nbr[(size_t)v * 6 + d++] = v - 1;
                if (y + 1 < H) nbr[(size_t)v * 6 + d++] = v + W;
                if (y - 1 >= 0) nbr[(size_t)v * 6 + d++] = v - W;
                if (z + 1 < L) nbr[(size_t)v * 6 + d++] = v + W * H;
                if (z - 1 >= 0) nbr[(size_t)v * 6 + d++] = v - W * H;
            }
    MAXW = VIA;
    for (int i = 0; i < L; i++) MAXW = std::max(MAXW, LD[i]);
    // Ring must be strictly larger than the largest edge weight that can be
    // pushed (jitter can inflate weights), and must not exceed bucket[].
    NBUCK = 2;
    while (NBUCK <= 2 * MAXW + 2 && NBUCK < 64) NBUCK *= 2;
}

// --------------------------------------------------------------- routing ---
static inline bool blocked(int v, int n) {
    int o = vowner[v];
    if (o >= 0 && o != n) return true;
    int p = vPin[v];
    return (p >= 0 && p != n);
}

// Route net n optimally (pruned SPT) in the free subgraph.
// Returns its delay, or -1 if some sink is unreachable. Sets nets[n].verts/edges.
static int route_net(int n, double p_tie) {
    Net &N = nets[n];
    const int drv = pinV[N.drv];
    if (blocked(drv, n)) return -1;

    uint32_t ver = ++gver;
    for (int i = 0; i < NBUCK; i++) bucket[i].clear();

    d_ver[drv] = ver; d_dist[drv] = 0; d_par[drv] = -1;
    bucket[0].push_back(drv);

    const int ns = (int)N.sinks.size();
    long long total = 0;
    int left = ns + 1;
    int cur = 0, guard = 0, guard_max = NV * (MAXW + 1) + 16;

    while (left > 0) {
        int v = -1;
        while (v < 0) {
            if (++guard > guard_max) return -1;
            std::vector<int> &bk = bucket[cur % NBUCK];
            if (bk.empty()) { cur++; continue; }
            int cand = bk.back(); bk.pop_back();
            if (d_ver[cand] != ver || s_ver[cand] == ver) continue;   // stale ver or settled
            if (d_dist[cand] != cur) {
                // Circular buckets: this entry can belong to a future distance
                // (up to MAXW ahead). Re-file it instead of dropping it, or the
                // vertex is lost and its sink becomes spuriously unreachable.
                bucket[d_dist[cand] % NBUCK].push_back(cand);
                continue;
            }
            s_ver[cand] = ver;
            v = cand;
        }
        if (v == drv) left--;
        for (int i = 0; i < ns; i++)
            if (pinV[N.sinks[i]] == v) { total += cur; left--; }
        if (left == 0) break;

        const int *nb6 = &nbr[(size_t)v * 6];
        for (int d = 0; d < 6; d++) {
            int u = nb6[d];
            if (u < 0 || blocked(u, n)) continue;
            int nd = cur + edge_w(v, u);
            if (d_ver[u] != ver) {
                d_ver[u] = ver; d_dist[u] = nd; d_par[u] = v;
                bucket[nd % NBUCK].push_back(u);
            } else if (nd < d_dist[u]) {
                d_dist[u] = nd; d_par[u] = v;
                bucket[nd % NBUCK].push_back(u);
            } else if (nd == d_dist[u] && s_ver[u] != ver && RNG.unit() < p_tie) {
                d_par[u] = v;   // dist[v] < dist[u] always, so no cycle
            }
        }
    }

    // prune the SPT down to the union of driver->sink paths
    uint32_t pv = ++gver;
    t_ver[drv] = pv; t_mark[drv] = 1;
    std::vector<std::pair<int, int>> es;
    for (int i = 0; i < ns; i++) {
        int s = pinV[N.sinks[i]];
        int v = s;
        while (!(t_ver[v] == pv && t_mark[v])) {
            t_ver[v] = pv; t_mark[v] = 1;
            int p = d_par[v];
            if (p < 0 || d_ver[p] != ver) return -1;
            es.push_back({p, v});
            v = p;
        }
    }
    std::vector<int> vs;
    for (int v = 0; v < NV; v++) if (t_ver[v] == pv && t_mark[v]) vs.push_back(v);
    N.verts.swap(vs);
    N.edges.swap(es);
    return (int)total;
}

static std::vector<int> eown;   // NV*6, ownership from this endpoint's side

static void claim(int n) {
    Net &N = nets[n];
    for (int v : N.verts) vowner[v] = n;
    for (auto &e : N.edges) {
        int a = e.first, b = e.second;
        for (int d = 0; d < 6; d++) if (nbr[(size_t)a * 6 + d] == b) eown[(size_t)a * 6 + d] = n;
        for (int d = 0; d < 6; d++) if (nbr[(size_t)b * 6 + d] == a) eown[(size_t)b * 6 + d] = n;
    }
}
static void release(int n) {
    Net &N = nets[n];
    for (int v : N.verts) vowner[v] = -1;
    for (auto &e : N.edges) {
        int a = e.first, b = e.second;
        for (int d = 0; d < 6; d++) if (nbr[(size_t)a * 6 + d] == b) eown[(size_t)a * 6 + d] = -1;
        for (int d = 0; d < 6; d++) if (nbr[(size_t)b * 6 + d] == a) eown[(size_t)b * 6 + d] = -1;
    }
}

// Route net n along a RANDOMIZED-cost shortest path instead of the true SPT.
// This is the move class a pure order-based joint re-route cannot express: it
// makes a net voluntarily take a different (possibly worse, possibly
// different-corridor) route so that another net in the same ripped set can
// claim the corridor this one just gave up. `jitter` is the relative spread of
// the randomized edge weights; 0 => true SPT.
static int route_net_jitter(int n, double p_tie, double jitter) {
    if (getenv("SA_TRACE")) fprintf(stderr, "J enter n=%d jitter=%.2f\n", n, jitter);
    Net &N = nets[n];
    const int drv = pinV[N.drv];
    if (blocked(drv, n)) return -1;

    uint32_t ver = ++gver;
    for (int i = 0; i < NBUCK; i++) bucket[i].clear();

    d_ver[drv] = ver; d_dist[drv] = 0; d_par[drv] = -1;
    bucket[0].push_back(drv);

    const int ns = (int)N.sinks.size();
    long long total = 0;
    int left = ns + 1;
    int cur = 0, guard = 0, guard_max = NV * (MAXW + 1) + 16;

    while (left > 0) {
        int v = -1;
        while (v < 0) {
            if (++guard > guard_max) return -1;
            std::vector<int> &bk = bucket[cur % NBUCK];
            if (bk.empty()) { cur++; continue; }
            int cand = bk.back(); bk.pop_back();
            if (d_ver[cand] != ver || s_ver[cand] == ver) continue;
            if (d_dist[cand] != cur) {
                bucket[d_dist[cand] % NBUCK].push_back(cand);
                continue;
            }
            s_ver[cand] = ver;
            v = cand;
        }
        if (v == drv) left--;
        for (int i = 0; i < ns; i++)
            if (pinV[N.sinks[i]] == v) { total += cur; left--; }
        if (left == 0) break;

        const int *nb6 = &nbr[(size_t)v * 6];
        for (int d = 0; d < 6; d++) {
            int u = nb6[d];
            if (u < 0 || blocked(u, n)) continue;
            int w = edge_w(v, u);
            if (jitter > 0.0) {
                // integer randomized cost: w * U(1-jitter, 1+jitter)
                double f = 1.0 + jitter * (RNG.unit() * 2.0 - 1.0);
                int wi = (int)std::lround(w * f);
                if (wi < 1) wi = 1;
                w = wi;
            }
            int nd = cur + w;
            if (d_ver[u] != ver) {
                d_ver[u] = ver; d_dist[u] = nd; d_par[u] = v;
                bucket[nd % NBUCK].push_back(u);
            } else if (nd < d_dist[u]) {
                d_dist[u] = nd; d_par[u] = v;
                bucket[nd % NBUCK].push_back(u);
            } else if (nd == d_dist[u] && s_ver[u] != ver && d_dist[v] < d_dist[u]
                       && RNG.unit() < p_tie) {
                // Tie-break MUST keep the parent chain strictly decreasing in
                // distance, otherwise the SPT prune loop can cycle forever.
                // With randomized weights this is not automatic, so test it.
                d_par[u] = v;
            }
        }
    }

    uint32_t pv = ++gver;
    t_ver[drv] = pv; t_mark[drv] = 1;
    std::vector<std::pair<int, int>> es;
    for (int i = 0; i < ns; i++) {
        int v = pinV[N.sinks[i]];
        int steps = 0;
        while (!(t_ver[v] == pv && t_mark[v])) {
            if (++steps > NV) return -1;   // cycle guard: never expected
            t_ver[v] = pv; t_mark[v] = 1;
            int p = d_par[v];
            if (p < 0 || d_ver[p] != ver) return -1;
            es.push_back({p, v});
            v = p;
        }
    }
    std::vector<int> vs;
    for (int v = 0; v < NV; v++) if (t_ver[v] == pv && t_mark[v]) vs.push_back(v);
    N.verts.swap(vs);
    N.edges.swap(es);
    // d_dist now holds RANDOMIZED distances; recompute the true tree delay with
    // LOCAL buffers so the shared Dijkstra scratch stays intact.
    std::vector<int> bd(N.verts.size(), -1);
    if (getenv("SA_TRACE")) fprintf(stderr, "J n=%d verts=%zu edges=%zu\n", n, N.verts.size(), N.edges.size());
    std::unordered_map<int, int> idx;
    idx.reserve(N.verts.size() * 2);
    for (size_t i = 0; i < N.verts.size(); i++) idx[N.verts[i]] = (int)i;
    int di = idx.count(drv) ? idx[drv] : -1;
    if (di < 0) return -1;          // driver must be in the tree
    bd[di] = 0;
    long long real = 0;
    std::vector<int> q;
    q.push_back(di);
    for (size_t i = 0; i < q.size(); i++) {
        int vi = q[i];
        int v = N.verts[vi];
        for (auto &e : N.edges) {
            int a = e.first, b = e.second;
            int o = (a == v) ? b : ((b == v) ? a : -1);
            if (o < 0) continue;
            int oi = idx[o];
            if (bd[oi] >= 0) continue;
            bd[oi] = bd[vi] + edge_w(v, o);
            q.push_back(oi);
        }
    }
    if (q.size() != N.verts.size()) return -1;   // disconnected
    for (int i = 0; i < ns; i++) {
        int sv = pinV[N.sinks[i]];
        if (bd[idx[sv]] < 0) return -1;
        real += bd[idx[sv]];
    }
    return (int)real;
}

struct Save { int delay = 0; std::vector<int> verts; std::vector<std::pair<int, int>> edges; };
static void snap(int n, Save &s) { s.delay = nets[n].delay; s.verts = nets[n].verts; s.edges = nets[n].edges; }
static void restore(int n, const Save &s) { nets[n].delay = s.delay; nets[n].verts = s.verts; nets[n].edges = s.edges; }
static void recompute_occ() {
    std::fill(vowner.begin(), vowner.end(), -1);
    std::fill(eown.begin(), eown.end(), -1);
    for (int n = 0; n < nNets; n++) claim(n);
}

// ------------------------------------------------------------------ load ---
static void load(const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) { fprintf(stderr, "cannot open %s\n", path); exit(2); }
    char line[1 << 16];
    long long dummy = 0;
    int np, ns, nid, dp, ne, id, nx, ny, nz, nn, a, b;
    while (fgets(line, sizeof line, f)) {
        char t = line[0];
        if (t == '#' || t == '\n' || t == '\r') continue;
        if (t == 'I') {
            sscanf(line + 1, "%d %d %d %d", &W, &H, &L, &VIA);
            NV = W * H * L; LD.assign(L, 0);
        } else if (t == 'D') {
            char *p = line + 1;
            for (int i = 0; i < L; i++) LD[i] = (int)strtol(p, &p, 10);
        } else if (t == 'P') {
            sscanf(line + 1, "%d", &nPins);
            pinV.assign(nPins, -1); pinNet.assign(nPins, -1);
        } else if (t == 'C') {
            sscanf(line + 1, "%lld", &dummy);
            for (int i = 0; i < nPins; i++) {
                if (fscanf(f, " %d %d %d %d %d", &id, &nx, &ny, &nz, &nn) != 5) { fprintf(stderr, "pin parse\n"); exit(2); }
                pinV[id] = vid(nx, ny, nz);
                pinNet[id] = nn;
            }
        } else if (t == 'N') {
            sscanf(line + 1, "%d", &nNets);
            nets.assign(nNets, Net());
            for (int i = 0; i < nNets; i++) {
                if (fscanf(f, " %d %d %d", &id, &dp, &ns) != 3) { fprintf(stderr, "net parse\n"); exit(2); }
                nets[id].drv = dp;
                nets[id].sinks.resize(ns);
                for (int j = 0; j < ns; j++) fscanf(f, " %d", &nets[id].sinks[j]);
            }
        } else if (t == 'E') {
            sscanf(line + 1, "%d", &np);
            for (int i = 0; i < np; i++) {
                if (fscanf(f, " %d %d", &nid, &ne) != 2) { fprintf(stderr, "route parse\n"); exit(2); }
                nets[nid].edges.resize(ne);
                for (int j = 0; j < ne; j++) { if (fscanf(f, " %d %d", &a, &b) != 2) { fprintf(stderr, "edge2 parse\n"); exit(2); } nets[nid].edges[j] = {a, b}; }
            }
        }
    }
    fclose(f);
}

static void init_state_from_routes() {
    vowner.assign(NV, -1);
    eown.assign((size_t)NV * 6, -1);
    vPin.assign(NV, -1);
    for (int p = 0; p < nPins; p++) vPin[pinV[p]] = pinNet[p];
    d_dist.assign(NV, 0); d_ver.assign(NV, 0); d_par.assign(NV, -1); s_ver.assign(NV, 0);
    t_mark.assign(NV, 0); t_ver.assign(NV, 0);
    gver = 1;
    g_total = 0;
    std::vector<int> dist(NV);
    for (int n = 0; n < nNets; n++) {
        Net &N = nets[n];
        std::vector<int> vs;
        for (auto &e : N.edges) { vs.push_back(e.first); vs.push_back(e.second); }
        std::sort(vs.begin(), vs.end());
        vs.erase(std::unique(vs.begin(), vs.end()), vs.end());
        N.verts.swap(vs);
        std::fill(dist.begin(), dist.end(), -1);
        std::vector<int> q; q.reserve(N.verts.size());
        int dv = pinV[N.drv];
        dist[dv] = 0; q.push_back(dv);
        for (size_t i = 0; i < q.size(); i++) {
            int v = q[i];
            for (auto &e : N.edges) {
                int a = e.first, b = e.second;
                int o = (a == v) ? b : ((b == v) ? a : -1);
                if (o < 0 || dist[o] >= 0) continue;
                dist[o] = dist[v] + edge_w(v, o);
                q.push_back(o);
            }
        }
        long long d = 0;
        for (int s : N.sinks) d += dist[pinV[s]];
        N.delay = (int)d;
        g_total += d;
        claim(n);
    }
}

// ---------------------------------------------------------------- output ---
// Independent re-derivation of delay + legality from the stored edge lists,
// mirroring m3d/checker.py. The SA's own incremental g_total is NEVER trusted;
// every reported number is cross-checked against this.
static long long g_routechanges = 0, g_moves_counted = 0;
static long long sum_of_net_delays() {
    long long t = 0;
    for (int n = 0; n < nNets; n++) t += nets[n].delay;
    return t;
}

static long long verify_state(const char *tag) {
    long long total = 0;
    std::vector<int> vo(NV, -1);
    std::vector<std::pair<long long, int>> eo;
    std::vector<int> dist(NV, -1);
    int bad = 0;
    for (int n = 0; n < nNets; n++) {
        Net &N = nets[n];
        // vertex set
        std::vector<int> vs;
        for (auto &e : N.edges) { vs.push_back(e.first); vs.push_back(e.second); }
        std::sort(vs.begin(), vs.end());
        vs.erase(std::unique(vs.begin(), vs.end()), vs.end());
        if ((int)N.edges.size() != (int)vs.size() - 1) {
            fprintf(stderr, "VERIFY %s net %d NOT A TREE: %zu edges %zu verts\n", tag, n, N.edges.size(), vs.size());
            bad++;
        }
        for (int v : vs) {
            if (vo[v] >= 0 && vo[v] != n) {
                fprintf(stderr, "VERIFY %s SHORT vertex %d nets %d/%d\n", tag, v, vo[v], n);
                bad++; goto nextnet;
            }
            int pn = vPin[v];
            if (pn >= 0 && pn != n) {
                fprintf(stderr, "VERIFY %s FOREIGN PIN at v=%d net %d (pin net %d)\n", tag, v, n, pn);
                bad++; goto nextnet;
            }
        }
        for (int v : vs) vo[v] = n;
        // BFS from driver over the tree
        std::fill(dist.begin(), dist.end(), -1);
        int dv = pinV[N.drv];
        dist[dv] = 0;
        std::vector<int> q; q.push_back(dv);
        for (size_t i = 0; i < q.size(); i++) {
            int v = q[i];
            for (auto &e : N.edges) {
                int a = e.first, b = e.second;
                int o = (a == v) ? b : ((b == v) ? a : -1);
                if (o < 0 || dist[o] >= 0) continue;
                dist[o] = dist[v] + edge_w(v, o);
                q.push_back(o);
            }
        }
        if ((int)q.size() != (int)vs.size()) {
            fprintf(stderr, "VERIFY %s net %d DISCONNECTED (%d of %d reached)\n", tag, n, (int)q.size(), (int)vs.size());
            bad++; goto nextnet;
        }
        long long d = 0;
        for (int s : N.sinks) {
            int sv = pinV[s];
            if (dist[sv] < 0) { fprintf(stderr, "VERIFY %s net %d sink unreachable\n", tag, n); bad++; goto nextnet; }
            d += dist[sv];
        }
        if (d != nets[n].delay)
            fprintf(stderr, "VERIFY %s net %d DELAY MISMATCH tree=%lld engine=%d\n", tag, n, d, nets[n].delay);
        total += d;
    nextnet:;
    }
    fprintf(stderr, "VERIFY %s: verified_total=%lld engine_total=%lld sum_nets=%lld bad=%d\n",
            tag, total, g_total, sum_of_net_delays(), bad);
    // Hard gate: the engine's incremental objective is only trustworthy if it
    // agrees with the independent re-derivation. Never report a result that
    // fails this.
    if (bad != 0 || total != g_total) {
        fprintf(stderr, "VERIFY %s: *** FAILED -- engine objective is not trustworthy ***\n", tag);
        exit(3);
    }
    return total;
}

static void write_sol(const char *path, const char *inst_name) {
    FILE *f = fopen(path, "w");
    fprintf(f, "{\"format\":\"m3d-submission\",\"version\":1,\"instance\":\"%s\",\"routes\":[", inst_name);
    for (int n = 0; n < nNets; n++) {
        fprintf(f, "%s{\"net\":%d,\"edges\":[", n ? "," : "", n);
        Net &N = nets[n];
        for (size_t i = 0; i < N.edges.size(); i++) {
            int a = N.edges[i].first, b = N.edges[i].second;
            fprintf(f, "%s[[%d,%d,%d],[%d,%d,%d]]", i ? "," : "",
                    vx[a], vy[a], vz[a], vx[b], vy[b], vz[b]);
        }
        fprintf(f, "]}");
    }
    fprintf(f, "]}\n");
    fclose(f);
}

// ------------------------------------------------------------------ main ---
static std::vector<Save> g_best;
static long long g_best_total = -1;

static void snapshot_best() {
    if (g_best_total >= 0 && g_total >= g_best_total) return;   // only on improvement
    g_best_total = g_total;
    g_best.resize(nNets);
    for (int n = 0; n < nNets; n++) snap(n, g_best[n]);
}
static void load_best() {
    if (g_best_total < 0) return;
    for (int n = 0; n < nNets; n++) restore(n, g_best[n]);
    recompute_occ();
    g_total = g_best_total;   // the objective must track the restored routes
}

struct Args {
    const char *in = nullptr; const char *out = nullptr; const char *name = "case";
    uint64_t seed = 12345;
    int cycles = 8;
    long long iters = 200000;
    int kmin = 2, kmax = 8;
    double thi = 0, tlo = 0;
    double p_tie = 0.5;
    int best_of = 1;
    double p_best = 1.0;
    int calib = 0;
    int logEvery = 0;
    double kfrac = 0.0;
    int kfix = 0;
    int saveinit = 0;
    int noanneal = 0;   // 1 => strict descent (the control experiment)
    double jitter = 0.0;
    int greedy = 1;
    int randinit = 0;
};

static std::vector<int> S, order, inS;
static std::vector<Save> saves;

static void pick_set(int kmin, int kmax) {
    int k = kmin + RNG.below(kmax - kmin + 1);
    if (k > nNets) k = nNets;
    S.clear();
    // S MUST hold distinct nets: a duplicate would double-count its delay in
    // the delta and double-claim its vertices, corrupting both the objective
    // and resource ownership.
    inS.assign(nNets, 0);
    int seed = RNG.below(nNets);
    if (RNG.below(2)) {   // bias half the time toward high-delay nets
        long long r = (long long)(RNG.unit() * (double)g_total);
        long long acc = 0; seed = nNets - 1;
        for (int n = 0; n < nNets; n++) { acc += nets[n].delay; if (r < acc) { seed = n; break; } }
    }
    S.push_back(seed); inS[seed] = 1;
    for (int i = 1; i < k; i++) {
        int c = RNG.below(nNets);
        if (inS[c]) { i--; continue; }   // rejection sampling; terminates fast
        S.push_back(c); inS[c] = 1;
    }
}

// Route the ripped set S: nets are re-inserted in a random order. Each net is
// routed with randomized edge weights (jitter) so it may take a different
// corridor, then greedily re-optimized to its true SPT in the resulting
// occupancy. This is ruin-and-recreate with a stochastic middle.
static bool route_set_jitter(double p_tie, double jitter, bool greedy) {
    order = S;
    for (size_t i = order.size(); i > 1; i--) std::swap(order[i - 1], order[RNG.below((int)i)]);
    for (int n : order) {
        std::vector<int> oldv = nets[n].verts;
        int d;
        if (jitter > 0.0) {
            d = route_net_jitter(n, p_tie, jitter);
            if (d >= 0) {
                if (greedy) {
                    // Re-optimize to the true SPT in the occupancy we just
                    // created. NOTE: this usually UNDOES the jitter (the net
                    // simply returns to its own optimum), which is why
                    // --greedy 0 exists as the interesting setting.
                    claim(n);
                    std::vector<int> keepv = nets[n].verts;
                    std::vector<std::pair<int, int>> keepe = nets[n].edges;
                    int d2 = route_net(n, p_tie);
                    if (d2 >= 0 && d2 <= d) d = d2;
                    else { nets[n].verts.swap(keepv); nets[n].edges.swap(keepe); }
                }
            }
        } else {
            d = route_net(n, p_tie);
        }
        if (d < 0) return false;
        nets[n].delay = d;
        claim(n);
        if (oldv != nets[n].verts) g_routechanges++;
    }
    g_moves_counted++;
    return true;
}

static bool route_set_in_random_order(double p_tie) {
    order = S;
    for (size_t i = order.size(); i > 1; i--) std::swap(order[i - 1], order[RNG.below((int)i)]);
    for (int n : order) {
        std::vector<int> oldv = nets[n].verts;
        int d = route_net(n, p_tie);
        if (d < 0) return false;
        nets[n].delay = d;
        claim(n);
        if (oldv != nets[n].verts) g_routechanges++;
    }
    g_moves_counted++;
    return true;
}

static void restore_set(const std::vector<Save> &old) {
    for (int n : S) release(n);
    for (size_t i = 0; i < S.size(); i++) restore(S[i], old[i]);
    for (int n : S) claim(n);
}

int main(int argc, char **argv) {
    Args A;
    for (int i = 1; i < argc; i++) {
        std::string s = argv[i];
        auto val = [&]() -> const char * { return argv[++i]; };
        if (s == "--in") A.in = val();
        else if (s == "--out") A.out = val();
        else if (s == "--name") A.name = val();
        else if (s == "--seed") A.seed = strtoull(val(), nullptr, 10);
        else if (s == "--cycles") A.cycles = atoi(val());
        else if (s == "--iters") A.iters = atoll(val());
        else if (s == "--kmin") A.kmin = atoi(val());
        else if (s == "--kmax") A.kmax = atoi(val());
        else if (s == "--kfix") A.kfix = atoi(val());
        else if (s == "--thi") A.thi = atof(val());
        else if (s == "--tlo") A.tlo = atof(val());
        else if (s == "--ptie") A.p_tie = atof(val());
        else if (s == "--bestof") A.best_of = atoi(val());
        else if (s == "--pbest") A.p_best = atof(val());
        else if (s == "--calib") A.calib = atoi(val());
        else if (s == "--kfrac") A.kfrac = atof(val());
        else if (s == "--log") A.logEvery = atoi(val());
        else if (s == "--saveinit") A.saveinit = 1;
        else if (s == "--noanneal") A.noanneal = atoi(val());
        else if (s == "--jitter") A.jitter = atof(val());
        else if (s == "--greedy") A.greedy = atoi(val());
        else if (s == "--randinit") A.randinit = atoi(val());
    }
    if (!A.in || !A.out) { fprintf(stderr, "usage: --in F --out F [--name N] [opts]\n"); return 2; }
    if (A.best_of < 1) A.best_of = 1;
    if (A.kfix > 0) { A.kmin = A.kmax = A.kfix; }
    if (A.kfrac > 0) {
        A.kmin = std::max(2, (int)std::lround(nNets * A.kfrac * 0.5));
        A.kmax = std::max(A.kmin + 1, (int)std::lround(nNets * A.kfrac * 1.5));
    }

    RNG = Rng(A.seed);
    load(A.in);
    build_adj();
    init_state_from_routes();

    // Random greedy construction: nets routed one at a time in random order,
    // each taking its SPT in the occupancy built so far. Tests whether the SA
    // can find good solutions AT ALL, independent of the PR#3 incumbent.
    if (A.randinit) {
        // Clear the loaded routes first: otherwise the "random" construction
        // is layered on top of the incumbent's occupancy and g_total.
        for (int n = 0; n < nNets; n++) { nets[n].verts.clear(); nets[n].edges.clear(); nets[n].delay = 0; }
        std::fill(vowner.begin(), vowner.end(), -1);
        std::fill(eown.begin(), eown.end(), -1);
        g_total = 0;
        std::vector<int> ord(nNets);
        for (int i = 0; i < nNets; i++) ord[i] = i;
        for (int i = nNets; i > 1; i--) std::swap(ord[i - 1], ord[RNG.below(i)]);
        for (int n : ord) {
            int d = route_net(n, A.p_tie);
            if (d < 0) { fprintf(stderr, "[%s] randinit: net %d unroutable\n", A.name, n); return 4; }
            nets[n].delay = d;
            claim(n);
            g_total += d;
        }
        fprintf(stderr, "[%s] randinit total=%lld\n", A.name, g_total);
        verify_state("randinit");
    }

    const long long start_total = g_total;
    fprintf(stderr, "[%s] start total=%lld nets=%d NV=%d k=[%d,%d] p_tie=%.2f best_of=%d p_best=%.2f\n",
            A.name, start_total, nNets, NV, A.kmin, A.kmax, A.p_tie, A.best_of, A.p_best);

    if (A.saveinit) { verify_state("init"); write_sol(A.out, A.name); return 0; }
    snapshot_best();

    std::vector<long long> deltas;

    // ---- calibration: sample move deltas with no acceptance ----
    if (A.calib) {
        deltas.reserve(A.calib);
        for (int it = 0; it < A.calib; it++) {
            pick_set(A.kmin, A.kmax);
            int k = (int)S.size();
            saves.resize(k);
            for (int i = 0; i < k; i++) { snap(S[i], saves[i]); release(S[i]); }
            if (route_set_jitter(A.p_tie, A.jitter, A.greedy != 0)) {
                long long d = 0;
                for (int i = 0; i < k; i++) d += nets[S[i]].delay - saves[i].delay;
                deltas.push_back(d);
            }
            restore_set(saves);
        }
        std::vector<long long> pos;
        for (long long d : deltas) if (d > 0) pos.push_back(d);
        std::sort(pos.begin(), pos.end());
        double meanpos = 0; for (long long d : pos) meanpos += (double)d;
        meanpos /= std::max<size_t>(1, pos.size());
        printf("CALIB %s n=%zu npos=%zu meanpos=%.2f p50=%.0f p75=%.0f p90=%.0f p99=%.0f max=%lld\n",
               A.name, deltas.size(), pos.size(), meanpos,
               pos.empty() ? 0.0 : (double)pos[pos.size() / 2],
               pos.empty() ? 0.0 : (double)pos[pos.size() * 3 / 4],
               pos.empty() ? 0.0 : (double)pos[pos.size() * 9 / 10],
               pos.empty() ? 0.0 : (double)pos[(size_t)(pos.size() * 0.99)],
               pos.empty() ? 0LL : pos.back());
        for (double T : {0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0, 512.0, 1024.0}) {
            long long acc = 0;
            for (long long d : deltas) if (d <= 0 || RNG.unit() < exp(-(double)d / T)) acc++;
            printf("  T=%9.2f accept=%.4f\n", T, (double)acc / std::max<size_t>(1, deltas.size()));
        }
        return 0;
    }

    // ---- temperature band ----
    if (!A.noanneal && (A.thi <= 0 || A.tlo <= 0)) {
        std::vector<long long> pos;
        for (int it = 0; it < 6000; it++) {
            pick_set(A.kmin, A.kmax);
            int k = (int)S.size();
            saves.resize(k);
            for (int i = 0; i < k; i++) { snap(S[i], saves[i]); release(S[i]); }
            if (route_set_jitter(A.p_tie, A.jitter, A.greedy != 0)) {
                long long d = 0;
                for (int i = 0; i < k; i++) d += nets[S[i]].delay - saves[i].delay;
                if (d > 0) pos.push_back(d);
            }
            restore_set(saves);
        }
        std::sort(pos.begin(), pos.end());
        double p50 = pos.empty() ? 4.0 : (double)pos[pos.size() / 2];
        if (A.thi <= 0) A.thi = std::max(1.0, 0.8 * p50);
        if (A.tlo <= 0) A.tlo = std::max(0.02, A.thi / 600.0);
        fprintf(stderr, "[%s] calib p50(pos delta)=%.0f -> T %.3f .. %.4f\n", A.name, p50, A.thi, A.tlo);
    }

    const double lam = std::log(std::max(1.0001, A.thi / std::max(1e-9, A.tlo)));
    long long moves = 0, accepts = 0, uphill = 0;
    // acceptance-vs-temperature curve, logged on a geometric T grid
    const int NCURVE = 16;
    double curveT[NCURVE]; long long curveAcc[NCURVE] = {0}, curveTry[NCURVE] = {0};

    for (int cyc = 0; cyc < A.cycles; cyc++) {
        load_best();
        const long long cyc0 = g_total;
        long long cyc_acc = 0;
        for (long long it = 0; it < A.iters; it++) {
            const double T = A.noanneal ? 0.0 : A.thi * std::exp(-lam * (double)it / (double)A.iters);
            pick_set(A.kmin, A.kmax);
            const int k = (int)S.size();
            saves.resize(k);
            for (int i = 0; i < k; i++) { snap(S[i], saves[i]); release(S[i]); }

            long long bestDelta = LLONG_MAX / 4;
            int bestIdx = -1;
            std::vector<std::vector<Save>> cands(A.best_of);
            std::vector<long long> cd(A.best_of, LLONG_MAX / 4);
            for (int c = 0; c < A.best_of; c++) {
                for (int i = 0; i < k; i++) { release(S[i]); restore(S[i], saves[i]); release(S[i]); }
                long long d = LLONG_MAX / 4;
                if (route_set_jitter(A.p_tie, A.jitter, A.greedy != 0)) {
                    d = 0;
                    cands[c].resize(k);
                    for (int i = 0; i < k; i++) {
                        cands[c][i].delay = nets[S[i]].delay;
                        cands[c][i].verts = nets[S[i]].verts;
                        cands[c][i].edges = nets[S[i]].edges;
                        d += nets[S[i]].delay - saves[i].delay;
                    }
                }
                cd[c] = d;
                if (d < bestDelta) { bestDelta = d; bestIdx = c; }
            }
            int use = (bestIdx < 0) ? -1 : ((RNG.unit() < A.p_best) ? bestIdx : RNG.below(A.best_of));
            long long delta = (use < 0) ? LLONG_MAX / 4 : cd[use];

            bool accept;
            if (use < 0) accept = false;
            else if (delta <= 0) accept = true;
            else accept = (!A.noanneal) && RNG.unit() < std::exp(-(double)delta / T);

            if (accept) {
                if (delta > 0) uphill++;
                accepts++; cyc_acc++;
                g_total += delta;
            } else {
                for (int i = 0; i < k; i++) release(S[i]);
                for (int i = 0; i < k; i++) restore(S[i], saves[i]);
                for (int i = 0; i < k; i++) claim(S[i]);
            }
            moves++;

            if (!A.noanneal) {
                // bucket by the DECILE of the cooling schedule, not by a
                // temperature lookup (which collapsed into one bin before).
                int ci = (int)((double)it / (double)A.iters * (NCURVE - 1));
                if (ci < 0) ci = 0;
                if (ci >= NCURVE) ci = NCURVE - 1;
                curveT[ci] = T;
                curveTry[ci]++;
                if (accept) curveAcc[ci]++;
            }

            if (A.logEvery && (it % A.logEvery == 0))
                fprintf(stderr, "  cyc%d it%lld T=%.4f cur=%lld best=%lld cycacc=%.3f\n",
                        cyc, it, T, g_total, g_best_total, (double)cyc_acc / (double)(it + 1));
            snapshot_best();
        }
        fprintf(stderr, "[%s] cycle %d: %lld -> %lld (best %lld) accrate=%.4f\n",
                A.name, cyc, cyc0, g_total, g_best_total, (double)cyc_acc / (double)A.iters);
    }

    if (!A.noanneal) {
        printf("CURVE %s  (measured move-acceptance rate vs temperature)\n", A.name);
        printf("%12s %10s %10s\n", "T", "tried", "accepted");
        for (int c = 0; c < NCURVE; c++)
            if (curveTry[c]) printf("%12.4f %10lld %10.4f\n", curveT[c], curveTry[c], (double)curveAcc[c] / (double)curveTry[c]);
    }

    load_best();
    verify_state("final");
    fprintf(stderr, "[%s] route-churn: %lld of %lld net reroutes changed the vertex set (%.1f%%)\n",
            A.name, g_routechanges, g_moves_counted,
            g_moves_counted ? 100.0 * (double)g_routechanges / (double)g_moves_counted : 0.0);
    fprintf(stderr, "[%s] FINAL total=%lld start=%lld gain=%.3f%% moves=%lld acc=%.4f uphill=%lld\n",
            A.name, g_total, start_total,
            start_total ? 100.0 * (double)(start_total - g_total) / (double)start_total : 0.0,
            moves, moves ? (double)accepts / (double)moves : 0.0, uphill);
    write_sol(A.out, A.name);
    return 0;
}
