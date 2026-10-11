# Tessituragram (fork)

A fork of [Tessituragram](https://github.com/Tessituragram/Tessituragram) (MIT, (c) Troy
Conklin), which analyses the vocal demands of single-track MIDI files.

This fork is being taken somewhere different: a **feature extraction pipeline** that turns
any symbolic music file into structured, documented features, with emphasis on vocal skill
and difficulty. Tessitura becomes one feature among many.

## Remotes and branches

```
origin    github.com/jonathanstelman/Tessituragram   (ours)
upstream  github.com/Tessituragram/Tessituragram     (theirs)

dev                      our trunk, branched from upstream/web-dev
feat/feature-extraction  current work
```

**Never base work on `upstream/main`.** It is machine-generated: `.github/workflows/
sync-backend.yaml` runs on pushes to `web-dev`, builds an orphan commit from a fixed file
list, and force-pushes it over `main`. It has no shared history, so pulling it conflicts
every time. Sync from their development branch instead:

```bash
git fetch upstream && git merge upstream/web-dev
```

## Environment

The venv is not auto-activated. Use its interpreter explicitly:

```bash
venv/bin/python -m pytest -q          # baseline: 103 passing
venv/bin/python -m songfeat --help
```

CPython 3.12.3, created with `uv`. Dependencies are pinned in `requirements.txt`
(UTF-8/LF — it was UTF-16/CRLF upstream and was re-encoded here).

## Layout: what is ours and what is theirs

| Path | Owner | Notes |
|---|---|---|
| `songfeat/` | ours | the feature extraction pipeline |
| `tests/test_songfeat/` | ours | 51 tests |
| `src/`, `main.py`, `main.spec` | upstream | the original CLI and its analysis engine |
| `tests/`, `conftest.py` | upstream | 52 tests; keep them passing |
| `apps/`, `templates/`, `static/`, `tessituragram_web/` | upstream | their Django app — **leave it alone** |
| `data/` | upstream | fonts, images, and the MIDI corpus |

## Things that will surprise you

**The corpus files all end with a C1 marker.** `post_process()` at `src/midi_reader.py:740-755` requires every input
to end with a trailing C1 reference pitch, which it then discards — and all 150 files in
`data/test_data_arias/` carry one. It is a parsing marker, not music, and it wrecks pitch
range if counted. `songfeat` does not require it and strips it on request:
`load(path, drop_trailing_marker=True)`.

**`tessituragram_web/settings.py` is gitignored upstream** and was deleted there, so their
Django app cannot start as published. This fork restores it (SQLite by default, console
email) and tracks it. That is a deliberate divergence; expect a merge conflict on
`.gitignore`.

**The reference data and the reference implementation disagree.** On aria I the ground-truth
spreadsheet gives tessitura quartiles that differ from what their own CLI prints. Do not
"fix" either to match the other without reading the Validation section of the spec.

## Current work

- Design: `docs/superpowers/specs/2026-10-10-songfeat-design.md`
- Plan: `docs/superpowers/plans/2026-10-10-songfeat.md` (17 TDD tasks)

The plan is written to be executed by someone with no prior context. Start at Task 1.

## Assertions must be able to fail

Three vacuous assertions in this plan's own test code reached review before being
caught, each passing unconditionally. Treat assertion strength as a review item, not
a style preference: a test that cannot fail is worse than no test, because it reports
coverage it does not provide.

`tests/test_songfeat/test_assertions.py` enforces mechanically what can be: every test
function contains an assertion, and no assertion sits alone inside a filtered loop
without a guard that the filter matched. The rest needs judgement at review time.

The patterns actually found here, worth checking by hand:

| Pattern | Why it passed anyway |
|---|---|
| `assert not any(k.startswith("_error_") for k in out)` | the key was `_errors`; the prefix never matched |
| `assert out["n_syllables"] is not None` | trivially true for a real `0` |
| `assert all(out[f] is None for f in FIELDS)` | `all()` over an empty `FIELDS` is `True` |
| `for x in xs: if cond: assert ...` | no iteration when nothing matches `cond` |
| `assert len(names) > 90` | a floor, when the exact count is known and deliberate |
| `assert value > 0` | passes for any positive number, including a wrong one |
| `assert x is None or isinstance(x, str)` | a disjunction almost nothing fails |

Two rules follow. **Pin the value when you know it** — an exact count or
`pytest.approx` of a computed figure, not a threshold. And **when a test loops or
filters, assert it checked something**: count the matches and assert the count, so an
empty collection fails loudly instead of passing silently.

## Contributing upstream

Two issues have been filed against upstream (README corrections, and a stale committed
binary that rejects the documented `--clef_range` flag). Upstream has no CONTRIBUTING file
and had no prior issues or PRs, so treat patches as unsolicited and ask which branch they
should target — `main` is force-pushed, so a PR against it cannot survive.
