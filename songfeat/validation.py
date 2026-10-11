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

#: Labels in column 10 of each aria sheet, paired with the value in column 11
#: (ground-truth-layout.md; an earlier revision of that file said 9 and 10,
#: an off-by-one from a 0-indexed lookup -- load_ground_truth finds labels by
#: value rather than by column, so that error never reached this code).
GROUND_TRUTH_LABELS = (
    "t", "tr", "Fptp", "Q0p", "Q1p", "Q2p", "Q3p", "Q4p",
    "Hp tp", "Hp %p", "Mp tp", "Mp %p", "Lp tp", "Lp %p",
)

#: The sheet repeats a block of passaggio sub-labels once per voice type
#: (low/medium/high voice), each preceded by one of these title cells one
#: column to the left. Keyed by the two-letter code load_ground_truth folds
#: into the disambiguated key (e.g. "LV/Mp tp"), because "Mp tp" alone
#: collides across all three blocks and would keep only the last one seen.
PASSAGGIO_BLOCK_TITLES = {
    "LV passaggi": "LV", "MV passaggi": "MV", "HV passaggi": "HV",
}

#: Sub-labels that repeat per block and therefore need PASSAGGIO_BLOCK_TITLES
#: folded into their key; the other GROUND_TRUTH_LABELS appear once per sheet.
PASSAGGIO_SUBLABELS = {"Hp tp", "Hp %p", "Mp tp", "Mp %p", "Lp tp", "Lp %p"}

#: Fix round 1, ruling AG: maps a block's two-letter code to the voice-type
#: name songfeat's passaggi feature uses (songfeat/constants.py:PASSAGGI),
#: and a register label to the register name within that voice type, so
#: compare() can look up `pass_{voice}_{register}_seconds` for each of the
#: nine block/register combinations.
PASSAGGIO_BLOCK_TO_VOICE = {"LV": "low", "MV": "medium", "HV": "high"}
PASSAGGIO_REGISTER_TO_SONGFEAT = {"Hp": "high", "Mp": "middle", "Lp": "low"}

#: Fix round 2, ruling AJ: a tolerance travels across units unexamined if
#: one number is reused for Hz, seconds and percentage points just because
#: it was convenient. Each unit class gets its own named constant with a
#: one-line reason, and TOLERANCES/_tolerance_for below pick among them
#: explicitly rather than falling through a single shared default.

#: Frequency quartiles (Q0p-Q4p), in Hz. 0.5 Hz is tight relative to a
#: semitone at vocal range (a few Hz), so a quartile landing on the wrong
#: note still reads as "not agreeing" rather than being absorbed.
HZ_TOLERANCE = 0.5

#: Total time and rest time (t, tr), in seconds. Carried over from the
#: brief as given -- a full second is generous relative to the sub-0.01 s
#: float noise seen on clean arias, while still catching the double-digit
#: discrepancies the overlapping-note finding surfaces (fix round 1).
SECONDS_TOLERANCE = 1.0

#: Cycle dose (Fptp), in vibrations -- a compound Hz-times-seconds unit on
#: a quantity in the tens of thousands, where sub-0.1-vibration rounding
#: noise is routine; 50 absorbs that scale without absorbing the
#: thousand-plus deltas the overlap artifact produces.
DOSE_TOLERANCE = 50.0

#: Passaggio dwell time, in seconds, per block/register (added fix round
#: 2, ruling AI). About 2x the corpus-wide median absolute delta on
#: non-degenerate zones (0.215 s measured in the fix round 1 report, from
#: this same compare()) -- loose enough to absorb a typical aria's
#: definitional noise while still flagging the heavy-tailed, overlap-
#: affected arias whose deltas run into double digits. Deliberately not
#: reused from HZ_TOLERANCE even though the number is the same: this is a
#: seconds-scale judgement, not an accident of sharing one default.
PASSAGGIO_SECONDS_TOLERANCE = 0.5

#: Passaggio dwell percentage, in percentage points, per block/register
#: (added fix round 2, ruling AI). A flat point-width tolerance is a known
#: mismatch of scale: on a zone with a tiny sounding-time share, a small
#: absolute percentage error is a large *relative* one (the mechanism
#: ruling AI's aria XCIX example demonstrates -- a 0.08-point error on an
#: 0.63-point share is a 13% relative miss), so a flat tolerance is
#: effectively lenient there; on a zone that dominates the piece, the same
#: flat width is comparatively strict in relative terms. A relative
#: tolerance would dodge that, but percentage points are the unit the
#: sheet itself reports, and this harness exists to report, not gate, so a
#: flat width in that unit stays legible rather than hiding a relative
#: scale behind it -- this tradeoff is accepted deliberately, not
#: overlooked. 0.3 is about 2x the corpus-wide median absolute delta
#: (0.14 points) on zones with a non-trivial expected share (>0.5 points;
#: see fix round 2 report), the same "2x median" method used for
#: PASSAGGIO_SECONDS_TOLERANCE above, not a number chosen to produce a
#: particular agreement count.
PASSAGGIO_PERCENT_TOLERANCE = 0.3

