"""Spec v3 invariants — I-chi / I-ORIENT / I-REACH / I-GAUGE-CLOSURE (C2).

RED contract for cycle 2 (DESIGN_V3_TOPOLOGY.md):

- I-chi        Euler closure: sum over patches of (2 - k) must equal the
               declared chi = 2 - 2g - n_free (n_free = free rims: rims
               in no junction). g > 0 is a reserved error in v3.
- I-ORIENT     every junction's identified pairs must alternate traversal
               directions (construction already rejects; the validator
               catches post-construction mutation) and both named
               boundaries must exist on their patches.
- I-REACH      every patch must be reachable from the cast-on patch via
               the junction graph (connectivity of the identification
               graph catches floating/unattached patches).
- I-GAUGE-CLOSURE  every junction member rim's loop count must agree
               across the junction beyond T_LOOPS (generalizes v2's
               pairwise T_LOOPS to junctions of arbitrary arity);
               UNVERIFIED without a gauge, like v2 I-LOOP.

Determinism contract unchanged: validate() twice on a broken graph
agrees byte-for-byte (sorted, content-keyed findings).
"""
import unittest

from ugc.primitives import (Boundary, INARIANT_CLASSES, Junction, Patch,
                            UGPGraph, validate)


def _rim(bid, length_mm, center=(0.0, 0.0, 0.0), normal=(0.0, 1.0, 0.0)):
    return Boundary(bid, "rim", length_mm, frame=(center, normal))


def _pair_junction(jid, a, b, ca="cw", cb="ccw"):
    return Junction(jid, [(a[0], a[1], ca), (b[0], b[1], cb)])


def _shirt(gauge=None, chi=None, mangle=None):
    """k=4 torso + two k=2 sleeves, armholes junctioned. chi = 0 with
    2 free rims (neck, cuffs) — a valid v3 shirt body."""
    g = UGPGraph(gauge=gauge)
    g.add_patch(Patch("torso", [_rim("hem", 700), _rim("neck", 660),
                                _rim("armhole_l", 330),
                                _rim("armhole_r", 330)]))
    g.add_patch(Patch("sleeve_l", [_rim("armhole", 330), _rim("cuff_l", 300)]))
    g.add_patch(Patch("sleeve_r", [_rim("armhole", 330), _rim("cuff_r", 300)]))
    g.add_junction(_pair_junction("j_l", ("torso", "armhole_l"),
                                  ("sleeve_l", "armhole")))
    g.add_junction(_pair_junction("j_r", ("torso", "armhole_r"),
                                  ("sleeve_r", "armhole")))
    if chi is not None:
        g.declared_chi = chi
    if mangle:
        mangle(g)
    return g


class TestCatalogSurface(unittest.TestCase):
    def test_new_classes_are_in_the_catalog(self):
        for name in ("I-CHI", "I-ORIENT", "I-REACH", "I-GAUGE-CLOSURE"):
            self.assertIn(name, INARIANT_CLASSES)

    def test_validate_runs_every_class_once(self):
        findings = validate(_shirt())
        by_class = [f.invariant for f in findings]
        for name in INARIANT_CLASSES:
            self.assertEqual(by_class.count(name), 1, name)


class TestIChi(unittest.TestCase):
    def test_valid_shirt_passes(self):
        f = {x.invariant: x.status for x in validate(_shirt())}
        self.assertEqual(f["I-CHI"], "PASS")

    def test_wrong_declared_chi_fails_with_expected_actual(self):
        g = _shirt(chi=3)
        f = [x for x in validate(g) if x.invariant == "I-CHI"]
        self.assertEqual(f[0].status, "FAIL")
        self.assertIn("expected 3", f[0].message)
        self.assertIn("actual 0", f[0].message)

    def test_mutation_breaking_chi_is_caught(self):
        # sneaky post-construction edit: a span deleted from a patch
        def mangle(g):
            p = g.patch("sleeve_l")
            p.spans = (p.span("armhole"),)
        g = _shirt(mangle=mangle)
        f = {x.invariant: x.status for x in validate(g)}
        self.assertEqual(f["I-CHI"], "FAIL")

    def test_genus_gt_zero_is_reserved(self):
        # pair-of-pants: chi = -1 -> g=1 territory; v3 reserves g>0
        g = UGPGraph()
        g.add_patch(Patch("hips", [_rim("waist", 700), _rim("leg_l", 365),
                                   _rim("leg_r", 365)]))
        g.declared_chi = -1
        f = [x for x in validate(g) if x.invariant == "I-CHI"]
        self.assertEqual(f[0].status, "FAIL")
        self.assertIn("reserved", f[0].message)

    def test_default_declared_chi_matches_open_v2_style_graphs(self):
        # declared_chi defaults to 2 - n_free (genus 0): the shirt's
        # 2 free rims -> 0, consistent with its actual sum.
        g = _shirt()
        self.assertEqual(g.declared_chi, 0)


