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

## Pipeline CLI

`python3 -m ugc.cli` is the pipeline front door: the same build / validate
/ lower / report flow as the API, one subcommand each. Every JSON payload
is the library's own `to_dict()` shape — no renames, no re-shapes.

```bash
python3 -m ugc.cli families                          # the nine U-01 families
python3 -m ugc.cli build sock --scale 1.5 --json     # graph (family + scale + graph.to_dict())
python3 -m ugc.cli validate --graph my_graph.json    # full invariant catalog
python3 -m ugc.cli plan sock --json                  # versioned lowering envelope
python3 -m ugc.cli report sock                       # per-class buildability (§8)
```

Graph input for validate/plan/report is `--graph PATH` or
`--graph-json JSON` (mutually exclusive); plan/report also accept a FAMILY
argument (`sock`) built at scale 1.0. Family names are case-insensitive.
`--json` prints machine-readable JSON on stdout; human text otherwise.

Exit codes:

- `0` — success;
- `1` — the graph failed the invariant catalog: build/plan/report refuse
  with a JSON payload carrying the exact `ValidationResult` (`errors` +
  `findings`) and the refused slot (`"plan"` / `"report"`) set to `null`;
- `2` — usage error: unknown family or backend, non-positive or
  non-numeric `--scale`, missing/unreadable graph file, malformed JSON,
  wrong graph version, malformed graph entities, bad subcommand. (Schema
  refusals from `UGPGraph.from_dict` are input-shape problems, so a
  negative-radius graph is `2`, while a constructible-but-disconnected
  graph is `1` — the catalog owns graph-content verdicts.)
- `3` — the library raised an unexpected exception (programmer bug):
  traceback on stderr, nothing partial on stdout.

Determinism holds at the CLI boundary too: same input bytes, same stdout
bytes (`sort_keys` everywhere; nothing sourced from wall clock or dict
order).

## Benchmark

`benchmark/benchmark.py` measures what the engine actually does across
all nine U-01 families and the canonical backends — every number comes
from the engine's own surfaces (`buildability_report`, `lower`,
`garment_stats`, `Boundary.loops_for`), never recomputed:

```python
import benchmark.benchmark as bench
bench.write_report("benchmark/report.json")          # no gauge
bench.write_report("benchmark/report-gauged.json",
                   gauge={"wale_mm": 2.5, "course_mm": 3.0})
```

Per family and backend the report carries: graph facts (primitive
boundary lengths in mm; loop counts only via the engine's own
conversion when the graph carries a complete gauge), joints with their
declared construction (`"unsupported"` surfaces verbatim — documented,
not hidden, §10), declared open boundaries, the full validation
verdict, buildability per invariant class, and the lowered program.
Without a gauge, loop counts are null and `machine_verdict` is
`UNSIMULATED` — the report cannot claim a simulation the engine did
not run. A graph that fails validation is recorded as a refusal
(`{"lowerable": false, "refusal": …}` with the exact catalog codes),
never a crash and never a partial program.

Committed reports: `benchmark/report.json` (ungauged),
`benchmark/report-gauged.json` (wale 2.5 mm / course 3 mm).

## Layout

```
ugc/primitives.py    graph model + §6 invariant engine
ugc/validation.py    ValidationResult API over the engine
ugc/garments.py      U-01 family builders (9 families)
ugc/backend.py       lowering, stats ledger, JSON envelope
ugc/__main__.py      CLI
benchmark/           U-01 benchmark + canonical JSON reports
tests/               unittest, no deps (CLI + viewer smoke incl.)
tools/emit_specs.py  emit per-family viewer bundles to out/<family>.json
viewer/              zero-dependency WebGL viewer (index.html + app.js)
DESIGN.md            spec-v2: primitives, joints, ops, invariants, §8
```

## Viewer

Browse the emitted spec graphs at `http://127.0.0.1:<port>/viewer/`:

```
python3 tools/emit_specs.py          # regenerate out/<family>.json
python3 -m ugc.cli serve             # read-only http://127.0.0.1:8765
```

The page renders exactly what the bundles contain: per-primitive geometry
(tube / hemisphere / disk) from the spec params, rim overlays, joint
anchors, and the validation/buildability/plan facts — including
unsupported constructions and `machine_verdict=UNSIMULATED`, surfaced
verbatim. `out/` is gitignored; regenerate after any library change.

Geometric validity never implies knitability (§9). This is a planning and
simulation reference; it does not drive hardware.
