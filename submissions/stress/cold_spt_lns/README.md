# cold_spt_lns - stress

Independent cold-start routes by [kesudh](https://github.com/kesudh).

Source, immutable source archives, runtime definition and reproduction commands
are in [the shared intro entry](../../intro/cold_spt_lns/README.md).

    python submissions/intro/cold_spt_lns/run.py --check-only --tier stress
    python submissions/intro/cold_spt_lns/run.py --reproduce --tier stress

Each case retains its actual producing run, full runtime, source version
and solver arguments in runs.json.

R6 is ROOT-checked legal at delay 1,047,836, 18 below the previous public stress delay 1,047,854; its original producing runtime is 6893.094000000041 seconds and its separate exact-replay runtime is 6652.4679999999935 seconds. The archived source version is 1e314104a237b9f78c07a4044e9969c63b9f3c2d8315ea13c3b82a54cfa306d8, with binary SHA-256 505ee00bffd1cf671e85d54c6b16c522ec1f7b79e3f1d896e856757c26c864ef.
The exact historical Rust compiler/toolchain is unknown; confirmed tier wins remain 0/6 and no tier lead is claimed.
