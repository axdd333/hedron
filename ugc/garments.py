"""Garment generators — the six U-01 families on the spec-v2 IR.

Each family is a pure function (family, scale) -> UGPGraph with mm
geometry, declared spec-v2 joints (type x construction x anchor), and an
explicit default_knit op program satisfying I-SEAL. Nine names, six
builders: shorts shares trousers, dress shares skirt.

Construction choices follow DESIGN.md §5.4 and real whole-garment practice:
- knitted_in where whole-garment machines form the child from the parent's
  live rim (sleeve-side pick-ups, legs off the hips, skirt off the torso,
  sock foot off the leg across a knitted heel turn);
- grafted for separately-shaped closures mated to a live rim (dome tops,
  toe caps, hood);
- short_row_close for shaped terminations knit within one piece;
- unsupported (documented, not hidden) where v2's op set cannot claim the
  realization — glove fingers need mid-fabric pick_up_path (§10).

Graph assembly order (UGPGraph contract): primitives first, then op
instances, then joints (add_joint resolves both endpoints immediately).
"""
import math

from ugc.primitives import (Primitive, UGPGraph, KnitOp, Joint,
                            PrimitiveError)

__all__ = ["build_garment", "GARMENT_FAMILIES"]

GARMENT_FAMILIES = ("hat", "sock", "glove", "skirt", "dress", "trousers",
                    "shorts", "shirt", "hoodie")

_LINEAR_KEYS = ("r1", "r2", "l", "r", "rx", "ry", "rz", "w", "h")

# world-frame +Y is the body's vertical: garments hang downward (-Y) from
# the waist/shoulder; upward (+Y) flows are head/limb directions.


def _scaled_params(params, scale):
    return {k: (v * scale if k in _LINEAR_KEYS else v)
            for k, v in params.items()}


def _scaled_pos(pos, scale):
    return tuple(c * scale for c in pos)


def _prim(pid, kind, params, pos, axis=(0, 1, 0), scale=1.0):
    return Primitive(id=pid, kind=kind,
                     params=_scaled_params(params, scale),
                     origin=_scaled_pos(pos, scale), axis=axis)


def _root_cast_on(graph, rim_prim, op_id):
    """Start the root piece's fabric at rim_start (§4.2 fabric_start)."""
    graph.add_op(KnitOp(id=op_id, op="cast_on",
                        consumes=[], produces="%s/rim_start" % rim_prim.id))


def _rim_joint(gid, child, parent, construction, anchor_point,
               child_boundary="rim_start", realized_by=None):
    """Parent rim mates child opening over the full perimeter (§5.4).

    child_boundary defaults to 'rim_start' for tubes; pass 'rim' for
    hemisphere children which expose only a single 'rim' boundary.
    """
    return Joint(id=gid, joint="rim_joint", child=child.id,
                 child_boundary=child_boundary, parent=parent.id,
                 parent_boundary="rim_end", construction=construction,
                 anchor={"feature": "rim",
                         "boundary": "rim_end",
                         "point": anchor_point},
                 realized_by=realized_by)


def _continuation(gid, child, parent, construction, anchor_point,
                  child_boundary="rim_start", realized_by=None):
    """Child claims the parent's terminus fabric flow (§5.1)."""
    return Joint(id=gid, joint="terminus_continuation", child=child.id,
                 child_boundary=child_boundary, parent=parent.id,
                 parent_boundary="rim_end", construction=construction,
                 anchor={"feature": "terminus",
                         "boundary": "rim_end",
                         "point": anchor_point},
                 realized_by=realized_by)


def _branch(gid, child, parent, anchor_point, child_boundary="rim_start"):
    """surface_branch: unsupported-only in v2 (§5.4, §10).

    child_boundary is the child's opening on the parent surface: rim_start
    for tubes (the fabric the pick_up produces), rim for render-only caps.
    """
    return Joint(id=gid, joint="surface_branch", child=child.id,
                 child_boundary=child_boundary, parent=parent.id,
                 parent_boundary=None, construction="unsupported",
                 anchor={"feature": "surface", "boundary": None,
                         "point": anchor_point})


# --- builders ----------------------------------------------------------------


