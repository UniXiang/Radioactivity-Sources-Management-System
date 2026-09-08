from datetime import datetime, timezone
import asyncio

import httpx


async def login(client, username, password):
    response = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200


def source_payload():
    return {
        "display_name": "Ge68-01", "isotope": "Ge-68", "serial_number": "GE-001",
        "activity": {"reference_value": 100000, "reference_unit": "Bq", "reference_date": "2026-01-01T00:00:00+00:00"},
        "location": {"building": "Calibration Room", "cabinet": "A", "position": "A-01"},
    }


def test_source_state_workflow_and_permissions(app):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/health")).json()["status"] == "ok"
            assert (await client.patch("/api/v1/sources/none", json={"display_name": "bad"})).status_code == 401
            await login(client, "viewer", "viewer-password")
            assert (await client.post("/api/v1/sources", json=source_payload())).status_code == 403
            await client.post("/api/v1/auth/logout")
            await login(client, "admin", "admin-password")
            created = await client.post("/api/v1/sources", json=source_payload())
            assert created.status_code == 201
            source_id = created.json()["source_id"]
            updated = await client.patch(f"/api/v1/sources/{source_id}", json={"activity": {"reference_value": 99000, "reference_unit": "Bq", "reference_date": "2026-01-01T00:00:00+00:00"}})
            assert updated.status_code == 200 and updated.json()["activity"]["reference_value"] == 99000
            await client.post("/api/v1/auth/logout")
            await login(client, "operator", "operator-password")
            assert (await client.patch(f"/api/v1/sources/{source_id}", json={"activity": {"reference_value": 1, "reference_unit": "Bq", "reference_date": "2026-01-01T00:00:00+00:00"}})).status_code == 403
            checkout = await client.post(f"/api/v1/sources/{source_id}/checkout", json={"holder": "Zhang", "purpose": "ACU calibration"})
            assert checkout.status_code == 200 and checkout.json()["status"] == "checked_out"
            start = await client.post(f"/api/v1/sources/{source_id}/calibration/start", json={"calibration_system": "ACU", "operator": "operator", "purpose": "run"})
            assert start.status_code == 200 and start.json()["source"]["status"] == "calibrating"
            end = await client.post(f"/api/v1/sources/{source_id}/calibration/end")
            assert end.status_code == 200 and end.json()["status"] == "checked_out"
            returned_status = await client.post(f"/api/v1/sources/{source_id}/return", json={"location": {"building": "Room"}})
            assert returned_status.status_code == 200 and returned_status.json()["status"] == "in_stock"
            returned = (await client.get(f"/api/v1/sources/{source_id}")).json()
            actions = [row["action"] for row in returned["transactions"]]
            assert {"create", "checkout", "return", "calibration_start", "calibration_end"}.issubset(actions)
            assert len(returned["calibrations"]) == 1
            assert returned["calibrations"][0]["end_time"] is not None
            activity = await client.get(f"/api/v1/sources/{source_id}/activity?time=2026-01-01T00:00:00Z")
            assert activity.status_code == 200 and activity.json()["activity"]["value"] == 99
    asyncio.run(run())


def test_anonymous_viewer_is_read_only(app):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            me = await client.get("/api/v1/auth/me")
            assert me.status_code == 200 and me.json()["role"] == "viewer" and me.json()["guest"] is True
            assert (await client.get("/api/v1/dashboard")).status_code == 200
            assert (await client.get("/api/v1/sources")).status_code == 200
            assert (await client.get("/api/v1/calibrations")).status_code == 200
            assert (await client.patch("/api/v1/sources/none", json={"display_name": "blocked"})).status_code == 401
            assert (await client.get("/api/v1/audit")).status_code == 401
    asyncio.run(run())


def test_server_restart_keeps_registries(app, test_settings):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await login(client, "admin", "admin-password")
            source_id = (await client.post("/api/v1/sources", json=source_payload())).json()["source_id"]
            first = (await client.get(f"/api/v1/sources/{source_id}")).json()
        from app.main import create_app
        restarted = create_app(test_settings)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restarted), base_url="http://test") as client:
            await login(client, "admin", "admin-password")
            second = (await client.get(f"/api/v1/sources/{source_id}")).json()
            assert second["source"]["source_id"] == first["source"]["source_id"]
    asyncio.run(run())
