import asyncio
from bot.config import settings
from bot.services.sheets import SheetsService

async def main():
    sheets = SheetsService(
        service_account_info=settings.get_service_account_info(),
        spreadsheet_id=settings.google_sheet_id,
        sheet_name=settings.sheet_name,
    )
    users_I = sheets.get_list_values("Списки!I2:I")
    users_C = sheets.get_list_values("Списки!C2:C")
    projects_K = sheets.get_list_values("Списки!K2:K")
    print("USERS in I:", users_I)
    print("USERS in C:", users_C)
    print("PROJECTS in K:", projects_K)

if __name__ == "__main__":
    asyncio.run(main())

