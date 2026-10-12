# Universal Garment Primitive (UGP) — IR spec v2

Spec version **2**. This document is the vocabulary. Every name introduced
here — primitive kinds, boundary ids, joint types, construction methods, op
ids, invariant classes, tolerance constants — becomes API. Downstream cards
build against these exact strings.

One vocabulary, one taxonomy. Every rule, test, viewer, and benchmark file
refers to the SAME words as this page.

## 0. Pipeline

    garment spec (families + params)
        → UGP graph (render primitives + joints + knit ops)   [this repo's IR]
        → validation (invariant classes I-*, §6)              [hard errors, not warnings]
        → backend lowering (per machine)                      [ops → machine ops]
        → buildability reports per backend

## 1. The two views

A UGP graph carries two parallel views of the same garment. Neither is
derived from the other at runtime; both are serialized.

- **Render view** — parametric solid primitives (`tube`, `sphere`, ...) plus
  joints with anchors. Exists to be drawn. A primitive is *visualization
  geometry only*; nothing about it asserts fabric.
- **Knit view** — boundary descriptors (§4.1) and knit operations (§4.3).
  Exists to state, mechanically, how loops of one piece relate to loops of
  another and where fabric starts and ends.

The separation has one consequence that drives everything below: **a disk is
a render cap, NOT a knit closure.** Capping a rim in the render view does
not close it in the knit view; closures are operations applied to boundaries
(§4.3, §6 I-SEAL).

## 2. Render primitives

| id          | surface        | parametric shape (r = radius, l = length) | closed |
|-------------|----------------|-------------------------------------------|--------|
| `tube`      | open cylinder  | `r1, r2, l` (r2 = r1 when not tapered)    | False  |
| `sphere`    | closed ball    | `r`                                       | True   |
| `ellipsoid` | closed ovoid   | `rx, ry, rz`                              | True   |
| `hemisphere`| half-ball dome | `r`                                       | True   |
| `disk`      | flat circle    | `r`                                       | True   |
| `rect`      | flat rectangle | `w, h`                                    | True   |

- All coordinates and lengths in **millimeters** (§3).
- All rotation axes are **unit** vectors — the primitives module normalizes
  on ingest; writers never have to (I-AXIS).
- Closed forms seal an open end (hat crown, sock toe). Open forms expose a
  rim (neckline, cuff) that other primitives attach to.
- Each kind exposes the boundary descriptors listed in §4.1.

## 3. Units, gauge, tolerances

- **Millimeters** for every length and coordinate. Degrees for angles. Loops
  (dimensionless loop counts) for knit correspondence. No other units exist
  in the IR; every invariant below is stated in these, so pass/fail is
  machine-independent.
- **Gauge** is graph-level, optional:
  `{"wale_mm": <loop width along the rim>, "course_mm": <row height>}`.
  Absent gauge ⇒ every loop-derived quantity is `null` and loop-dependent
  invariants report UNVERIFIED, never a guess.
- **Tolerance constants** (defaults; a graph may override per instance, and
  overrides are serialized):

  | constant            | default | unit    | used by    |
  |---------------------|---------|---------|------------|
  | `T_ANCHOR`          | 0.5     | mm      | I-ANCHOR   |
  | `T_RIM`             | 1.0     | mm      | I-RIMMATCH, I-CONT |
  | `T_LOOPS`           | 2.0     | loops   | I-LOOP     |
  | `T_AXIS_EPS`        | 1e-9    | —       | I-AXIS     |
  | `MAX_CONT_TURN_DEG` | 90.0    | degrees | I-CONT     |
  | `MAX_BRANCH_TILT_DEG` | 90.0  | degrees | I-BRANCHORIENT |

## 4. Knit structure view

### 4.1 Boundary descriptors

Every primitive exposes an ordered list of **boundaries**. A boundary is a
closed loop on the primitive's surface where fabric can start, end, or join
another piece. Descriptor fields:

    {"boundary": "<id>", "kind": "rim" | "inert",
     "length_mm": <float>, "loops": <float> | null,
     "frame": {"center": [x,y,z], "normal": [x,y,z]}}

- `length_mm` — path length of the loop in mm (e.g. `2*pi*r` for a circular
  rim at radius r).
- `loops` — loop count = `length_mm / wale_mm` under the graph gauge; `null`
  when gauge is absent. This is the course-unit currency every
  correspondence rule (I-LOOP) compares. Consumers integerize; the IR never
  does.
- `kind: "inert"` marks render-only boundaries: `loops` is the constant 0.0,
  no op may consume them, and I-SEAL exempts them. This is the formal
  encoding of "a disk is a render cap, not a knit closure."

Per-kind boundary table (`knit_bearing` = the primitive represents fabric):

| kind        | knit_bearing | boundaries (ids)                                    |
|-------------|--------------|-----------------------------------------------------|
| `tube`      | yes          | `rim_start` (origin plane, radius r1), `rim_end` (terminus plane, radius r2) |
| `hemisphere`| yes          | `rim` (base plane, radius r)                        |
| `sphere`    | yes          | — (closed; `closure: "integral"`)                   |
| `ellipsoid` | yes          | — (closed; `closure: "integral"`)                   |
| `disk`      | **no**       | `rim` (inert, loops = 0.0)                          |
| `rect`      | **no**       | `edge_bottom`, `edge_top`, `edge_left`, `edge_right` (inert, loops = 0.0) |

`hemisphere`, `sphere`, `ellipsoid` carry `closure: "integral"`: the form
closes itself toward its apex by decreasing; no op and no boundary is
involved at the apex. (v1 called these "closed" in the metrics sense; v2
adds the knit reading — a hemisphere owns exactly one joinable rim.)

### 4.2 Boundary disposition

Every knit-bearing boundary ends in exactly one terminal state:

- `consumed:<op instance id>` — sealed or joined by exactly one consuming op
  (`bind_off`, `short_row_close`, `graft`, `pick_up`, `selvedge_seam`).
- `declared_open` — listed in the graph's `open_boundaries` (necklines,
  cuffs, steeks left intentionally unfinished).
