from songfeat.model import Note, Part, Piece, Syllable


def make_piece() -> Piece:
    return Piece(
        source_path="x.mid",
        source_format="midi",
        parts=[
            Part(index=0, name="Voice", notes=[
                Note(midi=60, onset=0.0, duration=1.0, part=0),
                Note(midi=67, onset=1.0, duration=1.0, part=0),
            ]),
            Part(index=1, name="Piano", notes=[
                Note(midi=36, onset=0.0, duration=2.0, part=1),
            ]),
        ],
    )


def test_each_part_owns_its_notes():
    piece = make_piece()
    assert [n.midi for n in piece.parts[0].notes] == [60, 67]
    assert [n.midi for n in piece.parts[1].notes] == [36]


def test_piece_notes_aggregates_across_parts():
    assert len(make_piece().notes) == 3


def test_part_pitch_extremes_are_not_pooled():
    """The bug this restructure exists to prevent."""
    piece = make_piece()
    assert min(n.midi for n in piece.parts[0].notes) == 60  # not 36


def test_note_carries_every_verse_and_its_syllabic_marker():
    note = Note(
        midi=60, onset=0.0, duration=1.0, part=0,
        lyric="Er",
        lyrics=(
            Syllable(number=1, text="Er", syllabic="begin", extend=False),
            Syllable(number=2, text="Wer", syllabic="single", extend=False),
        ),
    )
    assert note.lyric == "Er", "verse-1 convenience text must not change meaning"
    assert len(note.lyrics) == 2
    assert note.lyrics[1].number == 2
    assert note.lyrics[0].syllabic == "begin"


def test_note_without_lyrics_has_an_empty_tuple_not_none():
    """A tuple keeps Note hashable, which frozen-dataclass equality relies on."""
    note = Note(midi=60, onset=0.0, duration=1.0, part=0)
    assert note.lyrics == ()
    assert hash(note) is not None
