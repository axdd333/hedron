# UGP — Investor Deck (10 slides)

Deck date: 2026-10-12. Every external number traces to SOURCES.md in this
directory. Claims about the competitive field follow PRIOR_ART.md's verified
landscape — nothing on these slides claims more than that review supports.

---

## S1 — Title

**UGP — the machine-independent validation and interop layer for knitted garments.**

Design tools draw garments. Knitting machines need instructions. Today nothing
between them checks whether the garment can be built at all. UGP is that
missing layer: a written spec (v2), a reference validator, and a public
benchmark for what each knitting backend can actually build.

- Open spec + reference implementation; lowering targets include open
  machine-independent formats (knitout) and, by contract, vendor stacks.
- Positioning per prior-art review: not "a compiler," not "an IR" — the
  **validation and interop layer above them**.

> notes: one line, then the problem. the phrase that survives diligence:
> "the seam between design intent and machine ops is unowned."

---

## S2 — Problem

**Garments are designed in one world and manufactured in another. Nobody
checks the crossing.**

- Seamless apparel is a $69.7B market in 2026 heading to $142.2B by 2036
  (7.4% CAGR) — whole-garment knitting is how a growing share of it is made.
- The machines are expensive and their stacks are closed: an industrial
  knit-and-wear package (Stoll ADF + design software) was line-itemed at
  **$125,605**; the studio-class Kniterate runs **$15,999**.
- Validation exists only inside vendor toolchains: SHIMA SEIKI's KnitPaint
  advertises "mistakes and difficult-to-knit areas detected in advance" —
  proprietary, and locked to their machines.
- The open alternative (knitout, CMU) is **instruction-level**: no garment
  geometry, no join semantics, no feasibility checks at the design level.

Result: designers iterate blind, manufacturers eat the mistakes, and every
software layer refuses to make claims about the garment itself.

> notes: the CAD vendors simulate drape but have zero knit-machine
> semantics; the vendors with knit semantics keep validation behind one
> stack. that gap is the company.

---

## S3 — Solution

**A garment-level spec with hard, numeric validity — checked before any
machine sees the design.**

UGP (Universal Garment Primitive) spec v2 carries two views of one garment:

- **Render view** — parametric primitives (tubes, domes, disks) to be drawn.
- **Knit view** — boundary descriptors in millimeters and loop counts, plus
  a closed six-op set (cast on, bind off, short-row close, graft, pick up,
  selvedge seam) and three joint types × four construction methods with a
  mechanically checkable legality matrix.

On top of it:

- **11 invariant classes** — anchor, rim-length match, loop correspondence,
  radius/axis continuity, branch orientation, boundary sealing — each
  pass/fail in mm / degrees / loops, enforced as hard errors.
- **An honesty contract** — every lowering backend declares per invariant
  class whether it re-checks (CHECKS) or trusts upstream (UNVERIFIED),
  serialized with the artifact. Non-claims are part of the spec.

The one-sentence version: **invalid garments are mechanically
unrepresentable — and every claim a backend fails to verify is labeled.**

> notes: demo beat: show a sock graph failing I-RIMMATCH, then a legal one.
> the disk-cap point lands with investors who've seen CAD demos lie.

---

## S4 — Why now

**The incumbent order is consolidating and the open layer is maturing —
the unowned seam is open for exactly one window.**

- **Incumbent churn.** Stoll (Karl Mayer) discontinued flat-knitting —
  Reutlingen production closed 2025-10-31; selected assets moved to Ningbo
  Cixing (announced Jun 2026). A top-two brand exiting under its parent is
  the moment customers re-evaluate their stack.
- **The closed incumbent isn't coming down.** SHIMA SEIKI: WHOLEGARMENT
  since 1995, **2,900+ patents** hardware-to-software, validation stays
  proprietary inside SDS-ONE/APEXFiz.
- **The open world formalized below garment level.** 2016: the 3D machine
  knitting compiler. 2017: knitout. 2023: formal semantics. 2025:
  polynomial-time program equivalence. The stitch and instruction layers are
  now rigorous — and *still* nobody models the garment as an assembly of
  parts with knit-legal joins.
