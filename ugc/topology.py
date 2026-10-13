"""Spec v3 invariant engine — ugc.topology (t_8ea48971, C2).

The four v3 invariant classes of DESIGN_V3_TOPOLOGY.md, expressed as
Finding producers over Patch/Junction graphs (same Finding shape as
ugc.primitives §6, so the v2 catalog machinery consumes them as-is):

  I-CHI             Euler closure: sum over patches of (2 - k) must equal
                    the declared chi. Junctions never change chi (they
                    identify curves pairwise). Declared chi defaults to
                    2 - n_free (genus 0, n_free = rims in no junction);
                    a graph may override via graph.declared_chi.
                    g = (2 - chi - n_free) / 2 > 0 is a reserved error in
                    v3: handles don't exist yet, and we say so rather
                    than silently accepting or silently rejecting chi<0.
  I-ORIENT          every junction pair alternates traversal directions
                    (cw/ccw). The Junction constructor already refuses
                    same-direction pairs; this re-check catches
                    post-construction mutation, which the v2 engine
                    treats as a first-class threat (params dicts are
                    mutable). A same-direction identification on two
                    closed rims would glue a Moebius band: non-orientable
                    surfaces are refused via the alternation rule.
  I-REACH           every patch must be reachable from the cast-on patch
                    (lowest patch id — the graph's fabric origin) across
                    the junction graph. Catches floating/unattached
                    patches and disconnected components.
  I-GAUGE-CLOSURE   every junction member rim's loop count
                    (length_mm / gauge.wale_mm, the v2 §6 loop model)
                    must agree across the junction beyond T_LOOPS —
                    v2's pairwise T_LOOPS generalized to junctions of
                    arbitrary (even) arity. Without a gauge the class is
                    UNVERIFIED, exactly like v2 I-LOOP: no gauge, no
                    loop correspondence, and the result says so.

Determinism: findings are content-keyed and sorted by
(invariant, subject, message) before returning; validate() twice on the
same graph yields byte-identical findings.
"""
import ugc.primitives as P

__all__ = ["check_chi", "check_orient", "check_reach",
           "check_gauge_closure", "validate_v3"]

# traversal-opposite lookup: a junction pair must be (cw, ccw) or (ccw, cw)
_OPPOSITE = {"cw": "ccw", "ccw": "cw"}


def _member_span(graph, patch_id, boundary_id):
    """The Boundary a junction member names, or None when missing."""
    try:
        patch = graph.patch(patch_id)
    except KeyError:
        return None
    try:
        return patch.span(boundary_id)
    except KeyError:
        return None


def check_chi(graph, tols):
    findings = []
    patches = graph.patches()
    if not patches:
        # v3 bookkeeping is vacuous without patches (v2-only graph)
        return [P.Finding("I-CHI", "PASS", "*",
                          "no patches: v3 chi bookkeeping not applicable")]
    actual = sum(p.chi_contribution for p in patches)
    free_rims = 0
    claimed = set()
    for j in graph.junctions():
        for patch_id, boundary_id, _ in j.members:
            claimed.add((patch_id, boundary_id))
    for p in patches:
        for b in p.spans:
            if b.kind == "rim" and (p.id, b.boundary) not in claimed:
                free_rims += 1
    g_decl = getattr(graph, "declared_chi", None)
    if g_decl is None:
        # v3 honesty: the closed surface's chi is DECLARED, never
        # inferred — an inferred default would self-adjust under
        # mutation and let tampered graphs pass the closure check
        return [P.Finding(
            "I-CHI", "FAIL", "*",
            "graph declares %d patches but no declared_chi — set "
            "graph.declared_chi (v3: chi is a claim about the closed "
            "surface, 2 - 2g - n_free)" % len(patches))]
    genus = (2 - g_decl - free_rims) / 2.0
    if genus > 0:
        return [P.Finding(
            "I-CHI", "FAIL", "*",
            "declared chi %g with %d free rims implies genus %g — "
            "handles are reserved (not modeled) in v3; declare an "
            "orientable genus-0 surface with free boundary instead"
            % (g_decl, free_rims, genus))]
    if actual != g_decl:
        findings.append(P.Finding(
            "I-CHI", "FAIL", "*",
            "Euler closure violated: sum(2-k) over %d patches = %d, "
            "declared chi = %d (expected %d, actual %d; free rims = %d)"
            % (len(patches), actual, g_decl, g_decl, actual, free_rims)))
        return findings
    findings.append(P.Finding(
        "I-CHI", "PASS", "*",
        "sum(2-k) = %d == declared chi %d over %d patches "
        "(genus 0, %d free rims)" % (actual, g_decl, len(patches),
                                     free_rims)))
    return findings


