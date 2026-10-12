"""Universal Garment Primitive (UGP) — IR spec v2 core representation.

Implements the vocabulary of DESIGN.md v2: render primitives with
boundary descriptors, the closed joint taxonomy (type x construction x
anchor), the default_knit op set, and the I-* invariant checks.

Two views, one graph:
- render view: parametric solids, visualization geometry only;
- knit view: boundary descriptors + dispositions + knit ops.
A disk is a render cap, NOT a knit closure.
"""
import json
import math

__all__ = [
    "Primitive", "UGPGraph", "Boundary", "KnitOp", "Joint",
    "PRIMITIVE_KINDS", "JOINT_TYPES", "CONSTRUCTIONS", "ANCHOR_FEATURES",
    "OP_SET_DEFAULT_KNIT", "INARIANT_CLASSES", "TOLERANCES", "DEFAULTS",
    "CONSUMING_OPS", "PRODUCING_OPS",
]

# --- spec v2 vocabulary (DESIGN.md §2, §4.3, §5, §6) ----------------------
PRIMITIVE_KINDS = ("tube", "sphere", "ellipsoid", "hemisphere", "disk",
                   "rect")
JOINT_TYPES = ("rim_joint", "surface_branch", "terminus_continuation")
CONSTRUCTIONS = ("knitted_in", "grafted", "selvedge_seam", "unsupported")
ANCHOR_FEATURES = ("terminus", "rim", "surface")
OP_SET_DEFAULT_KNIT = ("cast_on", "bind_off", "short_row_close", "graft",
                       "pick_up", "selvedge_seam")
INARIANT_CLASSES = ("I-DEGENERATE", "I-SCHEMA", "I-AXIS", "I-GRAPH",
                    "I-ANCHOR", "I-RIMMATCH", "I-CONT", "I-BRANCHORIENT",
                    "I-LOOP", "I-SEAL", "I-JOINT")
TOLERANCES = {
    "T_ANCHOR": 0.5,       # mm
    "T_RIM": 1.0,          # mm
    "T_LOOPS": 2.0,        # loops
    "T_AXIS_EPS": 1e-9,
    "MAX_CONT_TURN_DEG": 90.0,
    "MAX_BRANCH_TILT_DEG": 90.0,
}

CONSUMING_OPS = frozenset(("bind_off", "short_row_close", "graft",
                           "pick_up", "selvedge_seam"))
PRODUCING_OPS = frozenset(("cast_on", "pick_up"))
_RENDER_ONLY_KINDS = frozenset(("disk", "rect"))
_NO_BOUNDARY_KINDS = frozenset(("sphere", "ellipsoid"))

_PLURAL = {"rim_joint": "rim_joints", "surface_branch": "surface_branches",
           "terminus_continuation": "terminus_continuations"}

# --- primitive parameter schema (defaults in mm) ---------------------------
DEFAULTS = {
    "tube": {"r1": 10, "r2": 10, "l": 10},
    "sphere": {"r": 10},
    "ellipsoid": {"rx": 10, "ry": 10, "rz": 10},
    "hemisphere": {"r": 10},
    "disk": {"r": 10},
    "rect": {"w": 10, "h": 10},
}
_LINEAR_KEYS = frozenset(("r1", "r2", "l", "r", "rx", "ry", "rz", "w", "h"))


class _BaseError(Exception):
    """Base for all ugc.primitives errors (documented removal of bare ValueError use)."""


class PrimitiveError(_BaseError, ValueError):
    """Invalid primitive definition (kind, params, axis, ids)."""


class JointError(_BaseError, ValueError):
    """Invalid joint: taxonomy violations (type/construction/anchor)."""


class OpError(_BaseError, ValueError):
    """Invalid op instance: unknown op id or wrong consume/produce shape."""


class SchemaError(_BaseError, ValueError):
    """Broken identifier or reference (duplicate/unknown ids, boundaries)."""


class GraphValidationError(_BaseError, ValueError):
    """Graph-level invariant failure (I-*); carries .invariant and .subject."""


