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


def test_profile_flag_reports_degeneracy_and_weak_columns(capsys):
    # -g vocal keeps this fast (one group, one file) while still covering
    # chromaticism, the only feature with best_with set -- so the weak-
    # column annotation (ruling AD) has something real to flag.
    code = main([ARIA, "-g", "vocal", "-q", "--drop-trailing-marker", "--profile"])
    assert code == 0
    out = capsys.readouterr().out
    assert "carry no information" in out

    weak_lines = [line for line in out.splitlines() if "weaker on this input" in line]
    assert weak_lines == [
        "4 columns are weaker on this input (midi): declared best_with excludes it"
    ]
    # Pin the count, not just presence: a removed or partial annotation
    # would still contain the substring "weak" without flagging all four
    # chromaticism fields.
    assert out.count("[weak: not best_with this format]") == 4


def test_sheets_format_without_out_is_a_usage_error_not_a_crash(capsys):
    # No -o, so make_sink has no spreadsheet id/URL to work with; this must
    # not fall through to a bare TypeError from `"..." in None`, and must
    # not attempt to construct a real SheetsSink (no creds are configured).
    with pytest.raises(SystemExit):
        main([ARIA, "-g", "basic", "-q", "-f", "sheets"])


def test_sheets_help_warns_that_a_re_run_duplicates_rows():
    """Finding 6's ruling: document the missing key column rather than
    implement deduplication. A user picking --format sheets has to be able
    to see the hazard from --help, not only from the source."""
    text = build_parser().format_help()
    assert "deduplicate" in text, text
    assert "source_path + part_index" in text, text


def _musicxml_with_lyrics(tmp_path, words):
    """A one-part score with one ``single`` syllable per word.

    ``music21``'s ``note.lyric = word`` setter creates exactly that: a
    single Lyric with ``syllabic='single'`` and ``number=1`` (verified
    directly against music21's own Note.lyrics before writing this
    helper), which is what the loader and ``assemble_text`` turn back
    into ``" ".join(words)``.
    """
    from music21 import note, stream

    part = stream.Part()
    part.id = "Voice"
    for word in words:
        pitch = note.Note("C4", quarterLength=1.0)
        pitch.lyric = word
        part.append(pitch)
    score = stream.Score()
    score.insert(0, part)
    out = tmp_path / "song.musicxml"
    score.write("musicxml", fp=str(out))
    return out


def test_lyrics_estimate_prints_a_price_and_makes_no_call(capsys, tmp_path):
    """--lyrics-estimate answers 'what will this cost' before spending it."""
    from songfeat import cli

    score = _musicxml_with_lyrics(tmp_path, ["love", "me"])
    code = cli.main([str(score), "--groups", "lyrics", "--lyrics-estimate"])
    printed = capsys.readouterr().out

    assert code == 0
    assert "8 calls" in printed
    assert "153 questions" in printed
    assert "JEV_KEY" not in printed, "the estimate needs no key and must not demand one"


def test_a_default_run_with_no_groups_configures_nothing(tmp_path, monkeypatch):
    """The controller's binding ruling: ``lyrics`` is opt-in in the
    strongest terms. A default run (no --groups, or a --groups that
    does not name 'lyrics') must never call service.configure, even
    when JEV_KEY is set -- configuring would build a real client and
    start spending money the moment the env var exists."""
    from songfeat import cli
    from songfeat.features.lyrics import service

    monkeypatch.setenv("JEV_KEY", "sk-not-a-real-key")
    service.reset()
    score = _musicxml_with_lyrics(tmp_path, ["love", "me"])
    out = tmp_path / "o.csv"

    code = cli.main([str(score), "-o", str(out)])

    assert code == 0
    assert service.is_configured() is False, (
        "a default run must leave the lyrics service unconfigured"
    )


def test_a_non_lyrics_groups_filter_also_configures_nothing(tmp_path, monkeypatch):
    from songfeat import cli
    from songfeat.features.lyrics import service

    monkeypatch.setenv("JEV_KEY", "sk-not-a-real-key")
    service.reset()
    score = _musicxml_with_lyrics(tmp_path, ["love", "me"])
    out = tmp_path / "o.csv"

    code = cli.main([str(score), "--groups", "basic", "-o", str(out)])

    assert code == 0
    assert service.is_configured() is False


