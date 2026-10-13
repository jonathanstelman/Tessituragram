"""Fixtures for the songfeat suite.

One job so far: no test may write the real answer cache into the
working tree. A 20KB ``.songfeat/jev-cache.sqlite`` was found sitting
in the repository root, built by a run of this suite. That file is
mutable shared state: a suite that writes it is a suite whose runs are
not independent, and whose second run can pass on answers the first one
stored.

Pointing ``cache.DEFAULT_PATH`` at ``tmp_path`` is not belt-and-braces
with the ``--lyrics-cache`` flag every CLI test already passes -- it
covers the paths that have no flag to pass, such as
``--validate-lyrics``, and any future code that reaches for the default
because that is what the default is for.
"""

from pathlib import Path

import pytest

from songfeat.features.lyrics import cache

#: The real default, resolved against the repository root rather than
#: the working directory, so a test that chdirs cannot make this guard
#: look at the wrong file and pass vacuously.
REPO_DEFAULT_CACHE = Path(__file__).resolve().parents[2] / cache.DEFAULT_PATH


@pytest.fixture(autouse=True)
def no_real_answer_cache(tmp_path, monkeypatch):
    """Redirect the default cache path, and prove nothing touched it.

    ``cli.main`` imports ``DEFAULT_PATH`` inside the function, at call
    time, so patching the module attribute reaches it.

    The check is "this test did not create or modify the file", not
    "the file does not exist": a developer who has made a real
    classification run legitimately has one, and it must not turn their
    whole suite red.
    """
    monkeypatch.setattr(
        cache, "DEFAULT_PATH", str(tmp_path / ".songfeat" / "jev-cache.sqlite")
    )
    before = (
        REPO_DEFAULT_CACHE.stat().st_mtime_ns
        if REPO_DEFAULT_CACHE.exists()
        else None
    )
    yield
    if before is None:
        assert not REPO_DEFAULT_CACHE.exists(), (
            f"this test created {REPO_DEFAULT_CACHE}: a test must never "
            "write the real answer cache into the working tree"
        )
    else:
        assert REPO_DEFAULT_CACHE.stat().st_mtime_ns == before, (
            f"this test wrote to {REPO_DEFAULT_CACHE}, the real answer "
            "cache in the working tree"
        )
