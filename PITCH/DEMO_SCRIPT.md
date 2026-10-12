# UGP — investor demo script (25 min, live terminal)

Companion to DECK.md (slide refs in brackets). Every command in this file was
run against the repo before it was written here; the outputs shown are what
the commands actually print. Determinism is the product — the demo cannot
drift, because the outputs are byte-stable (beat 4 proves it).

Date: 2026-10-12. Repo state: commit `f20b799` (results c2), 287 tests green.

---

## 0. Pre-flight (10 min before the room)

```bash
cd /Users/ahmedm/Developer/Projects/hedron
python3 -m unittest discover -s tests -t .     # → "Ran 287 tests ... OK" (~3s)
python3 PITCH/verify.py                        # → "all traced", ask sums $250k OK
```

- Terminal font ≥ 16pt, one window, clean scrollback (`clear`).
- Second window/tab: `python3 -m ugc.cli serve --port 8765` then open
  `http://127.0.0.1:8765/viewer/index.html` in the browser. Leave it on hat.
- Terminal colors on: PASS/UNVERIFIED green/amber reads from the back row.
- If the room has no projector confidence: everything below also works over
  screen-share; the viewer is the only GPU-dependent piece (WebGL).

## The spine (say it once, up front)

> "Design tools draw garments. Knitting machines need instructions. Nothing
> between them checks whether the garment can be built at all. UGP is that
> check — a spec, a validator, and a benchmark. I'll build a sock, break a
> sock, and show you why both demos are the business." [S1→S2]

---

## Beat 1 — the artifact (min 2–6) [S3, S5]

```bash
python3 -m ugc.cli families
```
```
ugc garment families (9):
  dress / glove / hat / hoodie / shirt / shorts / skirt / sock / trousers
```

```bash
python3 -m ugc.cli plan sock
```
```
plan: sock -> backend default_knit
reference machine ops: CAST_ON, PICK_UP, KNIT, GRAFT
program (3 ops):
  sock_cast_on       cast_on  -> CAST_ON       produces sock_leg/rim_start
  sock_foot_pick_up  pick_up  -> PICK_UP+KNIT  consumes sock_leg/rim_end ...
  sock_toe_graft     graft    -> GRAFT         consumes sock_foot/rim_end ...
pieces: 3  joints: 2  open boundaries: none
verdict: UNSIMULATED
note: I-LOOP UNVERIFIED: no gauge on graph — loop correspondence was not checked
```

Say: nine garment families, each ~27 lines of *configuration* on top of one
shared representation (2,295 shared lines vs 343 per-family — 7.93:1, the
number is emitted by `benchmark/loc_accounting.py`, not hand-typed). The
program is the machine plan: cast on the leg, pick up stitches for the foot,
graft the toe. Four distinct verbs across all nine families.

Point at the last two lines: **"UNSIMULATED is a feature.** The graph has no
gauge data, so loop correspondence was *not checked* — and the artifact says
so instead of pretending. Every claim a backend fails to verify is labeled.
That honesty contract is serialized with the output; it is not a slide." [S3]

```bash
python3 -m ugc.cli report sock
```
```
geometric_validity: PASS
  I-DEGENERATE PASS  I-SCHEMA PASS  I-AXIS PASS  I-GRAPH PASS
  I-ANCHOR PASS  I-RIMMATCH PASS  I-CONT PASS  I-BRANCHORIENT PASS
  I-SEAL PASS  I-JOINT PASS
  I-LOOP UNVERIFIED
```

Say: eleven invariant classes, each pass/fail in millimeters, degrees, loop
counts. "And note what PASS means — and *only* what it means: geometric
validity never implies knitability. That sentence is in the spec, in the
report note, and in our design doc. We refuse the lie every CAD demo makes."

## Beat 2 — break the sock (min 6–10) [S3, S7 — the money moment]

> "Now the demo the incumbents can't run. Watch what happens when the design
> is *wrong*."

