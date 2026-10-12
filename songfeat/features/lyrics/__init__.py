"""Lyric classification features.

Importing this package registers every axis. The group is opt-in: its
columns appear only when ``lyrics`` is named in a groups filter, because
it is the one group that is neither offline nor free.
"""

from . import meta  # noqa: F401  (registration side effect)
from . import themes  # noqa: F401
