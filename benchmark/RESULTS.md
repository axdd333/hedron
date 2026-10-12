# RESULTS — measured, not asserted

Reproduce every number in this file:

```bash
python3 -m unittest discover            # 287 tests, all green
python3 -c "from benchmark.loc_accounting import repo_counts, negative_path_tests as n; import pprint; pprint.pprint(repo_counts('.')); print(n('.'))"
python3 -m benchmark.benchmark benchmark/report.json
# -> ungauged report regenerated, byte-identical to the committed one
#    (the gauged report: the two-line write_report call below)
```

Measured at commit `ac4326a` + this results commit. No hand-typed numbers:
the headline table is emitted by `benchmark/loc_accounting.py`, itself pinned
by `tests/test_loc_accounting.py` (TDD: RED before the module existed).

## Headline: shared representation vs per-family work

| measure | shared (primitives + validation + backend) | nine-family builders (garments.py) |
|---|---|---|
| total lines | 2,295 | 343 |
| ast-code lines | 1,918 | 242 |

**Ratio: 7.93 : 1** (ast-code; 6.69 : 1 on raw lines). One shared
representation, one validator, one lowering contract — each garment family
costs ~27 code lines on top.

Method: ast statement spans (multi-line statements count whole; standalone
blank/comment lines excluded). Never `wc -l`, never grep heuristics.

## Machine op library actually emitted

Lowering all nine families through `default_knit` produces exactly
**4 distinct machine verbs**: `CAST_ON`, `KNIT`, `GRAFT`, `PICK_UP`.
Graph-side the builders use 3 of the 6-op set (`cast_on`, `graft`,
`pick_up`); `bind_off`, `short_row_close`, `selvedge_seam` are spec'd but
unexercised by reference builders (documented known-open, below).

## Buildability honesty (the non-negotiable)

- All nine families: `geometric_validity: PASS` — and the report says what
  that means and nothing more ("geometric validity never implies
  knitability", DESIGN §9).
- `I-LOOP: UNVERIFIED` for every family until gauge data exists — the
  loop-correspondence check refuses to pretend.
- Verdict ledger: ungauged run = 9 × `UNSIMULATED`; gauged run = 9 ×
  `SIMULATED`. `garment_stats` are stamped SIMULATED iff the gauge is
  complete; the ungauged report carries no fabricated stitch counts.
- A deliberately broken graph is **recorded, not raised**: the benchmark
  output contains the `BackendNotApplicable` refusal with catalog codes as
  a datapoint.

## Validator / must-reject coverage

- 92 of 287 tests exercise rejection paths (assertFalse/`.ok` False,
  assertRaises, error-code assertions — counted programmatically by
  `negative_path_tests`), covering all fourteen must-reject cases of
  DESIGN §7 and all 11 invariant classes.
- Validation is byte-level deterministic: same graph in, identical error
  ordering out (pinned by test).
- Benchmark reports are byte-identical on regeneration (sha256 match,
  both ungauged and gauged) — canonical JSON, insertion-order independent.

## Known-open (documented, not hidden)

- Reference builders exercise 3 of 6 primitive kinds (`tube`, `hemisphere`,
  `disk`); `sphere`, `ellipsoid`, `rect` await families that need them.
- `surface_branch` is only legal with construction `unsupported` in v2
  (§5.4) — glove fingers, shirt/hoodie sleeves, trousers/shorts legs are
  documented unsupported branches, visible verbatim in reports.
- Benchmark v1 covers one in-repo backend (`default_knit`) × nine families;
  no external backend has been lowered yet.
- All nine families are composed from five shared builder helpers
  (`_prim`, `_root_cast_on`, `_rim_joint`, `_continuation`, `_branch`) —
  the per-family cost above is configuration, not re-implementation.