class Primitive:
    """One parametric solid in the garment graph (render view owner).

    Render geometry is visualization only; the knit view lives in the
    boundary descriptors this primitive exposes and the ops that consume
    them.
    """

    def __init__(self, id, kind, params, origin, axis=(0, 1, 0)):
        if kind not in PRIMITIVE_KINDS:
            raise PrimitiveError("unknown primitive kind: %r" % (kind,))
        self.id = str(id)
        self.kind = kind
        merged = dict(DEFAULTS[kind])
        unknown = set(params or {}) - set(DEFAULTS[kind])
        if unknown:
            raise PrimitiveError(
                "unknown params for kind %r: %s"
                % (kind, ", ".join(sorted(unknown))))
        merged.update(params or {})
        for key, val in merged.items():
            _require_finite_number(key, val)
        for key, val in merged.items():
            if key in _LINEAR_KEYS and val <= 0:
                raise PrimitiveError(
                    "%s.%s must be > 0 mm, got %r" % (kind, key, val))
        self.params = merged
        self.origin = _require_point(origin, "origin")
        self.axis = _norm(axis)
        self.disposition = {}   # boundary_id -> KnitOp instance id
        self.disposition_state = {}  # boundary_id -> terminal-state string
        # -- identity is v1-kept but validated: empty/duplicate ids are §7.4 ---
        if not self.id or any(c.isspace() for c in self.id):
            raise PrimitiveError(
                "primitive id must be non-empty with no whitespace: %r"
                % (id,))

    # -- transforms --------------------------------------------------------
    @staticmethod
    def rotation_matrix(deg, axis):
        x, y, z = _norm(axis)
        rad = math.radians(deg)
        c, s = math.cos(rad), math.sin(rad)
        C = 1.0 - c
        return [
            [c + x * x * C, x * y * C - z * s, x * z * C + y * s],
            [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
            [z * x * C - y * s, z * y * C + x * s, c + z * z * C],
        ]

    def _basis(self):
        """Orthonormal right-handed local frame (x, y, z); y = self.axis."""
        y_ax = self.axis
        ref = (0.0, 0.0, 1.0) if abs(y_ax[1]) > 0.9 else (0.0, 1.0, 0.0)
        x_ax = _norm(_vcross(y_ax, ref))
        z_ax = _vcross(x_ax, y_ax)
        return x_ax, y_ax, z_ax

    def world_to_local(self, p):
        x_ax, y_ax, z_ax = self._basis()
        d = _vsub(_require_point(p, "point"), self.origin)
        return (d[0] * x_ax[0] + d[1] * x_ax[1] + d[2] * x_ax[2],
                d[0] * y_ax[0] + d[1] * y_ax[1] + d[2] * y_ax[2],
                d[0] * z_ax[0] + d[1] * z_ax[1] + d[2] * z_ax[2])

    # -- knit view: boundaries ----------------------------------------------
    @property
    def knit_bearing(self):
        """True when the primitive represents fabric (DESIGN.md §4.1)."""
        return self.kind not in _RENDER_ONLY_KINDS

    @property
    def closure(self):
        """\"integral\" for closed forms, else None."""
        if self.kind in _NO_BOUNDARY_KINDS or self.kind == "hemisphere":
            return "integral"
        return None

    @property
    def terminus_boundary(self):
        """Boundary id of the terminus rim (tube: rim_end; others: rim)."""
        if self.kind == "tube":
            return "rim_end"
        if self.kind == "hemisphere":
            return "rim"
        raise PrimitiveError(
            "kind %r has no terminus rim boundary" % (self.kind,))

    @property
    def boundaries(self):
        """Ordered Boundary descriptors (DESIGN.md §4.1)."""
        axis = self.axis
        o = self.origin
        if self.kind == "tube":
            r1 = self.params["r1"]
            start = o
            end_c = _vadd(o, _vscale(axis, self.params["l"]))
            return [
                Boundary("rim_start", "rim", 2.0 * math.pi * r1,
                         frame=(start, _vscale(axis, -1.0))),
                Boundary("rim_end", "rim", 2.0 * math.pi * self.params["r2"],
                         frame=(end_c, tuple(axis))),
            ]
        if self.kind == "hemisphere":
            r = self.params["r"]
            return [Boundary("rim", "rim", 2.0 * math.pi * r,
                             frame=(o, _vscale(axis, -1.0)))]
        if self.kind == "disk":
            r = self.params["r"]
            return [Boundary("rim", "inert", 2.0 * math.pi * r,
                             frame=(o, _vscale(axis, -1.0)))]
        if self.kind == "rect":
            # rect lies in the plane through origin, normal = axis; edges
            # run in the local x/z basis, outward normals in-plane.
            half_w = self.params["w"] / 2.0
            half_h = self.params["h"] / 2.0
            x_ax, _, z_ax = self._basis()
            centers = {
                "edge_bottom": _vadd(o, _vscale(x_ax, -half_w)),
                "edge_top": _vadd(o, _vscale(x_ax, half_w)),
                "edge_left": _vadd(o, _vscale(z_ax, -half_h)),
                "edge_right": _vadd(o, _vscale(z_ax, half_h)),
            }
            out = {
                "edge_bottom": _vscale(x_ax, -1.0),
                "edge_top": x_ax,
                "edge_left": _vscale(z_ax, -1.0),
                "edge_right": z_ax,
            }
            lengths = {"edge_bottom": self.params["h"],
                       "edge_top": self.params["h"],
                       "edge_left": self.params["w"],
                       "edge_right": self.params["w"]}
            return [Boundary(eid, "inert", lengths[eid],
                             frame=(centers[eid], out[eid]))
                    for eid in ("edge_bottom", "edge_top", "edge_left",
                                "edge_right")]

        return []

    def boundary(self, boundary_id):
        for b in self.boundaries:
            if b.boundary == boundary_id:
                return b
        raise KeyError("unknown boundary %r on primitive %r"
                       % (boundary_id, self.id))

    # -- render metrics (v1 kept, render view only) --------------------------
    def metrics(self):
        k, p = self.kind, self.params
        if k == "tube":
            r1, r2, l = p["r1"], p["r2"], p["l"]
            vol = math.pi * l * (r1 * r1 + r1 * r2 + r2 * r2) / 3.0
            slant = math.sqrt(l * l + (r1 - r2) ** 2)
            area = math.pi * (r1 + r2) * slant + math.pi * (r1 * r1 + r2 * r2)
            return {"volume": vol, "surfaceArea": area,
                    "terminus": _vadd(self.origin, _vscale(self.axis, l))}
        if k == "sphere":
            r = p["r"]
            return {"volume": 4.0 / 3.0 * math.pi * r ** 3,
                    "surfaceArea": 4.0 * math.pi * r ** 2}
        if k == "ellipsoid":
            rx, ry, rz = p["rx"], p["ry"], p["rz"]
            vol = 4.0 / 3.0 * math.pi * rx * ry * rz
            a, b, c = sorted((rx, ry, rz), reverse=True)
            p_const = 1.6075
            area = 4.0 * math.pi * (
                (a ** p_const * b ** p_const + a ** p_const * c ** p_const
                 + b ** p_const * c ** p_const) / 3.0) ** (1.0 / p_const)
            return {"volume": vol, "surfaceArea": area}
        if k == "hemisphere":
            r = p["r"]
            return {"volume": 2.0 / 3.0 * math.pi * r ** 3,
                    "surfaceArea": 3.0 * math.pi * r ** 2}
        if k == "disk":
            r = p["r"]
            return {"volume": 0.0, "surfaceArea": 2.0 * math.pi * r ** 2}
        if k == "rect":
            w, h = p["w"], p["h"]
            return {"volume": 0.0, "surfaceArea": 2.0 * w * h}
        raise PrimitiveError("unhandled kind %r" % (k,))

    # -- serialization -------------------------------------------------------
    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "params": self.params,
                "origin": list(self.origin), "axis": list(self.axis)}

    @classmethod
    def from_dict(cls, d):
        return cls(id=d["id"], kind=d["kind"], params=d.get("params"),
                   origin=tuple(d["origin"]), axis=tuple(d.get("axis")
                                                         or (0, 1, 0)))


