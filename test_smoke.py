"""Quick smoke tests for MaintainSMIP API."""
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
    assert response.json()["user"]["role"] == "manager"


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