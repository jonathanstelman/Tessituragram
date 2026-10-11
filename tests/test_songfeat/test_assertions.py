"""Guards against tests that cannot fail.

Several assertions in this suite's own history passed unconditionally -- a
prefix that never matched, an `is not None` that was trivially true for a
real zero, a filtered loop that never iterated. A test that cannot fail is
worse than no test, because it reports coverage it does not provide.

Only the mechanically reliable rules live here. Assertion *strength* needs
judgement: two `is not None` checks in test_vocal_pitch.py are exactly
right, because the proposition under test is literally "this column stays
populated while its sibling goes null". A scanner cannot tell those from
lazy ones, so it does not try. See CLAUDE.md for the review-time checklist.
"""

from __future__ import annotations

import ast
import pathlib

TEST_DIR = pathlib.Path(__file__).parent

#: Helpers that establish a test's verdict without a bare `assert`.
ASSERTING_CALLS = {"raises", "warns", "deprecated_call", "fail", "approx", "xfail"}

#: Tests exempt from the filtered-loop rule, each with a reason. Keep this
#: empty if you can; an entry is a promise that a human checked the case.
FILTERED_LOOP_ALLOWLIST: dict[str, str] = {}


def _test_functions(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                yield node


def _source_files():
    return sorted(p for p in TEST_DIR.glob("test_*.py") if p.name != pathlib.Path(__file__).name)


def test_every_test_function_can_fail():
    """A test with no assertion and no raises/warns asserts nothing."""
    files = _source_files()
    assert files, "found no test modules to scan"

    offenders = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in _test_functions(tree):
            has_assert = any(isinstance(n, ast.Assert) for n in ast.walk(fn))
            called = {
                getattr(n.func, "attr", getattr(n.func, "id", ""))
                for n in ast.walk(fn)
                if isinstance(n, ast.Call)
            }
            if not has_assert and not (called & ASSERTING_CALLS):
                offenders.append(f"{path.name}:{fn.lineno} {fn.name}")

    assert not offenders, (
        "these tests contain no assertion and no raises/warns, so they pass "
        "whatever the code does: " + ", ".join(offenders)
    )


def test_filtered_loops_assert_they_checked_something():
    """An assertion reached only through a filter needs a match guard.

    `for x in xs: if cond: assert ...` asserts nothing when nothing matches
    `cond` -- and nothing in the test says so. The fix is to count matches
    and assert the count, so an empty collection fails loudly.
    """
    files = _source_files()
    assert files, "found no test modules to scan"

    offenders = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in _test_functions(tree):
            key = f"{path.name}::{fn.name}"
            if key in FILTERED_LOOP_ALLOWLIST:
                continue
            if not _has_assert_behind_a_filter(fn):
                continue
            if not _has_unconditional_assert(fn):
                offenders.append(f"{path.name}:{fn.lineno} {fn.name}")

    assert not offenders, (
        "these tests only assert inside a filtered loop, so they pass when the "
        "filter matches nothing; add a guard asserting the match count: "
        + ", ".join(offenders)
    )


def _has_assert_behind_a_filter(fn: ast.AST) -> bool:
    """True when an assertion sits inside an `if` nested in a loop."""
    for node in ast.walk(fn):
        if not isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.If) and any(
                isinstance(n, ast.Assert) for n in ast.walk(inner)
            ):
                return True
    return False


def _has_unconditional_assert(fn: ast.AST) -> bool:
    """True when the function body has an assertion outside any loop or if.

    That is the guard shape: `assert seen, "..."` at statement level, which
    fails when the filtered loop never ran.
    """
    return any(isinstance(stmt, ast.Assert) for stmt in fn.body)
