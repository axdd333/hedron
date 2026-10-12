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
        anchor_point = _require_point(anchor.get("point"), "anchor.point")
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