- **Cautionary evidence the consumer layer was premature, not the tooling.**
  Unmade raised $4M (2018) for on-demand consumer knits, then pivoted to
  B2B software (UnmadeOS). The durable need is interop and validation, sold
  to operators — not consumer D2C.

> notes: if asked "why will SHIMA not just add this": they monetize the
> stack, not interop; publishing falsifiable coverage tables contradicts
> their sales motion. CMU extending knitout upward is the real risk —
> window is execution speed (see PRIOR_ART §6).

---

## S5 — Product

**Shipped: spec v2, builders, validator, round-trip. Next: the benchmark.**

- **Spec v2** (shipped) — the vocabulary: 6 primitive kinds, 6 ops, 3 joint
  types × 4 constructions × 3 anchor features, 11 invariant classes, 14
  must-reject cases, serialized JSON with version and tolerances.
- **Reference builders** (shipped, tests green) — nine garment families
  (hat, sock, glove, skirt, dress, trousers, shorts, shirt, hoodie) built
  on v2; contract tests for registry, scale, and JSON round-trip.
- **Validator** (shipped in-repo) — runs the full invariant set before any
  backend lowers a graph; hard errors, never warnings.
- **Benchmark v1** (6 weeks out) — which garments each backend can build,
  per invariant class, published as a falsifiable coverage table. No
  vendor, no academic lab publishes anything like it. This is the wedge
  artifact: it forces every lowering target to either measure up or
  disclose.

> notes: honesty about state is the pitch. v2 exists, builders are green,
> the benchmark is scoped. funding converts the benchmark from repo doc to
> public standard with real machines behind it.

---

## S6 — Market

**Bottom-up wedge into a $69.7B manufacturing shift.**

- Anchor number (sourced, single): seamless apparel **$69.7B (2026) →
  $142.2B (2036)**. UGP sells tooling into that shift — the tooling slice
  is smaller and we do not inflate it.
- Beachhead, in order:
  1. **Design tools** — CAD vendors and indie tools integrating a
     garment-level validity check at authoring time.
  2. **Machine vendors & on-demand manufacturers** — certification that a
     backend honors the spec (benchmark tiers), and pre-check APIs that
     keep unproducible orders out of expensive machine time.
  3. **Education & studios** — Kniterate-class machines in universities and
     makerspaces need a teachable, machine-neutral design contract.
- Expansion path follows the certification: per-seat/CI licensing →
  backend certification fees → enterprise interop contracts.

> notes: if pressed on TAM: we don't claim the $69.7B; we claim the check
> that every participant in it will eventually need, priced like any
> validation/CI infrastructure.

---

## S7 — Competition

**Nobody owns the layer. Each neighbor proves a piece of it.**

| neighbor | what they own | what they do NOT do |
|---|---|---|
| SHIMA SEIKI (WHOLEGARMENT + SDS-ONE) | closed vertical stack, 2,900+ patents | machine-independent representation, export, third-party checks |
| Stoll → Cixing | knit-and-ware hardware lineage | open representation; company in post-acquisition consolidation |
| Kniterate | affordable studio hardware | garment-level validation or design layer |
| CLO3D / Browzwear / Style3D | 3D garment CAD + simulation | zero knit-machine semantics |
| knitout / CMU Textiles Lab | machine-independent *instruction* format | garment geometry, joins, invariants; spec public but unlicensed |
| MIT — Knitting Skeletons (2019) | parametric primitive composition | legality matrix, boundary sealing, numeric invariants |
| stitch-mesh line (2012–2021) | yarn-level correspondence + simulation | garment-joint semantics, cross-machine programs |

- UGP cites the compiler line (McCann 2016, knitout 2017) as **foundations**,
  not competitors — and claims exactly what the reviewed corpus lacks: the
  joint taxonomy × construction legality matrix, boundary-sealing invariants
  (I-SEAL), numeric feasibility in mm/deg/loops checked before lowering, and
  the per-backend honesty contract.