```bash
python3 - <<'PY'
import json
g = json.load(open('out/sock.json'))['graph']
foot = [p for p in g['primitives'] if p['id']=='sock_foot'][0]
foot['params']['r1'] = 40.0   # leg ends at r2 = 50mm — the joint no longer matches
json.dump(g, open('/tmp/sock_broken.json','w'), sort_keys=True)
d = json.load(open('out/sock.json'))['graph']
leg = [p for p in d['primitives'] if p['id']=='sock_leg'][0]
leg['params']['r1'] = -5.0    # degenerate: negative radius
json.dump(d, open('/tmp/sock_degen.json','w'), sort_keys=True)
PY
python3 -m ugc.cli validate --graph /tmp/sock_broken.json; echo "exit=$?"
```
```
{
  "errors": [
    { "code": "I-CONT", "kind": "radius_step",
      "message": "radius step 10.000 mm exceeds T_RIM=1.000",
      "ids": ["sock_j_heel"], "expected": 1.0, "actual": 10.0 },
    { "code": "I-RIMMATCH", "kind": "rim_length_mismatch",
      "message": "rim lengths differ by 62.832 mm (T_RIM=1.000)",
      "ids": ["sock_j_heel"], "expected": 1.0, "actual": 62.832 } ],
  "fatal": false, ...
}
exit=1
```

```bash
python3 -m ugc.cli plan --graph /tmp/sock_broken.json; echo "exit=$?"
```
Same error envelope, `exit=1` — **no machine program is emitted.**

Say: "A 10mm radius step at the heel — invisible in a 3D render, expensive on
a $15,999 studio machine and worse on a $125,605 industrial package. The
validator catches it with exact numbers and refuses to lower. Invalid garments
are mechanically unrepresentable. CLO3D will happily drape this sock. The
machine will eat it. We are the only layer in this demo that says no — and
says it in millimeters." [S2 numbers]

Degenerates die at the door too:
```bash
python3 -m ugc.cli validate --graph /tmp/sock_degen.json; echo "exit=$?"
# (the graph with a negative radius)
ugc: error: unsupported graph in /tmp/sock_degen.json: tube.r1 must be > 0 mm, got -5.0
exit=2
```

## Beat 3 — the honesty contract + falsifiability (min 10–14) [S3, S8]

```bash
python3 -m benchmark.benchmark /tmp/report_regen.json
shasum benchmark/report.json /tmp/report_regen.json
```
Both lines print the **same sha256**. Then:

```bash
python3 -c "import json;d=json.load(open('benchmark/report.json'));print(d['machine_verdict_counts'])"
# {'default_knit': {'UNSIMULATED': 9}, 'default_sim': {'UNSIMULATED': 9}}
```

Say: "Two backends × nine families, every verdict UNSIMULATED because there is
no gauge data yet — the ledger refuses to fabricate stitch counts. The report
regenerates **byte-identical** — canonical JSON, insertion-order independent,
pinned by tests. That's what makes our benchmark *falsifiable*: when we
publish which garments a backend can build per invariant class, anyone can
rerun the table and get the same bytes. Vendors demo. We publish tables
anyone can recompute. Funding converts this from a repo doc into a public
standard with real machines behind it." [S5 benchmark v1]

## Beat 4 — see it (min 14–17) [S5]

Browser tab (pre-opened): the viewer. Click through hat → sock → glove →
hoodie. Left rail shows all nine families with piece counts (glove is 7
pieces); the canvas is the actual spec graph — primitives, joints, open
boundaries — with per-invariant pass/unverified colors.

Say: "Same JSON the validator ate. Design tools integrate this view; this
page is the integration spec, running."

## Beat 5 — state and traction (min 17–20) [S9]

```bash
python3 -m unittest discover -s tests -t .   # 287 tests, OK, ~3s
```

- 287 tests green, **92 of them are must-reject tests** — the validator's
  negative space is covered, not just its happy path (counted
  programmatically by `benchmark/loc_accounting.py`).
- Shipped: spec v2, nine-family reference builders, the validator, the
  lowering contract, the benchmark harness, the viewer, a pipeline CLI.
- Results live in `benchmark/RESULTS.md` — "measured, not asserted," every
  number reproducible from the file's own commands.
- Non-dilutive calendar is real and scheduled: Accelerate UConn deadline
  Oct 19 (1 week out), CCEI Summer Accelerator $15k (Feb 17), IQ, Get Seeded,
  Wolff, I-Corps. [S9 table]

## Beat 6 — the ask (min 20–25) [S10]

