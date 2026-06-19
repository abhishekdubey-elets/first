"""Google Sheets Agent.

Pushes verified transfer records to Google Sheets (one row per record; updates
in place on changes) and writes a SheetSyncLog audit entry per run.
"""
from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.enums import LogLevel, SyncStatus, TransferStatus
from app.models.log import SheetSyncLog
from app.models.transfer import IasTransfer
from app.services import google_sheets
from app.services.app_settings import get_export_config


class SheetsAgent(BaseAgent):
    name = "sheets"

    def export(self, transfer: IasTransfer) -> bool:
        """Upsert a single transfer to the sheet. Returns success."""
        cfg = get_export_config()
        if not cfg.get("auto_export"):
            return False
        if not cfg.get("credentials_uploaded") or not cfg.get("spreadsheet_id"):
            self.audit("export", "Sheets export skipped: not configured",
                       level=LogLevel.WARNING, transfer_id=transfer.id)
            self._log_sync(SyncStatus.SKIPPED, 0, 0, "Sheets not configured")
            return False
        try:
            row = google_sheets.upsert_transfer(transfer)
            transfer.sheet_row = row
            transfer.status = TransferStatus.EXPORTED
            self.audit("export", f"Exported transfer {transfer.id} to row {row}",
                       level=LogLevel.SUCCESS, transfer_id=transfer.id, row=row)
            self._log_sync(SyncStatus.SUCCESS, 1, 0, f"row {row}")
            return True
        except Exception as exc:  # noqa: BLE001
            transfer.status = TransferStatus.EXPORT_FAILED
            self.audit("export", f"Sheets export failed for transfer {transfer.id}",
                       level=LogLevel.ERROR, transfer_id=transfer.id, error=str(exc))
            self._log_sync(SyncStatus.FAILED, 0, 1, str(exc))
            return False

    def _log_sync(self, status: SyncStatus, written: int, failed: int, msg: str) -> None:
        if self.db is not None:
            self.db.add(SheetSyncLog(status=status, rows_written=written,
                                     rows_failed=failed, message=msg[:1000]))
            self.db.flush()
