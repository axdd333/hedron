"""Pipeline CLI — ugc.cli (t_553af028).

A command-line front door for the UGP pipeline: families / build /
validate / plan / report. Thin on purpose — every payload comes from the
library's own to_dict()/to_json() shapes, no renames, no re-shapes, no
fabricated fields.

Contract
--------
1. Exit codes (this cycle's decision log):
     0  success;
     1  build/plan/report refused — the graph failed the invariant
        catalog (BackendNotApplicable path); the refusal payload embeds
        the same errors/findings the validate subcommand would print;
     2  usage error — unknown family, unknown backend, non-positive or
        non-numeric --scale, missing/unreadable graph file, malformed
        JSON, wrong graph version, missing input, bad subcommand;
     3  the library raised an unexpected exception (programmer bug, not
        a property of the graph) — traceback on stderr, nothing partial
        on stdout.
2. Usage errors are the CLI's own; graph-content failures belong to the
   catalog and exit 1. Schema-level refusals from UGPGraph.from_dict
   (version mismatch, unknown collections, malformed entities) are
   input-shape problems and exit 2.
3. --json prints machine-readable JSON (validate/report: the
   ValidationResult dict; plan: the versioned lowering envelope identical
   to lowered_to_json output; build: family + scale + graph.to_dict();
   families: the sorted family list). Refusal payloads (exit 1) are JSON
   too, with the refused slot ("plan"/"report") set to null.
4. Family names are case-insensitive ("SOCK" == "sock"); --scale must be
   a positive finite number and applies to linear params and origins via
   build_garment, never by post-hoc mutation.
5. Determinism: identical input -> identical bytes. json.dumps uses
   sort_keys=True everywhere; nothing is sourced from wall clock or
   dict iteration order.
"""
import argparse
import json
import math
import sys
import traceback

from ugc.backend import BackendNotApplicable, lowered_to_json
from ugc.garments import GARMENT_FAMILIES, build_garment
from ugc.primitives import (JointError, OpError, PrimitiveError,
                            RegistryError, SchemaError, UGPGraph)
from ugc.validation import validate

__all__ = ["main"]

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2
EXIT_BUG = 3

_GRAPH_ERRORS = (SchemaError, PrimitiveError, JointError, OpError,
                 KeyError, TypeError, ValueError)


class _UsageError(Exception):
    """Bad invocation — the caller's fault, not the graph's."""


# ---------------------------------------------------------------------------
# shared argument plumbing
# ---------------------------------------------------------------------------
def _add_graph_input(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--graph", metavar="PATH",
                       help="graph JSON file (version 2)")
    group.add_argument("--graph-json", metavar="JSON",
                       help="graph JSON inline")


def _resolve_family(raw):
    family = (raw or "").strip().lower()
    if family not in GARMENT_FAMILIES:
        raise _UsageError(
            "unknown family %r; families: %s"
            % (raw, ", ".join(sorted(GARMENT_FAMILIES))))
    return family


def _parse_scale(raw):
    try:
        scale = float(raw)
    except (TypeError, ValueError):
        raise _UsageError("--scale must be a number, got %r" % (raw,))
    if not math.isfinite(scale) or scale <= 0:
        raise _UsageError(
            "--scale must be positive and finite, got %s" % (raw,))
    return scale


def _check_backend(backend):
    from ugc.primitives import backend_ids
    if backend not in backend_ids():
        raise _UsageError(
            "unknown backend %r; available: %s"
            % (backend, ", ".join(sorted(backend_ids()))))


