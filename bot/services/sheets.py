"""Google Sheets API integration service."""

import logging
from typing import Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetsService:
    """Handles all Google Sheets interactions."""

    def __init__(self, service_account_info: dict, spreadsheet_id: str, sheet_name: str):
        self._spreadsheet_id = spreadsheet_id
        self._sheet_name = sheet_name
        credentials = Credentials.from_service_account_info(
            service_account_info, scopes=SCOPES
        )
        self._service = build("sheets", "v4", credentials=credentials)
        self._sheets = self._service.spreadsheets()

    def get_list_values(self, range_name: str) -> list[str]:
        """Helper to get a list of values from a column."""
        try:
            result = self._sheets.values().get(
                spreadsheetId=self._spreadsheet_id,
                range=range_name,
            ).execute()
            values = result.get("values", [])
            # Return flattened list of non-empty strings
            return [str(row[0]).strip() for row in values if row and str(row[0]).strip()]
        except Exception as e:
            logger.error("Error fetching list %s: %s", range_name, e, exc_info=True)
            return []

    def get_users(self) -> list[str]:
        """Get valid user names from Списки!C2:C"""
        return self.get_list_values("Списки!C2:C")

    def get_projects(self) -> list[str]:
        """Get valid projects from Списки!K2:K"""
        return self.get_list_values("Списки!K2:K")

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
        """
        Append a row to the ДДС sheet.
        Row layout: A=Date, B=Type, C=Amount, D=Employee, E=empty, F=Project, G=Period, H=Comment.
        Uses safe append to range A5:H to avoid overwriting existing data.
        """
        values = [[date, operation_type, amount, employee_name, "", project, period, comment]]
        range_name = f"{self._sheet_name}!A5:H"

        try:
            result = self._sheets.values().append(
                spreadsheetId=self._spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": values},
            ).execute()

            logger.info(
                "Row appended to Google Sheets: %s (updated range: %s)",
                values,
                result.get("updates", {}).get("updatedRange", "unknown"),
            )
            return result

        except HttpError as e:
            logger.error("Google Sheets API error: %s", e, exc_info=True)
            return None
        except Exception as e:
            logger.error("Unexpected error appending to Google Sheets: %s", e, exc_info=True)
            return None
