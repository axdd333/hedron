# PRIOR_ART.md — UGP prior-art review (UGC-01)

Review date: **2026-10-12**. Scope: whole-garment knitting systems, knit
programming/representations, garment CAD, and machine-independent/compiler
framings — academic + industrial + patent literature. Purpose: ground the
defensibility section of the pitch. Every number carries a source URL; where a
number could not be verified, it says so.

**Method & limitations (transparency).** General-purpose web search engines
were bot-walled during this review (Firecrawl 403; Bing/DDG served junk or
CAPTCHAs), so the sweep ran over: OpenAlex (abstracts, authors, citation
counts), Crossref, arXiv, Google Patents XHR API, Google/Bing News RSS,
GitHub API, company registries (Companies House), vendor sites directly, and
Wayback availability. Citation counts are OpenAlex figures as of 2026-10-12.
News-RSS-derived facts are marked "(headline)" when only the headline was
readable. Two verification gaps are flagged inline (Artlink patent full text;
whole-garment machine pricing).

---

## 1. Landscape comparison

| system | what it is | representation | open? | garment range | what it does NOT do (the gap UGP claims) |
|---|---|---|---|---|---|
| SHIMA SEIKI WHOLEGARMENT + SDS-ONE APEX4 | Vertical stack: seamless whole-garment machines (SWG-XR, MACH2XS, …) + closed design system | Proprietary machine formats; KnitPaint stitch programming | **No** (2,900+ patents held over the tech; formats closed) | Full seamless garments, incl. seamless gloves (the tech's origin story) | No machine-independent representation, no export path, no third-party compiler story; validation ("mistakes and difficult-to-knit areas detected in advance") exists but is locked inside the vendor's own toolchain |
| SDS KnitPaint-Online | SHIMA's knit programming UI, now sold as standalone cloud software | Image/lattice-based stitch programming derived from APEX projects | No | Programmed knits, collar machine variant (N.SSR 072) | Programming aid, not an interchange format; no garment-level join/closure model; vendor-locked |
| Stoll (Karl Mayer → Cixing) knit-and-wear | Industrial flat-knitter brand; ADF 530-16ki, CMS 703 knit-and-wear (announced Apr 2024, headline) | Proprietary (UNCONPET/own formats) | No | Fashioned panels → complete garments | Closed stack; company in upheaval — Reutlingen production closed 2025-10-31, selected assets transferred to Ningbo Cixing (Jun 2026); no open representation, no cross-machine story |
| Kniterate | Compact digital knitting machine for studios/makerspaces | Own software → K-code (.kc) machine format | Hardware closed; K-code targetable (CMU publishes an open knitout→K-code backend); machine software not an open IR | Sweaters, dresses, tank tops, scarves, shorts, hats, shoe uppers (vendor list) | $15,999 prosumer class; single-system (limited structures); no garment-level validation or machine-independent design layer of its own |
| CLO3D / Browzwear (VStitcher, Lotta) / Style3D | 3D garment CAD: patterns, fit, cloth simulation, virtual sampling | Mesh + physics simulation of fabric; 2D patterns → 3D drape | No (commercial SaaS) | Any sewn/cut garment, simulated | Zero knit-machine semantics: no loops, courses, transfers, closures, or machine ops; geometric validity never implies knittability — exactly the confusion UGP's knit view forbids |
| knitml | XML dialect for hand-knitting pattern interchange (2005-era, Google Code → GitHub mirror) | XML pattern documents | Yes (source public) | Hand-knitting instructions | Dormant (last push 2015, 13★); hand-knitting semantics only; no machine knitting, no geometry, no validation |
| KnitYak | D2C knitwear brand selling algorithmically designed scarves/sweaters | Computational designs → mill production | Not a tool; brand site live with design catalog | Scarves, sweaters, blankets | Consumer product line, not a representation or compiler; no published IR |
| OpenKnit | 2014–2016 open-source hobby knitting machine (+ "DOBBY" software) | Arduino-class machine control | Was open-source | Scarves/simple tubes (community demos) | Project defunct — main repo/org no longer resolvable on GitHub (404, checked 2026-10-12); hobbyist scale; no garment model |
| **knitout** (CMU Textiles Lab, 2017–) | Low-level **machine-independent** knitting instruction file format (.k) | Text instruction stream (knit/tuck/transfer/split per needle, carriers) | Spec + tools public on GitHub (63★); **no LICENSE file** (all-rights-reserved default) | Instruction streams for flat machines; backends incl. Kniterate; frontends in JS/Python | Instruction-level only: no garment geometry, no join/joint semantics, no boundary/closure invariants; "machine-independent" claimed at the op level, not the garment level |
| **A compiler for 3D machine knitting** (McCann, Albaugh, Narayanan et al., ACM TOG/SIGGRAPH 2016; 165 cites) | High-level knitting language → scheduling → low-level ops → machine backends (incl. SHIMA SEIKI MACH2XS) | Language + intermediate representation + per-machine backends | Research (knitout ecosystem public) | 3D-knittable objects/garments via compiler demos | Compiles *stitch structure*; has no explicit garment-assembly algebra (joint types × construction methods × anchors), no boundary-disposition/sealing invariants, no numeric rim/loop/axis feasibility checks at the design level |
| Semantics & Scheduling line (Lin, Narayanan, Ikarashi, Ragan-Kelley, Bernstein, McCann, TOG 2023, 16 cites; Polynomial-Time Program Equivalence, Hurtig et al. 2025) | Formal semantics for knitout; optimization passes; program-equivalence algorithm | Monoidal-category / string-diagram semantics over instruction sequences | Research (paper; code per lab) | Program correctness at instruction level | Does not model garment geometry or assembly; verifies program equivalence, not garment feasibility; no design-facing validation contract |
| Stitch-mesh line (Yuksel/Kaldor/James/Marschner 2012, 172 cites; Stitch meshing, Wu et al. 2018, 56 cites; Knittable Stitch Meshes, Wu/Swan/Yuksel 2019, 74 cites; Wearable 3D Machine Knitting, Wu et al. TVCG 2021, 41 cites) | Modeling + auto-conversion of arbitrary 3D shapes into knittable stitch structure; wearability constraints | Stitch mesh (quad mesh encoding stitch topology) → yarn curves → simulation | Research (tooling per papers) | Complex 3D knit structures, garments for virtual characters, wearable covers | Yarn/stitch-level correspondence, not garment-joint semantics (no construction-method taxonomy, no sealing/disposition algebra); outputs are structure/simulation, not cross-machine programs |
| Knitting Skeletons (Kaspar, Makatura, Matusik, MIT UIST 2019) | Interactive CAD tool: compose parametric knitted primitives + pattern layers into garments | Parametric primitives + pattern layers → machine instructions (custom stack) | Research | Garments composed from shaped panels (sweaters etc.) | Closest academic relative of UGP's primitive composition — but no joint-type/construction legality matrix, no boundary disposition (I-SEAL), no mm/deg/loops invariants, single machine ecosystem per demo |
| Artlink International patent family (US9695529B2, CN111291431B, HK40021903; priority 2015-04-21) | Patents titled "method and system for making three-dimensional fully-fashioned knitted patterns" (assignee Artlink International Development Ltd) | 3D form → fully-fashioned knit pattern generation | Patented, not published as a tool | Knitted pattern generation from 3D forms | Full text not readable during this review (Google bot-wall) — **flagged for manual read before any filing**; appears to cover pattern *generation*, not machine-independent validation or multi-backend lowering |
| Tailored Industry | On-demand WHOLEGARMENT knit manufacturer (Brooklyn), zero minimums, SaaS-ish ordering platform | Their own platform on SHIMA machines | Service, not software | Sweaters etc., made on demand | Operator, not a representation; no interop story; proves the on-demand WHOLEGARMENT service model runs at boutique scale |
| Unmade (London, est. 2013) | Consumer on-demand knit platform; raised $4M (Aug 2018, WWD headline); **pivoted** — company is Active at Companies House (accounts to Dec 2025) and now sells UnmadeOS, "cloud-based software to optimise your entire custom product cycle" | Proprietary design-parameterization → mill integration | No | Custom knitwear (consumer service discontinued; SaaS pivot live) | Cautionary datum: consumer on-demand knit economics were hard enough that the flagship startup abandoned D2C for B2B SaaS; no published IR or validation layer |

---

## 2. Notes per area

### 2.1 Industrial whole-garment knitting

- SHIMA SEIKI introduced WHOLEGARMENT in **1995** (SWG-V); the technology's
  30th anniversary is 2025. Shima states it holds **over 2,900 patents**
  (registered or pending, worldwide) covering "mechanical hardware to
  programming software and stitch formation," incl. shaped knitting
  (narrowing/widening), DSCS, 4-needlebed technology, SlideNeedle (6 → 12
  knitting techniques). Current WHOLEGARMENT machine list: SWG-XR, MACH2XS,
  MACH2VS, MACH2X, MACH2S, SWG-FIRST, SWG-X, SWG-V, NewSWG-V, NewSES-S·WG,
  NewSES-C·WG, SWG021/041/061/091 (N/N2), N.SVR183, SPG-R.
  Source: https://www.knittingindustry.com/2900-reasons-to-choose-wholegarment-technology/ (2025-03-18, interview with Shima corporate communications).
- SDS-ONE APEX4 is the closed design system in front of those machines;
  APEXFiz is their cloud/virtual-sampling service.
  https://www.shimaseiki.com/product/design/system/
- SDS KnitPaint-Online: standalone knit programming product; vendor-claimed
  features include automatic style→pattern generation with stitch counts and
  "mistakes and difficult-to-knit areas are detected in advance" — the
  vendor-side analog of UGP validation, but proprietary and inside one stack.
  https://www.shimaseiki.com/product/knit/sds_knitpaint-online/
- Stoll (Karl Mayer): "KARL MAYER has discontinued its flat-knitting machine
  business under the STOLL brand. The production facility in Reutlingen has
  been closed since October 31, 2025 … selected assets … to Ningbo Cixing"
  (stoll.com notice, fetched 2026-10-12). corroborated by
  https://www.knittingindustry.com/karl-mayer-confirms-closure-of-stoll-reutlingen-site/ (2025-10-21) and Cixing acquisition reports (Knitting Industry / Knitting Trade Journal, 2026-06-17, headlines).
- Kniterate: $15,999, gauge 7, 252 needles/bed (504 total), 6 yarn feeders,
  transfer + tuck + split, max width 36 in / 914.4 mm.
  https://www.kniterate.com/product/digital-knitting-machine/ (fetched 2026-10-12).
- Machine economics data point: a university grant line covered "the STOLL
  ADF 530-16 ki B" machine **plus design software** at **$125,605**
  (Champlin Foundation to Univ. of Rhode Island, Jan 2023).
  https://www.uri.edu/news/2023/01/champlin-foundation-grant-funds-state-of-the-art-knitting-machine/
- No public price for a current flagship WHOLEGARMENT machine (SWG-XR /
  MACH2XS) was found; treat "hundreds of thousands of dollars per machine"
  as anecdote until a source exists. **(verification gap)**

### 2.2 Knit programming / representations (academic line that matters)

The compiler lineage, in order:

1. **McCann, Albaugh, Narayanan et al., "A compiler for 3D machine knitting"
   (TOG 2016)** — high-level shape/structure language, scheduling pass,
   low-level ops, multiple machine backends. DOI:
   https://doi.org/10.1145/2897824.2925940
2. **knitout (2017–)** — "a file format for representing low-level knitting
   instructions in a **machine-independent** way" (the spec's own first
   sentence). https://github.com/textiles-lab/knitout — spec:
   https://textiles-lab.github.io/knitout/knitout.html — public backends
   include knitout→K-code for Kniterate:
   https://github.com/textiles-lab/knitout-backend-kniterate
