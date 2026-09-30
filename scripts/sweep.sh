#!/usr/bin/env bash
# Sweep SA configs on one hard case; print one line per config.
# usage: sweep.sh <case> <iters> <seed>
set -u
CASE=$1; ITERS=${2:-40000}; SEED=${3:-1}
SA=work/sa.exe
IN=work/txt/${CASE}.txt
OUT=work/sweep/${CASE}_$SEED.json
mkdir -p work/sweep
run() {
  local tag="$1"; shift
  local r
  r=$($SA --in "$IN" --out "$OUT" --name "$CASE" --iters "$ITERS" --seed "$SEED" "$@" 2>&1 | grep -oE "FINAL total=[0-9]+" | head -1)
  echo "$tag ${r:-FAILED}"
}
# control: strict descent (the accept-rule hypothesis, isolated)
run "DESCENT_k1        " --kfix 1 --noanneal 1 --ptie 0.5 --cycles 1
run "DESCENT_k4        " --kfix 4 --noanneal 1 --ptie 0.5 --cycles 1
# SA, no jitter (order-only neighbourhood)
run "SA_k4_j0_t80      " --kfix 4 --jitter 0 --greedy 1 --thi 80 --tlo 4 --ptie 0.5 --cycles 1
run "SA_k8_j0_t150     " --kfix 8 --jitter 0 --greedy 1 --thi 150 --tlo 6 --ptie 0.5 --cycles 1
# SA with jitter, greedy re-opt
run "SA_k4_j05_g_t80   " --kfix 4 --jitter 0.5 --greedy 1 --thi 80 --tlo 4 --ptie 0.5 --cycles 1
run "SA_k4_j05_ng_t80  " --kfix 4 --jitter 0.5 --greedy 0 --thi 80 --tlo 4 --ptie 0.5 --cycles 1
# wide k range
run "SA_k2-10_j05_t150 " --kmin 2 --kmax 10 --jitter 0.5 --greedy 0 --thi 150 --tlo 5 --ptie 0.5 --cycles 1
run "SA_k2-20_j08_t300 " --kmin 2 --kmax 20 --jitter 0.8 --greedy 0 --thi 300 --tlo 8 --ptie 0.5 --cycles 1
# best-of-N candidate sampling
run "SA_k4_j05_bo8     " --kfix 4 --jitter 0.5 --greedy 0 --bestof 8 --pbest 1.0 --thi 80 --tlo 4 --ptie 0.5 --cycles 1
# hot restart, many cycles
run "SA_k2-10_c4_t400  " --kmin 2 --kmax 10 --jitter 0.6 --greedy 0 --thi 400 --tlo 5 --ptie 0.5 --cycles 4
