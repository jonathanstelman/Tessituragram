"""Compare computed features against the manually verified corpus.

This reports agreement; it does not assert it. The reference spreadsheet
and the reference implementation disagree about the tessitura quartiles,
so a pass/fail gate here would encode one of two unreconciled answers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd

from .features import base
from .loaders import load

#: Labels in column 9 of each aria sheet, paired with the value to their right.
GROUND_TRUTH_LABELS = (
    "t", "tr", "Fptp", "Q0p", "Q1p", "Q2p", "Q3p", "Q4p",
    "Hp tp", "Hp %p", "Mp tp", "Mp %p", "Lp tp", "Lp %p",
)

#: Absolute tolerances per quantity.
TOLERANCES = {"t": 1.0, "tr": 1.0, "Fptp": 50.0}
DEFAULT_TOLERANCE = 0.5


@dataclass
class Comparison:
    aria: str
    quantity: str
    expected: float
    actual: float | None
    delta: float | None
    within_tolerance: bool


def load_ground_truth(xlsx_path: str) -> dict[str, dict[str, float]]:
    """Read the labelled summary cells from every per-aria sheet.

    The 150 sheets were filled in by hand, so a label is located by its
    value in whichever column holds it that row rather than by a fixed
    column offset -- a hard-coded (row, column) pair measured on one sheet
    is not guaranteed to hold on the other 149.
    """
    book = pd.ExcelFile(xlsx_path)
    truth: dict[str, dict[str, float]] = {}
    for sheet in book.sheet_names:
        if sheet == "Tab Master":
            continue
        frame = book.parse(sheet, header=None)
        values: dict[str, float] = {}
        for row in range(min(40, frame.shape[0])):
            for column in range(min(12, frame.shape[1] - 1)):
                cell = frame.iat[row, column]
                if isinstance(cell, str) and cell.strip() in GROUND_TRUTH_LABELS:
                    neighbour = frame.iat[row, column + 1]
                    if isinstance(neighbour, (int, float)):
                        values[cell.strip()] = float(neighbour)
        truth[sheet] = values
    return truth


def _roman_to_path(corpus_dir: str, roman: str) -> str | None:
    for name in os.listdir(corpus_dir):
        if name.endswith(f"-{roman}.mid"):
            return os.path.join(corpus_dir, name)
    return None


def compare(
    corpus_dir: str, xlsx_path: str, arias: list[str] | None = None
) -> list[Comparison]:
    truth = load_ground_truth(xlsx_path)
    wanted = arias or list(truth)
    results: list[Comparison] = []

    for roman in wanted:
        path = _roman_to_path(corpus_dir, roman)
        if path is None or not truth.get(roman):
            continue
        piece = load(path, drop_trailing_marker=True)
        out = base.extract_part(piece.parts[0], piece, groups_filter=["vocal"])

        pairs = [
            ("t", out.get("time_dose_seconds", 0) + out.get("rest_seconds", 0)),
            ("tr", out.get("rest_seconds")),
            ("Fptp", out.get("cycle_dose")),
            ("Q0p", out.get("q0_hz")),
            ("Q4p", out.get("q4_hz")),
            ("Q1p (duration-weighted)", out.get("q1_hz_dur")),
            ("Q2p (duration-weighted)", out.get("q2_hz_dur")),
            ("Q3p (duration-weighted)", out.get("q3_hz_dur")),
            ("Q1p (count-weighted)", out.get("q1_hz_cnt")),
            ("Q2p (count-weighted)", out.get("q2_hz_cnt")),
            ("Q3p (count-weighted)", out.get("q3_hz_cnt")),
        ]

        for quantity, actual in pairs:
            label = quantity.split(" (")[0]
            if label not in truth[roman]:
                continue
            expected = truth[roman][label]
            delta = None if actual is None else actual - expected
            tolerance = TOLERANCES.get(label, DEFAULT_TOLERANCE)
            results.append(
                Comparison(
                    aria=roman,
                    quantity=quantity,
                    expected=expected,
                    actual=actual,
                    delta=delta,
                    within_tolerance=delta is not None and abs(delta) <= tolerance,
                )
            )
    return results


def compare_to_reference(corpus_dir: str, limit: int | None = None) -> list[Comparison]:
    """Diff our values against what upstream main.py prints.

    The reference CLI writes a PDF and prints a report; we parse the report.
    Any divergence is a defect in one implementation or the other.
    """
    import re
    import subprocess

    pattern = re.compile(
        r"Compositional Range: ([\d.]+)-([\d.]+) Hz.*?"
        r"Tessitura Range:\s+([\d.]+)-([\d.]+) Hz.*?"
        r"Median Frequency: ([\d.]+) Hz.*?"
        r"Cycle Dose: ([\d.]+).*?"
        r"Total Time: ([\d.]+)s",
        re.S,
    )
    results: list[Comparison] = []
    paths = sorted(
        os.path.join(corpus_dir, n)
        for n in os.listdir(corpus_dir)
        if n.endswith(".mid")
    )[:limit]

    for path in paths:
        completed = subprocess.run(
            ["venv/bin/python", "main.py", "--filepath", path],
            capture_output=True, text=True,
        )
        match = pattern.search(completed.stdout.replace("–", "-"))
        if not match:
            continue
        low, high, t_low, t_high, median, dose, total = (
            float(g) for g in match.groups()
        )
        piece = load(path, drop_trailing_marker=True)
        out = base.extract_part(piece.parts[0], piece, groups_filter=["vocal"])
        aria = os.path.basename(path)
        for quantity, expected, actual in (
            ("ref Q0p", low, out["q0_hz"]),
            ("ref Q4p", high, out["q4_hz"]),
            ("ref median (dur)", median, out["q2_hz_dur"]),
            ("ref median (cnt)", median, out["q2_hz_cnt"]),
            ("ref cycle dose", dose, out["cycle_dose"]),
        ):
            delta = None if actual is None else actual - expected
            results.append(
                Comparison(
                    aria=aria, quantity=quantity, expected=expected,
                    actual=actual, delta=delta,
                    within_tolerance=delta is not None and abs(delta) <= 1.0,
                )
            )
    return results