def _load_graph(args):
    """Build a UGPGraph from --graph PATH or --graph-json JSON.

    Input-shape problems (unreadable file, bad JSON, wrong version,
    malformed entities) are usage errors; graph-content problems are
    left to the validation catalog.
    """
    if bool(args.graph) == bool(getattr(args, "graph_json", None)):
        raise _UsageError(
            "provide exactly one graph input: --graph PATH or "
            "--graph-json JSON")
    if args.graph:
        where = args.graph
        try:
            with open(where, "r", encoding="utf-8") as fh:
                blob = fh.read()
        except OSError as exc:
            raise _UsageError("cannot read graph file %s: %s"
                              % (where, exc))
    else:
        blob = args.graph_json
        where = "--graph-json"
    try:
        data = json.loads(blob)
    except ValueError as exc:
        raise _UsageError("invalid JSON in %s: %s" % (where, exc))
    if not isinstance(data, dict):
        raise _UsageError("graph in %s must be a JSON object" % (where,))
    try:
        return UGPGraph.from_dict(data)
    except _GRAPH_ERRORS as exc:
        raise _UsageError("unsupported graph in %s: %s" % (where, exc))


def _resolve_target(args):
    """A graph for plan/report: --graph/--graph-json wins over FAMILY."""
    has_graph = bool(args.graph or getattr(args, "graph_json", None))
    family = getattr(args, "family", None)
    if has_graph and family:
        raise _UsageError("give a FAMILY or a graph input, not both")
    if has_graph:
        return _load_graph(args), "graph"
    if family:
        return build_garment(_resolve_family(family), 1.0), family
    raise _UsageError("provide a FAMILY or a graph input "
                      "(--graph PATH / --graph-json JSON)")