- `fabric_start` — the foundation edge of a piece: produced by exactly one
  producing op (`cast_on`, `pick_up`) and not consumed by any op. A
  fabric-start edge may later be consumed (a cast-on edge grafted to another
  piece's live rim); consumption then takes precedence.

A boundary in none of these states (a floating live rim), in two at once,
or consumed by more than one op is an error (I-SEAL). Render-only (inert)
boundaries have no disposition and no state.

### 4.3 The `default_knit` op set

`default_knit` is the in-repo reference op-set (§9 for what that does NOT
mean). Exactly six ops, closed set:

| op id            | consumes                          | produces                        | effect |
|------------------|-----------------------------------|---------------------------------|--------|
| `cast_on`        | nothing                           | one `live` rim                  | starts fabric (cuff, waistband) |
| `bind_off`       | one `live` rim                    | nothing                         | seals terminally; rim becomes a finished selvedge |
| `short_row_close`| one `live` rim                    | nothing                         | seals by partial knitting (toes, heel caps, gore tips) |
| `graft`          | two `live` rims                   | nothing                         | joins loop-for-loop seamlessly (kitchener); both rims sealed |
| `pick_up`        | one `live` rim                    | one new `live` rim              | forms new stitches from the consumed rim; the produced rim belongs to the child primitive and starts its fabric |
| `selvedge_seam`  | two `live` rims                   | nothing                         | sews the two rims together; both become finished selvedges |

A **`live` rim** is a knit-bearing rim with existing stitches not yet sealed —
a fabric-start rim or any otherwise-unconsumed rim. `finished` is the
post-state of a rim sealed by `bind_off`, `short_row_close`, `graft`, or
`selvedge_seam`; it is a result, never a precondition.

Op instance schema:

    {"id": "<instance id>", "op": "<op id>",
     "consumes": ["<prim id>/<boundary id>", ...],
     "produces": "<prim id>/<boundary id>" | null,
     "params": {}}

Rules:
- Boundary references are `"prim_id/boundary_id"` and must resolve (I-SCHEMA).
- `pick_up` is the ONLY way a knit-bearing child becomes fabric from a
  parent's existing rim (v2 allows it at `rim_joint` and
  `terminus_continuation` joints only). Mid-fabric pick-up (from surface
  stitches, no rim) — fingers on a palm — needs `pick_up_path`, which is
  **reserved, not in the v2 set** (§10).
- A joint declares which op instances realize it via `realized_by` (§5.5);
  the validator enforces the construction⇔op mapping (§5.4).
