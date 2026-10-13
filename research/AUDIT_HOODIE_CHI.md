# Hoodie Topology Bug — Audit Finding (2026-10-13)

**Severity: HIGH — declared Euler characteristic of the hoodie family is wrong by 1.**

## The bug

`ugc/garments.py` `_build_shirt(scale, hood=True)` models the hood as a
`hemisphere` primitive = a **cap-disk (k=1)**: one boundary rim, grafted to the
torso neck. The v3 layer then declares `declared_chi = -1` with 3 free rims
(hem + 2 cuffs).

Physically a hood is a **tube (annulus, k=2)**: the knitter casts on at the
**face opening**, knits a closed tube, and grafts the far rim to the neck. The
face opening is a real boundary component of the finished garment — the wearer's
head passes through it. Dropping it:

- engine: torso(k=4, χ=−2) + hood(k=1, χ=+1) + 2 sleeves(k=2, χ=0) → sum −1, 3 free rims
- correct: torso(k=4, χ=−2) + hood(k=2, χ=0) + 2 sleeves(k=2, χ=0) → sum **−2**, 4 free rims
  (hem, cuff_l, cuff_r, **face opening**), matching χ = 2 − n_free for genus 0.

Cross-checks (all passing, confirming the invariant math itself is sound):
sock +1, glove +1, hat +1, skirt 0, dress 0, shirt −2, trousers −1, shorts −1.

The χ *math* (Mayer–Vietoris additivity under gluing along S¹ circles,
χ(S¹)=0) is correct; this is a **modeling** error in one family's patch
decomposition, exactly the class of error the independent Gemini review
predicted ("torso with 4 boundary components misrepresented").

## Secondary finding (fidelity, not math)

`glove` fingers are render-only disks — the topological object is a mitten
shell. χ=+1 is consistent, but the family name overstates what the IR proves.
Either rename the family or promote fingers to real capped-tube patches
(k=1 each, tips grafted closed — χ unchanged, junctions multiply).

## Required fix

1. Add an annulus hood path: `Patch("hood", [span("hood/rim"), span("hood/face_opening", ...)])`,
   junction torso/neck ↔ hood/rim (grafted), `hood/face_opening` free.
2. `declared_chi = -2` for hooded shirts; I-CHI then enforces 4 free rims.
3. RED→GREEN per project TDD contract: update `tests/test_family_topology.py`
   expectations first (RED), then the builder (GREEN).
4. Any real knitting pattern reference (e.g. a top-down hood knit from the face
   opening) should be cited in the card comment to keep the evidence chain honest.