class Boundary:
    """One knit-bearing or inert boundary loop on a primitive (§4.1)."""

    def __init__(self, boundary, kind, length_mm, loops=None, frame=None):
        if kind not in ("rim", "inert"):
            raise PrimitiveError("boundary kind must be 'rim' or 'inert', "
                                 "got %r" % (kind,))
        if length_mm <= 0:
            raise PrimitiveError("boundary length must be > 0 mm")
        self.boundary = boundary
        self.kind = kind
        self.length_mm = float(length_mm)
        # §4.1: inert boundaries carry the constant loops = 0.0
        self.loops = 0.0 if kind == "inert" else loops
        if frame is None:
            self.frame = {"center": (0.0, 0.0, 0.0),
                          "normal": (0.0, 1.0, 0.0)}
        elif isinstance(frame, dict):
            self.frame = {"center": tuple(frame["center"]),
                          "normal": tuple(frame["normal"])}
        else:
            center, normal = frame
            self.frame = {"center": tuple(center), "normal": tuple(normal)}

    @property
    def knit_bearing(self):
        return self.kind == "rim"

    @property
    def consumable(self):
        return self.kind == "rim"

    def loops_for(self, gauge):
        """Loop count under a graph gauge {wale_mm, course_mm}; None w/o gauge."""
        if not gauge or "wale_mm" not in gauge:
            return None
        return self.length_mm / float(gauge["wale_mm"])

    def __eq__(self, other):
        return (isinstance(other, Boundary)
                and self.boundary == other.boundary and self.kind == other.kind
                and abs(self.length_mm - other.length_mm) < 1e-9
                and self.frame == other.frame)

    def __repr__(self):  # pragma: no cover
        return "Boundary(%r, %s, %.3f mm)" % (self.boundary, self.kind,
                                              self.length_mm)


class KnitOp:
    """One op instance of the default_knit set (§4.3)."""

    def __init__(self, id, op, consumes, produces=None, params=None):
        if op not in OP_SET_DEFAULT_KNIT:
            raise OpError("unknown op id: %r (default_knit: %s)"
                          % (op, ", ".join(OP_SET_DEFAULT_KNIT)))
        consumes = list(consumes or [])
        if not isinstance(produces, (str, type(None))):
            raise OpError("produces must be 'prim/boundary' str or null")
        # -- shape table: (len(consumes), produces-required?) ---------------
        # cast_on produces one rim; bind_off/short_row_close consume one;
        # graft/selvedge_seam consume two; pick_up consumes one + produces one
        _shape = {"cast_on": (0, True), "bind_off": (1, False),
                  "short_row_close": (1, False), "graft": (2, False),
                  "pick_up": (1, True), "selvedge_seam": (2, False)}
        want_n, need_produce = _shape[op]
        if len(consumes) != want_n or (produces is None) == need_produce:
            raise OpError(
                "op %r wrong consume/produce shape: consumes=%r produces=%r"
                % (op, consumes, produces))
        for ref in consumes + ([produces] if produces else []):
            if not isinstance(ref, str) or ref.count("/") != 1:
                raise OpError(
                    "boundary refs must be 'prim_id/boundary_id', got %r"
                    % (ref,))
        self.id = str(id)
        self.op = op
        self.consumes = consumes
        self.produces = produces
        self.params = dict(params or {})

    def to_dict(self):
        return {"id": self.id, "op": self.op, "consumes": list(self.consumes),
                "produces": self.produces, "params": dict(self.params)}

    @classmethod
    def from_dict(cls, d):
        return cls(id=d["id"], op=d["op"], consumes=d.get("consumes"),
                   produces=d.get("produces"), params=d.get("params"))


class Joint:
    """Typed joint: topology (joint type) x construction x anchor (§5)."""

    def __init__(self, id, joint, child, child_boundary, parent,
                 parent_boundary, construction, anchor, realized_by=None):
        if joint not in JOINT_TYPES:
            raise JointError("unknown joint type: %r" % (joint,))
        if construction not in CONSTRUCTIONS:
            raise JointError("unknown construction: %r" % (construction,))
        if not isinstance(anchor, dict):
            raise JointError("anchor must be a dict {feature, boundary, point}")
        feature = anchor.get("feature")
        if feature not in ANCHOR_FEATURES:
            raise JointError("unknown anchor feature: %r" % (feature,))
        anchor_point = None
        try:
            anchor_point = _require_point(anchor.get("point"), "anchor.point")
        except PrimitiveError as exc:
            raise JointError(str(exc))
        self.id = str(id)
        self.joint = joint
        self.child = str(child)
        self.child_boundary = str(child_boundary)
        self.parent = str(parent)
        self.parent_boundary = (str(parent_boundary)
                                if parent_boundary is not None else None)
        self.construction = construction
        self.anchor = {"feature": feature,
                       "boundary": (str(anchor["boundary"])
                                    if anchor.get("boundary") is not None
                                    else None),
                       "point": anchor_point}
        self.realized_by = [str(r) for r in (realized_by or [])]

    def to_dict(self):
        return {"id": self.id, "joint": self.joint, "child": self.child,
                "child_boundary": self.child_boundary,
                "parent": self.parent,
                "parent_boundary": self.parent_boundary,
                "construction": self.construction,
                "anchor": dict(self.anchor),
                "realized_by": list(self.realized_by)}

    @classmethod
    def from_dict(cls, d):
        return cls(id=d["id"], joint=d["joint"], child=d["child"],
                   child_boundary=d["child_boundary"], parent=d["parent"],
                   parent_boundary=d.get("parent_boundary"),
                   construction=d["construction"], anchor=d["anchor"],
                   realized_by=d.get("realized_by"))


# --- helpers ----------------------------------------------------------------
def _require_finite_number(name, val):
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise PrimitiveError("%s must be a number, got %r" % (name, val))
    if math.isnan(val) or math.isinf(val):
        raise PrimitiveError("%s must be finite, got %r" % (name, val))
    return float(val)


def _require_point(p, name):
    if p is None:
        raise PrimitiveError("%s is required" % (name,))
    try:
        x, y, z = (float(c) for c in p)
    except (TypeError, ValueError):
        raise PrimitiveError("%s must be [x, y, z], got %r" % (name, p))
    for c in (x, y, z):
        if math.isnan(c) or math.isinf(c):
            raise PrimitiveError("%s must be finite, got %r" % (name, p))
    return (x, y, z)


