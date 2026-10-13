"""Spec v3 family re-expression — Patch/Junction on the U-01 families (C3).

RED contract for cycle 3 (DESIGN_V3_TOPOLOGY.md): every garment family
builds its v2 primitives/joints/ops AND an additive v3 patch/junction
layer re-expressing the true surface topology.

Per-family topology (hardcoded expectations — genus 0, chi = sum(2-k)):

  family     patches  junctions  free rims  chi   note
  hat        2        1          1          1    dome k=1 + body k=2
  sock       3        2          1          1    leg+foot k=2, toe k=1
  glove      2        1          1          1    fingers stay render-only
  skirt      1        0          2          0    single open tube
  dress      2        1          2          0    waist junction
  trousers   3        2          3         -1    hips k=3 WEB (pair of
                                             pants): the v2 "crotch
                                             opening" was a branch
                                             artifact, v3 drops it
  shorts     3        2          3         -1    same shape, short legs
  shirt      3        2          4         -2    torso k=4 web + sleeves
  hoodie     4        3          3         -1    shirt + hood k=1

The v3 layer is additive: v2 payloads (primitives/joints/ops/
open_boundaries) are untouched, version stays 2.
"""
import unittest

from ugc.garments import build_garment
from ugc.primitives import validate

TOPO = {
    # family: (n_patches, n_junctions, n_free_rims, chi)
    "hat":      (2, 1, 1, 1),
    "sock":     (3, 2, 1, 1),
    "glove":    (2, 1, 1, 1),
    "skirt":    (1, 0, 2, 0),
    "dress":    (2, 1, 2, 0),
    "trousers": (3, 2, 3, -1),
    "shorts":   (3, 2, 3, -1),
    "shirt":    (3, 2, 4, -2),
    "hoodie":   (4, 3, 3, -1),
}


def _v3_findings(g):
    keep = ("I-CHI", "I-ORIENT", "I-REACH", "I-GAUGE-CLOSURE")
    return [f for f in validate(g) if f.invariant in keep]


class TestFamilyTopology(unittest.TestCase):
    def test_every_family_carries_the_v3_layer(self):
        for fam, (np, nj, _nf, _chi) in TOPO.items():
            g = build_garment(fam)
            self.assertEqual(len(g.patches()), np, fam)
            self.assertEqual(len(g.junctions()), nj, fam)
            self.assertIsNotNone(g.declared_chi, fam)

    def test_declared_chi_matches_true_surface_topology(self):
        for fam, (_np, _nj, _nf, chi) in TOPO.items():
            g = build_garment(fam)
            self.assertEqual(g.declared_chi, chi, fam)

    def test_every_family_passes_the_four_v3_invariants(self):
        for fam in TOPO:
            g = build_garment(fam)
            fails = [f for f in _v3_findings(g) if f.status == "FAIL"]
            self.assertEqual(fails, [], fam)

    def test_gauge_closure_unverified_without_gauge(self):
        for fam in TOPO:
            f = {x.invariant: x.status for x in _v3_findings(build_garment(fam))}
            self.assertEqual(f["I-GAUGE-CLOSURE"], "UNVERIFIED", fam)

    def test_free_rim_count(self):
        for fam, (_np, _nj, nf, _chi) in TOPO.items():
            g = build_garment(fam)
            claimed = set()
            for j in g.junctions():
                for patch_id, boundary_id, _ in j.members:
                    claimed.add((patch_id, boundary_id))
            free = [b.boundary for p in g.patches() for b in p.spans
                    if (p.id, b.boundary) not in claimed]
            self.assertEqual(len(free), nf, (fam, free))

    def test_trousers_hips_is_a_k3_web_not_a_tube_with_open_crotch(self):
        # the true pair-of-pants surface has exactly three boundary
        # curves (waist + two leg openings); the v2 builder's "crotch
        # opening" was an artifact of expressing legs as side branches.
        g = build_garment("trousers")
        hips = g.patch("trousers_hips")
        self.assertEqual(hips.k, 3)
        leg_tops = {(p, b) for j in g.junctions()
                    for p, b, _ in j.members}
        self.assertIn(("trousers_hips", "leg_l_top"), leg_tops)
        self.assertIn(("trousers_hips", "leg_r_top"), leg_tops)

    def test_shirt_torso_is_a_k4_web_with_synthetic_armholes(self):
        g = build_garment("shirt")
        torso = g.patch("shirt_torso")
        self.assertEqual(torso.k, 4)
        spans = {b.boundary for b in torso.spans}
        self.assertEqual(spans,
                         {"hem", "neck", "armhole_l", "armhole_r"})

    def test_junction_loops_close_at_gauge(self):
        # junction member rims carry matching loop counts (v2 rims were
        # already I-RIMMATCH-clean; synthetic armholes/leg-tops are cut
        # to the child pick-up radius), so with a gauge the generalized
        # T_LOOPS closure must hold for every family
        for fam in TOPO:
            g = build_garment(fam)
            g.gauge = {"wale_mm": 2.5, "course_mm": 1.6}
            f = {x.invariant: x.status for x in _v3_findings(g)}
            self.assertEqual(f["I-GAUGE-CLOSURE"], "PASS", fam)

    def test_v2_payload_untouched_by_reexpression(self):
        # additive: primitives/joints/ops/open_boundaries identical to
        # the v2-only contract (op verbs + joint types per family)
        verbs = {
            "hat": {"cast_on", "graft"},
            "sock": {"cast_on", "pick_up", "graft"},
            "glove": {"cast_on", "graft"},
            "skirt": {"cast_on"},
            "dress": {"cast_on", "pick_up"},
            "trousers": {"cast_on"},
            "shorts": {"cast_on"},
            "shirt": {"cast_on"},
            "hoodie": {"cast_on", "graft"},
        }
        for fam, expected in verbs.items():
            g = build_garment(fam)
            self.assertEqual({o.op for o in g.ops}, expected, fam)

    def test_json_roundtrip_preserves_family_topology(self):
        for fam in TOPO:
            g = build_garment(fam)
            d = g.to_dict()
            self.assertEqual(d["version"], 2, fam)
            from ugc.primitives import UGPGraph
            g2 = UGPGraph.from_dict(d)
            self.assertEqual([p.id for p in g2.patches()],
                             [p.id for p in g.patches()], fam)
            self.assertEqual([j.id for j in g2.junctions()],
                             [j.id for j in g.junctions()], fam)
            self.assertEqual(g2.declared_chi, g.declared_chi, fam)

    def test_glove_fingers_stay_out_of_the_v3_layer(self):
        # render-only disks are not surfaces between rims; they stay
        # v2 render primitives and never become patches
        g = build_garment("glove")
        self.assertEqual({p.id for p in g.patches()},
                         {"glove_wrist", "glove_palm"})


if __name__ == "__main__":
    unittest.main()
