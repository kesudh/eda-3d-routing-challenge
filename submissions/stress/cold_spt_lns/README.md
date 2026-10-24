# cold_spt_lns - stress

Independent cold-start routes by [kesudh](https://github.com/kesudh).

Source, immutable source archives, runtime definition and reproduction commands
are in [the shared intro entry](../../intro/cold_spt_lns/README.md).

    python submissions/intro/cold_spt_lns/run.py --check-only --tier stress
    python submissions/intro/cold_spt_lns/run.py --reproduce --tier stress

Each case retains its actual producing run, full runtime, source version
and solver arguments in runs.json.

Source485 is ROOT-checked legal at delay 1,047,854, 10 below the published 1,047,864; its original producing runtime is 8,854.390000000014 seconds and exact replay runtime is 6,661.140000000014 seconds, with source version 485b695fb57482656fe0ad99fb7d03201979236b38d1ae735290b13225267eea and binary SHA-256 ab03e16154b0b8877be7ce8ad9fc8b7ec9a29dc3c50f3321416f7aaff92e07a3.
The exact historical Rust compiler/toolchain is unknown; confirmed tier wins remain 0/6 and no tier lead is claimed.