def _norm(v):
    x, y, z = _require_point(v, "axis")
    n = math.sqrt(x * x + y * y + z * z)
    if n == 0.0:
        raise PrimitiveError("axis must be a nonzero vector")
    return (x / n, y / n, z / n)


def _vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vscale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _vlen(a):
    return math.sqrt(_vdot(a, a))


class UGPGraph:
    """UGP graph: primitives + typed joints + knit ops (§12 JSON shape)."""

    def __init__(self, primitives=None, joints=None, ops=None, gauge=None,
                 tolerances=None, open_boundaries=None):
        self._prims = []
        self.rim_joints = []
        self.surface_branches = []
        self.terminus_continuations = []
        self.ops = []
        self.gauge = gauge
        self.tolerances = dict(TOLERANCES)
        if tolerances:
            unknown = set(tolerances) - set(TOLERANCES)
            if unknown:
                raise SchemaError("unknown tolerance constants: %s"
                                  % ", ".join(sorted(unknown)))
            self.tolerances.update(tolerances)
        self.open_boundaries = list(open_boundaries or [])
        for p in (primitives or []):
            self.add(p)
        for j in (joints or []):
            self.add_joint(j)
        for op in (ops or []):
            self.add_op(op)

    # -- primitives ----------------------------------------------------------
    def add(self, prim):
        if any(p.id == prim.id for p in self._prims):
            raise SchemaError("duplicate primitive id: %r" % (prim.id,))
        self._prims.append(prim)
        return prim

    def get(self, prim_id):
        for p in self._prims:
            if p.id == prim_id:
                return p
        raise KeyError(prim_id)

    def has(self, prim_id):
        return any(p.id == prim_id for p in self._prims)

    def __len__(self):
        return len(self._prims)

    def __iter__(self):
        return iter(self._prims)

    # -- joints ----------------------------------------------------------------
    def add_joint(self, joint):
        if joint.child == joint.parent:
            raise JointError("self-joint %r: child == parent" % (joint.id,))
        if not self.has(joint.child):
            raise SchemaError("joint %r references unknown child %r"
                              % (joint.id, joint.child))
        if not self.has(joint.parent):
            raise SchemaError("joint %r references unknown parent %r"
                              % (joint.id, joint.parent))
        plural = _PLURAL[joint.joint]
        getattr(self, plural).append(joint)
        return joint

    def joints(self):
        return (self.rim_joints + self.surface_branches
                + self.terminus_continuations)

    def joint_plurals(self):
        return {"rim_joints": self.rim_joints,
                "surface_branches": self.surface_branches,
                "terminus_continuations": self.terminus_continuations}

    # -- ops ---------------------------------------------------------------------
    def add_op(self, op):
        if any(o.id == op.id for o in self.ops):
            raise SchemaError("duplicate op instance id: %r" % (op.id,))
        self.ops.append(op)
        return op

    # -- serialization ---------------------------------------------------------------
    def to_json(self):
        return json.dumps(self.to_dict(), indent=2)

    def to_dict(self):
        return {"version": 2, "gauge": self.gauge,
                "tolerances": self.tolerances,
                "open_boundaries": list(self.open_boundaries),
                "primitives": [p.to_dict() for p in self._prims],
                "joints": {k: [j.to_dict() for j in v]
                           for k, v in self.joint_plurals().items()},
                "ops": [op.to_dict() for op in self.ops]}

    @classmethod
    def from_json(cls, blob):
        return cls.from_dict(
            json.loads(blob) if isinstance(blob, str) else blob)

    @classmethod
    def from_dict(cls, data):
        if data.get("version") != 2:
            raise SchemaError("unsupported graph version: %r"
                              % (data.get("version"),))
        g = cls(gauge=data.get("gauge"),
                tolerances=data.get("tolerances"),
                open_boundaries=data.get("open_boundaries"))
        for d in data.get("primitives", []):
            g.add(Primitive.from_dict(d))
        for plural, lst in (data.get("joints") or {}).items():
            if plural not in _PLURAL.values():
                raise SchemaError("unknown joint collection: %r" % (plural,))
            for jd in lst:
                g.add_joint(Joint.from_dict(jd))
        for od in data.get("ops", []):
            g.add_op(KnitOp.from_dict(od))
        return g


# ===========================================================================
# §6 validation — named, deterministic invariant checks
# ===========================================================================

class Finding(object):
    """One invariant verdict: named class, PASS/FAIL/UNVERIFIED, subject."""

    __slots__ = ("invariant", "status", "subject", "message")

    def __init__(self, invariant, status, subject, message=""):
        self.invariant = invariant
        self.status = status          # "PASS" | "FAIL" | "UNVERIFIED"
        self.subject = subject        # id of the offending graph element
        self.message = message

    def __repr__(self):  # pragma: no cover
        return "Finding(%s, %s, %r, %r)" % (self.invariant, self.status,
                                            self.subject, self.message)


class GraphValidationError(_BaseError, ValueError):
    """Raised by validate_strict; carries the full findings list."""

    def __init__(self, findings):
        failed = [f for f in findings if f.status == "FAIL"]
        lines = "; ".join("%s[%s]: %s" % (f.invariant, f.subject, f.message)
                          for f in failed)
        super(GraphValidationError, self).__init__(
            "graph validation failed: %s" % (lines or "no findings",))
        self.findings = list(findings)


# --- graph accessor shim (methods on UGPGraph, defined here for §6) --------
def _ugpgraph_resolution(g):
    """(prim_by_id, parent_joint_by_child_id)."""
    by_id = {p.id: p for p in g._prims}
    parent_of = {}
    for j in g.joints():
        if j.child in parent_of:
            parent_of[j.child] = None      # multi-parent marker
        else:
            parent_of[j.child] = j
    return by_id, parent_of


def _boundary_owner(ref):
    """'prim/boundary' -> (prim_id, boundary_id)."""
    prim_id, _, bnd = ref.partition("/")
    return prim_id, bnd


def _ref_exists(g, ref, by_id):
    prim_id, bnd = _boundary_owner(ref)
    prim = by_id.get(prim_id)
    if prim is None:
        return False
    try:
        prim.boundary(bnd)
    except KeyError:
        return False
    return True


