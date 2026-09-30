# PR#3 baseline discrepancy: 145,333 vs 145,807 — RESOLVED

## Verdict

**Both numbers are correct. There is no discrepancy in PR#5's claims.**

145,333 is PR#3 at commit `a5ef5e2406682473b99c6496a87a6279b64db9ba` (the commit PR#5
pinned, and the current HEAD of Taz33m's `pathfinder-lns` branch). 145,807 is PR#3 at
commit `e7d9fbe270e81f0a6d7fe693991312375f73894b`, which is our local `pr3` branch and the
number baked into `LEADERBOARD.md` on `pr3`.

The 474-unit gap is explained entirely by **one extra commit**: `a5ef5e2` ("Final update:
improve all six pathfinder_lns tiers") sits directly on top of `e7d9fbe`. Our local `pr3`
fetch was taken before that commit landed. Cause (a) in the original hypothesis list, with
the direction reversed from what was assumed — the branch moved *forward* past our fetch,
and the pinned commit is strictly better on all 9 cases.

```
a5ef5e2  Final update: improve all six pathfinder_lns tiers   <-- PR#5 pinned this
e7d9fbe  Improve hard and designs pathfinder_lns              <-- our local pr3 = 145,807
424570d  Improve hard pathfinder_lns: more seeds + warm-start/MIP polishing
50f2dd7  Add pathfinder_lns submissions for all six tiers
499ad7e  (upstream main)
```

## 1. Verified per-case and total delay of PR#3 @ a5ef5e2

Source: `git fetch https://github.com/Taz33m/eda-3d-routing-challenge.git` into
`refs/remotes/taz33m/*`, then blobs read from `a5ef5e2:submissions/hard/pathfinder_lns/`.

Ground truth = repo checker only:
`python -m m3d.cli score-suite --suite benchmarks_hard --submission-dir <dir>`
All 9 cases legal, `complete=True`, **AGGREGATE=1.3855**.

| case | a5ef5e2 (pinned) | pr3 head e7d9fbe | delta (old − new) |
|---|---:|---:|---:|
| case_01 | 8668 | 8674 | 6 |
| case_02 | 13164 | 13230 | 66 |
| case_03 | 11074 | 11086 | 12 |
| case_04 | 13079 | 13095 | 16 |
| case_05 | 15211 | 15311 | 100 |
| case_06 | 19816 | 19882 | 66 |
| case_07 | 21361 | 21433 | 72 |
| case_08 | 21516 | 21620 | 104 |
| case_09 | 21444 | 21476 | 32 |
| **total** | **145333** | **145807** | **474** |
| aggregate | 1.3855 | 1.3813 | +0.0042 |

**It equals 145,333 — exactly as PR#5 claims.** `a5ef5e2` improves every one of the 9 hard
cases; there is no case where it regresses. `LEADERBOARD.md` at `a5ef5e2` independently
records 145,333 / 1.3855, matching our recomputation.

## 2. Extraction of the stronger baseline

`a5ef5e2` IS better, so its routes are extracted to:

    F:/eda3d-wt/pr3-pinned/submissions/hard/pathfinder_lns_a5ef5e2/

Re-scored from that extracted copy: 9/9 legal, aggregate 1.3855, total 145,333. Blob
hashes confirmed distinct from `pr3` for all 9 cases (and `meta.json` differs only in its
`date` field, `2026-09-30` vs `2026-09-29`).

`a5ef5e2` also improves the other five tiers. Re-scored (both versions, same checker):

| tier | a5ef5e2 | pr3 head e7d9fbe | aggregate before → after |
|---|---:|---:|---|
| hard | 145,333 | 145,807 | 1.3813 → 1.3855 |
| congested | 493,503 | 495,119 | 1.2990 → 1.3037 |
| designs | 210,847 | 212,901 | 1.4118 → 1.4242 |
| scale | — (8/8 legal) | — (8/8 legal) | 1.1178 → 1.1235 |
| stress | 1,049,818 | 1,052,728 | 1.0876 → 1.0906 |

(intro tier not scored — this repo has no `benchmarks_intro/suite.json`; the suite dir does
not exist in our checkout. `a5ef5e2` does touch `submissions/intro/pathfinder_lns`.)

## 3. PR#5's per-case provenance table — VERIFIED CORRECT

PR#5's `meta.json` claims warm-start delays 8668 / 13164 / 11074 / 13079 / 15211 / 19816 /
21361 / 21516 / 21444. That is an **exact, per-case match** to `a5ef5e2` on all 9 cases.

Corroborated three independent ways:

1. **Checker.** `a5ef5e2` scores exactly those nine numbers (table above).
2. **Raw blob SHA-256.** Every one of the nine `warm_start_sha256` values in PR#5's
   `meta.json` matches the sha256 of the raw blob at `a5ef5e2`, byte for byte. Example:
   `case_01` warm_start `5a34e2ec…17ea2f` = sha256 of
   `a5ef5e2:submissions/hard/pathfinder_lns/case_01.sol.json`. All nine match.
3. **"Retained original route" cases.** PR#5 flags case_01, case_05, case_07 as
   `strict_improvement: false` / "retained original route", and their `route_sha256` values
   *look* different from `warm_start_sha256`. Checked: the parsed JSON is identical —
   `routes` lists compare equal, canonical sorted-key serialization is byte-equal — and the
   files differ by exactly **1 byte** (a trailing newline). So the hashes differ only for
   whitespace, and the "retained original route" claim is true. The task brief's note that
   these two match "our pr5 submission exactly" is correct but incidental: they match the
   *pinned PR#3* routes, which is the point of the claim.

None of the four candidate explanations (b) different-routes, (c) different submission
directory, (d) wrong/measured-differently holds. Same directory (`submissions/hard/
pathfinder_lns` in both), same checker, honest reporting.

**Side finding — PR#5's actual gain is small.** Scoring PR#5's own submission
(`submissions/hard/coordinated_refinement`) against the repo checker:

| case | PR#3 @ a5ef5e2 | PR#5 | gain |
|---|---:|---:|---:|
| case_01 | 8668 | 8668 | 0 (retained) |
| case_02 | 13164 | 13158 | 6 |
| case_03 | 11074 | 11072 | 2 |
| case_04 | 13079 | 13075 | 4 |
| case_05 | 15211 | 15211 | 0 (retained) |
| case_06 | 19816 | 19810 | 6 |
| case_07 | 21361 | 21361 | 0 (retained) |
| case_08 | 21516 | 21508 | 8 |
| case_09 | 21444 | 21442 | 2 |
| **total** | **145,333** | **145,305** | **28** |
| aggregate | 1.3855 | 1.3858 | +0.0003 |

PR#5's improvement over the pinned PR#3 baseline is **28 delay units / +0.0003 aggregate
/ +0.02%**, not a 9.6%-class win. Its own `LEADERBOARD.md` at `pr5` is consistent with this
(1.3858 vs 1.3855). The one-commit `e7d9fbe → a5ef5e2` jump (474 units, +0.0042 aggregate)
was worth ~17x more than PR#5's entire contribution.

For reference, PR#6 (`carter-group-routing`) scores 9/9 legal but only aggregate **1.1637**,
total 193,527 — far behind, and legal.

## 4. Recommendation on real remaining headroom

- **The strong baseline is 145,333 / 1.3855 (hard) at `a5ef5e2`, not 145,807 / 1.3813.**
  Use the extracted `submissions/hard/pathfinder_lns_a5ef5e2/` as the thing to beat. Any
  comparison against the stale 145,807 baseline overstates a win by 474 units (0.33%).
- **Headroom against the reference solver is large but the frontier is thin.** The best
  submission of the six PRs on hard is PR#5 at 1.3858. Everything else is either the
  baseline (1.0000), `negotiated_x2` (1.0168), or PR#6 (1.1637). The gap between the
  leader (1.3855) and the best non-PR result (1.1637) is the only meaningfully open
  competition; beating 1.3858 by a real margin means a genuinely new search strategy, not
  polish.
- **Do not treat PR#5 as the target to chase.** It is 28 units over baseline. A
  >0.5% aggregate win requires roughly 700+ delay units, which PR#3's own single-commit
  successive-halving warm-start LNS continuation achieved (474 units) and PR#5 did not.
- **Practical takeaway:** Taz33m's method is the one that still has headroom, and its own
  commit history shows the technique (more seeds + successive-halving warm-start LNS
  continuation) still produced gains on the final iteration across all six tiers. PR#5's
  "bounded group refinement" only recovers a sliver. The remaining headroom is in
  continuing that LNS continuation, not in post-hoc route refinement.

## Method / reproduction

```bash
git fetch https://github.com/Taz33m/eda-3d-routing-challenge.git \
  '+refs/heads/*:refs/remotes/taz33m/*'
git ls-tree -d --name-only a5ef5e2 submissions/hard/     # dir listing
git rev-parse a5ef5e2:submissions/hard/pathfinder_lns/case_01.sol.json   # blob compare
git show a5ef5e2:submissions/hard/pathfinder_lns/case_01.sol.json | sha256sum

python -m m3d.cli score-suite --suite benchmarks_hard \
  --submission-dir submissions/hard/pathfinder_lns_a5ef5e2
```

Notes: `git ls-tree -d --name-only <ref> submissions/hard/` returns full paths
(`submissions/hard/pathfinder_lns`) — take `.split('/')[-1]`. All scoring above is
`m3d.cli score-suite` / `m3d.checker`; no third-party engine was used.
