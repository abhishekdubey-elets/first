"""Google Sheets export service for IAS transfer records (gspread + service account).

The Sheets Agent calls ``upsert_transfer`` so a given transfer occupies exactly
one row: a new verified record appends; an updated record (more sources / higher
confidence) overwrites its existing row in place.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from app.core.config import settings
from app.core.logging import get_logger
from app.services.app_settings import get_export_config

log = get_logger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

HEADER = [
    "Timestamp",
    "Officer Name",
    "IAS Batch",
    "Cadre",
    "State",
    "Previous District",
    "Previous Posting",
    "New District",
    "New Posting",
    "Transfer Date",
    "Effective Date",
    "Reason",
    "Government Order Number",
    "Government Order Link",
    "Source Name",
    "Source URL",
    "Confidence Score",
    "Status",
    "Last Updated",
]

# Column (1-based) holding our stable key so we can find a row to update.
# We store the dedup key in a hidden trailing column.
KEY_COL = len(HEADER) + 1


class GoogleSheetsError(Exception):
    """Raised when a Sheets operation fails."""


def _client() -> gspread.Client:
    cred_path = Path(settings.GOOGLE_CREDENTIALS_FILE)
    if not cred_path.exists():
        raise GoogleSheetsError(
            "Google service-account credentials not uploaded/configured."
        )
    try:
        creds = Credentials.from_service_account_file(str(cred_path), scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as exc:  # noqa: BLE001
        raise GoogleSheetsError(f"Failed to authenticate with Google: {exc}") from exc


def _worksheet():
    cfg = get_export_config()
    spreadsheet_id = cfg["spreadsheet_id"]
    worksheet_name = cfg["worksheet_name"] or "Transfers"
    if not spreadsheet_id:
        raise GoogleSheetsError("No spreadsheet_id configured.")

    gc = _client()
    try:
        sh = gc.open_by_key(spreadsheet_id)
    except Exception as exc:  # noqa: BLE001
        raise GoogleSheetsError(
            f"Cannot open spreadsheet {spreadsheet_id}: {exc}"
        ) from exc

    try:
        ws = sh.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet_name, rows=2000, cols=KEY_COL)

    existing = ws.row_values(1)
    if existing[: len(HEADER)] != HEADER:
        ws.update(values=[HEADER], range_name="A1")
    return ws


def build_row(t: Any) -> list[str]:
    """Map an IasTransfer ORM object to a sheet row (header order)."""
    return [
        t.created_at.isoformat() if t.created_at else "",
        t.officer_name or "",
        t.ias_batch or "",
        t.cadre or "",
        t.state or "",
        t.previous_district or "",
        t.previous_posting or "",
        t.new_district or "",
        t.new_posting or "",
        t.transfer_date or "",
        t.effective_date or "",
        (t.reason or "")[:5000],
        t.notification_number or "",
        t.gov_order_link or "",
        t.source_name or "",
        t.source_url or "",
        f"{t.confidence_score:.2f}",
        t.status.value if hasattr(t.status, "value") else str(t.status),
        t.updated_at.isoformat() if t.updated_at else "",
    ]


def _find_row(ws, dedup_key: str) -> int | None:
    """Return the 1-based row index whose key column matches, else None."""
    if not dedup_key:
        return None
    try:
        keys = ws.col_values(KEY_COL)
    except Exception:  # noqa: BLE001
        return None
    for idx, value in enumerate(keys, start=1):
        if value == dedup_key:
            return idx
    return None


def upsert_transfer(t: Any) -> int:
    """Insert or update the row for a transfer. Returns the 1-based row index."""
    ws = _worksheet()
    row = build_row(t) + [t.dedup_key]
    existing_row = t.sheet_row or _find_row(ws, t.dedup_key)

    if existing_row and existing_row > 1:
        end_a1 = gspread.utils.rowcol_to_a1(existing_row, KEY_COL)
        ws.update(values=[row], range_name=f"A{existing_row}:{end_a1}")
        log.info("sheet_row_updated", row=existing_row, key=t.dedup_key)
        return existing_row

    ws.append_row(row, value_input_option="RAW")
    new_row = len(ws.col_values(KEY_COL))
    log.info("sheet_row_appended", row=new_row, key=t.dedup_key)
    return new_row


def sheet_health() -> dict[str, Any]:
    """Light-weight status for the Sheets Sync dashboard page."""
    try:
        ws = _worksheet()
        rows = max(0, len(ws.col_values(2)) - 1)  # minus header
        return {"connected": True, "total_rows": rows, "error": None}
    except GoogleSheetsError as exc:
        return {"connected": False, "total_rows": 0, "error": str(exc)}