# --- I-DEGENERATE -----------------------------------------------------------
def _check_degenerate(g, tols):
    # Constructor-level rejects cover §7.1-3; here we sweep what could have
    # been mutated after construction (params dict is mutable).
    findings = []
    ok = True
    for p in g._prims:
        for key, val in p.params.items():
            bad = (isinstance(val, bool) or not isinstance(val, (int, float))
                   or math.isnan(val) or math.isinf(val))
            if bad:
                findings.append(Finding(
                    "I-DEGENERATE", "FAIL", p.id,
                    "param %s is not a finite number: %r" % (key, val)))
                ok = False
            elif key in _LINEAR_KEYS and val <= 0:
                findings.append(Finding(
                    "I-DEGENERATE", "FAIL", p.id,
                    "param %s must be > 0 mm, got %r" % (key, val)))
                ok = False
        for vec, name in ((p.origin, "origin"), (p.axis, "axis")):
            if any(math.isnan(c) or math.isinf(c) for c in vec):
                findings.append(Finding(
                    "I-DEGENERATE", "FAIL", p.id,
                    "%s has a non-finite coordinate" % name))
                ok = False
        if p.kind in _RENDER_ONLY_KINDS:
            continue
    if ok:
        findings.append(Finding("I-DEGENERATE", "PASS", "*"))
    return findings


# --- I-SCHEMA ---------------------------------------------------------------
def _check_schema(g, tols):
    findings = []
    by_id, _ = _ugpgraph_resolution(g)
    ok = True
    seen_joint_ids = set()
    for j in g.joints():
        if j.id in seen_joint_ids:
            findings.append(Finding(
                "I-SCHEMA", "FAIL", j.id, "duplicate joint id"))
            ok = False
        seen_joint_ids.add(j.id)
        for role, pid in (("child", j.child), ("parent", j.parent)):
            if pid not in by_id:
                findings.append(Finding(
                    "I-SCHEMA", "FAIL", j.id,
                    "%s %r does not resolve" % (role, pid)))
                ok = False
        for role, ref in (("child_boundary", "%s/%s" % (j.child,
                                                        j.child_boundary)),
                          ("parent_boundary",
                           ("%s/%s" % (j.parent, j.parent_boundary))
                           if j.parent_boundary else None)):
            if ref is None:
                continue
            if not _ref_exists(g, ref, by_id):
                findings.append(Finding(
                    "I-SCHEMA", "FAIL", j.id,
                    "%s %r does not resolve" % (role, ref)))
                ok = False
        for op_id in j.realized_by:
            if not any(o.id == op_id for o in g.ops):
                findings.append(Finding(
                    "I-SCHEMA", "FAIL", j.id,
                    "realized_by %r does not resolve" % (op_id,)))
                ok = False
    seen_op_ids = set()
    for op in g.ops:
        if op.id in seen_op_ids:
            findings.append(Finding(
                "I-SCHEMA", "FAIL", op.id, "duplicate op instance id"))
            ok = False
        seen_op_ids.add(op.id)
        for ref in op.consumes:
            if not _ref_exists(g, ref, by_id):
                findings.append(Finding(
                    "I-SCHEMA", "FAIL", op.id,
                    "consumes %r does not resolve" % (ref,)))
                ok = False
        if op.produces and not _ref_exists(g, op.produces, by_id):
            findings.append(Finding(
                "I-SCHEMA", "FAIL", op.id,
                "produces %r does not resolve" % (op.produces,)))
            ok = False
    for ref in g.open_boundaries:
        if not _ref_exists(g, ref, by_id):
            findings.append(Finding(
                "I-SCHEMA", "FAIL", ref, "open_boundaries ref unknown"))
            ok = False
    if ok:
        findings.append(Finding("I-SCHEMA", "PASS", "*"))
    return findings


# --- I-AXIS -------------------------------------------------------------------
def _check_axis(g, tols):
    findings = []
    ok = True
    eps = tols["T_AXIS_EPS"]
    for p in g._prims:
        n = math.sqrt(sum(c * c for c in p.axis))
        if abs(n - 1.0) > eps:
            findings.append(Finding(
                "I-AXIS", "FAIL", p.id,
                "axis norm %r beyond T_AXIS_EPS" % (n,)))
            ok = False
    if ok:
        findings.append(Finding("I-AXIS", "PASS", "*"))
    return findings


# --- I-GRAPH -------------------------------------------------------------------
def _check_graph(g, tols):
    findings = []
    by_id, parent_of = _ugpgraph_resolution(g)
    ok = True
    for child, parent_joint in parent_of.items():
        if parent_joint is None:
            findings.append(Finding(
                "I-GRAPH", "FAIL", child, "primitive has multiple parents"))
            ok = False
    roots = [p.id for p in g._prims if p.id not in parent_of]
    if len(roots) != 1:
        findings.append(Finding(
            "I-GRAPH", "FAIL", "*",
            "expected exactly 1 root, found %d" % len(roots)))
        ok = False
    else:
        seen = set()
        stack = [roots[0]]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for j in g.joints():
                if j.parent == cur:
                    stack.append(j.child)
        if len(seen) != len(by_id):
            missing = sorted(set(by_id) - seen)
            findings.append(Finding(
                "I-GRAPH", "FAIL", missing[0],
                "primitives unreachable from root"))
            ok = False
    if ok:
        findings.append(Finding("I-GRAPH", "PASS", "*"))
    return findings


# --- I-ANCHOR -------------------------------------------------------------------
def _point_to_segment_dist(p, a, b):
    ab = _vsub(b, a)
    denom = _vdot(ab, ab)
    if denom == 0.0:
        return _vlen(_vsub(p, a))
    t = max(0.0, min(1.0, _vdot(_vsub(p, a), ab) / denom))
    closest = _vadd(a, _vscale(ab, t))
    return _vlen(_vsub(p, closest))


