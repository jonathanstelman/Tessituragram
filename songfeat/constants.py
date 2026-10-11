"""Named constants with recorded provenance.

Passaggio bands are lifted verbatim from the reference implementation at
src/tessitura.py:76-84. They are frequency ranges (zones), not single
break points. Their pedagogical source is not cited in that code; confirm
it against the project bibliography before publishing results that lean
on them.
"""

#: (low_hz, high_hz) per voice type and register.
PASSAGGI: dict[str, dict[str, tuple[float, float]]] = {
    "high": {"high": (622.3, 784.0), "middle": (311.1, 392.0), "low": (233.1, 293.7)},
    "medium": {"high": (587.3, 740.0), "middle": (293.7, 370.0), "low": (220.0, 277.2)},
    "low": {"high": (523.3, 659.3), "middle": (261.6, 329.6), "low": (196.0, 246.9)},
}

#: A rest at least this long (in quarter notes) ends a phrase.
PHRASE_GAP_QUARTERS = 2.0

#: A note at least this long counts as sustained.
SUSTAINED_MIN_SECONDS = 1.5

#: Within this many semitones of a passaggio edge counts as "near".
PASSAGGIO_PROXIMITY_SEMITONES = 2.0

#: A run is at least this many consecutive notes.
RUN_MIN_NOTES = 4

#: Notes in a run are no longer than this, in quarter notes.
RUN_MAX_NOTE_QUARTERS = 0.5

#: An interval of this many semitones or more is a leap.
LEAP_MIN_SEMITONES = 3

#: A rest-delimited segment this long or longer is counted by
#: ``phrasing.n_phrases_over_breath_threshold``. A configurable threshold,
#: not a measured constant: there is no physiological source for 8 seconds
#: specifically, only the intuition that a sustained line this long starts
#: to tax breath support.
#:
#: What it counts is a segment between notated rests, which is not a breath
#: phrase -- singers breathe mid-line where nothing is notated -- so the
#: count saturates on legato writing (6 of 8 on aria I). Do not "fix" the
#: number: widening the gap threshold, or expressing it in seconds, was
#: measured to segment more coarsely rather than more finely (11-XI goes
#: from a 42.6s maximum to 117.8s; even a 0.5s gap leaves 46.7s).
#: Recalibration is a reserved research question. See the phrasing
#: feature's description for what the columns do claim.
BREATH_DEMAND_SECONDS = 8.0
