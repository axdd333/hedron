"""UGC-01 constraint checker: ugc.validation (t_ff7ea486).

Spec v2 §6/§7 wrapper around the ugc.primitives invariant engine. Delivers
the card contract: validate(graph) -> ValidationResult with .ok, .errors[]
and a stable error-code catalog (code = spec I-* class, kind = catalog
slug), numeric expected/actual where the failure is numeric, deterministic
ordering, no LLM anywhere.

Catalog (code, kind):
  I-DEGENERATE  param_nonpositive     a linear param <= 0 mm
                param_nonfinite       a param is not a finite number
                coord_nonfinite       origin has a non-finite coordinate
                axis_nonfinite        axis has a non-finite coordinate
                axis_zero             axis norm <= T_AXIS_EPS
                kind_unknown          primitive kind not in KINDS
                joint_type_unknown    joint type not in JOINT_TYPES
                construction_unknown  construction not in CONSTRUCTIONS
                duplicate_prim_id     two primitives share an id
  I-SCHEMA      duplicate_joint_id    two joints share an id
                duplicate_op_id       two ops share an id
                unresolved_primitive_ref  joint endpoint not a known prim
                unresolved_boundary_ref   joint/op boundary does not resolve
                unresolved_open_boundary  open_boundaries ref does not resolve
  I-AXIS        axis_norm             |axis| != 1 beyond T_AXIS_EPS
  I-GRAPH       root_count            roots != 1 (ids = roots found)
                unreachable           prims not reachable from the root
                multiple_parents      a prim claimed by two parent joints
  I-RIMMATCH    rim_length_mismatch   |child rim - parent rim| > T_RIM mm
  I-CONT        radius_step           |dr| > T_RIM mm across a continuation
                axis_turn             |turn| > MAX_CONT_TURN_DEG
  I-BRANCHORIENT branch_into_material child axis . outward normal < 0
  I-LOOP        loop_mismatch         loop counts differ across a
                                      loop-bearing op beyond T_LOOPS
  I-SEAL        inert_consumed        an inert boundary consumed by an op
                floating_rim          knit-bearing rim with no op, not open
                conflicting_states    rim in >1 of produced/consumed/open
                multi_consumed        rim consumed by >1 op
                multi_produced        rim produced by >1 op
  I-JOINT       construction_illegal  construction illegal for the joint
                anchor_feature_mismatch  anchor feature != joint type's
                op_pattern_mismatch   realized_by ops violate the pattern
  I-ANCHOR      anchor_off_feature    anchor.point off feature > T_ANCHOR mm

§7 hard errors (degenerate geometry/schema violations) short-circuit the
engine: the result is fatal and reports I-DEGENERATE/I-SCHEMA verdicts
only. The engine itself never sees a graph that could raise mid-walk.
"""
import math

import ugc.primitives as P

__all__ = ["validate", "ValidationResult", "ValidationError"]

_LINEAR_KEYS = ("r1", "r2", "l", "r", "rx", "ry", "rz", "w", "h")
_UNRESOLVED = "does not resolve"


# ---------------------------------------------------------------------------
# result types
# ---------------------------------------------------------------------------
class ValidationError(object):
    """One cataloged failure: code (spec class) x kind (catalog slug)."""

    __slots__ = ("code", "kind", "ids", "message", "expected", "actual")

    def __init__(self, code, kind, ids, message, expected=None, actual=None):
        self.code = code
        self.kind = kind
        self.ids = tuple(ids)
        self.message = message
        self.expected = expected
        self.actual = actual

    def as_tuple(self):
        return (self.code, self.kind, self.ids, self.message,
                self.expected, self.actual)

    def to_dict(self):
        d = {"code": self.code, "kind": self.kind, "ids": list(self.ids),
             "message": self.message}
        if self.expected is not None:
            d["expected"] = self.expected
        if self.actual is not None:
            d["actual"] = self.actual
        return d

    def __repr__(self):
        return ("ValidationError(code=%r, kind=%r, ids=%r)"
                % (self.code, self.kind, self.ids))


class ValidationResult(object):
    """validate() outcome: engine findings + cataloged errors."""

    def __init__(self, findings, errors, fatal):
        self.findings = list(findings)
        self.errors = list(errors)
        self._fatal = bool(fatal)

    @property
    def ok(self):
        return not self.errors

    @property
    def fatal(self):
        return self._fatal

    def to_dict(self):
        return {"ok": self.ok, "fatal": self._fatal,
                "errors": [e.to_dict() for e in self.errors],
                "findings": [{"invariant": f.invariant, "status": f.status,
                              "subject": f.subject, "message": f.message}
                             for f in self.findings]}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _is_number(v):
    return not isinstance(v, bool) and isinstance(v, (int, float))


def _kind_of(prim, boundary_id):
    for b in prim.boundaries:
        if b.boundary == boundary_id:
            return b.kind
    return None