class TestIOrient(unittest.TestCase):
    def test_valid_shirt_passes(self):
        f = {x.invariant: x.status for x in validate(_shirt())}
        self.assertEqual(f["I-ORIENT"], "PASS")

    def test_mutated_direction_pair_fails(self):
        def mangle(g):
            # break the alternation post-construction
            j = g._junctions[0]
            j.members = ((j.members[0][0], j.members[0][1], "cw"),
                         (j.members[1][0], j.members[1][1], "cw"))
        g = _shirt(mangle=mangle)
        f = [x for x in validate(g) if x.invariant == "I-ORIENT"]
        self.assertEqual(f[0].status, "FAIL")
        self.assertIn("j_l", f[0].message)

    def test_non_orientable_k2_pair_is_reserved_like_genus(self):
        # a single junction flipping orientation on a closed k1/k1 pair
        # would glue a Mobius band: the manifold would be
        # non-orientable. v3 refuses it via the alternation rule.
        g = UGPGraph()
        g.add_patch(Patch("a", [_rim("rim", 10)]))
        g.add_patch(Patch("b", [_rim("rim", 10)]))
        j = Junction("j", [("a", "rim", "cw"), ("b", "rim", "ccw")])
        j.members = (("a", "rim", "cw"), ("b", "rim", "cw"))
        g.add_junction(j)
        f = [x for x in validate(g) if x.invariant == "I-ORIENT"]
        self.assertEqual(f[0].status, "FAIL")


class TestIReach(unittest.TestCase):
    def test_valid_shirt_passes(self):
        f = {x.invariant: x.status for x in validate(_shirt())}
        self.assertEqual(f["I-REACH"], "PASS")

    def test_floating_patch_fails(self):
        def mangle(g):
            g.add_patch(Patch("ghost", [_rim("rim", 100)]))
        g = _shirt(mangle=mangle)
        f = [x for x in validate(g) if x.invariant == "I-REACH"]
        self.assertEqual(f[0].status, "FAIL")
        self.assertIn("ghost", f[0].message)

    def test_two_disjoint_components_named(self):
        def mangle(g):
            # detach the right sleeve entirely: it becomes its own
            # component; both components reported
            g._junctions = [j for j in g._junctions if j.id != "j_r"]
            g._rim_claim = {k: v for k, v in g._rim_claim.items()
                            if v != "j_r"}
        g = _shirt(mangle=mangle)
        f = [x for x in validate(g) if x.invariant == "I-REACH"]
        self.assertEqual(f[0].status, "FAIL")
        self.assertIn("sleeve_r", f[0].message)

    def test_determinism_two_runs_agree_byte_for_byte(self):
        g = _shirt(mangle=lambda g: g.add_patch(
            Patch("ghost", [_rim("rim", 100)])))
        a = "\n".join(repr(x) for x in validate(g))
        b = "\n".join(repr(x) for x in validate(g))
        self.assertEqual(a, b)


class TestIGaugeClosure(unittest.TestCase):
    def test_no_gauge_is_unverified(self):
        f = {x.invariant: x.status for x in validate(_shirt())}
        self.assertEqual(f["I-GAUGE-CLOSURE"], "UNVERIFIED")

    def test_matching_loops_pass(self):
        g = _shirt(gauge={"wale_mm": 2.5, "course_mm": 1.6})
        f = {x.invariant: x.status for x in validate(g)}
        self.assertEqual(f["I-GAUGE-CLOSURE"], "PASS")

    def test_mismatched_loops_fail_beyond_t_loops(self):
        def mangle(g):
            # widen the left cuff: 300 mm vs 330 mm armhole —
            # delta 30 loops at wale 2.5 exceeds T_LOOPS=2
            g.patch("sleeve_l").span("cuff_l").length_mm = 400.0
        g = _shirt(gauge={"wale_mm": 2.5, "course_mm": 1.6},
                   mangle=mangle)
        f = [x for x in validate(g) if x.invariant == "I-GAUGE-CLOSURE"]
        self.assertEqual(f[0].status, "FAIL")
        self.assertIn("j_l", f[0].message)

    def test_arity4_junction_all_members_checked(self):
        g = UGPGraph(gauge={"wale_mm": 2.5, "course_mm": 1.6})
        g.add_patch(Patch("web", [_rim("w1", 300), _rim("w2", 300),
                                  _rim("w3", 300), _rim("w4", 300)]))
        g.add_patch(Patch("p2", [_rim("a", 300), _rim("b", 300)]))
        g.add_patch(Patch("p3", [_rim("a", 300), _rim("b", 300)]))
        g.add_junction(Junction("j4", [("web", "w1", "cw"),
                                       ("p2", "a", "ccw"),
                                       ("web", "w2", "cw"),
                                       ("p3", "a", "ccw")]))
        f = {x.invariant: x.status for x in validate(g)}
        self.assertEqual(f["I-GAUGE-CLOSURE"], "PASS")


if __name__ == "__main__":
    unittest.main()
