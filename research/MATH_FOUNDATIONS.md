# MATH_FOUNDATIONS.md — verified literature for UGP spec v3 (topological basis)

Compiled 2026-10-12 from live arXiv API queries (`export.arxiv.org/api/query`). Every
entry below was fetched during this session; abstracts quoted/paraphrased from the API.
Items I could not verify against a primary source are marked **UNVERIFIED**.

## 1. Knitted objects as mathematical objects — the graph/graph-theory line

### Wooly Graphs: A Mathematical Framework For Knitting (arXiv:2407.00511)
The closest thing to a formal foundation for exactly what we're building. From the
abstract: *"develop a mathematical foundation to model knitting with graphs. We provide
a precise definition for knit objects with a knot theoretic component and propose a
simple undirected graph, a simple directed graph, and a directed multigraph model for
any arbitrary knit object… categories related to the complexity of knitting structures…
while this problem is NP-hard in general, under specific cases, there are linear and
polynomial time algorithms which take advantage of unique properties of common knitting
techniques."*

**What this means for the IR:** existence-of-knit-object is *NP-hard in general* on
graphs — our per-backend buildability report is a restricted decision problem, which is
exactly why the CHECKED/UNVERIFIED honesty contract is correct rather than modest. We
validate invariants (cheap, sound), we do not claim to solve general knit-existence
(undecidable-in-practice to promise). Cite Wooly Graphs as the formal anchor for
"validation is a restriction of an NP-hard problem."

### Knitting Skeletons (arXiv:1904.05681, TOG 2019) — closest prior art, already cited
Parametric knitted primitives + stitch pattern layers, CAD-style composition. This is
the v2-style composition we're moving past; it never claims topological validation.
Keeps our positioning claim honest: they own "parametric garment primitives + machine
layout," we own "topological closure validation + machine-independent tolerances."

### TopoKnit (arXiv:2101.04560)
Process-oriented yarn-scale topology representation for weft-knitting: *"Process space
serves as an intermediary between the machine and fabric spaces."* Yarn-level, not
garment-level — complementary layer below us. If we ever lower to yarn/topology
verification, TopoKnit is the cite. For v3 it justifies the two-space separation
(garment space ↔ process space) that our validate→lower pipeline already implements.

## 2. The physical surface — gauge as discrete geometry

### Geometry and elasticity of a knitted fabric (arXiv:1801.08355, Paci et al.)
Stockinette as a lattice of interacting stitches; derives the fabric's mechanical
response from the stitch-level geometry. Supports treating **gauge as a discrete metric
on the manifold**: rows/wales form the lattice, mm-per-stitch is the metric scale, and
our loop-count tolerances are metric tolerances on that lattice. The paper validates
that stitch geometry — not bulk continuum — governs the surface, which is the physical
justification for rim-first (loop-count-first) data.

### Knitting Knots & the Framing Anomaly (arXiv:2210.16677)
Circular knitting's twisting fault formalized via **framing curves and the Gauss
linking integral**; they literally knit bands with framing 0, 1, −2. **This is a real
published precedent for topology-level invariants on knitted tubes** — a circular-knit
tube has a framing invariant (the wale helix framing) that physical knitting must
respect. For v3 this is the precedent for an orientation/twist invariant on closed
tubes: our I-ORIENT (junction orientation consistency) has a published sibling, and a
future I-FRAMING (twist of a closed circular knit) is a legitimate, citable addition.

### Knitting Multistability (arXiv:2410.14810)
Bistable unit cells in knitted structures — mechanics, not topology. Background only.

## 3. Manifold construction by craft — the "any surface" results

### sarah-marie belcastro, "Adventures in Mathematical Knitting" (American Scientist, 2013)
**UNVERIFIED as to text** (americanscientist.org blocked fetch this session) but the
existence and thesis are well-established: knitting constructs surfaces directly, and
the standard results she popularizes are that knitting realizes *any* compact orientable
2-manifold — the construction primitives being: flat panels (annuli/disk-like patches),
short-rows (local curvature insertion = shaping), picking up stitches (identifying a new
boundary along an existing curve = junction), grafting/seaming (boundary identification),
and adding tubes (handles/branches). Treat as verified-secondary; fetch the text before
printing it in the pitch.

### Crochet line (arXiv:2302.02205 surfaces of revolution; arXiv:2408.00747 Lobachevsky
surface; AmiGo arXiv:2211.01178 amigurumi)
Adjacent craft-math literature confirming the program: craft operations as manifold
construction with invariants checked against the target topology. AmiGo in particular
validates the *compiler-shaped* loop: target manifold → pattern ops → verification.

## 4. Pair-of-pants decomposition as the garment primitive set

