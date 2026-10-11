"""Command line entry point: files or folders in, a feature table out."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable

from .features import registry, schema
from .loaders import SUPPORTED_EXTENSIONS
from .pipeline import run
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
        help="output format (default: inferred from --out, else jsonl)",
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
        "--drop-trailing-marker",
        action="store_true",
        help=(
            "ignore a final isolated C1, the reference pitch the "
            "Tessituragram corpus appends to every file"
        ),
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress progress")
    return parser


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

    if not args.paths:
        build_parser().error("no input paths given")

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

    sink = make_sink(args.out, args.format)
    count, failures = run(
        files,
        sink,
        groups_filter,
        drop_trailing_marker=args.drop_trailing_marker,
        on_progress=progress,
    )

    if args.out and not args.quiet:
        print(f"wrote {count} records to {args.out}", file=sys.stderr)

    if failures:
        print(f"\n{len(failures)} file(s) failed:", file=sys.stderr)
        for path, reason in failures:
            print(f"  {os.path.basename(path)}: {reason}", file=sys.stderr)
        return 1 if not count else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
