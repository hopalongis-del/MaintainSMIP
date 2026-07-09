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
    me_body = me.json()
    assert me_body["display_name"] == "Master Admin"
    assert "password_changed" in me_body
    assert isinstance(me_body["password_changed"], bool)


def test_legacy_password_login(client: TestClient) -> None:
    client.post("/api/auth/logout")
    response = client.post("/api/auth/login", json={"password": "WeLoveRacing!"})
    assert response.status_code == 200, response.text
    assert response.json()["user"]["username"] == "admin"


def ensure_mike_test_password(client: TestClient, password: str = "mike") -> None:
    """Reset owner account to known credentials (username mike / password mike)."""
    login(client)
    users = client.get("/api/users").json()
    mike = next((user for user in users if user["username"] == "mike"), None)
    if not mike:
        return
    client.put(f"/api/users/{mike['id']}", json={"password": password})
    client.post("/api/auth/logout")


def test_owner_login(client: TestClient) -> None:
    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/login",
        json={"username": "mike", "password": "mike"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["username"] == "mike"
    assert body["user"]["role"] == "admin"
    assert body["user"]["password_changed"] is True


def test_team_members_and_audit_users(client: TestClient) -> None:
    login(client)
    team = client.get("/api/users/team-members")
    assert team.status_code == 200, team.text
    assert len(team.json()) >= 1

    audit_users = client.get("/api/audit/usernames")
    assert audit_users.status_code == 200, audit_users.text
    assert isinstance(audit_users.json(), list)


def test_pm_automation_rules(client: TestClient) -> None:
    login(client)
    created = client.post(
        "/api/pm/automation-rules",
        json={
            "name": "Smoke PM Automation",
            "template_id": "PM-TPL-001",
            "enabled": True,
            "scope_type": "all",
            "scope_values": [],
            "lead_days": 14,
        },
    )
    assert created.status_code == 200, created.text
    rule_id = created.json()["id"]

    listed = client.get("/api/pm/automation-rules")
    assert listed.status_code == 200, listed.text
    assert any(rule["id"] == rule_id for rule in listed.json())

    run_now = client.post("/api/pm/automation-rules/run-now")
    assert run_now.status_code == 200, run_now.text

    deleted = client.delete(f"/api/pm/automation-rules/{rule_id}")
    assert deleted.status_code == 200, deleted.text


def test_database_backup(client: TestClient) -> None:
    login(client)

    info = client.get("/api/admin/backup/info")
    assert info.status_code == 200, info.text
    info_data = info.json()
    assert info_data["exists"] is True
    assert info_data["size_bytes"] > 0

    backup = client.get("/api/admin/backup")
    assert backup.status_code == 200, backup.text
    assert backup.content.startswith(b"SQLite format 3")

    client.post("/api/auth/logout")
    denied = client.get("/api/admin/backup")
    assert denied.status_code == 401


def test_database_restore(client: TestClient) -> None:
    login(client)

    backup = client.get("/api/admin/backup")
    assert backup.status_code == 200, backup.text
    backup_bytes = backup.content

    restored = client.post(
        "/api/admin/restore",
        files={"file": ("restore-test.db", backup_bytes, "application/x-sqlite3")},
    )
    assert restored.status_code == 200, restored.text
    data = restored.json()
    assert data["ok"] is True
    assert data["size_bytes"] == len(backup_bytes)
    assert data.get("pre_restore_backup")

    bad = client.post(
        "/api/admin/restore",
        files={"file": ("bad.db", b"not sqlite", "application/octet-stream")},
    )
    assert bad.status_code == 400

    client.post("/api/auth/logout")
    denied = client.post(
        "/api/admin/restore",
        files={"file": ("restore-test.db", backup_bytes, "application/x-sqlite3")},
    )
    assert denied.status_code == 401


def test_database_backup_token(client: TestClient) -> None:
    token = "smoke-backup-token-12345"
    original = server.BACKUP_TOKEN
    server.BACKUP_TOKEN = token
    try:
        backup = client.get(
            "/api/admin/backup",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert backup.status_code == 200, backup.text
        assert backup.content.startswith(b"SQLite format 3")

        bad = client.get(
            "/api/admin/backup",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert bad.status_code == 401
    finally:
        server.BACKUP_TOKEN = original


def test_admin_user_management(client: TestClient) -> None:
    login(client)

    temp_username = f"smoke.temp.{int(time.time())}"
    created = client.post(
        "/api/users",
        json={
            "username": temp_username,
            "display_name": "Smoke Temp",
            "role": "technician",
            "password": "TempPass123!",
        },
    )
    assert created.status_code == 200, created.text
    temp_id = created.json()["id"]

    reset = client.put(
        f"/api/users/{temp_id}",
        json={"password": "ResetPass456!"},
    )
    assert reset.status_code == 200, reset.text

    client.post("/api/auth/logout")
    temp_login = client.post(
        "/api/auth/login",
        json={"username": temp_username, "password": "ResetPass456!"},
    )
    assert temp_login.status_code == 200, temp_login.text
    client.post("/api/auth/logout")

    login(client)
    deleted = client.delete(f"/api/users/{temp_id}")
    assert deleted.status_code == 200, deleted.text

    client.post("/api/auth/logout")
    deactivated_login = client.post(
        "/api/auth/login",
        json={"username": temp_username, "password": "ResetPass456!"},
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
        json={"username": "mike", "password": "mike"},
    )
    assert login.status_code == 200, login.text

    bad = client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong-password", "new_password": "NewPass123!"},
    )
    assert bad.status_code == 400, bad.text

    changed = client.post(
        "/api/auth/change-password",
        json={"current_password": "mike", "new_password": "NewPass123!"},
    )
    assert changed.status_code == 200, changed.text

    client.post("/api/auth/logout")
    old_login = client.post(
        "/api/auth/login",
        json={"username": "mike", "password": "mike"},
    )
    assert old_login.status_code == 401, old_login.text

    new_login = client.post(
        "/api/auth/login",
        json={"username": "mike", "password": "NewPass123!"},
    )
    assert new_login.status_code == 200, new_login.text

    # Self-service change requires 8+ chars; restore short owner password via admin reset.
    ensure_mike_test_password(client, "mike")


def _is_numeric_cart_id(value) -> bool:
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False


def ensure_smoke_cart(client: TestClient) -> dict:
    """Create (or return) a disposable cart with a numeric id for PM/WO APIs."""
    carts = client.get("/api/carts").json()
    active = next(
        (
            c
            for c in carts
            if str(c.get("status", "")).lower() != "retired" and _is_numeric_cart_id(c.get("id"))
        ),
        None,
    )
    if active:
        return active
    cart_id = int(time.time()) % 900000 + 100000
    created = client.post(
        "/api/carts",
        json={
            "id": cart_id,
            "serial": f"SN-{cart_id}",
            "model": "Carryall 1",
            "year": "2024",
            "location": "Shop",
            "status": "active",
            "notes": "Smoke test cart",
        },
    )
    assert created.status_code == 200, created.text
    return created.json()


def test_pm_record_dedup(client: TestClient) -> None:
    login(client)
    templates = client.get("/api/pm/templates").json()
    assert templates, "Need at least one PM template for dedup test"
    template = templates[0]
    cart = ensure_smoke_cart(client)

    payload = {
        "template_id": template["id"],
        "template_name": template["name"],
        "description": template.get("description") or "Smoke dedup test",
        "cart_id": cart["id"],
        "location": cart.get("location") or "Shop",
        "scheduled_date": "2099-01-01T00:00:00",
        "completed_date": None,
        "status": "scheduled",
        "checklist_results": [],
        "tech_name": "Smoke Tester",
        "labor_minutes": 0,
        "linked_wo_ids": [],
    }
    first = client.post("/api/pm/records", json=payload)
    assert first.status_code == 200, first.text
    record_id = first.json()["id"]

    duplicate = client.post("/api/pm/records", json=payload)
    assert duplicate.status_code == 409, duplicate.text

    client.delete(f"/api/pm/records/{record_id}")


def test_parts_module(client: TestClient) -> None:
    login(client)

    stats = client.get("/api/parts/stats")
    assert stats.status_code == 200, stats.text
    body = stats.json()
    assert "active_parts" in body
    assert "low_stock" in body

    vendor = client.post(
        "/api/vendors",
        json={
            "name": f"Smoke Vendor {int(time.time())}",
            "email": "smoke@example.com",
            "default_terms": "Net 30",
            "active": True,
        },
    )
    assert vendor.status_code == 200, vendor.text
    vendor_id = vendor.json()["id"]

    part = client.post(
        "/api/parts",
        json={
            "part_number": f"SMK-{int(time.time()) % 100000}",
            "description": "Smoke test brake pad",
            "category": "Brakes",
            "vendor_id": vendor_id,
            "unit_of_measure": "each",
            "unit_cost": 12.5,
            "on_hand": 2,
            "reorder_point": 5,
            "reorder_qty": 10,
            "location": "Cage A",
            "active": True,
        },
    )
    assert part.status_code == 200, part.text
    part_id = part.json()["id"]
    assert part.json()["needs_reorder"] is True

    listed = client.get("/api/parts?low_stock=1")
    assert listed.status_code == 200, listed.text
    assert any(item["id"] == part_id for item in listed.json())

    adjusted = client.post(
        f"/api/parts/{part_id}/adjust",
        json={"delta": 8, "note": "smoke receive"},
    )
    assert adjusted.status_code == 200, adjusted.text
    assert adjusted.json()["on_hand"] == 10
    assert adjusted.json()["needs_reorder"] is False

    # Drop back below reorder so from-reorder works
    client.post(f"/api/parts/{part_id}/adjust", json={"delta": -8, "note": "smoke use"})

    po = client.post(f"/api/purchase-orders/from-reorder?vendor_id={vendor_id}")
    assert po.status_code == 200, po.text
    po_body = po.json()
    assert po_body["status"] == "draft"
    assert po_body["po_number"]
    assert len(po_body["lines"]) >= 1

    approved = client.put(
        f"/api/purchase-orders/{po_body['id']}",
        json={"status": "approved"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_by"]

    vendors = client.get("/api/vendors")
    assert vendors.status_code == 200, vendors.text
    assert any(item["id"] == vendor_id for item in vendors.json())


def test_new_user_must_change_password_flag(client: TestClient) -> None:
    login(client)
    temp_username = f"smoke.temp.{int(time.time())}"
    created = client.post(
        "/api/users",
        json={
            "username": temp_username,
            "display_name": "Smoke Temp",
            "role": "technician",
            "password": "TempPass123!",
        },
    )
    assert created.status_code == 200, created.text

    client.post("/api/auth/logout")
    login_resp = client.post(
        "/api/auth/login",
        json={"username": temp_username, "password": "TempPass123!"},
    )
    assert login_resp.status_code == 200, login_resp.text
    assert login_resp.json()["user"]["password_changed"] is False

    login(client)
    client.delete(f"/api/users/{created.json()['id']}")


def run_tests(client: TestClient) -> None:
    login(client)
    ensure_mike_test_password(client)
    test_legacy_password_login(client)
    test_owner_login(client)
    test_change_password(client)
    test_admin_user_management(client)
    test_team_members_and_audit_users(client)
    test_pm_automation_rules(client)
    test_database_backup(client)
    test_database_restore(client)
    test_database_backup_token(client)
    test_pm_record_dedup(client)
    test_parts_module(client)
    test_new_user_must_change_password_flag(client)
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

    smoke_cart_id = int(time.time()) % 900000 + 200000

    create_cart = client.post(
        "/api/carts",
        json={
            "id": smoke_cart_id,
            "serial": "SMOKE-123",
            "model": "Carryall 1",
            "year": "2024",
            "location": "Shop",
            "status": "active",
            "notes": "Smoke test cart",
        },
    )
    assert create_cart.status_code == 200, create_cart.text
    assert create_cart.json()["serial"] == "SMOKE-123"

    missing_fields = client.post(
        "/api/carts",
        json={"id": smoke_cart_id + 1, "serial": "ONLY-SERIAL"},
    )
    assert missing_fields.status_code == 422, missing_fields.text

    duplicate_cart = client.post(
        "/api/carts",
        json={
            "id": smoke_cart_id,
            "serial": "SMOKE-123",
            "model": "Carryall 1",
            "year": "2024",
            "location": "Shop",
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
        json={"location": "Yard", "notes": "Updated smoke cart"},
    )
    assert update_cart.status_code == 200, update_cart.text
    assert update_cart.json()["location"] == "Yard"

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

    # Keep an active cart for WO / accident smoke tests below
    active_cart_id = smoke_cart_id + 50
    active_cart = client.post(
        "/api/carts",
        json={
            "id": active_cart_id,
            "serial": "SMOKE-ACTIVE-1",
            "model": "Carryall 2",
            "year": "2023",
            "location": "Shop",
            "status": "active",
            "notes": "Active smoke cart",
        },
    )
    assert active_cart.status_code == 200, active_cart.text

    activity_page = client.get("/activity.html")
    assert activity_page.status_code == 200, activity_page.text

    reports_page = client.get("/reports.html")
    assert reports_page.status_code == 200, reports_page.text

    parts_page = client.get("/parts.html")
    assert parts_page.status_code == 200, parts_page.text
    assert "Parts &amp; Inventory" in parts_page.text or "Parts & Inventory" in parts_page.text
    assert "parts.js" in parts_page.text

    weather = client.get("/api/widgets/weather?location=Charlotte")
    assert weather.status_code == 200, weather.text
    weather_body = weather.json()
    assert "temperature_f" in weather_body
    assert weather_body.get("location")

    nascar = client.get("/api/widgets/nascar-standings")
    assert nascar.status_code == 200, nascar.text
    nascar_body = nascar.json()
    assert len(nascar_body.get("drivers") or []) >= 1

    admin_page = client.get("/admin.html")
    assert admin_page.status_code == 200, admin_page.text

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
    assert health_data["seed_demo_data"] is False
    assert str(server.DB_PATH).endswith("maintainsmip.db")
    assert str(server.DATA_DIR) in health_data["data_dir"]
    assert client.get("/").status_code == 200
    assert client.get("/login.html").status_code == 200
    assert client.get("/logo1.png").status_code == 200
    assert client.get("/shared.css").status_code == 200
    assert client.get("/themes.js").status_code == 200
    assert client.get("/smi_events.js").status_code == 200
    assert client.get("/accidents.html").status_code == 200

    accidents = client.get("/api/accidents")
    assert accidents.status_code == 200, accidents.text

    create = client.post(
        "/api/workorders",
        json={
            "cart_id": active_cart_id,
            "title": "Smoke test WO",
            "description": "Temporary test order",
            "priority": "low",
            "status": "open",
            "type": "inspection",
            "assigned_to": "",
            "location": "Shop",
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
            "cart_id": active_cart_id,
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