import csv
import json
import os

import pytest

from songfeat.cli import build_parser, iter_score_files, main

ARIA_DIR = os.path.join("data", "test_data_arias")
ARIA = os.path.join(ARIA_DIR, "1-I.mid")


def test_iter_score_files_expands_a_directory():
    files = iter_score_files([ARIA_DIR])
    assert len(files) == 150
    assert all(f.endswith(".mid") for f in files)


def test_iter_score_files_passes_through_a_file():
    assert iter_score_files([ARIA]) == [ARIA]


def test_iter_score_files_ignores_unsupported_extensions(tmp_path):
    (tmp_path / "notes.txt").write_text("not a score")
    (tmp_path / "song.mid").write_bytes(b"")
    found = iter_score_files([str(tmp_path)])
    assert [os.path.basename(f) for f in found] == ["song.mid"]


def test_iter_score_files_deduplicates():
    assert iter_score_files([ARIA, ARIA]) == [ARIA]


def test_schema_flag_lists_columns(capsys):
    assert main(["--schema"]) == 0
    printed = capsys.readouterr().out.split()
    assert "min_note" in printed


def test_list_features_flag(capsys):
    assert main(["--list-features"]) == 0
    assert "pitch_range" in capsys.readouterr().out


def test_no_paths_is_an_error():
    with pytest.raises(SystemExit):
        main([])


def test_json_output_to_file(tmp_path):
    # -g basic: only min_note is asserted; the borrowed battery (Task 8)
    # has nothing to do with this test and would just slow it down.
    out = tmp_path / "out.json"
    assert main([ARIA, "-g", "basic", "-q", "-o", str(out)]) == 0
    records = json.loads(out.read_text())
    assert len(records) == 1
    assert records[0]["features"]["min_note"] == "C1"  # marker kept by default


def test_drop_marker_flag_changes_the_result(tmp_path):
    out = tmp_path / "out.json"
    assert main([ARIA, "-g", "basic", "-q", "--drop-trailing-marker", "-o", str(out)]) == 0
    assert json.loads(out.read_text())[0]["features"]["min_note"] == "D2"


def test_csv_output_has_a_stable_header(tmp_path):
    out = tmp_path / "out.csv"
    assert main([ARIA, "-g", "basic", "-q", "-o", str(out)]) == 0
    rows = list(csv.DictReader(out.open()))
    assert len(rows) == 1
    assert rows[0]["max_note"] == "E4"


def test_csv_output_has_no_stringified_errors_column(tmp_path):
    """The interim CLI's _errors dict used to str()-ify into every row."""
    out = tmp_path / "out.csv"
    assert main([ARIA, "-g", "basic", "-q", "-o", str(out)]) == 0
    header = out.read_text().splitlines()[0].split(",")
    assert "_errors" not in header
    rows = list(csv.DictReader(out.open()))
    assert "{}" not in rows[0].values()


def test_unparseable_file_is_reported_not_fatal(tmp_path, capsys):
    bad = tmp_path / "broken.mid"
    bad.write_bytes(b"nope")
    out = tmp_path / "out.json"
    code = main([str(bad), ARIA, "-g", "basic", "-q", "-o", str(out)])
    # One good record survives, so the run succeeds.
    assert code == 0
    assert len(json.loads(out.read_text())) == 1
    assert "broken.mid" in capsys.readouterr().err


def test_all_files_failing_returns_nonzero(tmp_path):
    bad = tmp_path / "broken.mid"
    bad.write_bytes(b"nope")
    assert main([str(bad), "-q", "-o", str(tmp_path / "out.json")]) == 1


def test_default_format_is_jsonl(tmp_path):
    out = tmp_path / "out.jsonl"
    assert main([ARIA, "-g", "basic", "-q", "-o", str(out)]) == 0
    assert len(out.read_text().strip().splitlines()) == 1


def test_parser_defaults():
    args = build_parser().parse_args([ARIA])
    assert args.drop_trailing_marker is False
    assert args.format is None


def test_sheets_format_without_out_is_a_usage_error_not_a_crash(capsys):
    # No -o, so make_sink has no spreadsheet id/URL to work with; this must
    # not fall through to a bare TypeError from `"..." in None`, and must
    # not attempt to construct a real SheetsSink (no creds are configured).
    with pytest.raises(SystemExit):
        main([ARIA, "-g", "basic", "-q", "-f", "sheets"])
