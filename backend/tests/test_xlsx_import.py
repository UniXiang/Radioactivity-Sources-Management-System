from io import BytesIO
import asyncio

from openpyxl import Workbook
import httpx


async def login(client):
    assert (await client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-password"})).status_code == 200


def xlsx_bytes():
    workbook = Workbook()
    first = workbook.active
    first.title = "2024"
    first.append(["Date", "Source", "Run", "Position", "Operator", "Comment", "OldField"])
    first.append(["2024/06/03", "Unknown old Ge68", "12345-12350", "Z=0", "Zhang", "ok", "ABC"])
    first.append(["2024/06/03", "Unknown old Ge68", "12345-12350", "Z=0", "Zhang", "ok", "ABC"])
    first.append(["bad-date", "Unknown old Ge68", "12345", "Z=1", "Zhang", "bad", "DEF"])
    first.append([None, None, None, None, None, None, None])
    second = workbook.create_sheet("Other")
    second.append(["Date", "Source"])
    second.append(["2024-01-01", "Ge68"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_xlsx_preview_validation_and_confirm(app):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await login(client)
            preview = await client.post("/api/v1/import/xlsx/preview", content=xlsx_bytes(), headers={"Content-Type": "application/octet-stream", "X-Filename": "history.xlsx"})
            assert preview.status_code == 200
            info = preview.json()
            assert {sheet["name"] for sheet in info["sheets"]} == {"2024", "Other"}
            mapping = {"calibration_date": "Date", "source_label_raw": "Source", "run_number": "Run", "position_label": "Position", "operator": "Operator", "comment": "Comment"}
            validation = await client.post("/api/v1/import/xlsx/validate", json={"upload_token": info["upload_token"], "sheet_name": "2024", "mapping": mapping})
            assert validation.status_code == 200
            summary = validation.json()["summary"]
            assert summary["total_rows"] == 3
            assert summary["failed_rows"] == 1
            assert summary["unmatched_sources"] == 3
            assert summary["duplicate_rows"] == 1
            confirm = await client.post("/api/v1/import/xlsx/confirm", json={"upload_token": info["upload_token"], "sheet_name": "2024", "mapping": mapping}, headers={"X-Filename": "history.xlsx"})
            assert confirm.status_code == 200
            assert confirm.json()["imported_rows"] == 1
            duplicate = await client.post("/api/v1/import/xlsx/confirm", json={"upload_token": info["upload_token"], "sheet_name": "2024", "mapping": mapping}, headers={"X-Filename": "history.xlsx"})
            assert duplicate.status_code == 400
            rows = (await client.get("/api/v1/calibrations")).json()
            assert rows[0]["source_id"] is None
            assert rows[0]["source_label_raw"] == "Unknown old Ge68"
            assert rows[0]["raw_data"]["OldField"] == "ABC"
    asyncio.run(run())