3. **Narayanan, Wu, Yuksel, "Visual knitting machine programming" (2019)** —
   structured visual programming compiled to machine code.
   https://doi.org/10.1145/3306346.3322995
4. **Lin et al., "Semantics and Scheduling for Machine Knitting Compilers"
   (TOG 2023)** — formal semantics for knitout; "existing representations …
   are incomplete or overly specific … difficult to define correctness."
   https://doi.org/10.1145/3592449
5. **Hurtig et al., "Polynomial-Time Program Equivalence for Machine
   Knitting" (2025)** — canonicalization over monoidal-category semantics.
   https://doi.org/10.1145/3747517

Geometry-side lineage:

- Kaldor, James, Marschner, "Simulating knitted cloth at the yarn level"
  (2008, 212 cites) https://doi.org/10.1145/1360612.1360664
- Yuksel et al., "Stitch meshes for modeling knitted clothing with
  yarn-level detail" (2012, 172 cites) https://doi.org/10.1145/2185520.2185533
- Wu et al., "Stitch meshing" (2018, 56 cites) — first fully automatic
  3D-shape → knit-model pipeline https://doi.org/10.1145/3197517.3201360
- Wu, Swan, Yuksel, "Knittable Stitch Meshes" (2019, 74 cites) — guarantees
  knittability; shift paths, mismatched knitting directions.
  https://doi.org/10.1145/3292481
