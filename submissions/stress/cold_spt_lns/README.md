# cold_spt_lns - stress

Independent cold-start routes by [kesudh](https://github.com/kesudh).

Source, immutable source archives, runtime definition and reproduction commands
are in [the shared intro entry](../../intro/cold_spt_lns/README.md).

    python submissions/intro/cold_spt_lns/run.py --check-only --tier stress
    python submissions/intro/cold_spt_lns/run.py --reproduce --tier stress

Each case retains its actual producing run, full runtime, source version
and solver arguments in runs.json.

The retained stress route has checked delay 1,059,868 and original complete producing time 91.390 seconds. It uses soft alternating X/Y preferences during cold construction, with all directions available and the physical score unchanged. An independent rebuild of its archived source reproduced the exact route bytes. This lowers the prior own delay by 19,834; it remains above the captured full-field leader at 1,042,080.
