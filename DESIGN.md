# Universal Garment Primitive (UGP) — the shared language

One vocabulary, one taxonomy. Every rule, test, viewer, and benchmark file
refers to the SAME words as this page.

## Pipeline

    garment spec (families + params)
        → UGP graph (primitives + edges)      [this repo's IR]
        → validation (geometry + machine)     [hard errors, not warnings]
        → backend ops (knitplan / json)       [per machine]
        → buildability reports per backend

## Primitives (structural vocabulary)

| id         | surface            | parametric shape (r = radius, l = length)         | closed          |
|------------|--------------------|---------------------------------------------------|-----------------|
| `tube`     | open cylinder      | `r1, r2, l` (r2 = r1 when not tapered)            | `False`         |
| `sphere`   | closed ball        | `r`                                               | `True`          |
| `ellipsoid`| closed ovoid       | `rx, ry, rz`                                      | `True`          |
| `hemisphere`| half-ball         | `r`                                               | `True` (dome)   |
| `disk`     | flat circle        | `r`                                               | `True`          |
| `rect`     | flat rectangle      | `w, h`                                            | `True`          |

- All coordinates in **millimeters**.
- All rotation axes are **unit** vectors — the primitives module normalizes on
  ingest, so writers never have to.
- Closed forms seal an open end (hat crown, sock toe). Open forms expose a rim
  (neckline, cuff) that other primitives can attach to.

## Edge taxonomy — ALL edges in the graph are one of EXACTLY these four

| tag           | structural meaning            | anchor semantics                                          |
|---------------|-------------------------------|-----------------------------------------------------------|
| `branch`      | child grows out of parent     | child's origin coincides with a point on parent's surface  |
| `continuation`| child continues parent        | child's origin coincides with parent's terminus            |
| `seam`        | child edge-seals parent       | child's origin coincides with a rim point of parent        |
| `mount`       | child lies flat on parent     | child's origin coincides with parent's surface point       |

`attach(child, parent, tag)` computes the relation type automatically:

- child closed + parent open-rim  → `seam`
- child open  + parent open-rim   → `branch`
- child closed + parent closed    → `mount`
- child open  + parent terminus   → `continuation`

Unknown relationships are exactly how a compiler should fail loudly.

## Known-open definitions (research targets, not bugs)

- Glove fingers: currently `disk mounts` on the palm sphere — geometrically
  closed but mechanically unfinished (fingers are true branches on a real
  machine; blocked by missing `branch-on-branch` stitching capability).
- Waist openings, gore inserts, asymmetric necklines: unsupported (`None`).

## Backend registry semantics

- Canonical machine defaults are **pre-seeded** (`default_knit`, `default_sim`).
  `MachineBackendRegistry.add_backend` is **additive**: adding an entry with an
  existing id does NOT remove the canonical default — it creates
  `<id>__custom`. Keeps "send to default_knit" stable for downstream tooling.

## What this representation is NOT

- Not a claim that every structure is knittable — validation exists precisely
  because most are not.
- Not a stitch-level format; backends lower UGP graphs into their own ops.
- Not universal yet. The benchmark documents exactly which features fall out.
