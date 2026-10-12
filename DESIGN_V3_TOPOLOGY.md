# UGP Spec v3 — Topological Basis (draft)

## Reframe
v2 composed garments from stacked surface primitives (tube, hemisphere, disk) — geometry
first, joined by rim matching. v3 inverts this: **a knitted garment IS a topological
object** — a compact orientable 2-manifold with boundary — and the geometry is derived,
not declared.

## The object
A garment = a 2-manifold S embedded in R³, described by:

1. **Genus** g — how many handles (closed loops) S has. A pullover worn normally has
   g = 0 with large boundary components (neck, cuffs, hem, sleeve ends). A t-shirt tied
   in a knot mid-torso would be g = 1. Knit structures that pass fabric through itself
   (cowl twists, mobius hems) change g; most garments are g = 0 and v3 should treat
   g > 0 as a flagged construct (twist/mobius ops), never silently allowed.

2. **Boundary components** ∂S = {B₁ … Bₙ} — the open rims. Each Bᵢ is a closed curve
   with a length in mm and a loop count derived from gauge. In v2 rims existed only as
   the edge of a primitive; in v3 they are first-class: the manifold is *defined* by its
   boundary curves and the surface spanning between them.

3. **Euler characteristic** χ = V − E + F = 2 − 2g − n where n = |∂S|. This is the
   first hard invariant: any proposed decomposition of a garment must sum to the
   declared χ. A dress torso + skirt + two straps decomposed wrong (double-counted a
   shared rim, dropped a boundary) will not close — χ catches it before any gauge math
   runs.

## Why this kills the stacked-pots problem
v2's tube-stack has no notion of *branching*: a shirt is "torso tube + sleeve tube"
glued rim-to-rim, which is why sleeves render as stubs and fingers as inert disks.
Topologically a shirt is one manifold: a boundary curve (armhole) on the torso surface
is *also* the closed end of the sleeve surface — a single shared loop. The v3 primitive
is therefore:

- **Patch** — a surface spanned between 1..k boundary curves (k=1: tube/closed rim;
  k=2: annulus = classic tube section; k≥3: the interesting cases — gussets, yokes,
  saddle shoulders). Patches carry fabric; rims carry topology.
- **Junction** — the identification of 2+ boundary curves (or one curve with itself on
  two patches). A junction is valid iff every participating rim has equal loop count
  within tolerance (already the v2 rim-match rule) AND the identified curves are
  consistently oriented (orientable manifold check — this is what prevents a seam that
  folds the fabric inside-out).

The roman dodecahedron is instructive, not literal: it's a solid whose surface is
nothing but *rims of different circumferences* — a glove body is the same object with
finger tubes identified at hole-rims. v3 never imports the shape; it imports the
insight that **holes are the primary data, surfaces are the filler**.

## Invariants added on top of v2 (all deterministic, machine-independent units)
- **I-χ**: sum of patch contributions − junction identifications == declared χ of the
  garment graph. Hard fail on mismatch.
- **I-ORIENT**: the junction graph is orientable; no junction may pair two rims with
  conflicting traversal direction (checked on the cyclic order of each rim's loop list).
- **I-REACH**: every boundary component of S must be reachable from the cast-on
  component through the junction graph — no floating patches (this catches a sleeve
  declared but never attached).
- **I-GAUGE-CLOSURE**: for every patch, loop count at each rim is the gauge-integral of
  the surface's mm length between them; rims joined by a junction must agree within
  tolerance (v2's T_LOOPS rule, generalized from rim-pairs to junction-arbitrary-arity).
- v2's I-SEAL / I-ANCHOR carry over unchanged; cast-on / bind-off become dispositions
  on boundary components, not primitive edges.

## What this changes in the repo
- `primitives.py`: patch replaces tube/hemisphere as the core surface object; keep
  tubes/hemispheres as derived convenience builders (k=2 and cap cases) so existing
  tests mostly hold.
- `garments.py`: every family re-expressed as patch/junction decompositions. Expected
  primitive counts shift from 2p–7p to patch/junction pairs (shirt = 4 patches, 4
  junctions; glove = 6 patches (palm, 4 fingers, thumb) + 5 junctions + wrist).
- `validation.py`: new invariants I-χ, I-ORIENT, I-REACH, I-GAUGE-CLOSURE join the
  catalog; error-code space extends the 28-entry table.
- `backend.py`: lowering walks the junction graph (spanning tree = knit order; back
  edges = pick-up joins) instead of primitive order. Determinism requirement unchanged:
  canonical order via sorted junction ids.
- Viewer: render patches as manifold surfaces with highlighted boundary curves — the
  picture stops looking like stacked pots and starts looking like topology.

## Non-goals
- No literal polyhedral shapes, no face-hole catalogs, no node/knob legends.
- No free-form genus games: g > 0 needs an explicit twist op family, out of scope for
  v3.0 except as a reserved error code.