def _by_id(g):
    return {p.id: p for p in g}


def _sorted_union(*seqs):
    out = set()
    for s in seqs:
        out.update(s)
    return tuple(sorted(out))


def _roots_and_children(joints):
    """parents -> children map plus each prim's parent count/roots."""
    children = {}
    parent_count = {}
    for j in joints:
        children.setdefault(j.parent, set()).add(j.child)
        parent_count[j.child] = parent_count.get(j.child, 0) + 1
    return children, parent_count


# ---------------------------------------------------------------------------
# §7 fatal pre-scan: I-DEGENERATE + I-SCHEMA on the raw graph
# ---------------------------------------------------------------------------
def _prescan(g):
    errors = []

    # -- duplicate ids -------------------------------------------------------
    seen = set()
    for p in g:
        if p.id in seen:
            errors.append(ValidationError(
                "I-DEGENERATE", "duplicate_prim_id", (p.id,),
                "duplicate primitive id %r" % (p.id,)))
        seen.add(p.id)
    jids = [j.id for j in g.joints()]
    for jid in sorted(set(x for x in jids if jids.count(x) > 1)):
        errors.append(ValidationError(
            "I-SCHEMA", "duplicate_joint_id", (jid,),
            "duplicate joint id %r" % (jid,)))
    oids = [o.id for o in g.ops]
    for oid in sorted(set(x for x in oids if oids.count(x) > 1)):
        errors.append(ValidationError(
            "I-SCHEMA", "duplicate_op_id", (oid,),
            "duplicate op instance id %r" % (oid,)))

    # -- primitive degeneracy (§7) -------------------------------------------
    known_kinds = set(P.PRIMITIVE_KINDS)
    for p in g:
        if p.kind not in known_kinds:
            errors.append(ValidationError(
                "I-DEGENERATE", "kind_unknown", (p.id,),
                "%s.kind %r not in KINDS" % (p.id, p.kind)))
        for key, val in sorted(p.params.items()):
            if key in _LINEAR_KEYS:
                if not _is_number(val) or not math.isfinite(val):
                    errors.append(ValidationError(
                        "I-DEGENERATE", "param_nonfinite", (p.id,),
                        "%s.%s must be a finite number, got %r"
                        % (p.id, key, val)))
                elif val <= 0:
                    errors.append(ValidationError(
                        "I-DEGENERATE", "param_nonpositive", (p.id,),
                        "%s.%s must be > 0 mm, got %r" % (p.id, key, val)))
        if not all(math.isfinite(c) for c in p.origin):
            errors.append(ValidationError(
                "I-DEGENERATE", "coord_nonfinite", (p.id,),
                "%s.origin has a non-finite coordinate" % (p.id,)))
        if not all(math.isfinite(c) for c in p.axis):
            errors.append(ValidationError(
                "I-DEGENERATE", "axis_nonfinite", (p.id,),
                "%s.axis has a non-finite coordinate" % (p.id,)))
        else:
            n = math.sqrt(sum(c * c for c in p.axis))
            if n <= g.tolerances["T_AXIS_EPS"]:
                errors.append(ValidationError(
                    "I-DEGENERATE", "axis_zero", (p.id,),
                    "%s.axis norm %r at or below T_AXIS_EPS=%g"
                    % (p.id, n, g.tolerances["T_AXIS_EPS"]),
                    expected=1.0, actual=n))

    # -- joint degeneracy (engine-blind via mutation) -------------------------
    known_joints = set(P.JOINT_TYPES)
    known_cons = set(P.CONSTRUCTIONS)
    for j in g.joints():
        if j.joint not in known_joints:
            errors.append(ValidationError(
                "I-DEGENERATE", "joint_type_unknown", (j.id,),
                "%s.joint %r not in JOINT_TYPES" % (j.id, j.joint)))
        if j.construction not in known_cons:
            errors.append(ValidationError(
                "I-DEGENERATE", "construction_unknown", (j.id,),
                "%s.construction %r not in CONSTRUCTIONS"
                % (j.id, j.construction)))

    # -- reference resolution (I-SCHEMA) --------------------------------------
    # Degenerate params (r<=0, non-finite) make p.boundaries raise
    # PrimitiveError inside the engine; skip resolution checks when the
    # degeneracy scan already failed -- the fatal short-circuit below
    # keeps the engine from ever seeing this graph.
    degenerate = any(e.code == "I-DEGENERATE" for e in errors)
    if degenerate:
        return errors
    prim_ids = set(_by_id(g))
    known_bounds = {}
    for p in g:
        try:
            known_bounds[p.id] = set(b.boundary for b in p.boundaries)
        except P._BaseError:
            known_bounds[p.id] = set()
    for j in g.joints():
        where = "joint %r" % (j.id,)
        for role, pid in (("child", j.child), ("parent", j.parent)):
            if pid not in prim_ids:
                errors.append(ValidationError(
                    "I-SCHEMA", "unresolved_primitive_ref", (j.id, pid),
                    "%s %s %r %s" % (where, role, pid, _UNRESOLVED)))
        for pid, bid in ((j.child, j.child_boundary),
                         (j.parent, j.parent_boundary)):
            if pid in known_bounds and bid is not None \
                    and bid not in known_bounds[pid]:
                errors.append(ValidationError(
                    "I-SCHEMA", "unresolved_boundary_ref",
                    (j.id, "%s/%s" % (pid, bid)),
                    "%s boundary %r on %r %s"
                    % (where, bid, pid, _UNRESOLVED)))
    for op in g.ops:
        for ref in op.consumes + ([op.produces] if op.produces else []):
            pid, _, bid = ref.partition("/")
            if pid not in known_bounds or bid not in known_bounds[pid]:
                errors.append(ValidationError(
                    "I-SCHEMA", "unresolved_boundary_ref", (op.id, ref),
                    "op %r boundary ref %r %s" % (op.id, ref, _UNRESOLVED)))
    for ref in g.open_boundaries:
        pid, _, bid = ref.partition("/")
        if pid not in known_bounds or bid not in known_bounds[pid]:
            errors.append(ValidationError(
                "I-SCHEMA", "unresolved_open_boundary", (ref,),
                "open_boundaries ref %r %s" % (ref, _UNRESOLVED)))
    return errors