def _anchor_residual(g, joint, by_id):
    """Distance in mm from anchor.point to the declared parent feature."""
    parent = by_id[joint.parent]
    point = joint.anchor["point"]
    feature = joint.anchor["feature"]
    if feature == "terminus":
        tb = parent.terminus_boundary
        b = parent.boundary(tb)
        return _vlen(_vsub(point, b.frame["center"]))
    if feature == "rim":
        b = parent.boundary(joint.anchor["boundary"])
        center = b.frame["center"]
        normal = b.frame["normal"]
        # point-to-circle: axial offset + in-plane radial offset
        d = _vsub(point, center)
        axial = _vdot(d, normal)
        radial_vec = _vsub(d, _vscale(normal, axial))
        radius = b.length_mm / (2.0 * math.pi)
        return math.sqrt(axial * axial
                         + (_vlen(radial_vec) - radius) ** 2)
    if feature == "surface":
        k, pr = parent.kind, parent.params
        if k == "sphere":
            return abs(_vlen(_vsub(point, parent.origin)) - pr["r"])
        if k == "ellipsoid":
            # approximate algebraic residual normalized to mm scale
            d = _vsub(point, parent.origin)
            val = sum((d[i] / pr[axis]) ** 2
                      for i, axis in enumerate(("rx", "ry", "rz")))
            scale = max(pr["rx"], pr["ry"], pr["rz"])
            return abs(math.sqrt(val) - 1.0) * scale
        if k == "tube":
            d = _vsub(point, parent.origin)
            x_ax, y_ax, z_ax = parent._basis()
            axial = _vdot(d, y_ax)
            r_at = pr["r1"] + (pr["r2"] - pr["r1"]) * (
                axial / pr["l"] if pr["l"] else 0.0)
            radial = math.sqrt(_vdot(_vsub(d, _vscale(y_ax, axial)),
                                     _vsub(d, _vscale(y_ax, axial))))
            return abs(radial - r_at)
        if k == "disk":
            d = _vsub(point, parent.origin)
            _, y_ax, _ = parent._basis()
            return abs(_vdot(d, y_ax))
        if k == "rect":
            d = _vsub(point, parent.origin)
            _, y_ax, _ = parent._basis()
            return abs(_vdot(d, y_ax))
        if k == "hemisphere":
            d = _vsub(point, parent.origin)
            return abs(_vlen(d) - pr["r"])
    raise JointError("unknown anchor feature: %r" % (feature,))


def _check_anchor(g, tols):
    findings = []
    by_id, _ = _ugpgraph_resolution(g)
    tol = tols["T_ANCHOR"]
    ok = True
    for j in g.joints():
        if j.parent not in by_id:
            continue     # I-SCHEMA already reports the dangling reference
        try:
            residual = _anchor_residual(g, j, by_id)
        except KeyError as exc:
            findings.append(Finding(
                "I-ANCHOR", "FAIL", j.id,
                "anchor references unknown boundary: %s" % (exc,)))
            ok = False
            continue
        if residual > tol:
            findings.append(Finding(
                "I-ANCHOR", "FAIL", j.id,
                "anchor point off %s feature by %.3f mm (T_ANCHOR=%.3f)"
                % (j.anchor["feature"], residual, tol)))
            ok = False
    if ok:
        findings.append(Finding("I-ANCHOR", "PASS", "*"))
    return findings


# --- I-RIMMATCH -----------------------------------------------------------------
def _mating_joints(g):
    for j in g.joints():
        if j.joint in ("rim_joint", "terminus_continuation"):
            yield j


def _check_rimmatch(g, tols):
    findings = []
    by_id, _ = _ugpgraph_resolution(g)
    tol = tols["T_RIM"]
    checked = False
    ok = True
    for j in _mating_joints(g):
        if j.parent not in by_id or j.child not in by_id:
            continue
        try:
            cb = by_id[j.child].boundary(j.child_boundary)
            pb = by_id[j.parent].boundary(j.parent_boundary)
        except KeyError:
            continue     # I-SCHEMA reports the dangling boundary
        checked = True
        delta = abs(cb.length_mm - pb.length_mm)
        if delta > tol:
            findings.append(Finding(
                "I-RIMMATCH", "FAIL", j.id,
                "rim lengths differ by %.3f mm (T_RIM=%.3f)"
                % (delta, tol)))
            ok = False
    if not checked:
        findings.append(Finding("I-RIMMATCH", "PASS", "*",
                                "no rim-mating joints"))
    elif ok:
        findings.append(Finding("I-RIMMATCH", "PASS", "*"))
    return findings


# --- I-CONT -----------------------------------------------------------------------
def _angle_between(a, b):
    dot = max(-1.0, min(1.0, _vdot(a, b)))
    return math.degrees(math.acos(dot))


def _check_cont(g, tols):
    findings = []
    by_id, _ = _ugpgraph_resolution(g)
    tol = tols["T_RIM"]
    max_turn = tols["MAX_CONT_TURN_DEG"]
    checked = False
    ok = True
    for j in g.joints():
        if j.joint != "terminus_continuation":
            continue
        if j.parent not in by_id or j.child not in by_id:
            continue
        checked = True
        try:
            pb = by_id[j.parent].boundary(j.parent_boundary)
            cb = by_id[j.child].boundary(j.child_boundary)
        except KeyError:
            continue
        parent_radius = pb.length_mm / (2.0 * math.pi)
        child_radius = cb.length_mm / (2.0 * math.pi)
        r_delta = abs(parent_radius - child_radius)
        if r_delta > tol:
            findings.append(Finding(
                "I-CONT", "FAIL", j.id,
                "radius step %.3f mm exceeds T_RIM=%.3f" % (r_delta, tol)))
            ok = False
        turn = _angle_between(by_id[j.parent].axis, by_id[j.child].axis)
        if turn > max_turn + 1e-9:
            findings.append(Finding(
                "I-CONT", "FAIL", j.id,
                "axis turn %.1f deg exceeds MAX_CONT_TURN_DEG=%.1f"
                % (turn, max_turn)))
            ok = False
    if not checked:
        findings.append(Finding("I-CONT", "PASS", "*",
                                "no terminus_continuation joints"))
    elif ok:
        findings.append(Finding("I-CONT", "PASS", "*"))
    return findings