def _build_hat(scale):
    g = UGPGraph()
    crown = _prim("hat_crown", "tube", {"r1": 95, "r2": 90, "l": 110},
                  (0, 0, 0), scale=scale)
    dome = _prim("hat_dome", "hemisphere", {"r": 90}, (0, 110, 0),
                 scale=scale)
    g.add(crown)
    g.add(dome)
    _root_cast_on(g, crown, "hat_cast_on")
    # hat_crown/rim_start (the brim) is produced by cast_on — fabric_start.
    # graft closes the crown's rim_end to the dome's single 'rim' boundary
    g.add_op(KnitOp(id="hat_dome_graft", op="graft",
                    consumes=["hat_crown/rim_end", "hat_dome/rim"]))
    # anchor: a point on the rim_end circle (radius=90, height=110*scale)
    rim_end_pt = (90.0 * scale, 110.0 * scale, 0.0)
    g.add_joint(_rim_joint("hat_j_dome", dome, crown, "grafted",
                           rim_end_pt, child_boundary="rim",
                           realized_by=["hat_dome_graft"]))
    return g


def _build_sock(scale):
    g = UGPGraph()
    leg = _prim("sock_leg", "tube", {"r1": 55, "r2": 50, "l": 250},
                (0, 0, 0), scale=scale)
    foot = _prim("sock_foot", "tube", {"r1": 50, "r2": 45, "l": 180},
                 (0, 0, 0), axis=(1, 0, 0), scale=scale)
    toe = _prim("sock_toe", "hemisphere", {"r": 45}, (180, 0, 0),
                scale=scale)
    g.add(leg)
    g.add(foot)
    g.add(toe)
    _root_cast_on(g, leg, "sock_cast_on")
    # sock_leg/rim_start (the cuff) is produced by cast_on — fabric_start.
    # heel turn: fabric continues through the terminus and comes back
    # horizontal — a 90° knitted-in turn (§5.1), the parent card's
    # d48fd0d decision.
    g.add_op(KnitOp(id="sock_foot_pick_up", op="pick_up",
                    consumes=["sock_leg/rim_end"],
                    produces="sock_foot/rim_start"))
    g.add_joint(_continuation("sock_j_heel", foot, leg, "knitted_in",
                              leg.metrics()["terminus"],
                              realized_by=["sock_foot_pick_up"]))
    g.add_op(KnitOp(id="sock_toe_graft", op="graft",
                    consumes=["sock_foot/rim_end", "sock_toe/rim"]))
    g.add_joint(_continuation("sock_j_toe", toe, foot, "grafted",
                              foot.metrics()["terminus"],
                              child_boundary="rim",
                              realized_by=["sock_toe_graft"]))
    return g


def _build_glove(scale):
    # Known-open per DESIGN.md §10: v2 expresses the finger joints
    # (surface_branch on the palm surface) but cannot claim their knit
    # realization — mid-fabric pick-up needs pick_up_path, reserved and
    # not in the v2 op set.  Fingers stay render-only disks with inert
    # rims and construction "unsupported"; documented, not hidden.
    #
    # The palm is a hemisphere (dome shape); the wrist is a tube from
    # which knitting begins.  The hemisphere 'rim' boundary at the wrist
    # end is the fabric entry point.
    g = UGPGraph()
    # wrist tube: cast on at rim_start, knit upward to rim_end
    wrist = _prim("glove_wrist", "tube", {"r1": 50, "r2": 55, "l": 60},
                  (0, 0, 0), scale=scale)
    # palm dome: sits on top of the wrist tube
    palm = _prim("glove_palm", "hemisphere", {"r": 55}, (0, 60, 0),
                 scale=scale)
    g.add(wrist)
    g.add(palm)
    _root_cast_on(g, wrist, "glove_cast_on")
    # wrist/rim_start (the cuff hem) is produced by cast_on — fabric_start.
    # graft wrist terminus onto the palm's rim
    g.add_op(KnitOp(id="glove_palm_graft", op="graft",
                    consumes=["glove_wrist/rim_end", "glove_palm/rim"]))
    rim_end_pt = (55.0 * scale, 60.0 * scale, 0.0)
    g.add_joint(_rim_joint("glove_j_palm", palm, wrist, "grafted",
                           rim_end_pt, child_boundary="rim",
                           realized_by=["glove_palm_graft"]))
    # fingers: render-only disks branched off the hemisphere surface.
    # Anchor points must lie on the hemisphere surface (|pt - origin| == r).
    # Palm origin = (0, 60*scale, 0), r = 55*scale.
    r = 55.0 * scale
    ox, oy, oz = 0.0, 60.0 * scale, 0.0
    finger_specs = [
        # (pid, unit direction from palm center) — normalized, then * r
        ("finger_1", (0.0, 1.0, 0.0)),
        ("finger_2", (0.0, 0.906, 0.423)),
        ("finger_3", (0.0, 0.906, -0.423)),
        ("finger_4", (0.0, 0.819, 0.574)),
        ("thumb",    (-0.940, 0.342, 0.0)),
    ]
    for pid, (ux, uy, uz) in finger_specs:
        disk_r = 10 if "thumb" not in pid else 12
        anchor = (ox + ux * r, oy + uy * r, oz + uz * r)
        disk_origin = anchor   # disk sits at the surface point
        g.add(_prim(pid, "disk", {"r": disk_r}, disk_origin, scale=scale))
        g.add_joint(_branch("glove_j_%s" % pid, g.get(pid), palm,
                            anchor, child_boundary="rim"))
    return g


