"""Command line entry point: files or folders in, a feature table out."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Any, Iterable

from . import features as features_module
from .features import extract_part, extract_piece, registry, schema
from .loaders import SUPPORTED_EXTENSIONS, ParseError, UnsupportedFormatError, load


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


def analyze_paths(
    paths: Iterable[str],
    groups_filter: Iterable[str] | None = None,
    on_progress=None,
    drop_trailing_marker: bool = False,
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """Return (records, failures). One row per part; one bad file never stops the batch."""
    records: list[dict[str, Any]] = []
    failures: list[tuple[str, str]] = []
    for path in paths:
        try:
            piece = load(path, drop_trailing_marker=drop_trailing_marker)
            piece_fields = extract_piece(piece, groups_filter)
            for part in piece.parts:
                part_fields = extract_part(part, piece, groups_filter)
                record = {**piece_fields, **part_fields}
                record["_errors"] = {**piece_fields["_errors"], **part_fields["_errors"]}
                records.append(record)
        except (ParseError, UnsupportedFormatError, FileNotFoundError) as exc:
            failures.append((path, f"{type(exc).__name__}: {exc}"))
        except Exception as exc:  # noqa: BLE001
            failures.append((path, f"{type(exc).__name__}: {exc}"))
        if on_progress:
            on_progress(path)
    return records, failures


def write_csv(records: list[dict[str, Any]], handle, groups_filter=None) -> None:
    columns = schema(groups_filter)
    # Include any error columns that actually appeared.
    extra = sorted({k for r in records for k in r if k not in columns})
    writer = csv.DictWriter(handle, fieldnames=columns + extra, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow(record)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="songfeat",
        description="Extract structured features from symbolic music files.",
    )
    parser.add_argument("paths", nargs="*", help="score files or folders")
    parser.add_argument("-o", "--out", help="write to this file (.csv or .json)")
    parser.add_argument(
        "-f",
        "--format",
        choices=("json", "csv"),
        help="output format (default: inferred from --out, else json)",
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

    records, failures = analyze_paths(
        files,
        groups_filter,
        on_progress=progress,
        drop_trailing_marker=args.drop_trailing_marker,
    )

    out_format = args.format
    if not out_format and args.out:
        out_format = "csv" if args.out.lower().endswith(".csv") else "json"
    out_format = out_format or "json"

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as handle:
            if out_format == "csv":
                write_csv(records, handle, groups_filter)
            else:
                json.dump(records, handle, indent=2, default=str)
        if not args.quiet:
            print(f"wrote {len(records)} records to {args.out}", file=sys.stderr)
    else:
        if out_format == "csv":
            write_csv(records, sys.stdout, groups_filter)
        else:
            json.dump(records, sys.stdout, indent=2, default=str)
            print()

    if failures:
        print(f"\n{len(failures)} file(s) failed:", file=sys.stderr)
        for path, reason in failures:
            print(f"  {os.path.basename(path)}: {reason}", file=sys.stderr)
        return 1 if not records else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
