"""Quick smoke tests for MaintainSMIP API."""
import time

from fastapi.testclient import TestClient

import server


def main() -> None:
    with TestClient(server.app) as client:
        run_tests(client)


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "WeLoveRacing!"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["user"]["username"] == "admin"
    assert body["user"]["role"] == "admin"

    me = client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["display_name"] == "Master Admin"


def test_legacy_password_login(client: TestClient) -> None:
    client.post("/api/auth/logout")
    response = client.post("/api/auth/login", json={"password": "WeLoveRacing!"})
    assert response.status_code == 200, response.text
    assert response.json()["user"]["username"] == "admin"


def test_seeded_user_resync_login(client: TestClient) -> None:
    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/login",
        json={"username": "mike.casady", "password": "WeLoveRacing!"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["role"] == "admin"


def test_admin_user_management(client: TestClient) -> None:
    login(client)

    created = client.post(
        "/api/users",
        json={
            "username": "smoke.temp",
            "display_name": "Smoke Temp",
            "role": "technician",
            "password": "TempPass123!",
        },
    )
    assert created.status_code == 200, created.text
    temp_user = created.json()
    temp_id = temp_user["id"]

    reset = client.put(
        f"/api/users/{temp_id}",
        json={"password": "ResetPass456!"},
    )
    assert reset.status_code == 200, reset.text

    client.post("/api/auth/logout")
    temp_login = client.post(
        "/api/auth/login",
        json={"username": "smoke.temp", "password": "ResetPass456!"},
    )
    assert temp_login.status_code == 200, temp_login.text
    client.post("/api/auth/logout")

    login(client)
    deleted = client.delete(f"/api/users/{temp_id}")
    assert deleted.status_code == 200, deleted.text

    client.post("/api/auth/logout")
    deactivated_login = client.post(
        "/api/auth/login",
        json={"username": "smoke.temp", "password": "ResetPass456!"},
    )
    assert deactivated_login.status_code == 401, deactivated_login.text

    login(client)
    me = client.get("/api/auth/me").json()
    self_delete = client.delete(f"/api/users/{me['id']}")
    assert self_delete.status_code == 400, self_delete.text
    assert "own account" in self_delete.json()["detail"].lower()

    admins = [user for user in client.get("/api/users").json() if user["role"] == "admin"]
    if len(admins) == 1:
        last_admin_id = admins[0]["id"]
        block = client.delete(f"/api/users/{last_admin_id}")
        assert block.status_code == 400, block.text


def test_change_password(client: TestClient) -> None:
    client.post("/api/auth/logout")
    login = client.post(
        "/api/auth/login",
        json={"username": "mike.casady", "password": "WeLoveRacing!"},
    )
    assert login.status_code == 200, login.text

    bad = client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong-password", "new_password": "NewPass123!"},
    )
    assert bad.status_code == 400, bad.text

    changed = client.post(
        "/api/auth/change-password",
        json={"current_password": "WeLoveRacing!", "new_password": "NewPass123!"},
    )
    assert changed.status_code == 200, changed.text

    client.post("/api/auth/logout")
    old_login = client.post(
        "/api/auth/login",
        json={"username": "mike.casady", "password": "WeLoveRacing!"},
    )
    assert old_login.status_code == 401, old_login.text

    new_login = client.post(
        "/api/auth/login",
        json={"username": "mike.casady", "password": "NewPass123!"},
    )
    assert new_login.status_code == 200, new_login.text

    client.post(
        "/api/auth/change-password",
        json={"current_password": "NewPass123!", "new_password": "WeLoveRacing!"},
    )
    client.post("/api/auth/logout")