- Moat is **process, not patent**: published falsifiable benchmarks compound;
  vendor demos don't.

> notes: closest single prior art: Knitting Skeletons for composition,
> knitout for the IR framing, SHIMA KnitPaint for vendor-side validation.
> all three cited on-slide — pre-empting diligence is the strategy.

---

## S8 — Business model

**Open the spec; sell the checks, the certification, and the interop.**

1. **Open core** — spec + reference validator + benchmark harness, public
   and forkable. Adoption is the product's distribution.
2. **Design-tool licensing** — per-seat / CI-integration licenses for
   commercial tools embedding garment-level validation.
3. **Backend certification** — vendors pay to be benchmark-published as
   UGP-compatible at a tier (which garments, which invariant classes, at
   what tolerances). The coverage table is the sales asset.
4. **Manufacturer pre-check API** — buildability screening for on-demand
   knit operations before machine time is booked.
5. **Sponsored pilots** — public/non-profit funding (campus programs, NSF
   I-Corps route) pays for early deployments while the commercial lines
   form.

> notes: pre-seed-stage sequencing: land 1 design-tool pilot + 1 machine
> vendor certification candidate before pricing anything hard.

---

## S9 — Traction & 6-month plan

**Built:** spec v2 · six-op reference set · builders for all nine garment
families with contract tests green · JSON round-trip · in-repo validator.

**Non-dilutive calendar already scheduled (all verified, UConn/CT):**

| when | what | value |
|---|---|---|
| Oct 19, 2026 | Accelerate UConn (customer discovery) application deadline — **1 week out** | $1,500 stipend, 20-interview discovery log |
| Oct–Mar (monthly) | Get Seeded pitch nights | seed-stage feedback; Demo Day Apr 14, 2027, up to $5,000 |
| Mar 5, 2027 | Innovation Quest application opens (spring) | campus prize capital + exposure |
| Feb 17, 2027 | CCEI Summer Accelerator deadline | **$15,000 non-dilutive** per startup; summer residency in Hartford (Jun 7–Aug 5, 2027); finalists advance to Wolff |
| Oct 2027 | Wolff New Venture Competition | $150,000+ pool, $30,000 grand prize |
| rolling | NSF I-Corps National Teams (via Northeast Hub) | up to **$50,000** for customer discovery ($10,000 participation fee paid from award) |
| rolling | Z Fellows ($10k, 1-week, rolling) · 1517 ($1k grants, 200+/yr) | early private capital without a round |

**The 6-month plan the money buys:** benchmark v1 public with three
lowering targets (knitout-based first) → 20-interview discovery log from
real design-tool users and one on-demand operator → one design-tool pilot
integration started.

> notes: the non-dilutive stack is not decoration; it sequences dilution
> last and fills the discovery requirements I-Corps and CCEI both demand.

---

## S10 — The ask

**Raising $250,000 pre-seed on a SAFE — 12-month runway, dilution last.**

Use of funds:

- **Founder + contract engineering (12 mo)** — benchmark v1, second/third
  lowering targets, pilot integration work: ~$150k
- **Machine time + benchmark infrastructure** — studio-class machine
  access and CI for the coverage tables: ~$40k
- **FTO / IP counsel** — the prior-art review flags a mandatory
  freedom-to-operate pass before any filing (SHIMA's patent estate; one
  Artlink patent family to read in full): ~$30k
- **Conferences + discovery travel**: ~$15k
- Buffer: ~$15k

Milestones to Series-seed readiness: benchmark v1 public · three lowering
targets verified against it · one commercial design-tool pilot signed ·
certification program priced with one vendor candidate.

**First money in is non-dilutive and already scheduled (S9). This round
buys the window between spec-done and standard-set.**

> notes: leave-behind: SOURCES.md — every number here has a URL and a
> fetch date; the two things we could not verify are flagged in it, not
> hidden. that habit is the product in miniature.
