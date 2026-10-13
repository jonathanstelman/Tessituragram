"""Append feature rows to a Google Sheet.

The Google client is an optional dependency: importing songfeat must not
require it, so the import happens inside the constructor. Rows are
appended in batches because the Sheets write quota is per minute and per
user, and a 150-file corpus with several parts each is enough to hit it.

See SheetsSink's own docstring for two things a caller needs to know: the
error columns are appended at close(), and a re-run does not deduplicate.
"""

from __future__ import annotations

import os
from typing import Any, Sequence

from ..record import FeatureRecord
from .base import BaseSink


class SheetsSink(BaseSink):
    """Append feature rows to one worksheet.

    Buffers every row, like ``CsvSink``, because the ``_error_*`` columns
    are only known once every record has been seen: ``schema()`` cannot
    name them, since which borrowed extractor failed on which file is a
    result, not a declaration. The header and the rows are therefore
    written at ``close()``, still in batches of ``batch_size`` so the
    per-minute Sheets write quota is respected.

    **A re-run appends; it does not deduplicate.** The design spec names
    an optional key column (``source_path`` plus ``part_index``) that
    would let a re-run replace matching rows instead of adding them. It is
    not implemented, deliberately: the ruling for this merge is to
    document the omission rather than build a key check. So running
    songfeat twice against the same sheet leaves two copies of every row,
    with nothing in the sheet to show it. Point ``--out`` at a fresh
    worksheet per run, or clear the sheet first, if that matters.
    """

    def __init__(
        self,
        spreadsheet_id: str,
        worksheet: str = "songfeat",
        credentials_env: str = "GOOGLE_APPLICATION_CREDENTIALS",
        batch_size: int = 200,
        client: Any = None,
        exclude: Sequence[str] = (),
    ) -> None:
        if client is None:
            try:
                import gspread
            except ImportError as exc:  # pragma: no cover - exercised by hand
                raise ImportError(
                    "SheetsSink needs the optional Google client. "
                    "Install it with: pip install gspread"
                ) from exc
            path = os.environ.get(credentials_env)
            if not path:
                raise RuntimeError(
                    f"{credentials_env} is not set. It must point at a service "
                    "account JSON file. Never commit that file."
                )
            try:
                client = gspread.service_account(filename=path)
            except Exception as exc:
                # google-auth's own errors interpolate the path (missing file)
                # or, worse, could echo file content (malformed JSON) into
                # str(exc). `from None` drops that chain so neither reaches a
                # traceback, log line, or repr here.
                raise RuntimeError(
                    f"Could not load the service account file named by "
                    f"{credentials_env}. Check that it exists and is valid "
                    "service-account JSON."
                ) from None

        self._client = client
        self._exclude = frozenset(exclude)
        self.spreadsheet_id = spreadsheet_id
        self.worksheet_title = worksheet
        self.batch_size = batch_size
        self._worksheet = None
        self._rows: list[dict[str, Any]] = []
        self._header: list[str] | None = None
        #: True only once open() has fully validated the sheet. close()
        #: runs from __exit__ even when open() raised, and must not write
        #: a header to a sheet it has just refused to write to.
        self._opened = False

    def open(self, schema: list[str]) -> None:
        # Excluded before the leading-columns comparison below, so a sheet
        # that was already written without provenance still validates
        # against the narrowed schema rather than the caller's full one.
        super().open([name for name in schema if name not in self._exclude])
        self._worksheet = self._client.open_by_key(
            self.spreadsheet_id
        ).worksheet(self.worksheet_title)
        existing = self._worksheet.get_all_values()
        if not existing:
            # The header cannot be written yet: the error columns that
            # belong on the end of it are only known at close().
            self._header = None
            self._opened = True
            return
        header = existing[0]
        # An existing sheet may already carry _error_* columns from an
        # earlier run, so the schema has to match its leading columns
        # rather than the whole header.
        if header[: len(self.schema)] != self.schema:
            # A silent append under a mismatched header lands data in the
            # wrong columns of a sheet someone else may be reading right
            # now. Refusing is recoverable; appending anyway is not, so
            # this raises instead of trying to migrate or reconcile it.
            diff = next(
                (i for i, pair in enumerate(zip(header, self.schema)) if pair[0] != pair[1]),
                min(len(header), len(self.schema)),
            )
            got = header[diff] if diff < len(header) else "<missing>"
            want = self.schema[diff] if diff < len(self.schema) else "<missing>"
            raise ValueError(
                f"Sheet header does not match schema: sheet has {len(header)} "
                f"column(s), schema has {len(self.schema)}; first difference "
                f"at column {diff} ({got!r} != {want!r})."
            )
        self._header = header
        self._opened = True

    def write(self, record: FeatureRecord) -> None:
        row = record.flat()
        self._rows.append({k: v for k, v in row.items() if k not in self._exclude})

    def close(self) -> None:
        if not self._opened:
            # close() runs from __exit__ and from run()'s finally block
            # even when open() raised, and must not write a header to a
            # sheet it has just refused. Clearing the flag here also makes
            # close() idempotent: a second call appending a second copy of
            # every row would be worse than the re-run duplication above.
            return
        self._opened = False
        # Only the error columns. ``flat()`` can carry keys outside the
        # schema for other reasons -- an identity column the caller left
        # out of a narrowed schema, say -- and a sheet silently sprouting
        # those is a different hazard from the one being fixed. In a real
        # run the schema already names every identity and feature column,
        # so the error columns are the whole of the difference anyway.
        extra = sorted(
            {
                name for row in self._rows for name in row
                if name.startswith("_error_") and name not in self.schema
            }
        )
        if self._header is None:
            columns = self.schema + extra
            self._worksheet.append_rows([columns], value_input_option="RAW")
            self._header = columns
        else:
            columns = self._header
            missing = [name for name in extra if name not in columns]
            if missing:
                # Appending anyway is the defect this method exists to
                # fix: the reason a borrowed extractor failed would land
                # nowhere and be lost. Refusing is recoverable -- add the
                # column, or write to a fresh worksheet.
                raise ValueError(
                    "Sheet header has no column for "
                    f"{', '.join(missing)}; appending would discard the "
                    "failure reason. Add the column(s) to the sheet, or "
                    "write this run to an empty worksheet."
                )

        for start in range(0, len(self._rows), self.batch_size):
            batch = self._rows[start:start + self.batch_size]
            self._worksheet.append_rows(
                [[row.get(column, "") for column in columns] for row in batch],
                value_input_option="RAW",
            )
        self._rows = []
