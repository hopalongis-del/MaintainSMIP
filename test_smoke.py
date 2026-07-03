"""Quick smoke tests for MaintainSMIP API."""
from fastapi.testclient import TestClient

import server

def main() -> None:
    with TestClient(server.app) as client:
        run_tests(client)


def login(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"password": "WeLoveRacing!"})
    assert response.status_code == 200, response.text


def run_tests(client: TestClient) -> None:
    login(client)

    stats = client.get("/api/stats")
    assert stats.status_code == 200, stats.text

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
            "assigned_to": "Mike Casady",
            "location": "SMIP",
            "due_date": "2026-07-10T00:00:00",
            "labor_minutes": 15,
            "parts_used": [],
            "comments": [],
        },
    )
    assert create.status_code == 200, create.text
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

    delete = client.delete(f"/api/workorders/{wo_id}")
    assert delete.status_code == 200, delete.text

    print("ALL TESTS PASSED")
    print("stats:", stats.json())
    print("wo_templates:", len(wo_templates.json()))
    print("work_orders:", len(wos.json()))
    print("pm_templates:", len(templates.json()))
    print("pm_records:", len(records.json()))
    print("carts:", len(carts.json()))
    print("accidents:", len(accidents.json()))
    print("open_accidents stat:", stats.json().get("open_accidents"))


if __name__ == "__main__":
    main()