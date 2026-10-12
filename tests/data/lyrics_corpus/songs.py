"""The lyric classification validation corpus, as data.

Original text only -- no copyrighted lyrics enter this repository.
Each song exists to test one case; see the plan's Task 3 table and the
``case`` field. Words are one-per-note, which is what ``build.py``
needs; multi-syllable words are split with "-" and reassembled by the
syllabic markers the builder writes.

Splits are two-part only ("mor-", "ning"), because the builder writes
begin/end and never middle: a three-part split would be read back as
two words.

No song is about a real or hypothetical student. The bereavement and
advisory texts describe invented situations, because nothing about a
student is ever stored anywhere in this project, fixtures included.

English, with one exception. "cast-agreement" is Italian, because the
grammatical-agreement casting mechanism the spec names ("sono stanca",
"je suis allee") cannot be expressed in English at all: without it that
mechanism would have no case in the corpus while a song claimed to be
it. Its agreement figure is therefore measured on a single
non-validated-language song and must be reported with that caveat, not
counted as validation. Everything else is English, per the spec's
English-first decision.

FROZEN. These texts and tests/data/lyrics_corpus/labels.json were
written before any classifier question wording existed, and must not be
edited to suit a question. Adding a song is fine; rewording one to make
a question pass is not.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Song:
    slug: str
    title: str
    language: str
    case: str
    verses: tuple[tuple[str, ...], ...]


SONGS: tuple[Song, ...] = (
    Song(
        slug="plain-love",
        title="The Lamp in the Window",
        language="en",
        case="obvious requited love, female narrator, male beloved, pronouns only",
        verses=(
            ("I", "keep", "a", "lamp", "a-", "light", "for", "him",
             "and", "he", "comes", "home", "to", "me"),
            ("He", "knows", "the", "road", "by", "heart", "a-", "lone",
             "and", "I", "am", "what", "he", "sees"),
        ),
    ),
    Song(
        slug="plain-nature",
        title="The Thaw on the Hill",
        language="en",
        case="obvious spring landscape; no people and no gender markers at all",
        verses=(
            ("The", "thaw", "runs", "down", "the", "hill", "in", "si-", "lver", "threads"),
            ("The", "black", "thorn", "breaks", "in-", "to", "a", "white", "rough", "cloud"),
            ("No", "voice", "comes", "up", "the", "val-", "ley", "but", "the", "wind"),
        ),
    ),
    Song(
        slug="plain-friendship",
        title="Thirty Years of Thursdays",
        language="en",
        case="obvious friendship and not romance; love must not fire",
        verses=(
            ("We", "ar-", "gue", "like", "two", "brid-", "ges", "on", "one", "road"),
            ("You", "know", "the", "worst", "of", "me", "and", "stayed", "a-", "round"),
            ("I", "have", "not", "loved", "you", "once", "and", "nev-", "er", "will"),
            ("But", "I", "would", "walk", "through", "fire", "to", "keep", "you", "here"),
        ),
    ),
    Song(
        slug="plain-faith",
        title="Keep Me Till Morning",
        language="en",
        case="obvious devotional text addressed to the divine",
        verses=(
            ("Keep", "me", "till", "mor-", "ning", "Lord", "and", "hold", "the", "dark"),
            ("I", "have", "no", "lamp", "but", "what", "your", "hand", "has", "lit"),
            ("Teach", "me", "the", "pa-", "tience", "of", "the", "wai-", "ting", "stone"),
        ),
    ),
    Song(
        slug="plain-resilience",
        title="I Will Not Be Moved",
        language="en",
        case="obvious endurance and defiance, first person",
        verses=(
            ("They", "told", "me", "bend", "and", "I", "have", "learned", "to", "stand"),
            ("The", "flood", "came", "through", "my", "door", "and", "left", "me", "here"),
            ("I", "will", "not", "be", "moved", "I", "will", "not", "be", "small"),
        ),
    ),
    Song(
        slug="plain-mourning",
        title="The Chair by the Window",
        language="en",
        case="obvious grief for a friend, elegiac tone",
        verses=(
            ("Your", "chair", "is", "by", "the", "win-", "dow", "where", "you", "sat"),
            ("I", "bring", "the", "morn-", "ing", "pa-", "per", "out", "of", "hab-", "it"),
            ("Friend", "there", "is", "no", "one", "left", "to", "ar-", "gue", "with"),
        ),
    ),
    Song(
        slug="plain-work",
        title="The Morning Shift",
        language="en",
        case="obvious labour song; Activities and Craft",
        verses=(
            ("Up", "at", "five", "and", "down", "the", "hill", "be-", "fore", "the", "light"),
            ("The", "ham-", "mer", "knows", "my", "hand", "bet-", "ter", "than", "my", "name"),
            ("Sing", "out", "the", "count", "and", "let", "the", "i-", "ron", "fall"),
        ),
    ),
    Song(
        slug="plain-folktale",
        title="The Miller's Lantern",
        language="en",
        case="obvious ghost story; Mythology and Folklore",
        verses=(
            ("They", "say", "the", "mil-", "ler", "walks", "the", "wa-", "ter", "stair"),
            ("His", "lan-", "tern", "swings", "where", "no", "one", "car-", "ries", "it"),
            ("Do", "not", "an-", "swer", "if", "he", "calls", "you", "by", "name"),
        ),
    ),
    Song(
        slug="plain-protest",
        title="The Rent Is Not the Rain",
        language="en",
        case="obvious injustice and protest; Social Commentaries",
        verses=(
            ("The", "rent", "is", "not", "the", "rain", "it", "did", "not", "fall"),
            ("A", "man", "signed", "it", "in", "ink", "in", "a", "warm", "room"),
            ("We", "will", "stand", "in", "the", "street", "un-", "til", "it", "turns"),
        ),
    ),
    Song(
        slug="metaphor-garden",
        title="What the Garden Knows",
        language="en",
        case="metaphor: love described entirely as tending a garden and never named",
        verses=(
            ("I", "broke", "the", "clay", "for", "you", "with", "my", "bare", "hands"),
            ("I", "pulled", "the", "weeds", "and", "watched", "the", "frost", "all", "night"),
            ("Noth-", "ing", "grows", "like", "this", "without", "a", "hand", "like", "mine"),
            ("Tell", "me", "what", "else", "I", "could", "have", "called", "it", "then"),
        ),
    ),
    Song(
        slug="metaphor-ship",
        title="The Long Crossing",
        language="en",
        case="metaphor: a life as a sea voyage; sea and time both plausible",
        verses=(
            ("I", "left", "the", "har-", "bour", "young", "and", "sure", "of", "wind"),
            ("The", "chart", "I", "had", "was", "drawn", "by", "o-", "ther", "hands"),
            ("The", "wa-", "ter", "takes", "the", "years", "and", "gives", "back", "salt"),
            ("I", "steer", "for", "har-", "bour", "now", "and", "name", "no", "port"),
        ),
    ),
    Song(
        slug="metaphor-winter",
        title="The House in Winter",
        language="en",
        case="metaphor: bereavement as winter; a sensitive subject reached through metaphor",
        verses=(
            ("The", "frost", "came", "ear-", "ly", "to", "the", "east", "room", "here"),
            ("Two", "cups", "stood", "on", "the", "shelf", "and", "now", "stand", "one"),
            ("I", "bank", "the", "fire", "a-", "gainst", "a", "long", "white", "year"),
            ("No", "spring", "is", "promised", "to", "a", "house", "like", "this"),
        ),
    ),
    Song(
        slug="irony-praise",
        title="The Kindest Man I Know",
        language="en",
        case="irony: praise in terms that are plainly insults; the literal reading is wrong",
        verses=(
            ("He", "nev-", "er", "lies", "ex-", "cept", "when", "he", "has", "time"),
            ("He", "gives", "my", "mo-", "ney", "to", "the", "poor", "at", "cards"),
            ("No", "one", "has", "loved", "me", "half", "as", "cheap-", "ly", "yet"),
            ("The", "kind-", "est", "man", "I", "know", "and", "I", "should", "know"),
        ),
    ),
    Song(
        slug="irony-cheerful-dirge",
        title="Dance, the Roof Is Down",
        language="en",
        case="irony: jaunty dance text about ruin and death",
        verses=(
            ("Dance", "for", "the", "roof", "has", "fal-", "len", "in", "the", "rain"),
            ("Dance", "for", "the", "dog", "is", "dead", "and", "so", "is", "June"),
            ("Strike", "up", "the", "mer-", "ry", "fife", "and", "bur-", "y", "me"),
            ("What", "else", "is", "there", "to", "do", "but", "dance", "and", "dance"),
        ),
    ),
    Song(
        slug="irony-patriot",
        title="For King and Mud",
        language="en",
        case="irony: a war song that undercuts itself",
        verses=(
            ("We", "marched", "out", "sing-", "ing", "for", "the", "king's", "good", "name"),
            ("The", "king", "was", "warm", "and", "we", "were", "in", "the", "mud"),
            ("Glo-", "ry", "is", "a", "word", "that", "they", "send", "by", "post"),
            ("Sing", "it", "a-", "gain", "and", "sing", "it", "while", "you", "can"),
        ),
    ),
    Song(
        slug="reveal-verse-three",
        title="The One I Wait For",
        language="en",
        case="reveal: the beloved is unmarked until verse three names him",
        verses=(
            ("I", "wait", "all", "win-", "ter", "for", "the", "one", "I", "want"),
            ("The", "let-", "ters", "come", "but", "nev-", "er", "say", "a", "date"),
            ("And", "when", "I", "see", "him", "I", "will", "know", "my", "year"),
        ),
    ),
    Song(
        slug="reveal-death",
        title="Sleep Now, Little One",
        language="en",
        case="reveal: reads as a lullaby until the last verse says the child has died",
        verses=(
            ("Sleep", "now", "lit-", "tle", "one", "the", "house", "is", "warm", "and", "still"),
            ("I", "have", "put", "the", "milk", "a-", "way", "and", "locked", "the", "door"),
            ("Sleep", "now", "un-", "der", "snow", "it", "is", "two", "years", "to-", "day"),
        ),
    ),
    Song(
        slug="reveal-narrator",
        title="This Road Since It Was Mud",
        language="en",
        case="reveal: the narrator's gender is fixed only by 'when I was a lad' in verse two",
        verses=(
            ("I", "have", "kept", "this", "road", "since", "it", "was", "mud", "and", "stone"),
            ("When", "I", "was", "a", "lad", "they", "paid", "in", "bread", "not", "coin"),
            ("Now", "the", "road", "is", "black", "and", "I", "am", "slow", "to", "climb"),
        ),
    ),
    Song(
        slug="whole-not-parts",
        title="I Know the Route",
        language="en",
        case="every line is innocent; together they describe a stalking",
        verses=(
            ("I", "know", "the", "bus", "you", "take", "at", "half", "past", "eight"),
            ("I", "know", "the", "lamp", "that", "stays", "on", "in", "your", "hall"),
            ("I", "have", "not", "missed", "a", "day", "of", "you", "this", "year"),
            ("You", "have", "not", "looked", "up", "once", "and", "that", "is", "fine"),
        ),
    ),
    Song(
        slug="bystanders",
        title="The Cafe on Tuesday",
        language="en",
        case="the Tom's Diner shape: gendered people present, none of them a relational focus",
        verses=(
            ("I", "am", "sit-", "ting", "in", "the", "cor-", "ner", "with", "my", "tea"),
            ("A", "man", "comes", "in", "and", "shakes", "the", "rain", "from", "his", "coat"),
            ("The", "wo-", "man", "at", "the", "count-", "er", "knows", "his", "or-", "der"),
            ("I", "watch", "the", "street", "and", "no", "one", "watch-", "es", "me"),
        ),
    ),
    Song(
        slug="cast-pronouns",
        title="She Walks the Long Way Home",
        language="en",
        case="gender cast by pronoun only; adaptation cost 1",
        verses=(
            ("I", "walk", "be-", "hind", "her", "to", "the", "gar-", "den", "gate"),
            ("She", "turns", "and", "takes", "the", "long", "way", "home", "a-", "gain"),
            ("I", "let", "her", "go", "and", "count", "the", "lights", "she", "passes"),
        ),
    ),
    Song(
        slug="cast-address",
        title="My Lady of the Narrow Street",
        language="en",
        case="gender cast by gendered address throughout; adaptation cost 3",
        verses=(
            ("My", "la-", "dy", "of", "the", "nar-", "row", "street", "I", "sing"),
            ("Sweet", "la-", "dy", "take", "this", "cold", "and", "crooked", "tune"),
            ("My", "la-", "dy", "I", "have", "noth-", "ing", "else", "to", "give"),
        ),
    ),
    Song(
        slug="cast-named-role",
        title="Orlando's Complaint",
        language="en",
        case="gender cast by a named dramatic role; adaptation cost 5",
        verses=(
            ("Orlando", "they", "have", "called", "me", "since", "the", "duke", "was", "young"),
            ("Orlando", "has", "no", "coun-", "try", "and", "no", "horse", "to", "ride"),
            ("Call", "me", "Orlando", "still", "and", "I", "will", "an-", "swer", "late"),
        ),
    ),
    Song(
        slug="cast-biology",
        title="The Child I Carried",
        language="en",
        case="gender cast by biology; adaptation cost 5",
        verses=(
            ("The", "child", "I", "car-", "ried", "walks", "the", "or-", "chard", "row"),
            ("I", "gave", "nine", "months", "of", "win-", "ter", "to", "that", "walk"),
            ("Go", "then", "and", "do", "not", "turn", "a-", "round", "for", "me"),
        ),
    ),
    Song(
        slug="cast-life-stage",
        title="They Dressed Me as a Bride",
        language="en",
        case=(
            "gender cast by marital life-stage nouns at every rhyme "
            "(bride, wife, maid); not adaptable, cost 5"
        ),
        verses=(
            ("They", "dressed", "me", "as", "a", "bride"),
            ("I", "wore", "my", "mo-", "ther's", "pride"),
            ("A", "wife", "they", "said", "and", "sighed"),
            ("A", "maid", "no", "more", "but", "tied"),
        ),
    ),
    Song(
        slug="cast-agreement",
        title="Sono Tornata Tardi",
        language="it",
        case=(
            "gender cast by grammatical agreement -- feminine participle and "
            "adjective endings, the one mechanism English cannot express; "
            "adaptation cost 4"
        ),
        verses=(
            ("Sono", "tor-", "nata", "tar-", "di", "dal", "mercato"),
            ("Sono", "stan-", "ca", "ma", "can-", "to", "piano"),
            ("La", "por-", "ta", "era", "a-", "perta", "e", "sono", "en-", "trata"),
            ("Non", "sono", "mai", "sta-", "ta", "tan-", "to", "conten-", "ta"),
        ),
    ),
    Song(
        slug="cast-two-mechanisms",
        title="Rosalind Writes at Midnight",
        language="en",
        case="two casting mechanisms at once: a named role and pronouns; the blocker is the costlier",
        verses=(
            ("I", "am", "Rosalind", "and", "I", "write", "to", "him", "at", "night"),
            ("He", "will", "not", "know", "the", "hand", "that", "holds", "the", "pen"),
            ("Rosalind", "has", "no", "right", "to", "love", "him", "in", "the", "day"),
        ),
    ),
    Song(
        slug="cast-none",
        title="Sanctus for a Small Church",
        language="en",
        case="a sacred text with no gendered reference at all; adaptation cost 0",
        verses=(
            ("Ho-", "ly", "ho-", "ly", "is", "the", "light", "we", "can-", "not", "hold"),
            ("Fill", "this", "small", "room", "and", "fill", "each", "emp-", "ty", "hand"),
            ("Peace", "be", "up-", "on", "the", "stone", "and", "on", "the", "snow"),
        ),
    ),
    Song(
        slug="sensitive-parent-central",
        title="Elegy for My Mother",
        language="en",
        case="bereavement at high centrality: the whole text is an elegy for a dead mother",
        verses=(
            ("My", "mo-", "ther", "died", "in", "May", "and", "took", "the", "year"),
            ("I", "have", "her", "ring", "her", "bad", "knee", "and", "her", "name"),
            ("There", "is", "no", "one", "left", "who", "knew", "me", "as", "a", "child"),
        ),
    ),
    Song(
        slug="sensitive-parent-passing",
        title="The Hay Is In",
        language="en",
        case="bereavement at low centrality: one passing line in an otherwise pastoral song",
        verses=(
            ("The", "hay", "is", "in", "and", "all", "the", "gates", "are", "shut"),
            ("The", "swal-", "lows", "turn", "a-", "bove", "the", "low", "red", "barn"),
            ("I", "passed", "my", "fa-", "ther's", "grave", "and", "walked", "on", "home"),
            ("The", "ket-", "tle", "will", "be", "hot", "when", "I", "get", "in"),
        ),
    ),
    Song(
        slug="sensitive-third-person",
        title="Her Mother's House",
        language="en",
        case="a dead parent, but someone else's; not first person",
        verses=(
            ("Her", "mo-", "ther", "died", "be-", "fore", "the", "house", "was", "sold"),
            ("She", "keeps", "the", "kitch-", "en", "just", "the", "way", "it", "was"),
            ("I", "bring", "the", "bread", "and", "say", "noth-", "ing", "at", "all"),
        ),
    ),
    Song(
        slug="advisory-first-person-violence",
        title="What I Did at the Ford",
        language="en",
        case="the singer commits the violence, in first person and depicted",
        verses=(
            ("I", "put", "my", "knife", "in-", "to", "the", "ri-", "der's", "side"),
            ("The", "ri-", "ver", "took", "the", "red", "and", "gave", "back", "none"),
            ("I", "have", "washed", "my", "hands", "in", "it", "and", "they", "are", "clean"),
        ),
    ),
    Song(
        slug="advisory-narrated-violence",
        title="The Battle from the Hill",
        language="en",
        case="a battle described from a distance; not first person and not depicted",
        verses=(
            ("From", "this", "hill", "the", "ar-", "mies", "look", "like", "mov-", "ing", "corn"),
            ("They", "say", "ten", "thou-", "sand", "fell", "be-", "fore", "the", "noon"),
            ("We", "could", "not", "hear", "it", "here", "we", "heard", "the", "bells"),
        ),
    ),
    Song(
        slug="advisory-alluded-sex",
        title="The Door Was Not Locked",
        language="en",
        case="desire implied and nothing depicted",
        verses=(
            ("The", "door", "was", "not", "locked", "and", "the", "night", "was", "long"),
            ("I", "thought", "of", "noth-", "ing", "else", "for", "three", "whole", "days"),
            ("We", "said", "good", "night", "and", "nei-", "ther", "of", "us", "moved"),
        ),
    ),
    Song(
        slug="advisory-clean-child",
        title="The Cat Has Nine Fine Hats",
        language="en",
        case="a nonsense song for children; every advisory zero",
        verses=(
            ("The", "cat", "has", "nine", "fine", "hats", "and", "wears", "them", "all"),
            ("One", "is", "made", "of", "but-", "ter", "one", "is", "made", "of", "bells"),
            ("Count", "them", "if", "you", "can", "the", "cat", "will", "not", "sit", "still"),
        ),
    ),
    Song(
        slug="grave-subject-comic-treatment",
        title="I Have Left You All My Debts",
        language="en",
        case="a comic text about a grave subject: a funny song about dying",
        verses=(
            ("I", "have", "left", "you", "all", "my", "debts", "and", "half", "a", "pie"),
            ("Bu-", "ry", "me", "be-", "side", "the", "man", "I", "cheat-", "ed", "twice"),
            ("Weep", "if", "you", "must", "but", "not", "un-", "til", "the", "wine", "is", "gone"),
        ),
    ),
    Song(
        slug="trivial-subject-grand-treatment",
        title="Hymn for a Lost Sock",
        language="en",
        case="a grave text about a trivial subject: a solemn hymn to a lost sock",
        verses=(
            ("O", "thou", "that", "wert", "my", "left", "and", "faith-", "ful", "sock"),
            ("Where", "art", "thou", "gone", "be-", "yond", "the", "dry-", "er", "door"),
            ("No", "hand", "shall", "match", "thee", "in", "this", "world", "a-", "gain"),
            ("Sing", "low", "and", "mourn", "the", "wool", "that", "was", "our", "own"),
        ),
    ),
)
