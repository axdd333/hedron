"""ugc CLI — lower U-01 garment families to machine-op programs.

Usage:
    python -m ugc <family> [--backend <id>] [--stats]
    python -m ugc --all  [--backend <id>]
    python -m ugc lower --graph <graph.json> [--backend <id>] [--stats]

Exit codes: 0 ok, 2 usage/validation refusal (backend refused to lower —
catalog errors go to stderr), 1 crash.
"""
import argparse
import json
import sys

from .garments import GARMENT_FAMILIES, build_garment
from .backend import (BackendError, BackendNotApplicable, lower,
                      lower_ops, garment_stats, lowered_to_json)
from .primitives import RegistryError, UGPGraph


def _build_parser():
    ap = argparse.ArgumentParser(
        prog="ugc",
        description="Lower U-01 garment families to a machine-op program.")
    ap.add_argument("family", nargs="?", default=None,
                    help="garment family (%s), or the verb 'lower' with "
                         "--graph" % ", ".join(sorted(GARMENT_FAMILIES)))
    ap.add_argument("--all", action="store_true",
                    help="lower every family")
    ap.add_argument("--backend", default="default_knit",
                    help="backend id (default: default_knit)")
    ap.add_argument("--stats", action="store_true",
                    help="print the statistical judgment ledger only")
    ap.add_argument("--graph", default=None,
                    help="lower a graph JSON file instead of a family")
    return ap


def main(argv=None):
    ap = _build_parser()
    args = ap.parse_args(list(argv) if argv is not None else None)

    def _usage_error(msg):
        sys.stderr.write("error: %s\n" % msg)
        return 2

    family = args.family
    if family == "lower":
        family = None          # 'lower' is the graph-lowering verb
    if family and args.graph:
        return _usage_error("give a family or --graph, not both")
    if args.all and (family or args.graph):
        return _usage_error("--all cannot be combined with a family or "
                            "--graph")

    if args.graph:
        try:
            with open(args.graph, "r") as fh:
                graph = UGPGraph.from_json(fh.read())
        except (OSError, ValueError) as exc:
            return _usage_error("cannot load graph %r: %s"
                                % (args.graph, exc))
    elif args.all:
        try:
            lower_ops(args.backend)   # RegistryError -> exit 2 before output
        except RegistryError as exc:
            return _usage_error(str(exc))
        entries = []
        for fam in sorted(GARMENT_FAMILIES):
            fam_result = lower(build_garment(fam, 1.0), backend=args.backend)
            entries.append({"family": fam,
                            "result": fam_result.to_dict()})
        sys.stdout.write(json.dumps(entries, indent=2, sort_keys=True) + "\n")
        return 0
    elif family:
        if family not in GARMENT_FAMILIES:
            return _usage_error(
                "unknown family %r; valid families: %s"
                % (family, ", ".join(sorted(GARMENT_FAMILIES))))
        graph = build_garment(family, 1.0)
    else:
        return _usage_error(
            "nothing to lower: give a family (%s), --all, or "
            "--graph <file>" % ", ".join(sorted(GARMENT_FAMILIES)))

    try:
        result = lower(graph, backend=args.backend)
    except BackendNotApplicable as exc:
        sys.stderr.write("BackendNotApplicable: %s\n"
                         "catalog errors:\n" % (exc,))
        for err in exc.result.errors:
            sys.stderr.write("  %s\n" % (err,))
        return 2
    except (RegistryError, BackendError) as exc:
        return _usage_error(str(exc))

    if args.stats:
        sys.stdout.write(json.dumps(garment_stats(graph, result),
                                    indent=2, sort_keys=True) + "\n")
        return 0

    envelope = json.loads(lowered_to_json(result))
    envelope["graph"] = graph.to_dict()
    if family:
        envelope["family"] = family
    sys.stdout.write(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