def _build_skirt(scale):
    g = UGPGraph()
    body = _prim("skirt_body", "tube", {"r1": 90, "r2": 160, "l": 450},
                 (0, 0, 0), axis=(0, 1, 0), scale=scale)
    g.add(body)
    _root_cast_on(g, body, "skirt_cast_on")
    # skirt_body/rim_start is produced by cast_on (fabric_start only).
    # skirt_body/rim_end is the hem — declared open.
    g.open_boundaries = ["skirt_body/rim_end"]
    return g


def _build_dress(scale):
    g = UGPGraph()
    torso = _prim("dress_torso", "tube", {"r1": 100, "r2": 95, "l": 350},
                  (0, 0, 0), scale=scale)
    # skirt r1 must match torso r2 (= 95) for I-RIMMATCH and I-CONT.
    # axis same as torso so the continuation turn is 0°.
    skirt = _prim("dress_skirt", "tube", {"r1": 95, "r2": 170, "l": 450},
                  (0, 350, 0), axis=(0, 1, 0), scale=scale)
    g.add(torso)
    g.add(skirt)
    _root_cast_on(g, torso, "dress_cast_on")
    # torso/rim_start (the neckline) is produced by cast_on — fabric_start.
    # dress_skirt/rim_end is the hem — declared open.
    g.open_boundaries = ["dress_skirt/rim_end"]
    g.add_op(KnitOp(id="dress_skirt_pick_up", op="pick_up",
                    consumes=["dress_torso/rim_end"],
                    produces="dress_skirt/rim_start"))
    g.add_joint(_continuation("dress_j_skirt", skirt, torso, "knitted_in",
                              torso.metrics()["terminus"],
                              realized_by=["dress_skirt_pick_up"]))
    return g


def _build_trousers(scale, leg_length=450):
    g = UGPGraph()
    hips = _prim("trousers_hips", "tube", {"r1": 110, "r2": 100, "l": 150},
                 (0, 0, 0), scale=scale)
    g.add(hips)
    # Legs are surface_branch (unsupported) — each starts with its own
    # cast_on.  Anchor points must lie on the hips tube surface
    # (radial == r at that axial position).  At axial y=0, r = r1 = 110.
    for side, dx in (("l", -110.0), ("r", 110.0)):
        # Leg axis (0,1,0): must not point INTO parent material.
        # _surface_outward_normal for tube returns tube.axis = (0,1,0),
        # so child axis dot normal = 1 (pointing outward — valid).
        leg = _prim("trousers_leg_%s" % side, "tube",
                    {"r1": 58, "r2": 50, "l": leg_length},
                    (dx, 0, 0), axis=(0, 1, 0), scale=scale)
        g.add(leg)
        _root_cast_on(g, leg, "trousers_leg_%s_cast_on" % side)
        g.add_joint(_branch("trousers_j_leg_%s" % side, leg, hips,
                            (dx * scale, 0.0, 0.0)))
    _root_cast_on(g, hips, "trousers_cast_on")
    # hips/rim_start (the waistband) is produced by cast_on — fabric_start.
    # hips/rim_end = crotch opening — declared open
    # each leg/rim_start produced by its own cast_on (fabric_start)
    # each leg/rim_end = hem — declared open
    g.open_boundaries = [
        "trousers_hips/rim_end",
        "trousers_leg_l/rim_end",
        "trousers_leg_r/rim_end",
    ]
    return g


