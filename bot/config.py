"""Application settings loaded from environment variables."""

import json
import re
from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str
    google_sheet_id: str
    sheet_name: str = "ДДС"
    google_service_account_file: Optional[str] = None
    google_service_account_json: Optional[str] = None
    database_path: str = "data/bot.db"

    @field_validator("google_sheet_id")
    @classmethod
    def extract_sheet_id(cls, v: str) -> str:
        """Extract sheet ID from a full Google Sheets URL if provided."""
        if v.startswith("http"):
            match = re.search(r"/d/([a-zA-Z0-9-_]+)", v)
            if match:
                return match.group(1)
            raise ValueError(f"Could not extract sheet ID from URL: {v}")
        return v

    def get_service_account_info(self) -> dict:
        """Load service account credentials from file or env variable."""
        if self.google_service_account_file:
            path = Path(self.google_service_account_file)
            if path.exists():
                return json.loads(path.read_text())
        if self.google_service_account_json:
            return json.loads(self.google_service_account_json)
        raise ValueError(
            "No Google service account credentials found. "
            "Set GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON."
        )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