- Ops may also exist with no joint (a `short_row_close` on a sock toe modeled
  without a cap primitive). Joints may not reference ops that don't exist.

## 5. Joints

### 5.1 Joint types (closed set — topology only)

v1's four tags mixed three concepts. v2 splits them: the joint type says
only **how the two pieces meet topologically**.

| joint type             | definition | justifies its existence because |
|------------------------|------------|---------------------------------|
| `rim_joint`            | the child's boundary loop coincides with a parent boundary loop over the full perimeter; the parent's opening mates with the child's opening | caps (dome on a crown), flared mates (torso onto skirt when the writer does not claim axis flow), seamed-on panels — the join reads as an edge, with no axis-continuity demand |
| `surface_branch`       | the child's boundary loop lies on the parent's surface interior, away from every parent boundary; the parent surface gains an opening where the branch attaches | sleeves from a torso, legs from hips — the parent fabric continues past the branch point |
| `terminus_continuation`| the child's starting rim coincides with the parent's terminus rim and the anchor sits at the parent's terminus; the join claims one continuous fabric flow (the axis may turn, e.g. a heel) | sock leg→heel→foot→toe, dress torso→skirt — carries the radius/axis continuity demands of I-CONT |

- v2 has **no auto-classification**. v1's `attach()` inferred the tag from
  closed/open; that inference is gone. The writer declares the joint type;
  the validator checks the declared type's own invariants. Declaring
  `rim_joint` for geometry that could pass as a continuation is legal — the
  type is a claim, and each claim is checked against its own rules.
- The v1 tags do not survive as fields. Mapping for migration reading only:
  `branch` → `surface_branch`; `continuation` → `terminus_continuation`;
  `seam` → `rim_joint` (usually construction `selvedge_seam`);
  `mount` → `surface_branch` with construction `unsupported` (mount mixed
  placement with topology and is retired).

### 5.2 Construction methods (closed set)

The construction method says **how the joint is realized in fabric**,
orthogonally to topology:

| construction    | meaning |
|-----------------|---------|
| `knitted_in`    | the child's stitches are formed from the parent's boundary loops via `pick_up` — one continuous fabric across the joint. Legal only where the parent side is a rim (`rim_joint`, `terminus_continuation`); mid-fabric formation is not in the v2 op set (§10) |
| `grafted`       | two separately-knitted `live` rims joined loop-for-loop (`graft`) — one fabric, two pieces |
| `selvedge_seam` | two pieces sewn together along their rims (`selvedge_seam` op) — two fabrics meeting at an edge |
| `unsupported`   | no knit structure is claimed; the joint exists in the render view only. Render-only children (disk, rect) MUST use this |

### 5.3 Anchors

The anchor is the spatial placement, independent of topology and method:

    "anchor": {"feature": "terminus" | "rim" | "surface",
               "boundary": "<parent boundary id>" | null,
               "point": [x, y, z]}

- `terminus` — the parent's terminus point (center of the parent's terminus
  rim). `boundary` names that rim (tube: `rim_end`; hemisphere: `rim`).
- `rim` — a point on the named parent boundary loop. `boundary` required.
- `surface` — a point on the parent's surface interior. `boundary` null.
- I-ANCHOR (§6) checks `point` against the named feature mechanically.

### 5.4 Legality matrix (mechanically checkable)

For each joint type, which (child_boundary, parent_feature) pairs are legal
and which constructions are valid. Any row not present in this table is
rejected (I-JOINT). "knit-bearing child" = the child exposes a non-inert rim.

