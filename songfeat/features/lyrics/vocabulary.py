"""The classification vocabularies, as data.

Themes are anchored on the Poetry Foundation's subject taxonomy, which
is already two-tier and was built for poems -- and art song texts are
poems. Three departures, all deliberate and all in the spec: friendship
sits beside family rather than inside a "Friends & Enemies" bucket,
because for repertoire they behave nothing alike; "Resilience & Self" is
new, because empowerment is a stance the narrator takes rather than a
subject; and "Arts & Sciences" is folded into Activities & Craft.

Child slugs never repeat their family, so the column reads
``theme_love_lost`` rather than ``theme_love_love_lost``.
"""

from __future__ import annotations

THEMES: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {
    "love": (
        "Is this text about love, in any of its forms?",
        (
            ("courtship", "Is this text about courtship, flirtation, or the first excitement of attraction?"),
            ("desire", "Is this text about physical desire or passion?"),
            ("devotion", "Is this text about steady, enduring devotion to a beloved?"),
            ("unrequited", "Is this text about love that is not returned?"),
            ("parting", "Is this text about lovers separating or saying farewell?"),
            ("complicated", "Is this text about love that is difficult, compromised, or ambivalent?"),
            ("lost", "Is this text about a love that has ended or been lost?"),
        ),
    ),
    "relationships": (
        "Is this text about a relationship between people other than romantic love?",
        (
            ("friendship", "Is this text about friendship, loyalty, or companionship?"),
            ("family", "Is this text about family, ancestry, or inherited ties?"),
            ("parent_child", "Is this text about the bond between a parent and a child?"),
            ("siblings", "Is this text about brothers or sisters?"),
            ("home", "Is this text about home, belonging, or being away from home?"),
            ("betrayal", "Is this text about betrayal or estrangement between people?"),
        ),
    ),
    "nature": (
        "Is this text about the natural world?",
        (
            ("seasons", "Is this text about a season or the turning of the year?"),
            ("weather", "Is this text about weather, storms, wind, or rain?"),
            ("landscape", "Is this text about landscape, countryside, or pastoral scenes?"),
            ("sea", "Is this text about the sea, a river, or a stream?"),
            ("animals", "Is this text about animals or birds?"),
            ("night", "Is this text about night, the moon, or the stars?"),
            ("flowers", "Is this text about flowers, trees, or growing things?"),
        ),
    ),
    "living": (
        "Is this text about the experience of being alive, aging, or passing time?",
        (
            ("mortality", "Is this text about death or mortality?"),
            ("coming_of_age", "Is this text about growing up or leaving childhood?"),
            ("aging", "Is this text about growing old?"),
            ("illness", "Is this text about illness, injury, or healing?"),
            ("memory", "Is this text about memory or nostalgia for the past?"),
            ("solitude", "Is this text about solitude or loneliness?"),
            ("dreams", "Is this text about dreams or sleep?"),
            ("time", "Is this text about the passage of time?"),
        ),
    ),
    "resilience": (
        "Does the speaker of this text take a stance of strength, agency, or resistance?",
        (
            ("empowerment", "Does the speaker of this text claim agency or power over their own situation?"),
            ("defiance", "Does the speaker of this text defy someone or something?"),
            ("endurance", "Is this text about enduring hardship over time?"),
            ("identity", "Is this text about discovering or asserting who the speaker is?"),
            ("grief_to_hope", "Does this text move from grief or despair toward hope?"),
            ("courage", "Is this text about courage in the face of fear?"),
        ),
    ),
    "religion": (
        "Is this text religious, devotional, or concerned with the transcendent?",
        (
            ("prayer", "Is this text a prayer or an act of devotion?"),
            ("divine", "Is this text about God or a divine being?"),
            ("liturgy", "Is this text a liturgical or scriptural text?"),
            ("doubt", "Is this text about religious doubt or loss of faith?"),
            ("afterlife", "Is this text about an afterlife, heaven, or judgment?"),
        ),
    ),
    "social": (
        "Is this text a commentary on society, politics, or injustice?",
        (
            ("war", "Is this text about war or armed conflict?"),
            ("exile", "Is this text about exile, displacement, or being driven from home?"),
            ("justice", "Is this text about injustice, protest, or the demand for justice?"),
            ("class", "Is this text about social class, poverty, or labour conditions?"),
            ("race", "Is this text about race, ethnicity, or racial injustice?"),
            ("gender", "Is this text about gender roles or sexuality as a social matter?"),
            ("city", "Is this text about city life or urban experience?"),
        ),
    ),
    "activities": (
        "Is this text about an activity, craft, or occupation?",
        (
            ("work", "Is this text about work or labour?"),
            ("travel", "Is this text about travel or a journey?"),
            ("music", "Is this text about music, singing, or an instrument?"),
            ("dancing", "Is this text about dancing?"),
            ("play", "Is this text about games, play, or sport?"),
            ("feasting", "Is this text about eating, drinking, or a feast?"),
        ),
    ),
    "mythology": (
        "Is this text drawn from myth, legend, folklore, or the supernatural?",
        (
            ("legend", "Is this text about a myth, legend, or classical story?"),
            ("fairy_tale", "Is this text a fairy tale or a story of enchantment?"),
            ("ghosts", "Is this text about ghosts, hauntings, or the uncanny?"),
            ("folk", "Is this text drawn from a folk or national tradition?"),
        ),
    ),
}

#: Mechanism slug to the adaptation cost it implies, 0-5. Used by the
#: perspective axis; declared here so the vocabularies live together.
#: Order is the tie-break order, documented rather than incidental.
CAST_MECHANISMS: tuple[tuple[str, int], ...] = (
    ("pronouns", 1),
    ("address", 3),
    ("agreement", 4),
    ("named_role", 5),
    ("biology", 5),
)