#: Per-quantity overrides, keyed by the ground-truth label exactly as
#: load_ground_truth stores it. Anything not listed here is a passaggio
#: quantity (block-qualified, contains "/") or a frequency quartile, and
#: _tolerance_for picks the right constant by inspecting the label's shape.
TOLERANCES = {"t": SECONDS_TOLERANCE, "tr": SECONDS_TOLERANCE, "Fptp": DOSE_TOLERANCE}


def _tolerance_for(label: str) -> float:
    """Pick a tolerance by the quantity's unit, not a single reused default.

    This is the one place fix round 2 (ruling AJ) asks to be auditable: a
    change to any of the four constants above is a change to exactly one
    unit class, visible here rather than buried in a shared fallback.
    """
    if label in TOLERANCES:
        return TOLERANCES[label]
    if "/" in label:
        # Passaggio quantities are block-qualified, e.g. "LV/Mp tp" or
        # "LV/Mp %p"; the suffix after the register code names the unit.
        return PASSAGGIO_PERCENT_TOLERANCE if label.endswith("%p") else PASSAGGIO_SECONDS_TOLERANCE
    return HZ_TOLERANCE


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

    A block title ("LV passaggi" etc.) is tracked while scanning so its
    six sub-labels ("Hp tp", "Mp tp", ...) can be folded into a key like
    "LV/Mp tp" (fix round 1, ruling AG). Without that, the three blocks'
    identically-named rows would collide on one flat dict key and silently
    keep only the last block scanned (HV's) -- not a missing value that
    would stand out, a wrong one that would look like a real comparison.
    """
    book = pd.ExcelFile(xlsx_path)
    truth: dict[str, dict[str, float]] = {}
    for sheet in book.sheet_names:
        if sheet == "Tab Master":
            continue
        frame = book.parse(sheet, header=None)
        values: dict[str, float] = {}
        block: str | None = None
        for row in range(min(40, frame.shape[0])):
            for column in range(min(12, frame.shape[1] - 1)):
                cell = frame.iat[row, column]
                if not isinstance(cell, str):
                    continue
                text = cell.strip()
                if text in PASSAGGIO_BLOCK_TITLES:
                    block = PASSAGGIO_BLOCK_TITLES[text]
                    continue
                if text in GROUND_TRUTH_LABELS:
                    neighbour = frame.iat[row, column + 1]
                    if isinstance(neighbour, (int, float)):
                        key = f"{block}/{text}" if block and text in PASSAGGIO_SUBLABELS else text
                        values[key] = float(neighbour)
        truth[sheet] = values
    return truth


def _total_time(sounding: float | None, rest: float | None) -> float | None:
    """Combine sounding and rest time into the piece's total, or None.

    Fix round 1, ruling AH: ``out.get("rest_seconds", 0)`` only substitutes
    0 when the *key* is absent, not when the feature legitimately computed
    None (piece.duration_seconds unknown -- songfeat/model.py:79 makes that
    case real, not missing). ``None + x`` would raise; silently treating a
    None as 0 would be worse, since it reports an unmeasurable quantity as
    if it agreed with the ground truth by luck. Either component missing
    makes the total unmeasurable too.
    """
    if sounding is None or rest is None:
        return None
    return sounding + rest


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
            ("t", _total_time(out.get("time_dose_seconds"), out.get("rest_seconds"))),
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
        # Fix round 1, ruling AG: the nine block/register passaggio dwell
        # times, now that load_ground_truth keys them distinctly instead of
        # collapsing the three blocks onto one "Hp tp"/"Mp tp"/"Lp tp" each.
        # Fix round 2, ruling AI: the matching nine percentages. A time can
        # agree while its percentage disagrees, because the percentage
        # divides by sounding time -- the exact quantity the overlapping-
        # note finding (fix round 1 report) implicates on ~1/3 of the
        # corpus. Comparing only times is structurally blind to that; the
        # percentages are the independent check on the denominator, not a
        # restatement of the times.
        for block, voice in PASSAGGIO_BLOCK_TO_VOICE.items():
            for register, songfeat_register in PASSAGGIO_REGISTER_TO_SONGFEAT.items():
                seconds_field = f"pass_{voice}_{songfeat_register}_seconds"
                pct_field = f"pass_{voice}_{songfeat_register}_pct"
                pairs.append((f"{block}/{register} tp", out.get(seconds_field)))
                pairs.append((f"{block}/{register} %p", out.get(pct_field)))

        for quantity, actual in pairs:
            label = quantity.split(" (")[0]
            if label not in truth[roman]:
                continue
            expected = truth[roman][label]
            delta = None if actual is None else actual - expected
            tolerance = _tolerance_for(label)
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
