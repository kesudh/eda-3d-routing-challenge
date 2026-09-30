// Microbenchmark: the exact per-net inner loop of an M3D router on hard-tier
// instances. Two modes, both EXACT (both return the true shortest-path-tree sum
// of sink delays, so results are verifiable against the Python reference
// spt_ref.py, which agrees to the digit):
//
//   mode 0 "full"  : one single-source Dijkstra per net over the entire 3D grid.
//   mode 1 "astar" : A* per net with an admissible heuristic
//                      h(v) = min over un-settled sinks of
//                             minLayerDelay*(|dx|+|dy|) + viaDelay*|dz|
//                    with early exit once all sinks are settled. This is the
//                    realistic inner loop a competitive router runs.
//
// Delays are small integers, so a dial/bucket queue would beat the binary heap;
// these numbers are therefore conservative (pessimistic) for "how cheap is
// exact search".
//
// Input: flat digest from digest.py.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <queue>
#include <vector>

using namespace std;

int main(int argc, char** argv) {
  ifstream f(argv[1]);
  if (!f) {
    fprintf(stderr, "cannot open %s\n", argv[1]);
    return 1;
  }
  int W, H, L, via, nNets;
  f >> W >> H >> L >> via >> nNets;
  vector<int> ld(L);
  for (int& i : ld) f >> i;
  vector<vector<int>> nets(nNets);
  for (int i = 0; i < nNets; ++i) {
    int k;
    f >> k;
    nets[i].resize(k);
    for (int& p : nets[i]) f >> p;
  }
  const int N = W * H * L;
  const int mode = argc > 2 ? atoi(argv[2]) : 0;
  int reps = argc > 3 ? atoi(argv[3]) : 20;
  int minL = *min_element(ld.begin(), ld.end());

  vector<vector<int>> pinNet(N);
  for (int i = 0; i < nNets; ++i)
    for (int p : nets[i]) pinNet[p].push_back(i);
  vector<char> isSink(N, 0);
  for (int i = 0; i < nNets; ++i)
    for (size_t k = 1; k < nets[i].size(); ++k) isSink[nets[i][k]] = 1;

  vector<double> dist(N), g(N);
  vector<char> inTree(N), closed(N);
  using P = pair<double, int>;
  double sinkSum = 0;
  long long pops = 0, sinkCnt = 0;

  auto t0 = chrono::steady_clock::now();
  for (int r = 0; r < reps; ++r) {
    for (int nid = 0; nid < nNets; ++nid) {
      int drv = nets[nid][0];
      int nsinks = (int)nets[nid].size() - 1;
      for (int i = 0; i < N; ++i) {
        dist[i] = 1e30;
        g[i] = 1e30;
        inTree[i] = 0;
        closed[i] = 0;
      }
      dist[drv] = 0;
      g[drv] = 0;
      double acc = 0;
      int done = 0;
      if (mode == 0) {
        priority_queue<P, vector<P>, greater<P>> pq;
        pq.push(P(0.0, drv));
        while (!pq.empty() && done < nsinks) {
          pair<double, int> pr = pq.top();
          pq.pop();
          double d = pr.first;
          int u = pr.second;
          ++pops;
          if (d > dist[u]) continue;
          if (!inTree[u]) {
            inTree[u] = 1;
            if (isSink[u]) {
              acc += d;
              if (++done == nsinks) break;
            }
          }
          int z = u / (W * H), rem = u % (W * H), y = rem / W, x = rem % W;
          for (int dir = 0; dir < 6; ++dir) {
            int v, w;
            switch (dir) {
              case 0: if (x + 1 >= W) continue; v = u + 1; w = ld[z]; break;
              case 1: if (x == 0) continue; v = u - 1; w = ld[z]; break;
              case 2: if (y + 1 >= H) continue; v = u + W; w = ld[z]; break;
              case 3: if (y == 0) continue; v = u - W; w = ld[z]; break;
              case 4: if (z + 1 >= L) continue; v = u + W * H; w = via; break;
              default: if (z == 0) continue; v = u - W * H; w = via; break;
            }
            if (inTree[v]) continue;
            bool blocked = false;
            for (size_t i = 0; i < pinNet[v].size(); ++i)
              if (pinNet[v][i] != nid) { blocked = true; break; }
            if (blocked) continue;
            double nd = d + w;
            if (nd < dist[v] - 1e-12) { dist[v] = nd; pq.push(P(nd, v)); }
          }
        }
      } else {
        auto heur = [&](int v) {
          int x = v % W, y = (v / W) % H, z = v / (W * H);
          double best = 1e30;
          for (size_t k = 1; k < nets[nid].size(); ++k) {
            int s = nets[nid][k];
            if (closed[s]) continue;
            int sx = s % W, sy = (s / W) % H, sz = s / (W * H);
            int dz = sz - z;
            if (dz < 0) dz = -dz;
            double hv = (double)minL * (abs(sx - x) + abs(sy - y)) + (double)via * dz;
            if (hv < best) best = hv;
          }
          return best;
        };
        auto cmp = [](const P& a, const P& b) { return a.first > b.first; };
        priority_queue<P, vector<P>, decltype(cmp)> pq(cmp);
        pq.push(P(heur(drv), drv));
        while (!pq.empty() && done < nsinks) {
          pair<double, int> pr = pq.top();
          pq.pop();
          int u = pr.second;
          ++pops;
          if (closed[u]) continue;
          closed[u] = 1;
          if (isSink[u]) {
            acc += g[u];
            if (++done == nsinks) break;
          }
          int z = u / (W * H), rem = u % (W * H), y = rem / W, x = rem % W;
          for (int dir = 0; dir < 6; ++dir) {
            int v, w;
            switch (dir) {
              case 0: if (x + 1 >= W) continue; v = u + 1; w = ld[z]; break;
              case 1: if (x == 0) continue; v = u - 1; w = ld[z]; break;
              case 2: if (y + 1 >= H) continue; v = u + W; w = ld[z]; break;
              case 3: if (y == 0) continue; v = u - W; w = ld[z]; break;
              case 4: if (z + 1 >= L) continue; v = u + W * H; w = via; break;
              default: if (z == 0) continue; v = u - W * H; w = via; break;
            }
            if (closed[v]) continue;
            bool blocked = false;
            for (size_t i = 0; i < pinNet[v].size(); ++i)
              if (pinNet[v][i] != nid) { blocked = true; break; }
            if (blocked) continue;
            double ng = g[u] + w;
            if (ng < g[v] - 1e-12) {
              g[v] = ng;
              pq.push(P(ng + heur(v), v));
            }
          }
        }
      }
      if (getenv("DUMP") && r == 0) printf("net %d acc %.0f\n", nid, acc);
      sinkSum += acc;
      sinkCnt += nsinks;
    }
  }
  auto t1 = chrono::steady_clock::now();
  double sec = chrono::duration<double>(t1 - t0).count();
  long long calls = 1LL * reps * nNets;
  printf(
      "%-5s grid %dx%dx%d verts=%d nets=%d calls=%lld  total %.4f s -> %.2f us/net  "
      "%.0f nets/s  pops/net %.0f  mean_sink_delay %.2f\n",
      mode == 0 ? "full" : "astar", W, H, L, N, nNets, calls, sec,
      sec / calls * 1e6, calls / sec, pops / (double)calls, sinkSum / sinkCnt);
  return 0;
}
