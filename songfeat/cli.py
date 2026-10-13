"""Command line entry point: files or folders in, a feature table out."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable

from .features import registry, schema
from .loaders import SUPPORTED_EXTENSIONS, load
from .pipeline import run
from .sinks.base import MemorySink
from .sinks.files import CsvSink, JsonSink, JsonlSink


def iter_score_files(paths: Iterable[str], recursive: bool = True) -> list[str]:
    """Expand files and directories into a sorted list of score files."""
    found: list[str] = []
    for path in paths:
        if os.path.isdir(path):
            walker = os.walk(path) if recursive else [(path, [], os.listdir(path))]
            for root, _dirs, names in walker:
                for name in names:
                    if os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS:
                        found.append(os.path.join(root, name))
        else:
            found.append(path)
    return sorted(set(found))


def make_sink(out: str | None, fmt: str | None):
    """Pick a sink from --out and --format. Defaults to jsonl on stdout."""
    if out and not fmt:
        ext = os.path.splitext(out)[1].lower()
        fmt = {".csv": "csv", ".json": "json", ".jsonl": "jsonl"}.get(ext, "jsonl")
    fmt = fmt or "jsonl"
    if fmt == "sheets":
        if not out:
            raise SystemExit("--format sheets requires -o/--out with a spreadsheet id or URL")
        from .sinks.sheets import SheetsSink
        key = out
        if "docs.google.com" in out:
            key = out.split("/d/")[1].split("/")[0]
        return SheetsSink(key)
    if out is None:
        return JsonlSink("/dev/stdout")
    return {"csv": CsvSink, "json": JsonSink, "jsonl": JsonlSink}[fmt](out)


#: The one ground-truth workbook we have; --validate has nowhere else to
#: point without a second corpus being added, so it is not a CLI argument.
GROUND_TRUTH_XLSX = os.path.join("tests", "system_tests", "Master Data Calculation.xlsx")


def print_validation(corpus_dir: str, xlsx_path: str) -> None:
    """Report per-quantity agreement with the manually verified corpus.

    A table, not a verdict: the spreadsheet and the reference CLI disagree
    with each other (see songfeat/validation.py), so the right output here
    is counts and mean deltas a human can read the disagreement out of,
    not a pass/fail that would have to pick a side.
    """
    from collections import defaultdict

    from .validation import compare

    results = compare(corpus_dir, xlsx_path)
    by_quantity = defaultdict(list)
    for entry in results:
        by_quantity[entry.quantity].append(entry)
    print(f"{'quantity':<30}{'agree':>8}{'of':>6}{'mean delta':>14}")
    for quantity, entries in by_quantity.items():
        agree = sum(1 for e in entries if e.within_tolerance)
        deltas = [e.delta for e in entries if e.delta is not None]
        mean = sum(deltas) / len(deltas) if deltas else float("nan")
        print(f"{quantity:<30}{agree:>8}{len(entries):>6}{mean:>14.2f}")


def print_profile(records) -> None:
    """Report dead columns and redundant pairs instead of writing records.

    Also surfaces each spec's declared ``best_with``: a column can be fully
    populated and still be a weaker measurement than its name suggests, when
    the input format lacks what the feature needs (design spec: availability
    is "recorded in feature metadata and surfaced by profile").
    """
    from .profile import correlated_pairs, profile_records, weak_for_format

    profiles = profile_records(records)
    dead = [p for p in profiles if p.is_constant or p.null_rate == 1.0]
    formats = sorted({r.source_format for r in records})
    weak = set()
    for fmt in formats:
        weak |= weak_for_format(fmt)
    weak_present = weak & {p.name for p in profiles}

    print(f"{len(profiles)} features, {len(dead)} carry no information")
    if weak_present:
        label = formats[0] if len(formats) == 1 else "/".join(formats)
        print(
            f"{len(weak_present)} columns are weaker on this input ({label}): "
            "declared best_with excludes it"
        )
    print()
    # "variance(ddof=1)" names the convention (sample variance, matching
    # pandas' Series.var() default) so a reader cross-checking against
    # numpy's ddof=0 default knows why the numbers differ, without having
    # to go find the module docstring.
    print(f"{'feature':<44}{'null%':>8}{'distinct':>10}{'variance(ddof=1)':>18}")
    for p in sorted(profiles, key=lambda p: (-p.null_rate, p.name)):
        variance = "" if p.variance is None else f"{p.variance:.4g}"
        flag = "  [weak: not best_with this format]" if p.name in weak_present else ""
        print(f"{p.name:<44}{p.null_rate * 100:>7.1f}%{p.n_distinct:>10}{variance:>18}{flag}")
    pairs = correlated_pairs(records)
    if pairs:
        print(f"\n{len(pairs)} correlated pairs at |r| >= 0.95:")
        for left, right, r in sorted(pairs, key=lambda p: -abs(p[2]))[:25]:
            print(f"  {left:<36}{right:<36}{r:>8.3f}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="songfeat",
        description="Extract structured features from symbolic music files.",
    )
    parser.add_argument("paths", nargs="*", help="score files or folders")
    parser.add_argument("-o", "--out", help="write to this file (.csv, .json, or .jsonl)")
    parser.add_argument(
        "-f",
        "--format",
        choices=("json", "jsonl", "csv", "sheets"),
        help=(
            "output format (default: inferred from --out, else jsonl). "
            "'sheets' appends to the Google Sheet named by --out and does "
            "NOT deduplicate: running twice against the same sheet leaves "
            "two copies of every row. The spec's optional key column "
            "(source_path + part_index) is not implemented; use a fresh "
            "worksheet per run, or clear the sheet first"
        ),
    )
    parser.add_argument(
        "-g",
        "--groups",
        help="comma-separated feature groups to compute (default: all)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="do not descend into subfolders",
    )
    parser.add_argument(
        "--list-features",
        action="store_true",
        help="describe the available features and exit",
    )
    parser.add_argument(
        "--schema",
        action="store_true",
        help="print the output field names and exit",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="analyse the inputs and report dead/redundant columns instead of writing records",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help=(
            "compare computed features against the manually verified "
            "ground-truth workbook and print an agreement report instead "
            "of writing records; the path argument is the corpus directory"
        ),
    )
    parser.add_argument(
        "--drop-trailing-marker",
        action="store_true",
        help=(
            "ignore a final isolated C1, the reference pitch the "
            "Tessituragram corpus appends to every file"
        ),
    )
    parser.add_argument(
        "--lyrics-questions", choices=("core", "full"), default="full",
        help=(
            "which classifier question set to ask: 'full' is 153 questions "
            "in 8 calls per song; 'core' is 13 in one call, about 8%% of "
            "the cost, for development. The set used is recorded in the "
            "clf_question_set column, so a lean run cannot be mistaken "
            "for a complete one"
        ),
    )
    parser.add_argument(
        "--lyrics-estimate", action="store_true",
        help=(
            "print the number of classifier calls, questions and input "
            "tokens the given inputs would need, then exit without "
            "calling anything or writing records"
        ),
    )
    parser.add_argument(
        "--lyrics-max-calls", type=int, default=None, metavar="N",
        help=(
            "stop the run after N classifier calls rather than continuing; "
            "a guard against a glob that matched more than you meant"
        ),
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress progress")
    return parser


def _build_jev_client(args):
    """The configured client, or None when no key is available.

    A missing key is not an error: it means one feature group reports
    null with a reason, and the rest of the run proceeds. The key is
    read here, once, from the environment -- never from a CLI argument,
    where it would land in shell history.
    """
    key = os.environ.get("JEV_KEY")
    if not key:
        return None
    from .features.lyrics.client import HttpJevClient
    return HttpJevClient(key, max_calls=args.lyrics_max_calls)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    groups_filter = args.groups.split(",") if args.groups else None

    if args.list_features:
        for spec in registry().values():
            print(f"{spec.name}  [{spec.group}]")
            print(f"  {spec.description}")
            print(f"  fields: {', '.join(spec.fields)}\n")
        return 0

    if args.schema:
        for name in schema(groups_filter):
            print(name)
        return 0

    if args.validate:
        if not args.paths:
            build_parser().error("--validate requires a corpus directory")
        print_validation(args.paths[0], GROUND_TRUTH_XLSX)
        return 0

    if not args.paths:
        build_parser().error("no input paths given")

    if args.lyrics_estimate:
        from .features.lyrics.assemble import assemble_text
        from .features.lyrics.client import estimate
        from .features.lyrics.questions import question_set

        files = iter_score_files(args.paths, recursive=not args.no_recursive)
        questions = question_set(args.lyrics_questions)
        calls = questions_asked = tokens = 0
        classifiable = 0
        for path in files:
            piece = load(path, drop_trailing_marker=args.drop_trailing_marker)
            for part in piece.parts:
                assembled = assemble_text(part)
                if assembled is None:
                    continue
                classifiable += 1
                predicted = estimate(questions, assembled.text)
                calls += predicted.calls
                questions_asked += predicted.questions
                tokens += predicted.input_tokens
        print(f"{len(files)} file(s), {classifiable} part(s) with lyrics")
        print(f"{calls} calls, {questions_asked} questions, "
              f"{tokens} input tokens")
        print(f"question set: {args.lyrics_questions}")
        return 0

    files = iter_score_files(args.paths, recursive=not args.no_recursive)
    if not files:
        print("no supported score files found", file=sys.stderr)
        return 1

    total = len(files)
    counter = {"n": 0}

    def progress(path: str) -> None:
        counter["n"] += 1
        if not args.quiet and total > 1:
            print(f"  [{counter['n']}/{total}] {os.path.basename(path)}", file=sys.stderr)

    lyrics_active = groups_filter is not None and "lyrics" in groups_filter
    if lyrics_active:
        from .features.lyrics.cache import DEFAULT_PATH, AnswerCache
        from .features.lyrics.client import MISSING_KEY
        from .features.lyrics import service

        client = _build_jev_client(args)
        service.configure(
            client=client,
            cache=AnswerCache(DEFAULT_PATH),
            question_set_name=args.lyrics_questions,
            # The group WAS requested; a missing key is a different
            # fact than "nobody asked for this group", so it gets its
            # own reason rather than falling back to NOT_CONFIGURED.
            unavailable_reason=MISSING_KEY if client is None else None,
        )

    sidecar_dir = None
    if args.out and lyrics_active:
        sidecar_dir = os.path.join(os.path.dirname(args.out) or ".", "lyrics")

    sink = MemorySink() if args.profile else make_sink(args.out, args.format)
    count, failures = run(
        files,
        sink,
        groups_filter,
        drop_trailing_marker=args.drop_trailing_marker,
        on_progress=progress,
        sidecar_dir=sidecar_dir,
    )

    if args.profile:
        print_profile(sink.records)
    elif args.out and not args.quiet:
        print(f"wrote {count} records to {args.out}", file=sys.stderr)

    if failures:
        print(f"\n{len(failures)} file(s) failed:", file=sys.stderr)
        for path, reason in failures:
            print(f"  {os.path.basename(path)}: {reason}", file=sys.stderr)
        return 1 if not count else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
