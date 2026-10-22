# cold_spt_lns - designs

Independent cold-start routes by [kesudh](https://github.com/kesudh).

The complete source, method, timing definition, and reproduction instructions
are in [the shared intro entry](../../intro/cold_spt_lns/README.md).

```sh
python submissions/intro/cold_spt_lns/run.py --check-only --tier designs
python submissions/intro/cold_spt_lns/run.py --reproduce --tier designs
```

`runtime.json` and `runs.json` describe the actual complete solver invocation
that produced each shipped file. All cases use the same seed and work counts.