# ---------------------------------------------------------------------------
# I-GRAPH: root uniqueness + reachability (card class 1, lists orphans)
# ---------------------------------------------------------------------------
def _check_graph(g):
    errors = []
    joints = g.joints()
    prims = list(g)
    prim_ids = set(p.id for p in prims)
    children, parent_count = _roots_and_children(joints)
    roots = sorted(pid for pid in prim_ids if parent_count.get(pid, 0) == 0)
    if len(roots) != 1:
        errors.append(ValidationError(
            "I-GRAPH", "root_count", tuple(roots) if roots else tuple(),
            "expected exactly 1 root, found %d" % len(roots),
            expected=1, actual=len(roots)))
    if roots:
        reach = set()
        stack = [roots[0]]
        while stack:
            cur = stack.pop()
            if cur in reach:
                continue
            reach.add(cur)
            stack.extend(sorted(children.get(cur, ())))
        orphans = sorted(prim_ids - reach)
        if orphans:
            errors.append(ValidationError(
                "I-GRAPH", "unreachable", tuple(orphans),
                "unreachable from root: %s" % ", ".join(orphans),
                expected=0, actual=len(orphans)))
    multi = sorted(pid for pid, n in parent_count.items() if n > 1)
    for pid in multi:
        errors.append(ValidationError(
            "I-GRAPH", "multiple_parents", (pid,),
            "%s claimed by %d parent joints" % (pid, parent_count[pid]),
            expected=1, actual=parent_count[pid]))
    return errors


# ---------------------------------------------------------------------------
# engine findings -> catalog
# ---------------------------------------------------------------------------
_MSG_MARKERS = (
    # (substring of engine message, kind) -- order matters: first hit wins
    ("rim lengths differ", "rim_length_mismatch"),
    ("radius step", "radius_step"),
    ("axis turn", "axis_turn"),
    ("points into parent material", "branch_into_material"),
    ("loop counts differ", "loop_mismatch"),
    ("inert boundary consumed", "inert_consumed"),
    ("floating knit-bearing rim", "floating_rim"),
    ("conflicting states", "conflicting_states"),
    ("consumed by", "multi_consumed"),
    ("produced by", "multi_produced"),
    ("requires anchor feature", "anchor_feature_mismatch"),
    ("construction", "construction_illegal"),
    ("pick_up", "op_pattern_mismatch"),
    ("graft consuming", "op_pattern_mismatch"),
    ("selvedge_seam consuming", "op_pattern_mismatch"),
    ("requires no parent_boundary", "op_pattern_mismatch"),
    ("anchor point off", "anchor_off_feature"),
    ("anchor references unknown boundary", "unresolved_boundary_ref"),
    ("anchor feature invalid", "anchor_feature_mismatch"),
    ("axis norm", "axis_norm"),
    ("duplicate joint id", "duplicate_joint_id"),
    ("duplicate op instance id", "duplicate_op_id"),
    ("open_boundaries ref unknown", "unresolved_open_boundary"),
    ("multiple parents", "multiple_parents"),
    ("root", "root_count"),
    ("does not resolve", "unresolved_boundary_ref"),
    ("not a finite number", "param_nonfinite"),
    ("non-finite coordinate", "coord_nonfinite"),
)


def _marker_kind(message):
    for needle, kind in _MSG_MARKERS:
        if needle in message:
            return kind
    return "engine_finding"