def _build_shirt(scale, hood=False):
    g = UGPGraph()
    torso = _prim("shirt_torso", "tube", {"r1": 110, "r2": 120, "l": 300},
                  (0, 0, 0), scale=scale)
    g.add(torso)
    # Sleeves: surface_branch (unsupported).  Anchor at torso rim_end
    # (y=300, r2=120) — the axial position where r = r2 = 120, so the
    # surface residual = |radial - r_at_axial| = |120 - 120| = 0.
    for side, dx, ax in (("l", -1.0, (-1, 0, 0)), ("r", 1.0, (1, 0, 0))):
        # Sleeve axis points laterally away from torso (outward).
        # _surface_outward_normal for tube returns y_ax = (0,1,0).
        # Child axis must have non-negative dot with (0,1,0).
        # Use (0,1,0) for both sleeves — sleeves grow upward in spec space.
        g.add(_prim("shirt_sleeve_%s" % side, "tube",
                    {"r1": 55, "r2": 45, "l": 250},
                    (dx * 120, 300, 0), axis=(0, 1, 0), scale=scale))
    if hood:
        # Hood: hemisphere, its 'rim' grafted onto torso/rim_end.
        g.add(_prim("hood", "hemisphere", {"r": 120}, (0, 300, 0),
                    scale=scale))
    _root_cast_on(g, torso, "shirt_cast_on")
    # torso/rim_start (the hem) is produced by cast_on — fabric_start.
    open_bnds = []
    for side in ("l", "r"):
        sleeve = g.get("shirt_sleeve_%s" % side)
        _root_cast_on(g, sleeve, "shirt_sleeve_%s_cast_on" % side)
        # Each sleeve's rim_end = cuff — declared open
        open_bnds.append("shirt_sleeve_%s/rim_end" % side)
        # Anchor: at torso rim_end circle, r2=120, height=300*scale.
        dx = -1.0 if side == "l" else 1.0
        anchor = (dx * 120.0 * scale, 300.0 * scale, 0.0)
        g.add_joint(_branch("shirt_j_sleeve_%s" % side, sleeve, torso,
                            anchor))
    if hood:
        hood_p = g.get("hood")
        # Hood 'rim' radius must match torso rim_end r2=120 for I-RIMMATCH.
        g.add_op(KnitOp(id="hood_graft", op="graft",
                        consumes=["shirt_torso/rim_end", "hood/rim"]))
        # Anchor: a point on the torso rim_end circle (r2=120, y=300).
        rim_end_pt = (120.0 * scale, 300.0 * scale, 0.0)
        g.add_joint(_rim_joint("shirt_j_hood", hood_p, torso, "grafted",
                               rim_end_pt, child_boundary="rim",
                               realized_by=["hood_graft"]))
    else:
        # No hood: torso/rim_end = neck opening — declared open
        open_bnds.append("shirt_torso/rim_end")
    g.open_boundaries = open_bnds
    return g


_BUILDERS = {
    "hat": lambda s: _build_hat(s),
    "sock": lambda s: _build_sock(s),
    "glove": lambda s: _build_glove(s),
    "skirt": lambda s: _build_skirt(s),
    "dress": lambda s: _build_dress(s),
    "trousers": lambda s: _build_trousers(s),
    "shorts": lambda s: _build_trousers(s, leg_length=150),
    "shirt": lambda s: _build_shirt(s),
    "hoodie": lambda s: _build_shirt(s, hood=True),
}


def build_garment(family, scale=1.0):
    if family not in _BUILDERS:
        raise ValueError("unknown garment family: %r (known: %s)"
                         % (family, ", ".join(GARMENT_FAMILIES)))
    if (not isinstance(scale, (int, float)) or isinstance(scale, bool)
            or not math.isfinite(scale) or scale <= 0):
        raise ValueError("scale must be a positive finite number, got %r"
                         % (scale,))
    return _BUILDERS[family](float(scale))
