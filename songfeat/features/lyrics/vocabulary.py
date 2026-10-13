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

#: How a text treats its subject, as distinct from what it is about.
#: Not mutually exclusive: a wry song about unrequited love is comic and
#: ironic and barely sincere. This axis exists because "I need a comic
#: song for a jury" is among the most common repertoire requests, and
#: humour is not a subject.
TONES: tuple[tuple[str, str], ...] = (
    ("comic", "Is this text funny, or meant to amuse?"),
    ("ironic", "Does this text mean something other than what it literally says?"),
    ("sincere", "Is this text sincere and direct, meaning what it says?"),
    ("elegiac", "Is this text mournful or elegiac in its treatment?"),
    ("playful", "Is this text playful or light in its treatment, without being a joke?"),
    ("grand", "Is this text grand, exalted, or ceremonial in its treatment?"),
)

#: Content advisories: nine dimensions, anchored on Common Sense Media's
#: content grid. Consumerism is dropped -- it barely occurs in this
#: canon -- and death, self-harm and religious content are added.
#: Religious content is a FILTER need rather than a warning: it matters
#: to teachers in secular schools and with students of other faiths.
#:
#: The order is the age-band tie-break order (Task 8), documented here
#: rather than left incidental.
ADVISORIES: tuple[tuple[str, str], ...] = (
    ("sex", "How much sexual content does this text contain?"),
    ("violence", "How much violence or frightening content does this text contain?"),
    ("self_harm", "How much self-harm or suicide does this text contain?"),
    ("substance_use", "How much drinking, drug use, or intoxication does this text contain?"),
    ("language", "How much profanity or coarse language does this text contain?"),
    ("death", "How much death or mortality does this text contain?"),
    ("positive_messages", "How strongly does this text carry a positive message or lesson?"),
    ("role_models", "How strongly does this text present someone worth emulating?"),
    ("religious_content", "How much explicitly religious content does this text contain?"),
)

#: The two modifier questions, asked for every dimension. The dimension
#: label is substituted from OUR OWN constant above, never from a lyric:
#: the fixed-question-text rule is about input, not about templating.
ADVISORY_MODIFIERS: tuple[tuple[str, str], ...] = (
    ("first_person", "Does the singer voice this content as themselves, in the first person?"),
    ("depicted", "Does the text depict this content directly, rather than alluding to it?"),
)

#: "unspecified" means the text does not say. It is a real answer and is
#: distinct from None, which means we did not ask.
GENDERS: tuple[str, ...] = (
    "female", "male", "non_binary", "collective", "unspecified",
)

#: The mechanism questions, asked once per subject. The subject label is
#: substituted from our own constants, never from a lyric.
CAST_QUESTIONS: dict[str, str] = {
    "pronouns": "Is this established by pronouns?",
    "address": "Is this established by a gendered term of address, such as 'my lady' or 'sir'?",
    "agreement": "Is this established by gendered grammar, such as an adjective or participle ending?",
    "named_role": "Is this established by naming a specific character whose gender is known?",
    "biology": "Is this established by a biological or life-stage detail, such as pregnancy or boyhood?",
}

#: Subjects a particular student may need to avoid entirely, regardless
#: of how well a song fits otherwise. This axis exists to find songs to
#: rule OUT for one person, which is why it never aggregates: a
#: composite would be pretending to know something about the student.
#:
#: The list will never be complete -- a student will arrive whose
#: circumstance is not here. It grows by release, and the feature's
#: description says so, so that thirteen flags are not mistaken for
#: coverage.
SENSITIVE: tuple[tuple[str, str], ...] = (
    ("loss_of_parent", "Does this text concern the death or loss of a parent?"),
    ("loss_of_child", "Does this text concern the death or loss of a child?"),
    ("loss_of_sibling", "Does this text concern the death or loss of a brother or sister?"),
    ("loss_of_partner", "Does this text concern the death or loss of a spouse or partner?"),
    ("serious_illness", "Does this text concern serious or terminal illness?"),
    ("suicide", "Does this text concern suicide?"),
    ("self_harm", "Does this text concern deliberate self-harm?"),
    ("infant_loss", "Does this text concern miscarriage or the death of an infant?"),
    ("family_breakup", "Does this text concern divorce or the breaking up of a family?"),
    ("abandonment", "Does this text concern being abandoned by a parent or caregiver?"),
    ("war_displacement", "Does this text concern being displaced or made a refugee by war?"),
    ("abuse", "Does this text concern domestic, physical or sexual abuse?"),
    ("family_addiction", "Does this text concern addiction in a family member?"),
)