# --- I-BRANCHORIENT -------------------------------------------------------------------
def _surface_outward_normal(prim, point):
    k, pr = prim.kind, prim.params
    o = prim.origin
    if k == "sphere":
        n = _vsub(point, o)
        ln = _vlen(n)
        if ln == 0.0:
            raise JointError("anchor point coincides with sphere center")
        return _vscale(n, 1.0 / ln)
    if k == "ellipsoid":
        d = _vsub(point, o)
        n = (d[0] / (pr["rx"] ** 2), d[1] / (pr["ry"] ** 2),
             d[2] / (pr["rz"] ** 2))
        ln = _vlen(n)
        if ln == 0.0:
            raise JointError("anchor point coincides with ellipsoid center")
        return _vscale(n, 1.0 / ln)
    if k == "tube":
        _, y_ax, _ = prim._basis()
        return y_ax      # outward at the terminus region
    if k in ("disk", "rect"):
        _, y_ax, _ = prim._basis()
        return y_ax
    if k == "hemisphere":
        n = _vsub(point, o)
        ln = _vlen(n)
        if ln == 0.0:
            raise JointError("anchor point coincides with dome center")
        return _vscale(n, 1.0 / ln)
    raise JointError("no outward normal for kind %r" % (k,))


def _check_branchorient(g, tols):
    findings = []
    by_id, _ = _ugpgraph_resolution(g)
    max_tilt = tols["MAX_BRANCH_TILT_DEG"]
    checked = False
    ok = True
    for j in g.joints():
        if j.joint != "surface_branch":
            continue
        if j.parent not in by_id or j.child not in by_id:
            continue
        checked = True
        try:
            normal = _surface_outward_normal(by_id[j.parent],
                                             j.anchor["point"])
            dot = _vdot(by_id[j.child].axis, normal)
        except JointError as exc:
            findings.append(Finding(
                "I-BRANCHORIENT", "FAIL", j.id, str(exc)))
            ok = False
            continue
        if dot < -1e-9:
            findings.append(Finding(
                "I-BRANCHORIENT", "FAIL", j.id,
                "child axis points into parent material (axis . normal = "
                "%.3f)" % (dot,)))
            ok = False
    if not checked:
        findings.append(Finding("I-BRANCHORIENT", "PASS", "*",
                                "no surface_branch joints"))
    elif ok:
        findings.append(Finding("I-BRANCHORIENT", "PASS", "*"))
    return findings


# --- I-LOOP -------------------------------------------------------------------------
def _loops_for_ref(g, ref, by_id):
    prim_id, bnd = _boundary_owner(ref)
    prim = by_id.get(prim_id)
    if prim is None:
        return None
    try:
        b = prim.boundary(bnd)
    except KeyError:
        return None
    return b.loops_for(g.gauge)


def _check_loop(g, tols):
    findings = []
    by_id, _ = _ugpgraph_resolution(g)
    tol = tols["T_LOOPS"]
    if not g.gauge or "wale_mm" not in g.gauge:
        return [Finding("I-LOOP", "UNVERIFIED", "*",
                        "no gauge: loop correspondence not checked")]
    checked = False
    ok = True
    for op in g.ops:
        if op.op not in ("graft", "selvedge_seam", "pick_up"):
            continue
        pairs = []
        if op.op == "pick_up":
            pairs.append((op.consumes[0], op.produces))
        else:
            pairs.append((op.consumes[0], op.consumes[1]))
        for a, b in pairs:
            la = _loops_for_ref(g, a, by_id)
            lb = _loops_for_ref(g, b, by_id)
            if la is None or lb is None:
                continue
            checked = True
            delta = abs(la - lb)
            if delta > tol:
                findings.append(Finding(
                    "I-LOOP", "FAIL", op.id,
                    "loop counts differ by %.2f across %s <-> %s "
                    "(T_LOOPS=%.1f)" % (delta, a, b, tol)))
                ok = False
    if not checked:
        findings.append(Finding("I-LOOP", "PASS", "*",
                                "no loop-bearing ops"))
    elif ok:
        findings.append(Finding("I-LOOP", "PASS", "*"))
    return findings


# --- I-SEAL -------------------------------------------------------------------------
def _check_seal(g, tols):
    findings = []
    by_id, _ = _ugpgraph_resolution(g)
    ok = True
    consumed = {}     # ref -> [op ids]
    produced = {}     # ref -> [op ids]
    for op in g.ops:
        for ref in op.consumes:
            consumed.setdefault(ref, []).append(op.id)
        if op.produces:
            produced.setdefault(op.produces, []).append(op.id)
    for p in g._prims:
        for b in p.boundaries:
            if b.kind != "rim":
                # §4.1: inert boundaries are exempt from disposition, but no
                # op may consume them either (a disk closes nothing).
                ref = "%s/%s" % (p.id, b.boundary)
                if ref in consumed:
                    findings.append(Finding(
                        "I-SEAL", "FAIL", ref,
                        "inert boundary consumed by op(s) %s"
                        % ", ".join(consumed[ref])))
                    ok = False
                continue
            ref = "%s/%s" % (p.id, b.boundary)
            states = []
            if ref in produced:
                states.append("fabric_start")
            if ref in consumed:
                states.append("consumed")
            if ref in g.open_boundaries:
                states.append("declared_open")
            if len(states) == 0:
                findings.append(Finding(
                    "I-SEAL", "FAIL", ref,
                    "floating knit-bearing rim: no op and not declared open"))
                ok = False
            elif len(states) > 1:
                findings.append(Finding(
                    "I-SEAL", "FAIL", ref,
                    "rim in conflicting states: %s" % " + ".join(states)))
                ok = False
            elif len(consumed.get(ref, [])) > 1:
                findings.append(Finding(
                    "I-SEAL", "FAIL", ref,
                    "rim consumed by %d ops (%s)"
                    % (len(consumed[ref]), ", ".join(consumed[ref]))))
                ok = False
            elif len(produced.get(ref, [])) > 1:
                findings.append(Finding(
                    "I-SEAL", "FAIL", ref,
                    "rim produced by %d ops (%s)"
                    % (len(produced[ref]), ", ".join(produced[ref]))))
                ok = False
    if ok:
        findings.append(Finding("I-SEAL", "PASS", "*"))
    return findings


# --- I-JOINT -------------------------------------------------------------------------
_MATRIX = {
    # (joint type, parent_feature): set of legal constructions for
    # knit-bearing children
    ("rim_joint", "rim"): frozenset(("knitted_in", "grafted",
                                     "selvedge_seam")),
    ("terminus_continuation", "terminus"): frozenset(("knitted_in",
                                                      "grafted")),
}
_SURFACE_BRANCH_CONSTRUCTION = frozenset(("unsupported",))