| joint type             | parent_feature | child_boundary                              | legal constructions |
|------------------------|----------------|---------------------------------------------|---------------------|
| `rim_joint`            | `rim` (boundary required) | child's non-inert rim, unconsumed | `knitted_in`, `grafted`, `selvedge_seam` |
| `rim_joint`            | `rim` (boundary required) | child inert rim (disk/rect)                | `unsupported` only — and the parent rim must still be consumed by a parent-side op or `declared_open` (I-SEAL applies to the parent regardless) |
| `rim_joint`            | `rim`          | child with no boundary (sphere/ellipsoid)   | REJECT — a closed form has no opening to mate |
| `surface_branch`       | `surface` (boundary null) | child's non-inert rim | `unsupported` only — v2 cannot claim a knit realization mid-fabric: `knitted_in` needs a parent rim, `selvedge_seam` needs two rims, `grafted` needs a parent rim; all three are mechanically impossible here. Mid-fabric pick-up is reserved (`pick_up_path`, §10) |
| `surface_branch`       | `surface`      | child inert rim (disk/rect)                 | `unsupported` only (glove fingers today) |
| `surface_branch`       | `surface`      | child with no boundary                      | REJECT |
| `terminus_continuation`| `terminus` (boundary = parent's terminus rim, required) | child's non-inert rim, unconsumed | `knitted_in`, `grafted` |
| `terminus_continuation`| `terminus`     | child inert rim                             | REJECT — a continuation claims fabric flow; a render-only child contradicts the type |
| `terminus_continuation`| `terminus`     | any child, construction `selvedge_seam`     | REJECT — a sewn seam across a claimed continuation contradicts the type; declare `rim_joint` instead |

Additional mechanical rules:
- A primitive is the child of **at most one** joint (I-TREE).
- The construction⇔op mapping is enforced: `knitted_in` requires exactly one
  `pick_up` in `realized_by` consuming the parent rim (the joint's
  `parent_boundary`); `grafted` requires one `graft` consuming both rims;
  `selvedge_seam` requires one `selvedge_seam` consuming both rims;
  `unsupported` requires an empty `realized_by` — and, when the child is
  render-only (disk/rect), the parent rim must still be consumed by a
  parent-side `short_row_close` or `bind_off`, or be `declared_open` (the
  cap's closure lives on the parent, never on the disk).

### 5.5 Joint JSON

    {"id": "<joint id>",
     "joint": "rim_joint" | "surface_branch" | "terminus_continuation",
     "child": "<prim id>",  "child_boundary": "<boundary id>",
     "parent": "<prim id>", "parent_boundary": "<boundary id>" | null,
     "construction": "knitted_in" | "grafted" | "selvedge_seam" | "unsupported",
     "anchor": {...per §5.3},
     "realized_by": ["<op instance id>", ...]}

## 6. Invariants

Every invariant: named, deterministic pass/fail, stated in mm / degrees /
loops only. Validation runs ALL classes before any backend sees the graph.

| class | statement | fails when |
|-------|-----------|------------|
| `I-DEGENERATE` | all numeric params and coordinates are finite; every linear param > 0; the axis vector is nonzero pre-normalization | r/r1/r2/rx/ry/rz/w/h ≤ 0; any length ≤ 0; NaN or ±Inf anywhere in params, origins, anchors; zero-length axis |
| `I-SCHEMA` | every identifier and enum value is known and every reference resolves | unknown primitive kind, joint type, construction, op id, boundary id, or `realized_by`/boundary reference; duplicate primitive or joint or op instance ids |
| `I-AXIS` | after ingest normalization, ‖axis‖ = 1 within `T_AXIS_EPS` for every primitive | a stored axis was not normalized on ingest |
| `I-GRAPH` | the joint graph is a tree: exactly one component, each primitive has ≤ 1 parent joint, every referenced id exists | disconnected graphs (≥ 2 components), multi-parent primitives, dangling child/parent ids |
| `I-ANCHOR` | `anchor.point` lies on the declared parent feature within `T_ANCHOR` | terminus: point farther than `T_ANCHOR` from the terminus point; rim: distance from point to the rim circle > `T_ANCHOR`; surface: point off the parent's parametric surface by > `T_ANCHOR` (per-kind: sphere/ellipsoid radial residual; tube radial+axial profile residual; disk/rect planar residual) |
| `I-RIMMATCH` | at rim-mating joints (`rim_joint`, `terminus_continuation`): \|child_boundary.length_mm − parent_boundary.length_mm\| ≤ `T_RIM` | child opening and parent rim lengths differ beyond tolerance (this is also what makes partial-rim gore inserts unrepresentable in v2, §10) |
| `I-CONT` | at `terminus_continuation`: radius continuity — \|parent terminus rim radius − child rim radius\| ≤ `T_RIM`; axis continuity — angle(parent.axis, child.axis) ≤ `MAX_CONT_TURN_DEG` | the claimed continuous surface kinks or steps beyond the limits (a 90° heel turn passes; a weld of two unrelated tubes fails) |
| `I-BRANCHORIENT` | at `surface_branch`: angle(child.axis, outward surface normal at the anchor) ≤ `MAX_BRANCH_TILT_DEG`, i.e. child.axis · normal ≥ −1e-9 | the child grows into the parent's material (fingers pointing through the palm) |
| `I-LOOP` | for ops joining or deriving boundaries (`graft`, `selvedge_seam`, `pick_up`): \|loops_a − loops_b\| ≤ `T_LOOPS` | loop correspondence infeasible beyond tolerance. **UNVERIFIED when gauge is absent** — reported, never guessed |
| `I-SEAL` | every knit-bearing boundary ends in exactly one terminal state (§4.2): consumed by exactly one op, `fabric_start` from exactly one producing op, or `declared_open` | a rim consumed by zero or ≥ 2 ops, a producing op whose output rim is itself consumed or produced twice, or a floating rim in no state and not declared open. Inert boundaries are exempt. This is the invariant that makes render caps honest: a disk over a rim closes nothing — the rim underneath must still be sealed or declared open |
| `I-JOINT` | each joint satisfies the legality matrix (§5.4) and its `realized_by` ops exist with the required consume/produce pattern | illegal (child_boundary, parent_feature) pair; wrong construction for the type; missing or mismatched realizing ops |

## 7. Must-reject cases

The validator rejects (hard error, never a warning) every graph containing:

1. Degenerate dimensions — any radius/dimension ≤ 0, any length ≤ 0
   (`r = 0`, negative `l`, zero-width `rect`).
2. NaN or ±Inf in any coordinate, param, or anchor.
3. A zero axis vector (‖axis‖ = 0 before normalization).
4. Duplicate primitive, joint, or op instance ids.
5. Unknown primitive kinds, joint types, construction methods, or op ids.
6. Unknown or unresolvable boundary references (`child_boundary`,
   `parent_boundary`, op `consumes`/`produces`).
7. Disconnected graphs — primitives not reachable from the root through
   joints (a single primitive is trivially connected).
8. Multi-parent primitives (I-TREE).
9. Illegal (child_boundary, parent_feature, construction) triples per §5.4.
10. Anchors off their declared feature beyond `T_ANCHOR` (I-ANCHOR).
11. Rim mates whose lengths differ beyond `T_RIM` (I-RIMMATCH).
12. Continuations that kink beyond `MAX_CONT_TURN_DEG` or step in radius
    beyond `T_RIM` (I-CONT).
13. Branches whose axis points into the parent material (I-BRANCHORIENT).
14. Boundaries consumed by zero or multiple ops while not declared open
    (I-SEAL) — including any rim visually capped by a disk whose closure op
    is missing.

## 8. Backend contract

- The core validator always runs the full invariant set (§6) before a
  backend lowers a graph. Backend declarations govern **backend-side**
  behavior only.
- Each backend declares, for every invariant class, exactly one of:
  - `CHECKS` — the backend re-verifies the class during lowering (its own
    implementation, its own failure mode), or
  - `UNVERIFIED` — the backend trusts the upstream validator result.
  Both lists must together cover exactly the classes of §6; a class in
  neither or both is a registry error.
- Backend registry semantics (kept from v1): canonical defaults are
  **pre-seeded** (`default_knit`, `default_sim`). `add_backend` is
  **additive** — adding an entry with an existing id does NOT remove the
  canonical default; it creates `<id>__custom`. "Send to default_knit"
  stays stable for downstream tooling.
- A backend reports per-invariant-class status in its buildability report:
  PASS / FAIL (with the failing instance id) / UNVERIFIED.

## 9. Non-claims

- **`default_knit` is an in-repo op-set spec** (§4.3). It is NOT compatible
  with SHIMA SEIKI or any other industrial knitting machine, controller, or
  file format, and makes no claim to be. It exists so tests, the viewer, and
  the benchmark share one reference semantics.
- Geometric validity NEVER implies knitability. Validation exists precisely
  because most valid graphs are not knittable; passing I-* says the graph is
  well-formed, nothing more.
- Not a stitch-level format; backends lower UGP graphs into their own ops.
- Not universal yet. The benchmark documents exactly which features fall
  out.
- The knit view does not simulate yarn, tension, take-down, or machine
  timing. Loop correspondence (I-LOOP) is a counting feasibility check.

## 10. Known-open definitions (research targets, not bugs)

- **Glove fingers.** v2 can EXPRESS the joint (`surface_branch`, anchor on
  the palm surface) but not its knit realization: picking stitches from
  mid-fabric (no rim to consume) needs `pick_up_path`, reserved and not in
  the v2 op set. Fingers therefore stay `construction: "unsupported"`
  (render-only disks) — geometrically placed, mechanically unfinished.
- **Waist openings, gore inserts, asymmetric necklines.** Partial-rim joins
  (child rim consuming a sub-arc of a parent rim) violate I-RIMMATCH by
  construction and are not expressible in v2. A future `rim_insert` joint
  type or a boundary-arc model would be a v3 change; until then the
  validator rejects them and nothing silently degrades.
- **Cycles.** Collars or straps joining two pieces require multi-parent
  joins; I-TREE rejects them in v2.

## 11. Kept from v1 (unchanged commitments)

- Millimeter units everywhere; unit axes normalized on ingest.
- JSON serialization (`to_json` / `from_json` round-trip; shape in §12).
- Plural edge collections — joints are stored per type under plural keys
  (`rim_joints`, `surface_branches`, `terminus_continuations`).
- The U-01 family list: `hat, sock, glove, skirt, dress, trousers, shorts,
  shirt, hoodie` (nine names, six builders; shorts shares trousers, dress
  shares skirt).
- Backend registry semantics (§8).
- Hard errors, not warnings, for every §7 case.

## 12. Graph JSON (v2)

    {
      "version": 2,
      "gauge": {"wale_mm": 2.5, "course_mm": 1.6},   // or null
      "tolerances": {"T_ANCHOR": 0.5, "T_RIM": 1.0, "T_LOOPS": 2.0,
                     "T_AXIS_EPS": 1e-9,
                     "MAX_CONT_TURN_DEG": 90.0,
                     "MAX_BRANCH_TILT_DEG": 90.0},
      "open_boundaries": ["<prim id>/<boundary id>", ...],
      "primitives": [{"id", "kind", "params", "origin", "axis",
                      "boundaries": [...per §4.1]}],
      "joints": {
        "rim_joints": [...],
        "surface_branches": [...],
        "terminus_continuations": [...]
      },
      "ops": [...per §4.3]
    }

## 13. Changelog v1 → v2

1. **Edge taxonomy split.** v1's four tags (`branch`, `continuation`, `seam`,
   `mount`) mixed topology, construction method, and placement. v2: joint
   type (`rim_joint` | `surface_branch` | `terminus_continuation`) ×
   construction (`knitted_in` | `grafted` | `selvedge_seam` |
   `unsupported`) × anchor (`terminus` | `rim` | `surface` + point). The
   legality matrix (§5.4) replaces vibes with mechanically checkable rules.
   v1's auto-tag inference is removed; joint type is declared data.
2. **Render geometry separated from knit structure.** Primitives are
   visualization only. Each exposes boundary descriptors (`length_mm` and
   `loops`) and dispositions; closures are operations (`short_row_close`,
   `bind_off`), never implied by a render cap. A disk carries an inert rim
   (`loops = 0`) that no op can consume — a render cap, not a knit closure.
3. **Numeric invariants replace prose anchors.** I-DEGENERATE, I-SCHEMA,
   I-AXIS, I-GRAPH, I-ANCHOR, I-RIMMATCH, I-CONT, I-BRANCHORIENT, I-LOOP,
   I-SEAL, I-JOINT — each named, deterministic, in mm/degrees/loops with
   named tolerance constants (§3, §6).
4. **Must-reject list** (§7) enumerates the fourteen hard-error cases.
5. **Backend contract** (§8): per-class CHECKS / UNVERIFIED declarations;
   per-class status in buildability reports; registry semantics kept.
6. **Non-claims tightened** (§9): `default_knit` explicitly an in-repo
   op-set, NOT SHIMA SEIKI or any industrial equipment; validity never
   implies knitability.
7. **Kept:** mm units, axis normalization on ingest, JSON serialization,
   plural edge collections, the U-01 family list, registry semantics. The
   v1 tags survive only as the migration mapping in §5.1; they do not
   silently mix concepts anywhere in v2.