def _numbers_from(message):
    """Pull (expected, actual) numerics out of engine messages that carry
    a 'X=...' tolerance and a leading measured number."""
    import re
    m = re.search(r"by (-?\d+\.?\d*) mm \(T_RIM=(-?\d+\.?\d*)\)", message)
    if m:
        return float(m.group(2)), float(m.group(1))
    m = re.search(r"step (-?\d+\.?\d*) mm exceeds T_RIM=(-?\d+\.?\d*)",
                  message)
    if m:
        return float(m.group(2)), float(m.group(1))
    m = re.search(r"turn (-?\d+\.?\d*) deg exceeds "
                  r"MAX_CONT_TURN_DEG=(-?\d+\.?\d*)", message)
    if m:
        return float(m.group(2)), float(m.group(1))
    m = re.search(r"norm (-?[0-9.eE+-]+) beyond T_AXIS_EPS", message)
    if m:
        return 1.0, float(m.group(1))
    m = re.search(r"loop counts differ by (-?\d+\.?\d*) across "
                  r"(\S+) <-> (\S+) \(T_LOOPS=(-?\d+\.?\d*)\)", message)
    if m:
        return float(m.group(4)), float(m.group(1))
    m = re.search(r"by (-?\d+\.?\d*) mm \(T_ANCHOR=(-?\d+\.?\d*)\)", message)
    if m:
        return float(m.group(2)), float(m.group(1))
    m = re.search(r"(?:rim )?consumed by (\d+) ops", message)
    if m:
        return 1, int(m.group(1))
    m = re.search(r"(?:rim )?produced by (\d+) ops", message)
    if m:
        return 1, int(m.group(1))
    m = re.search(r"\(axis \. normal = (-?\d+\.?\d*)\)", message)
    if m:
        return 0.0, float(m.group(1))
    m = re.search(r"beyond T_LOOPS=(\d+)", message)
    if m:
        return float(m.group(1)), None
    return None, None


def _map_engine_findings(findings, g):
    """Engine FAILs for the non-fatal classes -> ValidationError records."""
    mapped = []
    fatal_codes = ("I-DEGENERATE", "I-SCHEMA")
    by_id = _by_id(g)
    for f in findings:
        if f.status != "FAIL":
            continue
        if f.invariant in fatal_codes:
            continue    # pre-scan already reported (or short-circuited)
        kind = _marker_kind(f.message)
        expected, actual = _numbers_from(f.message)
        ids = (f.subject,) if f.subject != "*" else tuple()
        # subject may be a prim id, joint id, op id, or 'prim/boundary'
        if kind in ("root_count", "multiple_parents"):
            ids = tuple(s for s in (f.subject,) if s in by_id) or ids
        if f.invariant == "I-GRAPH" and kind == "root_count":
            continue    # own walk above is authoritative (lists roots)
        if f.invariant == "I-GRAPH" and kind == "multiple_parents":
            continue    # own walk above is authoritative
        mapped.append(ValidationError(f.invariant, kind, ids,
                                      f.message, expected, actual))
    return mapped


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def validate(graph):
    """Validate a UGPGraph -> ValidationResult (never raises on graph
    content; only on non-UGPGraph arguments). Errors and findings are
    ordered canonically: (code, kind, ids, message) resp. (class order,
    subject, message) -- independent of graph insertion order."""
    if not isinstance(graph, P.UGPGraph):
        raise TypeError("validate() expects a UGPGraph, got %s"
                        % type(graph).__name__)
    pre = _prescan(graph)
    fatal = any(e.code in ("I-DEGENERATE", "I-SCHEMA") for e in pre)
    if fatal:
        # §7: hard errors short-circuit; report degenerate/schema only
        pre.sort(key=lambda e: (e.code, e.kind, e.ids, e.message))
        return ValidationResult([], pre, True)
    findings = P.validate(graph)
    errors = _check_graph(graph) + _map_engine_findings(findings, graph)
    errors.sort(key=lambda e: (e.code, e.kind, e.ids, e.message))
    class_order = {name: i for i, name in enumerate(P.INARIANT_CLASSES)}
    findings.sort(key=lambda f: (class_order.get(f.invariant, 99),
                                 f.subject, f.message))
    return ValidationResult(findings, errors, False)


def validate_strict(graph):
    """validate() + raise GraphValidationError carrying the engine findings
    plus one Finding per cataloged error."""
    result = validate(graph)
    if not result.ok:
        findings = list(result.findings)
        for e in result.errors:
            if not any(f.invariant == e.code and f.subject in (e.ids or ("*",))
                       for f in findings):
                findings.append(P.Finding(e.code, "FAIL",
                                          e.ids[0] if e.ids else "*",
                                          e.message))
        raise P.GraphValidationError(findings)
    return result
