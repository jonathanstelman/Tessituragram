"""Append feature rows to a Google Sheet.

The Google client is an optional dependency: importing songfeat must not
require it, so the import happens inside the constructor. Rows are
appended in batches because the Sheets write quota is per minute and per
user, and a 150-file corpus with several parts each is enough to hit it.
"""

from __future__ import annotations

import os
from typing import Any

from ..record import FeatureRecord
from .base import BaseSink


class SheetsSink(BaseSink):
    def __init__(
        self,
        spreadsheet_id: str,
        worksheet: str = "songfeat",
        credentials_env: str = "GOOGLE_APPLICATION_CREDENTIALS",
        batch_size: int = 200,
        client: Any = None,
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
        self.spreadsheet_id = spreadsheet_id
        self.worksheet_title = worksheet
        self.batch_size = batch_size
        self._worksheet = None
        self._pending: list[list[Any]] = []

    def open(self, schema: list[str]) -> None:
        super().open(schema)
        self._worksheet = self._client.open_by_key(
            self.spreadsheet_id
        ).worksheet(self.worksheet_title)
        existing = self._worksheet.get_all_values()
        if not existing:
            self._worksheet.append_rows([self.schema], value_input_option="RAW")
            return
        header = existing[0]
        if header != self.schema:
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

    def write(self, record: FeatureRecord) -> None:
        row = record.flat()
        self._pending.append([row.get(column, "") for column in self.schema])
        if len(self._pending) >= self.batch_size:
            self._flush()

    def _flush(self) -> None:
        if self._pending:
            self._worksheet.append_rows(self._pending, value_input_option="RAW")
            self._pending = []

    def close(self) -> None:
        self._flush()
