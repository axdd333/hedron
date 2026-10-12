# hedron — Unified Garment Primitives (UGP)

Parametric garment graphs you can prove things about, then lower to
machine ops. Every garment is a `UGPGraph`: primitives (parametric solids),
joints (how pieces meet), and knit ops (cast-on, graft, pick-up, bind-off,
short-row close, selvedge seam). Validation gates everything — a graph
that doesn't satisfy the spec-v2 invariants never lowers.

## Install / run

No dependencies. Python 3.9+.

```bash
python3 -m unittest discover -s tests -t .   # run the suite
python3 -m ugc sock                           # lower a family
python3 -m ugc sock --stats                   # plain-english ledger only
python3 -m ugc --all                          # every family
python3 -m ugc lower --graph my_graph.json    # lower your own graph
```

## Build a garment

```python
from ugc import GARMENT_FAMILIES, build_garment, lower

graph = build_garment("sock")      # 9 families: hat sock glove skirt
                                   # dress trousers shorts shirt hoodie
result = lower(graph)              # BackendNotApplicable if invalid

result.machine_ops   # ('CAST_ON', 'PICK_UP', 'KNIT', 'GRAFT')
result.ops           # one LoweredOp per graph op instance, program order
result.stats         # counts + machine_verdict (see below)
```

Your own graphs:

```python
from ugc import UGPGraph, Primitive, KnitOp, Joint, lower, validate

g = UGPGraph()
g.add(Primitive(id="leg", kind="tube",
                params={"r1": 55, "r2": 50, "l": 250}, origin=(0, 0, 0)))
...
report = validate(g)        # ValidationResult: .ok / .fatal / .errors
program = lower(g)          # refuses unless report.ok
```

## The contract

1. **Validation gates lowering.** `lower()` runs the full invariant catalog
   (§6 of DESIGN.md) first: degeneracy, schema, connectivity, anchors, rim
   matching, continuations, branch orientation, loop correspondence, seals.
   Any catalog error → `BackendNotApplicable` carrying the
   `ValidationResult`, with the specific `(code, kind, ids, expected,
   actual)` tuples. Fatal graphs are refused before any op is emitted.
   Nothing partial, nothing fabricated.
2. **Deterministic program order.** Ops are emitted keyed by the primitive
   they act on, walked breadth-first from the root; ties inside one
   primitive resolve by op id, cast-on first. Same content, same bytes —
   regardless of insertion order.
3. **Reference verbs, not a vendor format.** cast_on → `CAST_ON`;
   graft → `GRAFT`; pick_up → `PICK_UP`, `KNIT`; bind_off → `BIND_OFF`;
   short_row_close → `SHORT_ROW_CLOSE`; selvedge_seam → `SELVEDGE_SEAM`.
   Backends that speak other op sets lower themselves.
4. **Honest statistics.** `result.stats` ties every count to the lowered
   program. `machine_verdict` is `SIMULATED` only with a complete gauge
   (`wale_mm` and `course_mm`) — the condition under which loop
   correspondence was actually checked. Otherwise `UNSIMULATED`, and the
   notes say so. No gauge, no loop check, no pretending.
5. **Determinism and no silent state.** Lowering never mutates the graph;
   byte-identical re-lowerings are the contract (tested against hostile
   insertion orders and JSON roundtrips).

## Machine-readable output

```bash
python3 -m ugc sock        # versioned envelope: graph + program + stats
```

```json
{
  "version": 1,
  "backend": "default_knit",
  "machine_ops": ["CAST_ON", "PICK_UP", "KNIT", "GRAFT"],
  "ops": [{"graph_op": "sock_cast_on", "op": "cast_on",
           "machine_ops": ["CAST_ON"], "consumes": [],
           "produces": "sock_leg/rim_start"}],
  "open_boundaries": [],
  "stats": {"piece_count": 3, "joint_count": 2,
            "ops_by_kind": {"cast_on": 1, "graft": 1, "pick_up": 1},
            "machine_verdict": "UNSIMULATED"},
  "graph": {"version": 2, "primitives": ["..."], "joints": {}, "ops": []}
}
```

Exit codes: `0` ok, `2` usage error or validation refusal (catalog errors
on stderr), `1` crash.

## Layout

```
ugc/primitives.py    graph model + §6 invariant engine
ugc/validation.py    ValidationResult API over the engine
ugc/garments.py      U-01 family builders (9 families)
ugc/backend.py       lowering, stats ledger, JSON envelope
ugc/__main__.py      CLI
tests/               220 tests, unittest, no deps
DESIGN.md            spec-v2: primitives, joints, ops, invariants, §8
```

Geometric validity never implies knitability (§9). This is a planning and
simulation reference; it does not drive hardware.
