"""LOC accounting — programmatic evidence for the RESULTS.md headline.

Counts, via ast (never wc -l), the shared representation against the
per-family builders, and the negative-path tests across the suite.
"""
import ast
import os
import re

SHARED_FILES = ("ugc/primitives.py", "ugc/validation.py", "ugc/backend.py")
PER_FAMILY_FILE = "ugc/garments.py"


def ast_code_lines(path):
    """Lines covered by ast statements, minus blank/comment-only lines.

    Multi-line statements count every line of their span (the cost of
    reading them is real), which wc -l over-credits and grep under-counts.
    """
    src = open(path).read()
    tree = ast.parse(src)
    covered = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt) and node.end_lineno is not None:
            covered.update(range(node.lineno, node.end_lineno + 1))
    for i, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            covered.discard(i)
    return len(covered)


def total_lines(path):
    return len(open(path).read().splitlines())


def repo_counts(repo):
    """The RESULTS.md headline numbers, measured, not asserted."""
    shared_total = sum(total_lines(os.path.join(repo, f)) for f in SHARED_FILES)
    shared_code = sum(ast_code_lines(os.path.join(repo, f)) for f in SHARED_FILES)
    pf_total = total_lines(os.path.join(repo, PER_FAMILY_FILE))
    pf_code = ast_code_lines(os.path.join(repo, PER_FAMILY_FILE))
    return {
        "shared_files": list(SHARED_FILES),
        "shared_total": shared_total,
        "shared_code": shared_code,
        "per_family_file": PER_FAMILY_FILE,
        "per_family_total": pf_total,
        "per_family_code": pf_code,
        "ratio_code": round(shared_code / pf_code, 2),
        "ratio_total": round(shared_total / pf_total, 2),
    }


# Negative-path detection: ast over test functions, matching the same
# markers a reviewer would (assertFalse .ok, error-code assertions,
# BackendNotApplicable refusals, forbidden-value asserts).
_NEG_MARKERS = (
    re.compile(r"assertFalse|assertIs\s+Not|assertRaises|assertLogs"),
    re.compile(r"\.ok,\s*False|\.ok\s+is\s+False"),
    re.compile(r"assertIn\([^)]*I-[A-Z]+"),
    re.compile(r"assertEqual\([^)]*\.code"),
    re.compile(r"BackendNotApplicable"),
)


def _is_negative_path(test_src):
    return any(m.search(test_src) for m in _NEG_MARKERS)


def negative_path_tests(repo):
    """Count test_* functions exercising rejection paths across the suite."""
    n = 0
    tests_dir = os.path.join(repo, "tests")
    for name in sorted(os.listdir(tests_dir)):
        if not name.endswith(".py"):
            continue
        src = open(os.path.join(tests_dir, name)).read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
                body = ast.get_source_segment(src, node) or ""
                if _is_negative_path(body):
                    n += 1
    return n