def check_orient(graph, tols):
    findings = []
    ok = True
    for j in graph.junctions():
        for i in range(0, j.arity, 2):
            a, b = j.members[i], j.members[i + 1]
            if a[2] == b[2] or _OPPOSITE.get(a[2]) != b[2]:
                findings.append(P.Finding(
                    "I-ORIENT", "FAIL", j.id,
                    "junction %r pair %d traverses %r and %r in the same "
                    "direction %r — identification must alternate (cw/ccw) "
                    "or the seam folds the fabric inside-out"
                    % (j.id, i // 2, a[1], b[1], a[2])))
                ok = False
            for patch_id, boundary_id, _ in (a, b):
                if _member_span(graph, patch_id, boundary_id) is None:
                    findings.append(P.Finding(
                        "I-ORIENT", "FAIL", j.id,
                        "junction %r member %r/%r does not resolve on its "
                        "patch" % (j.id, patch_id, boundary_id)))
                    ok = False
    if ok:
        findings.append(P.Finding("I-ORIENT", "PASS", "*"))
    return findings


def check_reach(graph, tols):
    findings = []
    patches = graph.patches()
    if not patches:
        return [P.Finding("I-REACH", "PASS", "*",
                          "no patches: v3 reachability not applicable")]
    # adjacency across junction identifications
    adj = {}
    for j in graph.junctions():
        members = j.members
        for i in range(0, len(members), 2):
            a, b = members[i], members[i + 1]
            adj.setdefault(a[0], set()).add(b[0])
            adj.setdefault(b[0], set()).add(a[0])
    cast_on = min(p.id for p in patches)
    seen = set()
    stack = [cast_on]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(sorted(adj.get(cur, ())))
    unreached = sorted(p.id for p in patches if p.id not in seen)
    if unreached:
        findings.append(P.Finding(
            "I-REACH", "FAIL", unreached[0],
            "patches unreachable from cast-on patch %r across junctions: "
            "%s" % (cast_on, ", ".join(unreached))))
    else:
        findings.append(P.Finding(
            "I-REACH", "PASS", "*",
            "all %d patches reachable from cast-on patch %r"
            % (len(patches), cast_on)))
    return findings


def check_gauge_closure(graph, tols):
    gauge = getattr(graph, "gauge", None)
    if not gauge or "wale_mm" not in gauge:
        return [P.Finding(
            "I-GAUGE-CLOSURE", "UNVERIFIED", "*",
            "no gauge: loop correspondence across junctions not checked")]
    wale = float(gauge["wale_mm"])
    tol = float(tols.get("T_LOOPS", 2))
    findings = []
    checked = False
    ok = True
    for j in graph.junctions():
        counts = []
        for patch_id, boundary_id, _ in j.members:
            b = _member_span(graph, patch_id, boundary_id)
            if b is None:
                continue    # I-ORIENT reports the dangling member
            counts.append((patch_id, boundary_id, b.length_mm / wale))
        if len(counts) != j.arity:
            continue
        checked = True
        head = counts[0][2]
        for patch_id, boundary_id, loops in counts[1:]:
            delta = abs(head - loops)
            if delta > tol:
                findings.append(P.Finding(
                    "I-GAUGE-CLOSURE", "FAIL", j.id,
                    "loop counts differ by %.2f across junction %r: "
                    "%s/%s (%.2f) <-> %s/%s (%.2f) at wale_mm=%g "
                    "(T_LOOPS=%.1f)"
                    % (delta, j.id, counts[0][0], counts[0][1], head,
                       patch_id, boundary_id, loops, wale, tol)))
                ok = False
    if not checked:
        findings.append(P.Finding(
            "I-GAUGE-CLOSURE", "PASS", "*",
            "no junctions: loop closure not applicable"))
    elif ok:
        findings.append(P.Finding(
            "I-GAUGE-CLOSURE", "PASS", "*"))
    return findings


_CHECKS = (
    ("I-CHI", check_chi),
    ("I-ORIENT", check_orient),
    ("I-REACH", check_reach),
    ("I-GAUGE-CLOSURE", check_gauge_closure),
)


def validate_v3(graph):
    """Run the four v3 invariant classes; findings sorted canonically."""
    tols = graph.tolerances or {}
    findings = []
    for _, check in _CHECKS:
        findings.extend(check(graph, tols))
    class_order = {name: i for i, (name, _) in enumerate(_CHECKS)}
    findings.sort(key=lambda f: (class_order.get(f.invariant, 99),
                                 f.subject, f.message))
    return findings