def test_lyrics_estimate_never_builds_a_client(tmp_path, monkeypatch):
    """No network call: proven by making client construction itself fail
    loudly if the estimate path ever reaches it, rather than merely
    checking the printed text."""
    from songfeat import cli

    def _boom(args):
        raise AssertionError("--lyrics-estimate must never build a client")

    monkeypatch.setattr(cli, "_build_jev_client", _boom)
    score = _musicxml_with_lyrics(tmp_path, ["love", "me"])
    code = cli.main([str(score), "--groups", "lyrics", "--lyrics-estimate"])
    assert code == 0


def test_lyrics_estimate_call_count_matches_a_real_run(tmp_path, capsys):
    """A prediction nobody checks against reality is a number, not an
    estimate: parse the call count --lyrics-estimate printed for this
    input, then run the same lyric through a real (fake-backed)
    classification and assert the two numbers are equal."""
    from songfeat import cli
    from songfeat.features.lyrics import service
    from songfeat.features.lyrics.cache import AnswerCache
    from songfeat.features.lyrics.client import FakeJevClient

    score = _musicxml_with_lyrics(tmp_path, ["love", "me"])

    code = cli.main([str(score), "--groups", "lyrics", "--lyrics-estimate"])
    assert code == 0
    printed = capsys.readouterr().out
    predicted_calls = int(printed.split(" calls,", 1)[0].splitlines()[-1])

    client = FakeJevClient({})
    service.configure(
        client=client,
        cache=AnswerCache(str(tmp_path / "cache.sqlite")),
        question_set_name="full",
    )
    from songfeat.pipeline import run
    from songfeat.sinks.base import MemorySink
    run([str(score)], MemorySink(), groups_filter=["lyrics"])
    service.reset()

    assert predicted_calls > 0, "the estimate must have found lyrics to count"
    assert client.calls_made == predicted_calls


def test_lyrics_questions_core_is_recorded_in_the_output(tmp_path, monkeypatch):
    from songfeat import cli
    from songfeat.features.lyrics import service
    from songfeat.features.lyrics.client import FakeJevClient
    from songfeat.features.lyrics.questions import Answer

    monkeypatch.setattr(
        cli, "_build_jev_client",
        lambda args: FakeJevClient({"theme_love": Answer("theme_love", probability=0.9)}),
    )
    score = _musicxml_with_lyrics(tmp_path, ["love", "me"])
    out = tmp_path / "o.csv"
    code = cli.main([str(score), "--groups", "lyrics", "-o", str(out),
                     "--lyrics-questions", "core"])

    assert code == 0
    body = out.read_text(encoding="utf-8")
    assert "core@v1" in body
    service.reset()


def test_an_unknown_question_set_is_rejected_by_the_parser(capsys):
    from songfeat import cli

    with pytest.raises(SystemExit):
        cli.main(["x.musicxml", "--lyrics-questions", "cheap"])


def test_without_a_key_the_lyrics_group_says_so_and_the_run_still_succeeds(
    tmp_path, monkeypatch, capsys
):
    """A missing optional key is not an error: the run still succeeds and
    the reason is ``client.MISSING_KEY`` -- distinct from
    ``service.NOT_CONFIGURED``, which both mention "JEV_KEY" but mean
    different things ("you asked for this group but have no key" versus
    "nobody asked for this group"). cli.py now tells ``service.configure``
    which one applies (fix round 1), so the stronger, exact check is
    restored here rather than the earlier substring-only version.
    """
    from songfeat import cli
    from songfeat.features.lyrics import service
    from songfeat.features.lyrics.client import MISSING_KEY

    monkeypatch.delenv("JEV_KEY", raising=False)
    score = _musicxml_with_lyrics(tmp_path, ["love"])
    out = tmp_path / "o.csv"
    code = cli.main([str(score), "--groups", "lyrics", "-o", str(out)])

    assert code == 0, "a missing optional key is not a failed run"
    assert MISSING_KEY in out.read_text(encoding="utf-8")
    service.reset()