- Wu et al., "Wearable 3D Machine Knitting" (TVCG 2021, 41 cites) — automatic
  pipeline for knits that are both machine-knittable and *wearable* (can be
  put on/taken off the target object) https://doi.org/10.1109/tvcg.2021.3056101
- Kaspar, Makatura, Matusik, "Knitting Skeletons" (UIST 2019) — parametric
  knitted primitives + pattern layers, CAD-style composition.
  https://doi.org/10.1145/3332165.3347879
- Albaugh et al., "Digital Fabrication of Soft Actuated Objects by Machine
  Knitting" (CHI 2019, 116 cites); KnitUI (CHI 2021, 101 cites).
- Peripheral: "A Weft Knit Data Glove" (2021,
  https://doi.org/10.1109/tim.2021.3068173) is a textile sensor glove, not a
  garment-modeling system — no conflict with UGP's glove family.
- OpenKnit (2014–2016, hobby open-source machine): defunct — GitHub returns
  404 for the project/org (checked 2026-10-12). knitml: dormant since ~2015
  (https://github.com/fiddlerpianist/knitml, last push 2015-08-06). KnitYak:
  live as a design brand (https://knityak.com/), not a published tool.

### 2.3 Garment CAD & parametric fashion

- CLO3D — virtual garment design/simulation
  (https://www.clo3d.com/en/); Browzwear — VStitcher/Lotta, Fabric Analyzer,
  open-platform integrations (https://browzwear.com/); Style3D — simulation
  engine for deformable materials + AI design workflow
  (https://www.style3d.com/). All three: 2D-pattern/3D-simulation paradigms
  with **no knit-machine semantics**. They are UGP's contrast class: the
  render view without the knit view.
- On-demand knit operations: Tailored Industry (Brooklyn) runs WHOLEGARMENT
  machines with zero-minimum on-demand production
  (https://tailoredindustry.com/; also Textile World 2022-12-08
  "WHOLEGARMENT Technology Enables On-Demand Production" via
  Google News RSS listing).
- Unmade: Companies House UNMADE LTD. (08498078) — **Active**, SIC 62012
  (business/domestic software), accounts made up to 2025-12-31 filed
  2026-07-29. https://find-and-update.company-information.service.gov.uk/company/08498078
  Their site now sells UnmadeOS (custom-product-cycle software)
  (https://unmade.com/, fetched 2026-10-12). The 2018 round: "$4 Million to
  Help Brands Make Custom Knits on Demand" (WWD, 2018-08-13, headline).
  **Verdict: not defunct — pivoted from consumer on-demand knitwear to B2B
  SaaS.** The consumer-service economics are the cautionary tale, not the
  company's existence.

### 2.4 Machine-independent / compiler framing — the crux

Has anyone framed garments as an IR + multi-backend compilation problem?

**Yes.** knitout's spec sentence is literally "low-level knitting
instructions in a machine-independent way"
(https://github.com/textiles-lab/knitout), McCann 2016 compiled a high-level
language through an IR to multiple machine backends including SHIMA SEIKI
hardware (https://doi.org/10.1145/2897824.2925940), and the 2023/2025
follow-ups formalized semantics and program equivalence for that stack.
Google Patents full-text queries for `knitting "intermediate representation"`
and `machine-independent knitting representation` return no direct hits —
the hits returned are unrelated (network chirp patents, footwear knitted
components) — i.e., **the IR framing exists in the academic literature, not
in the patent literature we could reach.** The patent gap is real but the
academic prior art is a decade deep and formally mature.

What the reviewed corpus does *not* contain anywhere (checked across the
compiler line, the stitch-mesh line, MIT's tool line, and vendor material):

- a **declared joint taxonomy** (topology type × construction method ×
  anchor) with a mechanically checkable legality matrix;
- **boundary disposition** as a hard invariant (every knit-bearing rim ends
  in exactly one terminal state: consumed / fabric_start / declared_open —
  UGP's I-SEAL, "a disk is a render cap, not a knit closure");
- **machine-independent numeric feasibility invariants** (rim-length match,
  loop-count correspondence, radius/axis continuity, branch orientation)
  stated in mm/deg/loops and checked *before* any lowering;
- a **per-backend verification honesty contract** (CHECKS / UNVERIFIED per
  invariant class, serialized with the artifact).

---

## 3. Verdict

**Is the compiler/IR framing novel? No — and pitching it as such would die in
diligence.** McCann et al. (2016) + knitout (2017) already implement
"garment/shape description → intermediate representation → per-machine
backends," and the CMU/Utah/Washington line has since added formal semantics
(2023) and polynomial-time program equivalence (2025). "The first garment IR"
or "we compile garments like LLVM compiles programs" are indefensible
claims: the former is factually wrong (knitout), the latter an analogy the
2023 paper already made rigorous.

**What is actually open — and what UGP should claim:** nobody in the reviewed
corpus models the *garment as an assembly of parts with knit-legal joins*.
The compiler line works below garment level (stitches, courses, transfers);
the stitch-mesh line works at yarn/stitch correspondence; MIT's Skeletons
composes panels but without a legality algebra; the CAD vendors have no knit
semantics at all; the vendors that do (SHIMA) keep validation proprietary
inside their vertical stack. UGP's specific combination — (1) joint type ×
construction method × anchor taxonomy with a mechanical legality matrix,
(2) boundary-disposition/sealing invariants (I-SEAL), (3) machine-independent
numeric tolerances in mm/deg/loops checked before lowering, (4) per-backend
CHECKS/UNVERIFIED honesty contract with non-claims — **appears original in
the reviewed literature.** Closest single prior art: **Knitting Skeletons
(2019)** for primitive composition, **knitout/McCann 2016** for the IR
framing, **Stoll/KnitPaint "difficult-to-knit area detection"** for
vendor-side validation. The delta is the *validation algebra at garment
level + the honesty contract + cross-machine positioning*.

**Positioning that survives:** UGP is not "a compiler" and not "an IR" — it
is the **machine-independent validation & interop layer** that sits *above*
design tools and *in front of* lowering targets (knitout can literally be a
lowering target; SHIMA/Stoll stacks are the closed incumbents to route
around). DESIGN.md §9 already disclaims compatibility with industrial
machines — keep that framing; it is both honest and legally safer.

---

## 4. Market data points (every number with a source)

| data point | value | source |
|---|---|---|
| Seamless apparel market | $69.7B (2026) → $142.2B (2036), 7.4% CAGR; sports bras 34.6% of product mix | https://www.futuremarketinsights.com/reports/seamless-apparel-market (report page, dated 2026-01-22; fetched 2026-10-12) |
| WHOLEGARMENT patent estate | 2,900+ patents/pending worldwide, hardware + software + stitch structures | https://www.knittingindustry.com/2900-reasons-to-choose-wholegarment-technology/ (Shima corporate communications interview, 2025-03-18) |
| WHOLEGARMENT age | introduced 1995; 30 years in market (2025) | same Knitting Industry interview |
| Kniterate machine price | $15,999 (gauge 7, 504 needles, 6 feeders) | https://www.kniterate.com/product/digital-knitting-machine/ (fetched 2026-10-12) |
| Industrial knit-and-wear package cost | $125,605 = STOLL ADF 530-16ki B machine + design software (univ. grant line item, 2023) | https://www.uri.edu/news/2023/01/champlin-foundation-grant-funds-state-of-the-art-knitting-machine/ |
| Flagship WHOLEGARMENT machine price | **no public figure found** — do not quote a number | (absence verified 2026-10-12) |
| Stoll consolidation | Reutlingen production closed 2025-10-31; selected assets (brand, inventory, tech) transferring to Ningbo Cixing (announced Jun 2026) | https://www.stoll.com/en/ (notice, fetched 2026-10-12); https://www.knittingindustry.com/karl-mayer-confirms-closure-of-stoll-reutlingen-site/ (2025-10-21); Cixing acquisition: Knitting Industry + Knitting Trade Journal headlines 2026-06-17 |
| On-demand knit operator (live) | Tailored Industry: zero-minimum WHOLEGARMENT production, boutique pricing tiers | https://tailoredindustry.com/ (fetched 2026-10-12) |
| On-demand consumer knit caution | Unmade raised $4M (2018, headline) to scale custom knits; consumer service gone by ~2019–2020s; company active but pivoted to UnmadeOS SaaS | WWD headline via Google News RSS (2018-08-13); https://find-and-update.company-information.service.gov.uk/company/08498078 ; https://unmade.com/ |
| Academic attention to machine knitting | compiler paper 165 cites (2016); stitch-meshes 172 (2012); yarn-level sim 212 (2008); KnitUI 101 (2021) — sustained growth | OpenAlex citation counts, 2026-10-12 (per-DOI links in §2.2) |

Market-size hygiene: the Grand View Research "seamless apparel" page
returned "under development" during this review and Fortune Business
Insights is Cloudflare-walled; the FMI figure above is the one market-size
number that resolved to a readable, dated page. Report-level numbers beyond
FMI's are **not** quoted here on purpose.

---

## 5. Patent risk scan (what would block or shape a filing)

1. **SHIMA SEIKI: 2,900+ patents across hardware, programming software, and
   stitch structures** (source in §4). Any claim touching *how* whole-garment
   fabric is realized (needlebed tricks, slide-needle techniques, stitch
   formation) collides. UGP's validation/spec layer describes *checks over
   graph structure*, not machine techniques — lower exposure, but an FTO
   (freedom-to-operate) review by a patent attorney is mandatory before any
   filing; the founder's own brief already says the same.
2. **Artlink International family (US9695529B2 / CN111291431B /
   HK40021903, priority 2015-04-21)** — 3D form → fully-fashioned knitted
   pattern generation. This is the closest *patent* family to UGP's
   pipeline found in this review. Full text was not readable here (Google
   bot-wall): **must be read manually before filing.** Flagged.
3. **Nike knitted-component patents** (e.g. CN118345552B, CN117957345A,
   priority 2021-10-22, footwear uppers, surfaced in the patent scan).
   Footwear-adjacent claims are a dense thicket — keep UGP claims away from
   footwear manufacturing methods.
4. **Published prior art kills the obvious claims.** "Machine-independent
   knit representation" (knitout, 2017, public spec), "compiler from garment
   description to machine instructions" (McCann 2016, public paper),
   "automatic 3D shape → knittable structure" (Wu 2018/2019) are all
   §102-style public disclosures predating UGP. A filing shaped around any
   of those is dead on arrival.
5. **knitout has no LICENSE file** (GitHub license API 404, checked
   2026-10-12): the spec is public but formally all-rights-reserved.
   Interop/lowering targets are normal practice, but UGP cannot copy or
   relicense its text, and should not claim the format.
6. **Trademark note:** WHOLEGARMENT is a registered trademark with enforced
   terms of use (Shima policing generification — interview §2.1). UGP's
   DESIGN.md already avoids the term for `default_knit`; keep it that way
   in all pitch material.

---

## 6. Three strongest defensibility angles for the pitch

1. **Reject-first, garment-level validation.** Every reviewed system either
   compiles below garment level (knitout, McCann, Lin), guarantees stitch
   knittability without assembly semantics (stitch meshes), or hides
   validation inside a closed vertical stack (SHIMA KnitPaint). UGP's
   legality matrix + I-SEAL + mm/deg/loops tolerances make invalid garments
   *mechanically unrepresentable* before any machine sees them — that layer
   does not exist anywhere else we looked.
2. **The honesty contract as a wedge into a closed market.** Per-backend
   CHECKS/UNVERIFIED declarations, serialized non-claims, and validity-never-
   implies-knittability are an auditability norm no vendor or academic demo
   offers — and the market moment is right: the incumbent knit-and-wear
   brand (Stoll) just exited under Karl Mayer to Cixing, SHIMA's stack is
   patent-walled and closed, and the one open IR (knitout) is instruction-
   level and unlicensed. The seam between design intent and machine ops is
   unowned.
3. **Benchmarked, machine-independent claims instead of vendor promises.**
   Pairing the validation layer with a public benchmark (which garments a
   backend can/cannot build, per invariant class) is a differentiation no
   reviewed competitor offers — vendors demo, they don't publish
   falsifiable coverage tables. This is a process moat, not a patent moat —
   and it compounds with the compiler literature instead of fighting it
   (cite McCann 2016 and knitout as foundations, claim the validation layer
   above them).

**What would kill the moat (say this internally, not on stage):** Shima
shipping garment-level validation in APEXFiz cloud, or the CMU Textiles Lab
extending knitout upward with an assembly/geometry layer. Both are plausible;
UGP's window is execution speed on validation + benchmark + interop
contracts.
