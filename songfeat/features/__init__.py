"""Feature extractors, grouped by what they describe."""

from . import basic  # noqa: F401  (registers the basic features on import)
from . import lyrics  # noqa: F401  (registers the lyrics features on import)
from . import vocal_intervals  # noqa: F401  (registers the vocal features on import)
from . import vocal_passaggi  # noqa: F401  (registers the vocal features on import)
from . import vocal_phrasing  # noqa: F401  (registers the vocal features on import)
from . import vocal_pitch  # noqa: F401  (registers the vocal features on import)
from . import vocal_text  # noqa: F401  (registers the vocal features on import)
from .base import FeatureSpec, extract_part, extract_piece, feature, groups, registry, schema
from .music21_adapter import register_music21_features

register_music21_features()

__all__ = [
    "FeatureSpec",
    "extract_part",
    "extract_piece",
    "feature",
    "groups",
    "registry",
    "schema",
]