def run_tests(client: TestClient) -> None:
    login(client)
    test_legacy_password_login(client)
    test_seeded_user_resync_login(client)
    test_change_password(client)
    test_admin_user_management(client)
    login(client)

    stats = client.get("/api/stats")
    assert stats.status_code == 200, stats.text

    users = client.get("/api/users")
    assert users.status_code == 200, users.text
    assert any(user["username"] == "admin" for user in users.json())

    wo_templates = client.get("/api/wo/templates")
    assert wo_templates.status_code == 200, wo_templates.text
    assert len(wo_templates.json()) >= 1, wo_templates.text

    wos = client.get("/api/workorders")
    assert wos.status_code == 200, wos.text

    templates = client.get("/api/pm/templates")
    assert templates.status_code == 200, templates.text

    records = client.get("/api/pm/records")
    assert records.status_code == 200, records.text

    carts = client.get("/api/carts")
    assert carts.status_code == 200, carts.text
    assert len(carts.json()) > 0

    smoke_cart_id = f"SMOKE-TEST-{int(time.time())}"

    create_cart = client.post(
        "/api/carts",
        json={
            "id": smoke_cart_id,
            "serial": "SMOKE-123",
            "model": "Carryall 1",
            "year": "2024",
            "location": "SMIP",
            "status": "active",
            "notes": "Smoke test cart",
        },
    )
    assert create_cart.status_code == 200, create_cart.text
    assert create_cart.json()["serial"] == "SMOKE-123"

    missing_fields = client.post(
        "/api/carts",
        json={"id": "SMOKE-TEST-2", "serial": "ONLY-SERIAL"},
    )
    assert missing_fields.status_code == 422, missing_fields.text

    duplicate_cart = client.post(
        "/api/carts",
        json={
            "id": smoke_cart_id,
            "serial": "SMOKE-123",
            "model": "Carryall 1",
            "year": "2024",
            "location": "SMIP",
            "status": "active",
        },
    )
    assert duplicate_cart.status_code == 409, duplicate_cart.text

    blank_serial = client.put(
        f"/api/carts/{smoke_cart_id}",
        json={"serial": ""},
    )
    assert blank_serial.status_code == 422, blank_serial.text

    update_cart = client.put(
        f"/api/carts/{smoke_cart_id}",
        json={"location": "Charlotte", "notes": "Updated smoke cart"},
    )
    assert update_cart.status_code == 200, update_cart.text
    assert update_cart.json()["location"] == "Charlotte"

    retire_cart = client.put(
        f"/api/carts/{smoke_cart_id}",
        json={"status": "retired"},
    )
    assert retire_cart.status_code == 200, retire_cart.text
    assert retire_cart.json()["status"] == "retired"

    cart_audit = client.get(f"/api/audit?entity_type=cart&entity_id={smoke_cart_id}")
    assert cart_audit.status_code == 200, cart_audit.text
    cart_audit_entries = cart_audit.json()
    assert len(cart_audit_entries) >= 2, cart_audit.text
    assert any("Added cart" in entry["summary"] for entry in cart_audit_entries)
    assert any("Retired cart" in entry["summary"] for entry in cart_audit_entries)

    activity_page = client.get("/activity.html")
    assert activity_page.status_code == 200, activity_page.text

    reports_page = client.get("/reports.html")
    assert reports_page.status_code == 200, reports_page.text

    vapid = client.get("/api/push/vapid-public-key")
    assert vapid.status_code == 200, vapid.text
    assert vapid.json().get("public_key")

    prefs = client.put(
        "/api/notifications/preferences",
        json={
            "notify_overdue_wo": True,
            "notify_pm_due": True,
            "notify_accidents": False,
        },
    )
    assert prefs.status_code == 200, prefs.text
    assert prefs.json()["notify_accidents"] is False

    push_status = client.get("/api/push/status")
    assert push_status.status_code == 200, push_status.text
    assert push_status.json()["subscribed"] is False

    service_worker = client.get("/service-worker.js")
    assert service_worker.status_code == 200, service_worker.text

    activity_log = client.get("/api/audit?limit=50&days=30")
    assert activity_log.status_code == 200, activity_log.text
    assert isinstance(activity_log.json(), list)

    health = client.get("/api/health")
    assert health.status_code == 200, health.text
    health_data = health.json()
    assert health_data["status"] == "ok"
    assert health_data["db_exists"] is True
    assert str(server.DB_PATH).endswith("maintainsmip.db")
    assert str(server.DATA_DIR) in health_data["data_dir"]
    assert client.get("/").status_code == 200
    assert client.get("/login.html").status_code == 200
    assert client.get("/logo1.png").status_code == 200
    assert client.get("/shared.css").status_code == 200
    assert client.get("/accidents.html").status_code == 200

    accidents = client.get("/api/accidents")
    assert accidents.status_code == 200, accidents.text
    assert len(accidents.json()) >= 2

    create = client.post(
        "/api/workorders",
        json={
            "cart_id": 2000,
            "title": "Smoke test WO",
            "description": "Temporary test order",
            "priority": "low",
            "status": "open",
            "type": "inspection",
            "assigned_to": "",
            "location": "SMIP",
            "due_date": "2026-07-10T00:00:00",
            "labor_minutes": 15,
            "parts_used": [],
            "comments": [],
        },
    )
    assert create.status_code == 200, create.text
    assert create.json()["assigned_to"] == "Master Admin"
    wo_id = create.json()["id"]

    update = client.put(f"/api/workorders/{wo_id}", json={"status": "in_progress"})
    assert update.status_code == 200, update.text

    edit = client.put(
        f"/api/workorders/{wo_id}",
        json={
            "title": "Updated smoke test WO",
            "description": "Edited description",
            "priority": "high",
            "type": "battery",
        },
    )
    assert edit.status_code == 200, edit.text
    assert edit.json()["title"] == "Updated smoke test WO"

    audit = client.get(f"/api/audit?entity_type=work_order&entity_id={wo_id}")
    assert audit.status_code == 200, audit.text
    audit_entries = audit.json()
    assert len(audit_entries) >= 2, audit.text
    assert any("Created WO-" in entry["summary"] for entry in audit_entries)
    assert any("status" in entry["summary"].lower() for entry in audit_entries)

    delete = client.delete(f"/api/workorders/{wo_id}")
    assert delete.status_code == 200, delete.text

    accident = client.post(
        "/api/accidents",
        json={
            "cart_id": 2000,
            "description": "Smoke test accident damage",
            "severity": "minor",
            "status": "reported",
        },
    )
    assert accident.status_code == 200, accident.text
    assert accident.json()["reported_by"] == "Master Admin"
    accident_id = accident.json()["id"]
    photo = client.post(
        f"/api/accidents/{accident_id}/photos",
        files={"file": ("damage.jpg", b"not-a-real-jpeg-but-ok-for-test", "")},
    )
    assert photo.status_code == 200, photo.text
    photo_path = photo.json()["path"]
    assert client.get(f"/{photo_path}").status_code == 200
    accident_audit = client.get(f"/api/audit?entity_type=accident&entity_id={accident_id}")
    assert accident_audit.status_code == 200, accident_audit.text
    assert any("Reported ACC-" in entry["summary"] for entry in accident_audit.json())

    assert client.delete(f"/api/accidents/{accident_id}").status_code == 200

    print("ALL TESTS PASSED")
    print("stats:", stats.json())
    print("users:", len(users.json()))
    print("wo_templates:", len(wo_templates.json()))
    print("work_orders:", len(wos.json()))
    print("pm_templates:", len(templates.json()))
    print("pm_records:", len(records.json()))
    print("carts:", len(carts.json()))
    print("accidents:", len(accidents.json()))
    print("open_accidents stat:", stats.json().get("open_accidents"))


if __name__ == "__main__":
    main()