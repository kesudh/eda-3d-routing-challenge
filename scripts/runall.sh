#!/usr/bin/env bash
# Run one SA config across all 9 hard cases in parallel, then score with the
# repo's own checker (ground truth).
# usage: runall.sh <tag> <iters> <cycles> <seed> [extra sa args...]
set -u
TAG=$1; ITERS=$2; CYCLES=$3; SEED=$4; shift 4
SA=work/sa.exe
SUB=work/sub_${TAG}
mkdir -p "$SUB" work/logs_${TAG}
START=$(date +%s)
for i in 01 02 03 04 05 06 07 08 09; do
  ( $SA --in work/txt/case_$i.txt --out "$SUB/case_$i.sol.json" --name case_$i \
        --iters "$ITERS" --cycles "$CYCLES" --seed "$SEED" "$@" \
        > work/logs_${TAG}/case_$i.out 2> work/logs_${TAG}/case_$i.err ) &
done
wait
END=$(date +%s)
echo "=== tag=$TAG wall=$((END-START))s (parallel over 9 cases, 24 cores) ==="
for i in 01 02 03 04 05 06 07 08 09; do
  printf "case_%s %s\n" "$i" "$(grep -oE 'FINAL total=[0-9]+' work/logs_${TAG}/case_$i.err | head -1)"
done
echo "--- checker (ground truth) ---"
python -m m3d.cli score-suite --suite benchmarks_hard --submission-dir "$SUB" 2>&1 | tail -14