def _dump(payload):
    return json.dumps(payload, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# subcommands
# ---------------------------------------------------------------------------
def cmd_families(args):
    families = sorted(GARMENT_FAMILIES)
    if args.json:
        print(_dump(families))
        return EXIT_OK
    print("ugc garment families (%d):" % len(families))
    for fam in families:
        print("  %s" % fam)
    return EXIT_OK


def cmd_build(args):
    family = _resolve_family(args.family)
    scale = _parse_scale(args.scale)
    graph = build_garment(family, scale)
    if args.json:
        print(_dump({"family": family, "scale": scale,
                     "graph": graph.to_dict()}))
        return EXIT_OK
    prim_ids = [p.id for p in graph]
    joint_count = sum(1 for _ in graph.joints())
    print("built: %s (scale %s)" % (family, scale))
    print("pieces: %d (%s)" % (len(prim_ids), ", ".join(prim_ids)))
    print("joints: %d" % joint_count)
    print("units: mm; params are the family's real values, no placeholders")
    return EXIT_OK


def cmd_validate(args):
    graph = _load_graph(args)
    result = validate(graph)
    print(_dump(result.to_dict()))
    return EXIT_OK if result.ok else EXIT_REFUSED


def _refusal_payload(exc, slot):
    """Exit-1 payload: the refused slot is null, the evidence is the
    exact ValidationResult dict (errors + findings, no renames)."""
    payload = {slot: None}
    payload.update(exc.result.to_dict())
    return payload


def _render_plan_text(result, source_desc, backend):
    lines = ["plan: %s -> backend %s" % (source_desc, backend)]
    lines.append("reference machine ops: %s"
                 % ", ".join(result.machine_ops))
    lines.append("program (%d ops):" % len(result.ops))
    for lo in result.ops:
        line = "  %-14s %-16s -> %s" % (lo.graph_op, lo.op,
                                        "+".join(lo.machine_ops))
        if lo.consumes:
            line += "  consumes %s" % ",".join(lo.consumes)
        if lo.produces:
            line += "  produces %s" % lo.produces
        lines.append(line)
    stats = result.stats
    lines.append("pieces: %d  joints: %d  open boundaries: %s"
                 % (stats["piece_count"], stats["joint_count"],
                    stats["open_boundaries"] or "none"))
    lines.append("verdict: %s" % stats["machine_verdict"])
    for note in stats["notes"]:
        lines.append("note: %s" % note)
    return "\n".join(lines)


def cmd_plan(args):
    _check_backend(args.backend)
    graph, source_desc = _resolve_target(args)
    try:
        result = lower(graph, backend=args.backend)
    except BackendNotApplicable as exc:
        print(_dump(_refusal_payload(exc, "plan")))
        return EXIT_REFUSED
    if args.json:
        sys.stdout.write(lowered_to_json(result) + "\n")
    else:
        print(_render_plan_text(result, source_desc, args.backend))
    return EXIT_OK


def cmd_report(args):
    _check_backend(args.backend)
    graph, source_desc = _resolve_target(args)
    result = validate(graph)
    base = result.to_dict()
    if not result.ok:
        payload = {"report": None, "backend": args.backend}
        payload.update(base)
        print(_dump(payload))
        return EXIT_REFUSED
    from ugc.primitives import buildability_report
    report = buildability_report(graph, args.backend)
    payload = dict(report)
    payload["report"] = None
    payload["backend"] = report["backend"]
    payload.update(base)
    payload["ok"] = True
    payload["fatal"] = False
    payload["errors"] = []
    if args.json:
        print(_dump(payload))
        return EXIT_OK
    print("report: %s -> backend %s" % (source_desc, report["backend"]))
    print("geometric_validity: %s" % report["geometric_validity"])
    for inv in sorted(report["per_class"]):
        print("  %-15s %s" % (inv, report["per_class"][inv]))
    checks = report["backend_checks"]
    unverified = report["backend_unverified"]
    if checks:
        print("backend re-verifies: %s" % ", ".join(sorted(checks)))
    if unverified:
        print("backend trusts upstream: %s" % ", ".join(sorted(unverified)))
    print("note: %s" % report["note"])
    return EXIT_OK


from ugc.backend import lower  # noqa: E402  (kept after cmd defs for doc flow)


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def _build_parser():
    parser = argparse.ArgumentParser(
        prog="ugc",
        description="UGP pipeline CLI: build a family graph, validate it "
                    "against the spec-v2 invariant catalog, lower it to a "
                    "reference machine-op plan, and report per-class "
                    "buildability. See DESIGN.md §6/§8.")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p = sub.add_parser("families", help="list the U-01 garment families")
    p.add_argument("--json", action="store_true",
                   help="print the sorted family list as JSON")
    p.set_defaults(func=cmd_families)

    p = sub.add_parser("build", help="build a family graph (mm)")
    p.add_argument("family", help="garment family (see families)")
    p.add_argument("--scale", default="1.0",
                   help="positive finite scale factor (default 1.0)")
    p.add_argument("--json", action="store_true",
                   help="print family + scale + graph.to_dict() as JSON")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("validate", help="run the invariant catalog on a graph")
    _add_graph_input(p)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("plan",
                       help="lower a family or graph to machine ops")
    p.add_argument("family", nargs="?", default=None,
                   help="garment family (see families)")
    p.add_argument("--backend", default="default_knit",
                   help="backend id (default: default_knit)")
    _add_graph_input(p)
    p.add_argument("--json", action="store_true",
                   help="print the versioned lowering envelope (JSON)")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("report",
                       help="per-invariant-class buildability report")
    p.add_argument("family", nargs="?", default=None,
                   help="garment family (see families)")
    p.add_argument("--backend", default="default_knit",
                   help="backend id (default: default_knit)")
    _add_graph_input(p)
    p.add_argument("--json", action="store_true",
                   help="print the report dict (JSON)")
    p.set_defaults(func=cmd_report)
    return parser


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    try:
        return args.func(args)
    except _UsageError as exc:
        sys.stderr.write("ugc: error: %s\n" % exc)
        parser.print_usage(sys.stderr)
        return EXIT_USAGE
    except Exception:                      # unexpected library failure
        traceback.print_exc()
        sys.stderr.write("ugc: internal error (exit 3)\n")
        return EXIT_BUG


if __name__ == "__main__":
    sys.exit(main())
