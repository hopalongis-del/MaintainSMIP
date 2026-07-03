"""Clear work orders and accidents, then seed 9 WOs + 3 damage reports with photos."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).parent.resolve()
DEFAULT_BASE = "https://maintainsmip.onrender.com"
PASSWORD = "WeLoveRacing!"
USERNAME = "admin"

PHOTO_FILES = [
    ROOT / "uploads" / "accidents" / "4" / "2303c500c9f44a008f4060c75ef50cda.jpg",
    ROOT / "imports" / "workorders_scan_mid.png",
    ROOT / "imports" / "workorders_scan_top.png",
]


def iso_days(days: int) -> str:
    return (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat()


def login(session: requests.Session, base: str) -> None:
    response = session.post(
        f"{base}/api/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
        timeout=60,
    )
    response.raise_for_status()


def delete_all(session: requests.Session, base: str, resource: str) -> int:
    response = session.get(f"{base}/api/{resource}", timeout=60)
    response.raise_for_status()
    items = response.json()
    for item in items:
        item_id = item["id"]
        delete = session.delete(f"{base}/api/{resource}/{item_id}", timeout=60)
        delete.raise_for_status()
    return len(items)


def get_maintenance_sheet_template(session: requests.Session, base: str) -> dict:
    response = session.get(f"{base}/api/wo/templates", timeout=60)
    response.raise_for_status()
    templates = response.json()
    if not templates:
        return {}
    return templates[0].get("maintenance_sheet") or {}


def build_work_orders(sheet_template: dict) -> list[dict]:
    base_sheet = json.loads(json.dumps(sheet_template or {}))
    base_sheet.setdefault("checklist", [])
    base_sheet.setdefault("parts_lines", [{"qty": "", "part_number": "", "description": ""}])

    return [
        {
            "cart_id": 2002,
            "title": "Brake squeal under load",
            "description": "Grinding noise descending hills at Charlotte. Inspect pads and rear drum.",
            "priority": "high",
            "status": "in_progress",
            "type": "repair",
            "assigned_to": "Mike Casady",
            "location": "Charlotte",
            "due_date": iso_days(2),
            "labor_minutes": 45,
            "parts_used": ["Brake pad set"],
            "comments": [{"author": "Mike Casady", "text": "Pads at 20%, ordering replacements.", "date": iso_days(-1)}],
            "maintenance_sheet": {
                **base_sheet,
                "service_type": "repair",
                "start_date": iso_days(-2)[:10],
                "total_labor_hours": 0.75,
                "sheet_comments": "Grinding noise under load on hills.",
                "parts_lines": [{"qty": "1", "part_number": "BRK-204", "description": "Brake pad set"}],
                "checklist": [
                    {"id": "brake_shoes_clean", "section": "Brakes", "label": "Check / Clean Brake Shoes", "checked": True, "note": ""},
                    {"id": "brake_pedal_travel", "section": "Brakes", "label": "Check Brake Pedal Free Travel", "checked": True, "note": ""},
                ],
            },
        },
        {
            "cart_id": 2000,
            "title": "Battery terminal corrosion",
            "description": "Green buildup on positive terminal. Clean, load test, verify charger output.",
            "priority": "medium",
            "status": "open",
            "type": "battery",
            "assigned_to": "Gavin Weinmeister",
            "location": "SMIP",
            "due_date": iso_days(4),
            "labor_minutes": 30,
            "parts_used": [],
            "comments": [],
            "maintenance_sheet": base_sheet,
        },
        {
            "cart_id": 2057,
            "title": "Steering wander at speed",
            "description": "Cart drifts right above 12 mph on service roads. Check toe alignment and tire wear.",
            "priority": "critical",
            "status": "open",
            "type": "repair",
            "assigned_to": "Dusty Hixson",
            "location": "Bristol",
            "due_date": iso_days(-3),
            "labor_minutes": 0,
            "parts_used": [],
            "comments": [],
            "maintenance_sheet": base_sheet,
        },
        {
            "cart_id": 2003,
            "title": "Headlight intermittent",
            "description": "Left headlight flickers over bumps. Inspect harness at firewall.",
            "priority": "low",
            "status": "completed",
            "type": "electrical",
            "assigned_to": "Cory Yeager",
            "location": "Charlotte",
            "due_date": iso_days(-7),
            "labor_minutes": 25,
            "parts_used": ["Bulb 12V"],
            "comments": [{"author": "Cory Yeager", "text": "Loose ground strap tightened and tested.", "date": iso_days(-5)}],
            "maintenance_sheet": base_sheet,
        },
        {
            "cart_id": 2001,
            "title": "Quarterly safety inspection",
            "description": "Routine safety walk-around before CMS event weekend.",
            "priority": "medium",
            "status": "on_hold",
            "type": "inspection",
            "assigned_to": "Kevin Stellman",
            "location": "SMIP",
            "due_date": iso_days(6),
            "labor_minutes": 15,
            "parts_used": [],
            "comments": [{"author": "Kevin Stellman", "text": "Waiting on parts cage key.", "date": iso_days(0)}],
            "maintenance_sheet": base_sheet,
        },
        {
            "cart_id": 2010,
            "title": "Low tire tread — replace set",
            "description": "Front tires below 3/32. Replace before next event.",
            "priority": "high",
            "status": "open",
            "type": "tire",
            "assigned_to": "Brian Lachance",
            "location": "SMIP",
            "due_date": iso_days(1),
            "labor_minutes": 40,
            "parts_used": ["Tire set 18x8.5"],
            "comments": [],
            "maintenance_sheet": base_sheet,
        },
        {
            "cart_id": 2028,
            "title": "Rear differential oil leak",
            "description": "Oil spotting under rear end after transport to Texas.",
            "priority": "high",
            "status": "in_progress",
            "type": "repair",
            "assigned_to": "Stephen Hering",
            "location": "Texas",
            "due_date": iso_days(3),
            "labor_minutes": 55,
            "parts_used": ["Rear end gasket kit"],
            "comments": [],
            "maintenance_sheet": base_sheet,
        },
        {
            "cart_id": 2033,
            "title": "Driver seat latch won't lock",
            "description": "Seat flips forward under braking. Latch mechanism worn.",
            "priority": "medium",
            "status": "open",
            "type": "repair",
            "assigned_to": "Mark Hixson",
            "location": "Charlotte",
            "due_date": iso_days(5),
            "labor_minutes": 20,
            "parts_used": [],
            "comments": [],
            "maintenance_sheet": base_sheet,
        },
        {
            "cart_id": 2024,
            "title": "Post-event full maintenance service",
            "description": "Full SMI maintenance sheet after Las Vegas weekend operations.",
            "priority": "medium",
            "status": "open",
            "type": "inspection",
            "assigned_to": "Mike Casady",
            "location": "Las Vegas",
            "due_date": iso_days(7),
            "labor_minutes": 90,
            "parts_used": [],
            "comments": [],
            "maintenance_sheet": base_sheet,
        },
    ]


ACCIDENTS = [
    {
        "cart_id": 2002,
        "location": "Charlotte",
        "reported_by": "Mike Casady",
        "incident_date": iso_days(-1),
        "description": "Rear corner impact with loading dock post. Cracked body panel and bent rear bumper bracket.",
        "severity": "moderate",
        "status": "under_review",
        "damage_areas": ["rear bumper", "right rear panel", "tail light"],
        "notes": "Operator reported during CMS infield move.",
        "photos": [],
    },
    {
        "cart_id": 2057,
        "location": "Bristol",
        "reported_by": "Gavin Weinmeister",
        "incident_date": iso_days(-4),
        "description": "Roof scrape under low garage door. Bubble top scuffed, no structural damage visible.",
        "severity": "minor",
        "status": "repair_scheduled",
        "damage_areas": ["roof", "top trim"],
        "notes": "Body shop assessment scheduled.",
        "photos": [],
    },
    {
        "cart_id": 2000,
        "location": "SMIP",
        "reported_by": "Dusty Hixson",
        "incident_date": iso_days(-2),
        "description": "Front bumper contact with stationary cart in shop yard. Paint chip and minor bracket bend.",
        "severity": "minor",
        "status": "reported",
        "damage_areas": ["front bumper", "front cowl"],
        "notes": "Photos taken at time of report.",
        "photos": [],
    },
]


def create_work_orders(session: requests.Session, base: str, sheet_template: dict) -> list[int]:
    created_ids: list[int] = []
    for payload in build_work_orders(sheet_template):
        response = session.post(f"{base}/api/workorders", json=payload, timeout=60)
        response.raise_for_status()
        created_ids.append(response.json()["id"])
    return created_ids


def upload_photo(session: requests.Session, base: str, accident_id: int, photo_path: Path) -> None:
    with photo_path.open("rb") as handle:
        response = session.post(
            f"{base}/api/accidents/{accident_id}/photos",
            files={"file": (photo_path.name, handle, "image/jpeg" if photo_path.suffix.lower() in {".jpg", ".jpeg"} else "image/png")},
            timeout=120,
        )
    response.raise_for_status()


def create_accidents_with_photos(session: requests.Session, base: str) -> list[int]:
    created_ids: list[int] = []
    for index, payload in enumerate(ACCIDENTS):
        response = session.post(f"{base}/api/accidents", json=payload, timeout=60)
        response.raise_for_status()
        accident_id = response.json()["id"]
        created_ids.append(accident_id)
        photo_path = PHOTO_FILES[index % len(PHOTO_FILES)]
        if photo_path.exists():
            upload_photo(session, base, accident_id, photo_path)
        else:
            print(f"Warning: photo missing for ACC-{accident_id}: {photo_path}")
    return created_ids


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE
    session = requests.Session()

    print(f"Target: {base}")
    login(session, base)
    print("Signed in as admin")

    deleted_wos = delete_all(session, base, "workorders")
    print(f"Deleted {deleted_wos} work orders")

    deleted_accidents = delete_all(session, base, "accidents")
    print(f"Deleted {deleted_accidents} accident reports")

    sheet_template = get_maintenance_sheet_template(session, base)
    wo_ids = create_work_orders(session, base, sheet_template)
    print(f"Created {len(wo_ids)} work orders: {wo_ids}")

    accident_ids = create_accidents_with_photos(session, base)
    print(f"Created {len(accident_ids)} accident reports with photos: {accident_ids}")

    stats = session.get(f"{base}/api/stats", timeout=60).json()
    print("Stats:", stats)


if __name__ == "__main__":
    main()