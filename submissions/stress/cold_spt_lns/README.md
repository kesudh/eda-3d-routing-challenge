# cold_spt_lns - stress

Independent cold-start routes by [kesudh](https://github.com/kesudh).

Source, immutable source archives, runtime definition and reproduction commands
are in [the shared intro entry](../../intro/cold_spt_lns/README.md).

    python submissions/intro/cold_spt_lns/run.py --check-only --tier stress
    python submissions/intro/cold_spt_lns/run.py --reproduce --tier stress

Each case retains its actual producing run, full runtime, source version
and solver arguments in runs.json.

The retained stress route has checked delay 1,049,200 and original complete producing time 1,994.125 seconds. It uses one raw start with soft alternating X/Y preferences during cold construction, followed by 1,600 fixed portfolio refinement trials and eight final stable-polish passes across four deterministic schedules. All directions remain available and the physical score is unchanged. An independent rebuild of its archived source reproduced the exact route bytes and passed the official legality check. This lowers the prior own delay of 1,059,868 by 10,668; it remains 7,120 above the captured full-field leader at 1,042,080. Replay time is recorded separately and does not replace producing time.