def _check_joint(g, tols):
    findings = []
    by_id, _ = _ugpgraph_resolution(g)
    ok = True
    for j in g.joints():
        subject = j.id

        def fail(msg):
            findings.append(Finding("I-JOINT", "FAIL", subject, msg))

        if j.child not in by_id or j.parent not in by_id:
            continue      # I-SCHEMA reports dangling references
        child = by_id[j.child]
        parent = by_id[j.parent]
        child_b = None
        try:
            child_b = child.boundary(j.child_boundary)
            if j.parent_boundary is not None:
                parent.boundary(j.parent_boundary)
        except KeyError as exc:
            fail("boundary does not resolve: %s" % (exc,))
            ok = False
            continue
        try:
            _anchor_residual(g, j, by_id)
        except (JointError, KeyError) as exc:
            fail("anchor feature invalid: %s" % (exc,))
            ok = False
            continue

        # (a) anchor feature ⇔ joint type (§5.4 parent_feature column)
        feature = j.anchor["feature"]
        if j.joint == "rim_joint" and feature != "rim":
            fail("rim_joint requires anchor feature 'rim', got %r"
                 % (feature,))
            ok = False
        if j.joint == "surface_branch" and feature != "surface":
            fail("surface_branch requires anchor feature 'surface', got %r"
                 % (feature,))
            ok = False
        if j.joint == "terminus_continuation" and feature != "terminus":
            fail("terminus_continuation requires anchor feature 'terminus',"
                 " got %r" % (feature,))
            ok = False

        # (b) surface_branch must not name a parent boundary
        if j.joint == "surface_branch" and j.parent_boundary is not None:
            fail("surface_branch takes no parent_boundary (§5.4)")
            ok = False

        # (c) construction legality per §5.4 matrix
        if j.joint == "rim_joint":
            if child_b.kind == "inert":
                if j.construction != "unsupported":
                    fail("rim_joint with inert child rim requires "
                         "construction 'unsupported'")
                    ok = False
            else:
                if j.construction not in _MATRIX[("rim_joint", "rim")]:
                    fail("rim_joint with knit-bearing child forbids "
                         "construction %r" % (j.construction,))
                    ok = False
        elif j.joint == "surface_branch":
            if j.construction not in _SURFACE_BRANCH_CONSTRUCTION:
                fail("surface_branch allows construction 'unsupported' "
                     "only in v2 (mid-fabric pick_up_path is reserved)")
                ok = False
        elif j.joint == "terminus_continuation":
            if child_b.kind == "inert":
                fail("terminus_continuation with a render-only child "
                     "contradicts the claimed fabric flow")
                ok = False
            elif j.construction == "selvedge_seam":
                fail("terminus_continuation forbids construction "
                     "'selvedge_seam'; declare rim_joint instead")
                ok = False
            elif j.construction not in _MATRIX[("terminus_continuation",
                                                "terminus")]:
                fail("terminus_continuation forbids construction %r"
                     % (j.construction,))
                ok = False

        # (d) construction ⇔ realized_by op pattern (§5.4 mechanical rules)
        ops_by_id = {o.id: o for o in g.ops}
        rops = []
        missing_ref = False
        for op_id in j.realized_by:
            op = ops_by_id.get(op_id)
            if op is None:
                missing_ref = True     # I-SCHEMA reports this
                continue
            rops.append(op)
        if not missing_ref:
            parent_ref = ("t1"
                          if j.parent_boundary is None
                          else "%s/%s" % (j.parent, j.parent_boundary))
            if j.construction == "knitted_in":
                if (len(rops) != 1 or rops[0].op != "pick_up"
                        or rops[0].consumes != [parent_ref]
                        or rops[0].produces != "%s/%s" % (j.child,
                                                          j.child_boundary)):
                    fail("knitted_in requires exactly one pick_up "
                         "consuming the parent rim and producing the "
                         "child rim")
                    ok = False
            elif j.construction == "grafted":
                pair = set((j.parent_boundary, j.child_boundary)) - {None}
                if (len(rops) != 1 or rops[0].op != "graft"
                        or set(rops[0].consumes) != pair):
                    fail("grafted requires exactly one graft consuming "
                         "both rims")
                    ok = False
            elif j.construction == "selvedge_seam":
                pair = set((j.parent_boundary, j.child_boundary)) - {None}
                if (len(rops) != 1 or rops[0].op != "selvedge_seam"
                        or set(rops[0].consumes) != pair):
                    fail("selvedge_seam requires exactly one selvedge_seam "
                         "consuming both rims")
                    ok = False
            elif j.construction == "unsupported":
                if rops:
                    fail("unsupported requires an empty realized_by")
                    ok = False
    if ok:
        findings.append(Finding("I-JOINT", "PASS", "*"))
    return findings


# --- entry points -----------------------------------------------------------------------
_CHECKS = (
    ("I-DEGENERATE", _check_degenerate),
    ("I-SCHEMA", _check_schema),
    ("I-AXIS", _check_axis),
    ("I-GRAPH", _check_graph),
    ("I-ANCHOR", _check_anchor),
    ("I-RIMMATCH", _check_rimmatch),
    ("I-CONT", _check_cont),
    ("I-BRANCHORIENT", _check_branchorient),
    ("I-LOOP", _check_loop),
    ("I-SEAL", _check_seal),
    ("I-JOINT", _check_joint),
)


def validate(graph):
    """Run every invariant class (§6); return findings, never raises.

    Every class in INARIANT_CLASSES appears exactly once with status
    PASS, FAIL or UNVERIFIED. FAIL is a hard error for the caller —
    §7: hard errors, never warnings.
    """
    tols = graph.tolerances if graph.tolerances else dict(TOLERANCES)
    findings = []
    for _, check in _CHECKS:
        findings.extend(check(graph, tols))
    return findings


def validate_strict(graph):
    """validate(), raising GraphValidationError if any class FAILs."""
    findings = validate(graph)
    if any(f.status == "FAIL" for f in findings):
        raise GraphValidationError(findings)
    return findings