No paper specifically applies pants decomposition to garments (searched arXiv; nothing).
The mathematics is classical: every compact orientable surface with boundary admits a
decomposition into **pairs of pants** (three-holed spheres) and **annuli**
(Hatcher–Thurston complex; standard reference: Hatcher & Thurston, "A presenting system
for the mapping class group," plus any topology text's pants-decomposition chapter).
**This is the right formalism for UGP v3 and it's stronger than my ad-hoc "patch"
draft:**

- A **pair of pants** is a sphere with 3 boundary components: χ = 2 − 0 − 3 = −1.
- An **annulus** is a tube: χ = 0, 2 rims.
- Every garment body is a plumbing of pants and annuli:
  - **torso/shirt** = pair of pants (neck rim + 2 armhole rims) with sleeves = annuli
    glued at the armhole rims, possibly with a cuff annulus; bottom = hem annulus.
  - **trousers** = pair of pants with waist rim + 2 ankle rims, legs = annuli.
  - **dress** = torso pair-of-pants with the bottom rim replaced by a flared annulus
    (the skirt) + hem.
  - **hoodie** = shirt pants + hood (annulus glued at neck rim) + pocket patch.
  - **glove/mitten** = palm (pants-ish: wrist + hand + thumb rims) + finger annuli.
  - **hat** = annulus (brim) + disk/cap (crown closes one rim), χ = 1 with n = 1
    open rim if closed crown, n = 2 if open.
  - **sock** = leg annulus + heel turn (short-row patch) + foot annulus + toe cap.
- **χ bookkeeping rule** (verified identity): gluing along boundary gives
  χ(A∪B) = χ(A) + χ(B) − χ(A∩B); a junction identifying two rims has χ(A∩B) = χ(S¹) = 0,
  so **χ is additive under junction gluing with zero correction** — the I-χ invariant is
  a plain sum over patches. That is the invariant that makes decomposition errors
  mechanically visible.

**Concrete χ per family (all g = 0 garments; verify in tests):**

| family | decomposition | n (open rims) | χ = 2 − 2g − n |
|---|---|---|---|
| skirt | 1 annulus | 2 | 0 |
| dress | pants(torso) + annulus(skirt) | 4 (neck, 2 arms, hem) | −2 |
| shirt | pants(torso) + 2 annuli (sleeves) | 5 (neck, hem, 2 cuffs, +) | −3 |
| hoodie | shirt + hood annulus | 6 | −4 |
| trousers | pants + 2 leg annuli | 3 (waist, 2 ankles) | −1 |
| shorts | pants (short legs, no annuli) | 3 | −1 |
| sock | annulus(leg) + heel patch + annulus(foot) + toe cap | 1 (cuff) | 1 |
| hat | brim annulus + crown cap | 1 | 1 |
| glove | palm patch + 4 finger annuli + thumb + wrist annulus | 1 (wrist) | varies; test asserts |

(These counts are the *specification targets* for v3 tests, not yet engine-verified —
the C3 RED cycle should encode exactly this table.)

## 5. Roman dodecahedra — motivation only
No verified academic theory links them to knitting; the glove-knitting/finger-loop
hypothesis is amateur speculation (widely discussed online, no primary source). The
usurped insight stands on its own: a knitting site is a *rim with a loop count*, and
solids whose surface is organized as rims-of-varied-circumference are natural knit
bodies. Do not cite as scholarship.

## 6. Machine-knitting op layer
- **knitout** (McCann et al., 2016) — low-level machine-independent knit instruction
  language; our lowering layer's lineage. (UNVERIFIED link this session; known work.)
- **WHOLEGARMENT** (Shima Seiki) — proprietary whole-garment machine ecosystem;
  explicitly *not* a compatibility target (standing constraint).
- Nothing on arXiv maps high-level garment topology → machine ops with closure checks;
  the Wooly Graphs NP-hardness result explains why (general problem is hard; everyone
  restricts). Our niche — machine-independent *validation* with honest
  CHECKED/UNVERIFIED separation — remains unoccupied in the verified literature.

## IR consequences (one page summary)
1. Primitive set: **annulus, pair-of-pants, cap/disk** (+ junction identifying rims,
   arity ≥ 1). Drop "patch (k rims)" in favor of the classical pair — it has a
   literature, a fixed χ, and covering space structure.
2. Invariant set: **I-χ** (additive sum, zero junction correction — the cheap global
   catch), **I-ORIENT** (junction orientation consistency; framing precedent:
   2210.16677), **I-REACH** (junction-graph reachability from cast-on), **I-GAUGE**
   (loop counts from discrete-metric gauge, tolerance in mm; physical basis: 1801.08355).
3. Honesty: existence of a knit plan for an arbitrary graph is NP-hard (2407.00511) —
   state in DESIGN.md v3 that UGP validates invariants and lowers for *restricted*
   backends; CHECKED/UNVERIFIED contract is mathematically forced, not marketing.
4. Cite stack for the pitch: Wooly Graphs (formal foundation), TopoKnit (process space),
   Geometry & elasticity (gauge as metric), Framing (topological invariant realized in
   physical knitting), Knitting Skeletons (closest prior art, garment-level CAD).