> "$250,000 pre-seed on a SAFE, 12-month runway: ~$150k founder + contract
> engineering, ~$40k machine time and CI for the coverage tables, ~$30k FTO/
> IP counsel — the prior-art review makes that pass mandatory — ~$15k travel,
> ~$15k buffer. Milestones: benchmark v1 public with three lowering targets,
> a 20-interview discovery log, one design-tool pilot signed. First money in
> is non-dilutive and already scheduled. This round buys the window between
> spec-done and standard-set."

Close on the leave-behind: SOURCES.md — every number has a URL and a fetch
date; the two things we could not verify are flagged, not hidden. "That habit
is the product in miniature."

---

## 60-second version (booth / elevator)

```bash
python3 -m ugc.cli plan sock && python3 -m ugc.cli validate --graph /tmp/sock_broken.json
```
> "Nine garment families lower to a 4-verb machine program through one shared
> representation. Break the design — 10mm radius step at the heel — and the
> validator refuses with the exact millimeters. Every unverifiable claim is
> labeled UNVERIFIED, every report regenerates byte-identical. The seam
> between design intent and machine ops is unowned; we own the check."

## Q&A ammo (deck- and prior-art-grounded)

- **"Isn't knitout this?"** No — and it's a foundation, not a competitor.
  knitout is instruction-level, machine-independent, and public (CMU,
  2017–): no garment geometry, no join semantics, no design-level
  feasibility. We position *above* it; it's a lowering target. McCann 2016
  + knitout are cited on the competition slide on purpose — pre-empting
  diligence is the strategy. [S7]
- **"Why won't SHIMA add this?"** They monetize the stack, not interop;
  2,900+ patents and a closed APEX/APEXFiz chain. Publishing falsifiable
  coverage tables contradicts their sales motion. The real risk is CMU
  extending knitout upward — hence execution speed. [S4]
- **"What does UNVERIFIED actually mean?"** The invariant class was not
  checked for this artifact (e.g. I-LOOP needs gauge data) and the label
  travels with the output. A backend that re-checks a class declares CHECKS;
  one that trusts upstream declares UNVERIFIED. Non-claims are serialized.
- **"TAM?"** We don't claim the $69.7B seamless-apparel number; we claim the
  check every participant will need, priced like validation/CI
  infrastructure. [S6]
- **"Patents?"** SHIMA's estate means any claim touching *machine technique*
  collides; our claims live on graph-level checks. FTO review is a budgeted
  line item (~$30k). The Artlink family (US9695529B2) is the closest patent
  relative and must be read in full before filing — it's flagged in
  PRIOR_ART §5, not hidden.
- **"What's not done?"** (Volunteer it — it buys credibility.) No gauge data
  yet, so every I-LOOP is honestly UNVERIFIED; surface_branch garments
  (glove fingers, sleeves, legs) are documented unsupported in v2; only
  in-repo backends have been lowered; benchmark v1 is one backend family ×
  nine garments today. RESULTS.md "known-open" section lists all of it.
- **"Why is a founder without a knit factory credible?"** We're not selling
  machine time — we're the layer *in front of* machines, cite the compiler
  literature as foundations, and the open lane exists because both closed
  vendors have no incentive and the academic line stopped below garment
  level.

## Do-not-say list (prior-art hard rules)

- Never "the first garment IR" — a machine-independent knit representation
  has existed since knitout (2017); the claim dies in diligence. We are the
  validation/interop layer **above** it.
- Never "we compile garments like LLVM" — the 2023 semantics paper already
  made that rigorous; we're not a compiler.
- Never claim WHOLEGARMENT or industrial-machine compatibility — DESIGN §9
  disclaims it; the trademark is policed; `default_knit` is a neutral
  reference target, not a vendor format.
- Never quote a flagship WHOLEGARMENT machine price — no public figure
  exists (verified absence); use the $125,605 Stoll package and $15,999
  Kniterate instead.
- Never show I-LOOP as PASS — there is no gauge data. The honesty contract
  is the pitch; violating it on stage is fatal.

## If something fails live

- Any command errors that shouldn't: it's deterministic software — say
  "environment issue, not the product," rerun the 60-second version (it has
  no dependencies beyond stdlib Python 3.9+), and go to the viewer.
- Viewer blank/GPU fail: the JSON is the artifact — open `out/sock.json`
  raw and walk the structure; the viewer is a convenience, not the product.
- Asked for something unpublished: "that's in the known-open list — next
  milestone is the funding ask." Never improvise a number.
