"""Google Sheets API integration service — header-based smart writing."""

import logging
import time
from typing import Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Column index (0-based) → letter, e.g. 0→A, 25→Z, 26→AA
def _col_letter(index: int) -> str:
    result = ""
    index += 1  # 1-based
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


class SheetsService:
    """Handles all Google Sheets interactions."""

    def __init__(
        self,
        service_account_info: dict,
        spreadsheet_id: str,
        sheet_name: str,
        payments_spreadsheet_id: Optional[str] = None,
        dds_header_row: int = 4,
        payments_header_row: int = 1,
    ):
        self._spreadsheet_id = spreadsheet_id
        self._sheet_name = sheet_name
        self._payments_spreadsheet_id = payments_spreadsheet_id or spreadsheet_id
        self._dds_header_row = dds_header_row
        self._payments_header_row = payments_header_row

        credentials = Credentials.from_service_account_info(
            service_account_info, scopes=SCOPES
        )
        self._service = build("sheets", "v4", credentials=credentials)
        self._sheets = self._service.spreadsheets()

    # ── Generic helpers ────────────────────────────────────────────────────

    def get_list_values(self, range_name: str, spreadsheet_id: Optional[str] = None) -> list[str]:
        """Get a flat list of non-empty strings from a column range."""
        sid = spreadsheet_id or self._spreadsheet_id
        try:
            result = self._sheets.values().get(
                spreadsheetId=sid,
                range=range_name,
            ).execute()
            values = result.get("values", [])
            return [str(row[0]).strip() for row in values if row and str(row[0]).strip()]
        except Exception as e:
            logger.error("Error fetching list %s: %s", range_name, e, exc_info=True)
            return []

    def _get_actual_sheet_info(self, spreadsheet_id: str, target_title: str) -> Optional[tuple[str, int]]:
        """
        Check if a sheet matching target_title (ignoring case and spaces) exists.
        Returns (actual_title, sheet_id) if found, else None.
        """
        target_clean = target_title.replace(" ", "").lower()
        for attempt in range(1, 4):
            try:
                metadata = self._service.spreadsheets().get(
                    spreadsheetId=spreadsheet_id
                ).execute()
                for sheet in metadata.get("sheets", []):
                    actual_title = sheet["properties"]["title"]
                    if actual_title.replace(" ", "").lower() == target_clean:
                        return actual_title, sheet["properties"]["sheetId"]
                return None
            except Exception as e:
                if attempt < 3:
                    import time
                    logger.warning("Attempt %s/3 failed checking sheet %s existence: %s. Retrying...", attempt, target_title, e)
                    time.sleep(1.0)
                else:
                    logger.error("Error checking sheet existence: %s", e, exc_info=True)
        return None

    # ── Header-based smart write ───────────────────────────────────────────

    def _read_headers(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        header_row: int,
        retries: int = 3,
        retry_delay: float = 1.0,
    ) -> list[str]:
        """
        Read the header row and return a list of column names (0-indexed).
        header_row is 1-based (e.g. 4 means row 4).
        Retries on SSL/network errors.
        """
        range_name = f"'{sheet_name}'!{header_row}:{header_row}"
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                result = self._sheets.values().get(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                ).execute()
                rows = result.get("values", [])
                if not rows:
                    return []
                return [str(cell).strip() for cell in rows[0]]
            except Exception as e:
                last_exc = e
                if attempt < retries:
                    logger.warning(
                        "Attempt %s/%s failed reading headers from %s/%s row %s: %s — retrying in %.1fs",
                        attempt, retries, spreadsheet_id, sheet_name, header_row, e, retry_delay,
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error(
                        "Error reading headers from %s/%s row %s: %s",
                        spreadsheet_id, sheet_name, header_row, last_exc, exc_info=True,
                    )
        return []

    def _find_header_col(self, headers: list[str], target: str) -> Optional[int]:
        """
        Return the 0-based column index for the first header matching target
        (case-insensitive, stripped). Returns None if not found.
        """
        target_norm = target.strip().lower()
        for i, h in enumerate(headers):
            if h.strip().lower() == target_norm:
                return i
        return None

    def _find_bottom_row(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        start_row: int,
        col_letter: str = "A",
    ) -> int:
        """
        Scan a specific column `col_letter` starting from `start_row`.
        Returns the row index immediately after the LAST row that has 
        non-empty data in this column.
        """
        range_name = f"'{sheet_name}'!{col_letter}{start_row}:{col_letter}"
        
        for attempt in range(1, 4):
            try:
                result = self._sheets.values().get(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                ).execute()
                values = result.get("values", [])
                # len(values) gives the exact offset to the row after the last data cell in this column.
                return start_row + len(values)
            except Exception as e:
                if attempt < 3:
                    import time
                    logger.warning("Attempt %s/3 failed scanning range %s: %s. Retrying...", attempt, range_name, e)
                    time.sleep(1.0)
                else:
                    logger.error(
                        "Error scanning range %s in %s/%s: %s",
                        range_name, spreadsheet_id, sheet_name, e, exc_info=True,
                    )
                    raise RuntimeError(f"Could not scan range {range_name} due to network error.") from e

    def _write_row_by_headers(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        header_row: int,
        mapping: dict[str, object],
    ) -> Optional[dict]:
        """
        Core smart-write method.

        1. Reads headers from `header_row`.
        2. Builds a sparse row aligned to the header columns.
        3. Finds the first empty row (starting from header_row + 1).
        4. Writes via values().update().

        Args:
            mapping: {header_name: value} — only listed headers are written.
        """
        headers = self._read_headers(spreadsheet_id, sheet_name, header_row)
        if not headers:
            logger.error(
                "No headers found in %s/%s row %s — aborting write.",
                spreadsheet_id, sheet_name, header_row,
            )
            return None

        # Determine the widest column we need
        col_indices = {}
        for header_target in mapping:
            idx = self._find_header_col(headers, header_target)
            if idx is not None:
                col_indices[header_target] = idx
            else:
                logger.warning(
                    "Header '%s' not found in %s/%s — column skipped.",
                    header_target, spreadsheet_id, sheet_name,
                )

        if not col_indices:
            logger.error("No matching headers found — nothing to write.")
            return None

        max_col = max(col_indices.values())

        # Find bottom row using the first column we're going to write
        first_col_idx = min(col_indices.values())
        anchor_col_letter = _col_letter(first_col_idx)
        data_start_row = header_row + 1
        target_row = self._find_bottom_row(
            spreadsheet_id, sheet_name, data_start_row, anchor_col_letter
        )

        # Build the row (fill up to max_col with empty strings)
        row_data = [""] * (max_col + 1)
        for header_target, value in mapping.items():
            idx = col_indices.get(header_target)
            if idx is not None:
                row_data[idx] = value

        # Write via update (single row, exact position)
        start_col_letter = _col_letter(0)
        end_col_letter = _col_letter(max_col)
        write_range = f"'{sheet_name}'!{start_col_letter}{target_row}:{end_col_letter}{target_row}"

        try:
            result = self._sheets.values().update(
                spreadsheetId=spreadsheet_id,
                range=write_range,
                valueInputOption="USER_ENTERED",
                body={"values": [row_data]},
            ).execute()
            logger.info(
                "Row written to %s/%s at row %s (range: %s) — data: %s",
                spreadsheet_id, sheet_name, target_row,
                result.get("updatedRange", "unknown"), row_data,
            )
            return result
        except HttpError as e:
            logger.error(
                "Google Sheets API error writing to %s/%s: %s",
                spreadsheet_id, sheet_name, e, exc_info=True,
            )
            return None
        except Exception as e:
            logger.error(
                "Unexpected error writing to %s/%s: %s",
                spreadsheet_id, sheet_name, e, exc_info=True,
            )
            return None

    # ── Data fetchers ──────────────────────────────────────────────────────

    def get_users(self) -> list[str]:
        """Get valid user names from the 'Сотрудники' column in Списки sheet."""
        headers_row2 = self._read_headers(self._spreadsheet_id, "Списки", 2)
        
        idx = self._find_header_col(headers_row2, "Сотрудники")
        if idx is None:
            logger.error("Could not find 'Сотрудники' column in row 2 of Списки sheet.")
            return []
            
        col_letter = _col_letter(idx)
        return self.get_list_values(f"Списки!{col_letter}3:{col_letter}")

    def get_positions(self) -> list[str]:
        """Get positions from the 'Позиция' column in Списки sheet."""
        headers_row2 = self._read_headers(self._spreadsheet_id, "Списки", 2)
        
        idx = self._find_header_col(headers_row2, "Позиция")
        if idx is None:
            logger.error("Could not find 'Позиция' column in row 2 of Списки sheet.")
            return []
            
        col_letter = _col_letter(idx)
        return self.get_list_values(f"Списки!{col_letter}3:{col_letter}")

    def get_projects_for_operation(self, op_type: str) -> list[str]:
        """
        Find projects for a given operation type.
        
        New logic:
        1. Read row 2 of 'Списки' sheet to find all column headers.
        2. Search for a column where row 2 == op_type (e.g. "Съемки", "Пиар", "Таргет").
        3. If found, read values from row 3 downward in that column.
        4. If NOT found, return empty list (caller will skip project selection
           and default to "A.M. Maison").
        """
        headers_row2 = self._read_headers(self._spreadsheet_id, "Списки", 2)
        
        idx = self._find_header_col(headers_row2, op_type)
        if idx is None:
            logger.info("No project column found for operation type '%s' in row 2 — will use default project.", op_type)
            return []
            
        col_letter = _col_letter(idx)
        return self.get_list_values(f"Списки!{col_letter}3:{col_letter}")
        
    def get_operation_types(self) -> list[str]:
        """
        Get operation types from 'Списки' sheet.
        
        New logic: Read column P starting from row 3.
        Column P header (row 2) = "Тип операции".
        Values are filtered by checkboxes in the spreadsheet itself,
        so we just read whatever text values are present.
        """
        headers_row2 = self._read_headers(self._spreadsheet_id, "Списки", 2)
        
        idx = self._find_header_col(headers_row2, "Тип операции")
        if idx is None:
            logger.error("Could not find 'Тип операции' column in row 2 of Списки sheet.")
            return []
            
        col_letter = _col_letter(idx)
        return self.get_list_values(f"Списки!{col_letter}3:{col_letter}")

    def get_all_operation_types(self) -> list[str]:
        """
        Get all possible operation types from 'Списки' sheet.
        Header "Все операции" in row 2. (Usually column D).
        """
        headers_row2 = self._read_headers(self._spreadsheet_id, "Списки", 2)
        
        idx = self._find_header_col(headers_row2, "Все операции")
        if idx is None:
            logger.error("Could not find 'Все операции' column in row 2 of Списки sheet.")
            return []
            
        col_letter = _col_letter(idx)
        return self.get_list_values(f"Списки!{col_letter}3:{col_letter}")

    def get_allowed_ids(self) -> list[str]:
        """
        Get list of allowed Telegram IDs from the 'Доступ' column in 'Списки' sheet.
        """
        headers_row2 = self._read_headers(self._spreadsheet_id, "Списки", 2)
        
        idx = self._find_header_col(headers_row2, "Доступ")
        if idx is None:
            logger.error("Could not find 'Доступ' column in row 2 of Списки sheet.")
            return []
            
        col_letter = _col_letter(idx)
        return self.get_list_values(f"Списки!{col_letter}3:{col_letter}")

    # ── Write to ДДС ──────────────────────────────────────────────────────

    # Headers we map to in the ДДС sheet.
    # Key = exact header text in the spreadsheet (case-insensitive match).
    # Value = data to write.
    _DDS_HEADER_MAP = {
        "Дата": None,           # filled at call time
        "Тип операции": None,
        "Сумма": None,
        "Пользователь": None,
        "Проект": None,
        "За период": None,
        "Комментарий": None,
    }

    def append_to_dds(
        self,
        date: str,
        operation_type: str,
        amount: float,
        employee_name: str,
        project: str,
        period: str,
        comment: str,
    ) -> Optional[dict]:
        """
        Fast append to the ДДС sheet.
        Row layout: A=Date, B=Type, C=Amount, D=User, E=empty, F=Project, G=Period, H=Comment.
        """
        sheet_info = self._get_actual_sheet_info(self._spreadsheet_id, self._sheet_name)
        if not sheet_info:
            logger.error("Could not find ДДС sheet to get its ID.")
            return None
        actual_sheet_name, sheet_id = sheet_info

        values = [[date, operation_type, amount, employee_name, "", project, period, comment, False]]
        
        target_row = self._find_bottom_row(
            spreadsheet_id=self._spreadsheet_id,
            sheet_name=actual_sheet_name,
            start_row=5,
            col_letter='A',
        )
        range_name = f"'{actual_sheet_name}'!A{target_row}:I{target_row}"

        for attempt in range(3):
            try:
                result = self._sheets.values().update(
                    spreadsheetId=self._spreadsheet_id,
                    range=range_name,
                    valueInputOption="USER_ENTERED",
                    body={"values": values},
                ).execute()
                
                # Copy formatting (including checkboxes and dropdowns) from the row above
                if target_row > 5:
                    try:
                        self._service.spreadsheets().batchUpdate(
                            spreadsheetId=self._spreadsheet_id,
                            body={
                                "requests": [{
                                    "copyPaste": {
                                        "source": {
                                            "sheetId": sheet_id,
                                            "startRowIndex": target_row - 2,
                                            "endRowIndex": target_row - 1,
                                        },
                                        "destination": {
                                            "sheetId": sheet_id,
                                            "startRowIndex": target_row - 1,
                                            "endRowIndex": target_row,
                                        },
                                        "pasteType": "PASTE_FORMAT",
                                        "pasteOrientation": "NORMAL"
                                    }
                                },
                                {
                                    "copyPaste": {
                                        "source": {
                                            "sheetId": sheet_id,
                                            "startRowIndex": target_row - 2,
                                            "endRowIndex": target_row - 1,
                                        },
                                        "destination": {
                                            "sheetId": sheet_id,
                                            "startRowIndex": target_row - 1,
                                            "endRowIndex": target_row,
                                        },
                                        "pasteType": "PASTE_DATA_VALIDATION",
                                        "pasteOrientation": "NORMAL"
                                    }
                                }]
                            }
                        ).execute()
                    except Exception as format_exc:
                        logger.warning("Could not copy formatting to ДДС row %s: %s", target_row, format_exc)
                
                logger.info(
                    "Row written to ДДС: %s (updated range: %s)",
                    values,
                    result.get("updatedRange", "unknown"),
                )
                return result
            except Exception as e:
                logger.warning("Attempt %s/3 failed appending to ДДС: %s", attempt + 1, e)
                import time
                time.sleep(1)
        
        logger.error("Failed to append to ДДС after 3 attempts.")
        return None

    def _create_sheet(self, spreadsheet_id: str, title: str) -> Optional[tuple[str, int]]:
        """Create a new sheet with standard headers and return (title, sheet_id)."""
        try:
            body = {
                "requests": [{
                    "addSheet": {
                        "properties": {
                            "title": title
                        }
                    }
                }]
            }
            res = self._service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=body
            ).execute()
            sheet_id = res['replies'][0]['addSheet']['properties']['sheetId']
            
            # Write headers
            header_values = [
                ['Дата', 'Тип операции', 'Сумма', 'Пользователь', 'Получатель', 'Проект', 'За период', 'Комментарий', 'Оплата', '', 'ММ', 'ГГ', 'Расход', 'Приход']
            ]
            self._sheets.values().update(
                spreadsheetId=spreadsheet_id,
                range=f"'{title}'!A1:N1",
                valueInputOption="USER_ENTERED",
                body={"values": header_values}
            ).execute()
            
            logger.info("Successfully created new sheet '%s' with ID %s", title, sheet_id)
            return title, sheet_id
        except Exception as e:
            logger.error("Failed to create sheet %s: %s", title, e, exc_info=True)
            return None

    # ── Write to Оплаты ───────────────────────────────────────────────────

    def append_to_payments(
        self,
        project_name: str,
        date: str,
        operation_type: str,
        amount: float,
        employee_name: str,
        requisites: str,
        period: str = "",
    ) -> Optional[dict]:
        """
        Fast append to the Оплаты sheet (specific project sheet).
        Columns: A=Date, B=Type, C=Amount, D=User, E=empty, F=Project, G=Period, H=Comment.
        """
        sheet_info = self._get_actual_sheet_info(self._payments_spreadsheet_id, project_name)
        if not sheet_info:
            logger.info("Sheet matching '%s' not found. Attempting to create it...", project_name)
            sheet_info = self._create_sheet(self._payments_spreadsheet_id, project_name)
            if not sheet_info:
                logger.warning("Failed to create sheet '%s' — skipping payments write.", project_name)
                return False
            
        actual_sheet_name, sheet_id = sheet_info

        values = [[date, operation_type, amount, employee_name, "", project_name, period, requisites, False]]
        
        target_row = self._find_bottom_row(
            spreadsheet_id=self._payments_spreadsheet_id,
            sheet_name=actual_sheet_name,
            start_row=3,
            col_letter='A',
        )
        range_name = f"'{actual_sheet_name}'!A{target_row}:I{target_row}"

        for attempt in range(3):
            try:
                result = self._sheets.values().update(
                    spreadsheetId=self._payments_spreadsheet_id,
                    range=range_name,
                    valueInputOption="USER_ENTERED",
                    body={"values": values},
                ).execute()
                
                # Copy formatting (including checkboxes) from the row above
                if target_row > 3:
                    try:
                        self._service.spreadsheets().batchUpdate(
                            spreadsheetId=self._payments_spreadsheet_id,
                            body={
                                "requests": [{
                                    "copyPaste": {
                                        "source": {
                                            "sheetId": sheet_id,
                                            "startRowIndex": target_row - 2,
                                            "endRowIndex": target_row - 1,
                                        },
                                        "destination": {
                                            "sheetId": sheet_id,
                                            "startRowIndex": target_row - 1,
                                            "endRowIndex": target_row,
                                        },
                                        "pasteType": "PASTE_FORMAT",
                                        "pasteOrientation": "NORMAL"
                                    }
                                },
                                {
                                    "copyPaste": {
                                        "source": {
                                            "sheetId": sheet_id,
                                            "startRowIndex": target_row - 2,
                                            "endRowIndex": target_row - 1,
                                        },
                                        "destination": {
                                            "sheetId": sheet_id,
                                            "startRowIndex": target_row - 1,
                                            "endRowIndex": target_row,
                                        },
                                        "pasteType": "PASTE_DATA_VALIDATION",
                                        "pasteOrientation": "NORMAL"
                                    }
                                }]
                            }
                        ).execute()
                    except Exception as format_exc:
                        logger.warning("Could not copy formatting to Оплаты row %s: %s", target_row, format_exc)
                
                logger.info(
                    "Row written to Оплаты/%s: %s (updated range: %s)",
                    actual_sheet_name,
                    values,
                    result.get("updatedRange", "unknown"),
                )
                return result
            except Exception as e:
                logger.warning("Attempt %s/3 failed appending to Оплаты/%s: %s", attempt + 1, actual_sheet_name, e)
                import time
                time.sleep(1)
        
        logger.error("Failed to append to Оплаты/%s after 3 attempts.", actual_sheet_name)
        return None


    # ── Legacy alias for backward compatibility ────────────────────────────

    def append_row(
        self,
        date: str,
        operation_type: str,
        amount: float,
        employee_name: str,
        project: str,
        period: str,
        comment: str,
    ) -> Optional[dict]:
        """Backward-compatible wrapper — writes only to ДДС."""
        return self.append_to_dds(
            date=date,
            operation_type=operation_type,
            amount=amount,
            employee_name=employee_name,
            project=project,
            period=period,
            comment=comment,
        )

    def _dates_match(self, sheet_date: str, req_date: str) -> bool:
        """Helper to match dates, handling Google Sheets serial numbers like 46293."""
        sheet_date = sheet_date.strip()
        if sheet_date == req_date:
            return True
        try:
            val = float(sheet_date.replace(',', '.'))
            import datetime
            base_date = datetime.date(1899, 12, 30)
            delta = datetime.timedelta(days=int(val))
            if (base_date + delta).strftime("%d.%m.%Y") == req_date:
                return True
        except Exception:
            pass
        return False

    def _find_and_mark_row(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        data_start_row: int,
        req_data: dict,
        table_label: str,
    ) -> bool:
        """
        Search for the matching row in a sheet and set column I to TRUE.

        Matching logic:
          - Date (col A) — via _dates_match (handles serial numbers)
          - Operation type (col B)
          - Amount (col C) — float comparison ±0.01
          - Employee name (col D)
          - Project (col F, index 5)

        If no column F exists, we skip the project check (some Оплаты sheets
        may not have the empty column E, so project lands in col E instead).

        Returns True if we found and marked the row, False otherwise.
        """
        req_amount = float(req_data['amount'])
        range_name = f"'{sheet_name}'!A{data_start_row}:I"

        logger.info(
            "[%s] Searching for row: date=%s type=%s amount=%s user=%s project=%s  (range=%s, spreadsheet=%s)",
            table_label, req_data['date'], req_data['operation_type'],
            req_amount, req_data['employee_name'], req_data['project'],
            range_name, spreadsheet_id,
        )

        try:
            result = self._sheets.values().get(
                spreadsheetId=spreadsheet_id, range=range_name
            ).execute()
        except Exception as e:
            logger.error("[%s] Failed to read data: %s", table_label, e, exc_info=True)
            return False

        rows = result.get("values", [])
        if not rows:
            logger.warning("[%s] No data rows found in range %s", table_label, range_name)
            return False

        logger.info("[%s] Read %d rows starting at row %d", table_label, len(rows), data_start_row)

        best_match_score = 0
        best_match_details = ""

        for i, row in enumerate(rows):
            if len(row) < 4:
                continue

            # Parse amount
            try:
                sheet_amount = float(
                    str(row[2]).replace(',', '.').replace(' ', '').replace('\xa0', '')
                )
            except (ValueError, IndexError):
                continue

            # Check each field and collect match info
            date_ok = self._dates_match(row[0], req_data['date'])
            type_ok = row[1].strip() == req_data['operation_type']
            amount_ok = abs(sheet_amount - req_amount) < 0.01
            user_ok = row[3].strip() == req_data['employee_name']

            # Project check — try col F (index 5) first, then col E (index 4)
            project_ok = False
            if len(row) > 5 and row[5].strip():
                project_ok = row[5].strip() == req_data['project']
            elif len(row) > 4 and row[4].strip():
                # Fallback: maybe there's no empty column E in this sheet
                project_ok = row[4].strip() == req_data['project']
            else:
                # If neither col has data, skip project check entirely
                project_ok = True

            # Score this row
            score = sum([date_ok, type_ok, amount_ok, user_ok, project_ok])

            if score > best_match_score:
                best_match_score = score
                row_num = i + data_start_row
                project_val = repr(row[5]) if len(row) > 5 else 'N/A'
                best_match_details = (
                    f"row {row_num}: date={row[0]!r}({'✓' if date_ok else '✗'}) "
                    f"type={row[1]!r}({'✓' if type_ok else '✗'}) "
                    f"amount={row[2]!r}→{sheet_amount}({'✓' if amount_ok else '✗'}) "
                    f"user={row[3]!r}({'✓' if user_ok else '✗'}) "
                    f"project={project_val}({'✓' if project_ok else '✗'})"
                )

            if date_ok and type_ok and amount_ok and user_ok and project_ok:
                # ── Already marked? ──
                already_marked = (
                    len(row) > 8
                    and str(row[8]).strip().upper() in ("TRUE", "ИСТИНА", "1")
                )
                if already_marked:
                    logger.info("[%s] Row %d already marked as paid — skipping", table_label, i + data_start_row)
                    return True

                row_idx = i + data_start_row
                update_range = f"'{sheet_name}'!I{row_idx}"
                try:
                    self._sheets.values().update(
                        spreadsheetId=spreadsheet_id,
                        range=update_range,
                        valueInputOption="USER_ENTERED",
                        body={"values": [[True]]},
                    ).execute()
                    logger.info("[%s] ✅ Marked as paid at row %d", table_label, row_idx)
                    return True
                except Exception as e:
                    logger.error(
                        "[%s] Failed to write TRUE to %s: %s",
                        table_label, update_range, e, exc_info=True,
                    )
                    return False

        # If we get here, no exact match was found
        logger.warning(
            "[%s] ❌ Row NOT found. Best candidate (score %d/5): %s",
            table_label, best_match_score, best_match_details or "no rows checked",
        )
        return False

    def mark_as_paid(self, req_data: dict) -> bool:
        """
        Marks a specific request as paid (checks the box in column I)
        in both ДДС and Оплаты spreadsheets.

        Returns True only if BOTH tables were updated (or the Оплаты sheet
        does not exist for this project).
        """
        dds_ok = False
        payments_ok = False

        # 1. Update ДДС
        dds_sheet_info = self._get_actual_sheet_info(self._spreadsheet_id, self._sheet_name)
        if dds_sheet_info:
            actual_dds_name, _ = dds_sheet_info
            dds_ok = self._find_and_mark_row(
                spreadsheet_id=self._spreadsheet_id,
                sheet_name=actual_dds_name,
                data_start_row=5,
                req_data=req_data,
                table_label="ДДС",
            )
        else:
            logger.error("Could not find ДДС sheet '%s'", self._sheet_name)

        # 2. Update Оплаты
        payments_sheet_info = self._get_actual_sheet_info(
            self._payments_spreadsheet_id, req_data['project']
        )
        if payments_sheet_info:
            actual_pay_name, _ = payments_sheet_info
            payments_ok = self._find_and_mark_row(
                spreadsheet_id=self._payments_spreadsheet_id,
                sheet_name=actual_pay_name,
                data_start_row=3,
                req_data=req_data,
                table_label=f"Оплаты/{req_data['project']}",
            )
        else:
            logger.warning(
                "Sheet '%s' not found in payments spreadsheet — skipping.",
                req_data['project'],
            )
            # No payments sheet = not an error, consider it ok
            payments_ok = True

        logger.info("mark_as_paid result: ДДС=%s, Оплаты=%s", dds_ok, payments_ok)
        return {"dds_ok": dds_ok, "payments_ok": payments_ok}

