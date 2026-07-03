from __future__ import annotations
import hashlib
import hmac
import json
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional
from urllib.parse import quote

import aiosqlite
import uuid

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

ROOT_DIR = Path(__file__).parent.resolve()
DB_PATH = ROOT_DIR / 'maintainsmip.db'
CART_DATA_PATH = ROOT_DIR / 'cart_data.js'
UPLOADS_DIR = ROOT_DIR / 'uploads' / 'accidents'
APP_PASSWORD = os.environ.get('APP_PASSWORD', 'WeLoveRacing!')
APP_SECRET = os.environ.get('APP_SECRET', 'maintainsmip-session-secret')
SESSION_COOKIE = 'ms_session'
SESSION_MAX_AGE = 7 * 24 * 3600
PUBLIC_PATHS = {
    '/login.html',
    '/api/auth/login',
    '/api/health',
    '/shared.css',
    '/logo1.png',
}


def create_session_token() -> str:
    expires = int(time.time()) + SESSION_MAX_AGE
    payload = str(expires).encode()
    signature = hmac.new(APP_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return f'{expires}.{signature}'


def verify_session_token(token: str) -> bool:
    try:
        expires_str, signature = token.split('.', 1)
        expires = int(expires_str)
        if expires < time.time():
            return False
        expected = hmac.new(APP_SECRET.encode(), expires_str.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    except (ValueError, TypeError):
        return False


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not APP_PASSWORD:
            return await call_next(request)

        path = request.url.path
        if path in PUBLIC_PATHS:
            return await call_next(request)

        token = request.cookies.get(SESSION_COOKIE)
        if token and verify_session_token(token):
            return await call_next(request)

        if path.startswith('/api/'):
            return JSONResponse(status_code=401, content={'detail': 'Authentication required'})

        next_path = path if path != '/' else '/index.html'
        return RedirectResponse(f'/login.html?next={quote(next_path)}', status_code=302)

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(ROOT_DIR, exist_ok=True)
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    await migrate_schema()
    await create_tables()
    app.state.carts = parse_cart_data()
    await seed_pm_templates()
    await seed_wo_templates()
    await seed_demo_data()
    yield


app = FastAPI(title='MaintainSMIP API', version='1.0', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)
app.add_middleware(AuthMiddleware)


class CartItem(BaseModel):
    id: Any
    serial: Optional[str]
    model: Optional[str]
    year: Optional[str]
    location: Optional[str]
    status: Optional[str]
    notes: Optional[str]


class WorkOrderBase(BaseModel):
    cart_id: int
    title: str
    description: str
    priority: str = 'medium'
    status: str = 'open'
    type: str = 'repair'
    assigned_to: Optional[str] = ''
    location: Optional[str] = ''
    due_date: Optional[str] = None
    labor_minutes: int = 0
    parts_used: List[Any] = Field(default_factory=list)
    comments: List[Any] = Field(default_factory=list)
    maintenance_sheet: dict = Field(default_factory=dict)


class WorkOrderCreate(WorkOrderBase):
    pass


class WorkOrderUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None
    cart_id: Optional[int] = None
    assigned_to: Optional[str] = None
    location: Optional[str] = None
    due_date: Optional[str] = None
    completed_date: Optional[str] = None
    labor_minutes: Optional[int] = None
    parts_used: Optional[List[Any]] = None
    comments: Optional[List[Any]] = None
    maintenance_sheet: Optional[dict] = None


class WorkOrder(WorkOrderBase):
    id: int
    cart_serial: Optional[str] = None
    created_date: str
    completed_date: Optional[str] = None


class WoTemplateBase(BaseModel):
    name: str
    description: Optional[str] = ''
    default_title: str = 'Maintenance Service'
    default_type: str = 'repair'
    default_priority: str = 'medium'
    maintenance_sheet: dict = Field(default_factory=dict)
    active: bool = True


class WoTemplateCreate(WoTemplateBase):
    pass


class WoTemplate(WoTemplateBase):
    id: str


class PMTemplateBase(BaseModel):
    name: str
    description: Optional[str] = ''
    applies_to: dict = Field(default_factory=lambda: {'models': [], 'locations': [], 'all': True})
    trigger_type: str = 'interval_days'
    interval_value: int = 90
    checklist: List[dict] = Field(default_factory=list)
    estimated_labor_minutes: int = 0
    active: bool = True


class PMTemplateCreate(PMTemplateBase):
    pass


class PMTemplate(PMTemplateBase):
    id: Any


class PMRecordBase(BaseModel):
    template_id: Optional[Any] = None
    template_name: Optional[str] = None
    description: Optional[str] = ''
    cart_id: int
    location: Optional[str] = ''
    scheduled_date: Optional[str] = None
    completed_date: Optional[str] = None
    status: str = 'scheduled'
    checklist_results: List[dict] = Field(default_factory=list)
    tech_name: Optional[str] = ''
    labor_minutes: int = 0
    linked_wo_ids: List[int] = Field(default_factory=list)


class PMRecordCreate(PMRecordBase):
    pass


class PMRecord(PMRecordBase):
    id: Any


class AccidentReportBase(BaseModel):
    cart_id: int
    location: Optional[str] = ''
    reported_by: Optional[str] = ''
    incident_date: Optional[str] = None
    description: str
    severity: str = 'moderate'
    status: str = 'reported'
    damage_areas: List[str] = Field(default_factory=list)
    photos: List[str] = Field(default_factory=list)
    notes: Optional[str] = ''
    linked_wo_id: Optional[int] = None


class AccidentReportCreate(AccidentReportBase):
    pass


class AccidentReportUpdate(BaseModel):
    cart_id: Optional[int] = None
    location: Optional[str] = None
    reported_by: Optional[str] = None
    incident_date: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    damage_areas: Optional[List[str]] = None
    notes: Optional[str] = None
    linked_wo_id: Optional[int] = None


class AccidentReport(AccidentReportBase):
    id: int
    cart_serial: Optional[str] = None
    created_date: str


async def get_database() -> aiosqlite.Connection:
    return await aiosqlite.connect(DB_PATH)


def parse_cart_data() -> List[CartItem]:
    if not CART_DATA_PATH.exists():
        return []

    raw = CART_DATA_PATH.read_text(encoding='utf-8')
    match = re.search(r'const\s+cartData\s*=\s*(\[.*\]);', raw, re.DOTALL)
    if not match:
        return []

    payload = match.group(1)
    try:
        items = json.loads(payload)
        return [CartItem(**item) for item in items]
    except json.JSONDecodeError:
        return []


def parse_work_order_row(row: aiosqlite.Row) -> WorkOrder:
    data = dict(row)
    data['parts_used'] = json.loads(data.get('parts_used') or '[]')
    data['comments'] = json.loads(data.get('comments') or '[]')
    data['maintenance_sheet'] = json.loads(data.get('maintenance_sheet') or '{}')
    return WorkOrder(**data)


async def migrate_schema() -> None:
    """Recreate tables that used an older integer-id schema."""
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='work_orders'"
        )
        if await cursor.fetchone():
            cursor = await connection.execute('PRAGMA table_info(work_orders)')
            wo_columns = [col[1] for col in await cursor.fetchall()]
            if 'maintenance_sheet' not in wo_columns:
                await connection.execute('ALTER TABLE work_orders ADD COLUMN maintenance_sheet TEXT')
                await connection.commit()
            await backfill_demo_maintenance_sheets(connection)

        cursor = await connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pm_templates'"
        )
        if not await cursor.fetchone():
            return

        cursor = await connection.execute('PRAGMA table_info(pm_templates)')
        columns = await cursor.fetchall()
        id_col = next((col for col in columns if col[1] == 'id'), None)
        if id_col and str(id_col[2]).upper() == 'INTEGER':
            await connection.execute('DROP TABLE IF EXISTS pm_templates')
            await connection.commit()


async def create_tables() -> None:
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS work_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cart_id INTEGER,
                cart_serial TEXT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                priority TEXT,
                status TEXT,
                type TEXT,
                assigned_to TEXT,
                location TEXT,
                created_date TEXT,
                due_date TEXT,
                completed_date TEXT,
                labor_minutes INTEGER,
                parts_used TEXT,
                comments TEXT,
                maintenance_sheet TEXT
            )
            '''
        )
        await connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS wo_templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                default_title TEXT,
                default_type TEXT,
                default_priority TEXT,
                maintenance_sheet TEXT,
                active INTEGER
            )
            '''
        )
        await connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS pm_templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                applies_to TEXT,
                trigger_type TEXT,
                interval_value INTEGER,
                checklist TEXT,
                estimated_labor_minutes INTEGER,
                active INTEGER
            )
            '''
        )
        await connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS pm_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id TEXT,
                template_name TEXT,
                description TEXT,
                cart_id INTEGER,
                location TEXT,
                scheduled_date TEXT,
                completed_date TEXT,
                status TEXT,
                checklist_results TEXT,
                tech_name TEXT,
                labor_minutes INTEGER,
                linked_wo_ids TEXT
            )
            '''
        )
        await connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS accident_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cart_id INTEGER,
                cart_serial TEXT,
                location TEXT,
                reported_by TEXT,
                incident_date TEXT,
                description TEXT NOT NULL,
                severity TEXT,
                status TEXT,
                damage_areas TEXT,
                photos TEXT,
                notes TEXT,
                linked_wo_id INTEGER,
                created_date TEXT
            )
            '''
        )
        await connection.commit()


PM_TEMPLATE_SEED = [
    ('PM-TPL-001', '90-Day Inspection', 'Full inspection every 90 days', 'interval_days', 90, '{"all":true,"models":[],"locations":[]}', '[{"id":1,"task":"Check tire pressure","required":true},{"id":2,"task":"Inspect brakes","required":true},{"id":3,"task":"Test lights","required":true},{"id":4,"task":"Check battery connections","required":true},{"id":5,"task":"Inspect steering","required":true}]', 45, 1),
    ('PM-TPL-002', 'Annual Full Service', 'Complete annual service', 'interval_days', 365, '{"all":true,"models":[],"locations":[]}', '[{"id":1,"task":"Full brake service","required":true},{"id":2,"task":"Battery load test","required":true},{"id":3,"task":"Tire check","required":true},{"id":4,"task":"Motor inspection","required":true}]', 120, 1),
    ('PM-TPL-003', 'Battery Service', 'Battery check every 6 months', 'interval_days', 180, '{"all":true,"models":[],"locations":[]}', '[{"id":1,"task":"Check water levels","required":true},{"id":2,"task":"Clean terminals","required":true},{"id":3,"task":"Load test","required":true}]', 30, 1),
    ('PM-TPL-004', 'Brake Inspection', 'Brake check every 6 months', 'interval_days', 180, '{"all":true,"models":[],"locations":[]}', '[{"id":1,"task":"Check brake pads","required":true},{"id":2,"task":"Test brake response","required":true}]', 20, 1),
    ('PM-TPL-005', 'Roof Inspection', 'Annual roof and top check', 'interval_days', 365, '{"all":true,"models":[],"locations":[]}', '[{"id":1,"task":"Check for cracks","required":true},{"id":2,"task":"Check mounting hardware","required":true}]', 15, 1),
]


WO_TEMPLATE_PATH = ROOT_DIR / 'work_order_template.json'


async def seed_wo_templates() -> None:
    if not WO_TEMPLATE_PATH.exists():
        return
    payload = json.loads(WO_TEMPLATE_PATH.read_text(encoding='utf-8'))
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT COUNT(*) FROM wo_templates')
        if (await cursor.fetchone())[0] > 0:
            return
        await db.execute(
            '''
            INSERT INTO wo_templates (
                id, name, description, default_title, default_type,
                default_priority, maintenance_sheet, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                payload['id'],
                payload['name'],
                payload.get('description', ''),
                payload.get('default_title', 'Maintenance Service'),
                payload.get('default_type', 'repair'),
                payload.get('default_priority', 'medium'),
                json.dumps(payload.get('maintenance_sheet', {})),
                1,
            ),
        )
        await db.commit()


async def seed_pm_templates() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT COUNT(*) FROM pm_templates')
        count = (await cursor.fetchone())[0]
        if count > 0:
            return

        try:
            await db.executemany(
                'INSERT OR IGNORE INTO pm_templates (id,name,description,trigger_type,interval_value,applies_to,checklist,estimated_labor_minutes,active) VALUES (?,?,?,?,?,?,?,?,?)',
                PM_TEMPLATE_SEED,
            )
            await db.commit()
        except Exception:
            await db.execute('DROP TABLE IF EXISTS pm_templates')
            await db.execute(
                '''
                CREATE TABLE pm_templates (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    applies_to TEXT,
                    trigger_type TEXT,
                    interval_value INTEGER,
                    checklist TEXT,
                    estimated_labor_minutes INTEGER,
                    active INTEGER
                )
                '''
            )
            await db.executemany(
                'INSERT OR IGNORE INTO pm_templates (id,name,description,trigger_type,interval_value,applies_to,checklist,estimated_labor_minutes,active) VALUES (?,?,?,?,?,?,?,?,?)',
                PM_TEMPLATE_SEED,
            )
            await db.commit()


def _iso_days_from_now(days: int) -> str:
    return (datetime.utcnow() + timedelta(days=days)).isoformat()


DEMO_WORK_ORDERS = [
    {
        'cart_id': 2002,
        'title': 'Brake squeal under load',
        'description': 'Operator reports grinding noise when descending hills at Charlotte. Inspect pads and rear drum.',
        'priority': 'high',
        'status': 'in_progress',
        'type': 'repair',
        'assigned_to': 'Mike Casady',
        'location': 'Charlotte',
        'due_date': _iso_days_from_now(2),
        'labor_minutes': 45,
        'parts_used': ['Brake pad set'],
        'comments': [{'author': 'Mike Casady', 'text': 'Pads at 20%, ordering replacements.', 'date': _iso_days_from_now(-1)}],
        'maintenance_sheet': {
            'service_type': 'repair',
            'start_date': _iso_days_from_now(-2),
            'total_labor_hours': 0.75,
            'sheet_comments': 'Grinding noise under load on hills.',
            'parts_lines': [{'qty': '1', 'part_number': 'BRK-204', 'description': 'Brake pad set'}],
            'checklist': [
                {'id': 'brake_shoes_clean', 'checked': True},
                {'id': 'brake_pedal_travel', 'checked': True},
                {'id': 'brake_cables', 'checked': True},
            ],
        },
    },
    {
        'cart_id': 2000,
        'title': 'Battery terminal corrosion',
        'description': 'Green buildup on positive terminal. Clean, test load, verify charger output.',
        'priority': 'medium',
        'status': 'open',
        'type': 'battery',
        'assigned_to': 'Gavin Weinmeister',
        'location': 'SMIP',
        'due_date': _iso_days_from_now(4),
        'labor_minutes': 30,
        'parts_used': [],
        'comments': [],
    },
    {
        'cart_id': 2057,
        'title': 'Steering wander at speed',
        'description': 'Cart drifts right above 12 mph on service roads. Check toe alignment and tire wear.',
        'priority': 'critical',
        'status': 'open',
        'type': 'repair',
        'assigned_to': '',
        'location': 'Bristol',
        'due_date': _iso_days_from_now(-3),
        'labor_minutes': 0,
        'parts_used': [],
        'comments': [],
    },
    {
        'cart_id': 2003,
        'title': 'Headlight intermittent',
        'description': 'Left headlight flickers over bumps. Inspect harness and connector at firewall.',
        'priority': 'low',
        'status': 'completed',
        'type': 'electrical',
        'assigned_to': 'Cory Yeager',
        'location': 'Charlotte',
        'due_date': _iso_days_from_now(-7),
        'labor_minutes': 25,
        'parts_used': ['Bulb 12V'],
        'comments': [{'author': 'Cory Yeager', 'text': 'Loose ground strap — tightened and tested.', 'date': _iso_days_from_now(-5)}],
    },
    {
        'cart_id': 2001,
        'title': 'Quarterly safety inspection',
        'description': 'Routine safety walk-around before CMS event weekend.',
        'priority': 'medium',
        'status': 'on_hold',
        'type': 'inspection',
        'assigned_to': 'Kevin Stellman',
        'location': 'SMIP',
        'due_date': _iso_days_from_now(6),
        'labor_minutes': 15,
        'parts_used': [],
        'comments': [{'author': 'Kevin Stellman', 'text': 'Waiting on parts cage key.', 'date': _iso_days_from_now(0)}],
    },
]


DEMO_PM_RECORDS = [
    {
        'template_id': 'PM-TPL-001',
        'template_name': '90-Day Inspection',
        'description': 'Full inspection every 90 days',
        'cart_id': 2000,
        'location': 'SMIP',
        'scheduled_date': _iso_days_from_now(3),
        'status': 'scheduled',
        'checklist_results': [
            {'task_id': 1, 'task': 'Check tire pressure', 'passed': False, 'note': ''},
            {'task_id': 2, 'task': 'Inspect brakes', 'passed': False, 'note': ''},
            {'task_id': 3, 'task': 'Test lights', 'passed': False, 'note': ''},
            {'task_id': 4, 'task': 'Check battery connections', 'passed': False, 'note': ''},
            {'task_id': 5, 'task': 'Inspect steering', 'passed': False, 'note': ''},
        ],
    },
    {
        'template_id': 'PM-TPL-003',
        'template_name': 'Battery Service',
        'description': 'Battery check every 6 months',
        'cart_id': 2002,
        'location': 'Charlotte',
        'scheduled_date': _iso_days_from_now(5),
        'status': 'scheduled',
        'checklist_results': [
            {'task_id': 1, 'task': 'Check water levels', 'passed': False, 'note': ''},
            {'task_id': 2, 'task': 'Clean terminals', 'passed': False, 'note': ''},
            {'task_id': 3, 'task': 'Load test', 'passed': False, 'note': ''},
        ],
    },
    {
        'template_id': 'PM-TPL-004',
        'template_name': 'Brake Inspection',
        'description': 'Brake check every 6 months',
        'cart_id': 2057,
        'location': 'Bristol',
        'scheduled_date': _iso_days_from_now(-2),
        'status': 'scheduled',
        'checklist_results': [
            {'task_id': 1, 'task': 'Check brake pads', 'passed': False, 'note': ''},
            {'task_id': 2, 'task': 'Test brake response', 'passed': False, 'note': ''},
        ],
    },
    {
        'template_id': 'PM-TPL-002',
        'template_name': 'Annual Full Service',
        'description': 'Complete annual service',
        'cart_id': 2003,
        'location': 'Charlotte',
        'scheduled_date': _iso_days_from_now(-14),
        'status': 'completed',
        'completed_date': _iso_days_from_now(-10),
        'tech_name': 'Dusty Hixson',
        'labor_minutes': 110,
        'checklist_results': [
            {'task_id': 1, 'task': 'Full brake service', 'passed': True, 'note': ''},
            {'task_id': 2, 'task': 'Battery load test', 'passed': True, 'note': ''},
            {'task_id': 3, 'task': 'Tire check', 'passed': True, 'note': ''},
            {'task_id': 4, 'task': 'Motor inspection', 'passed': True, 'note': ''},
        ],
    },
]


DEMO_ACCIDENTS = [
    {
        'cart_id': 2002,
        'location': 'Charlotte',
        'reported_by': 'Mike Casady',
        'incident_date': _iso_days_from_now(-1),
        'description': 'Rear corner impact with loading dock post. Cracked body panel and bent rear bumper bracket.',
        'severity': 'moderate',
        'status': 'under_review',
        'damage_areas': ['rear bumper', 'right rear panel', 'tail light'],
        'notes': 'Operator reported during CMS infield move.',
        'created_days_ago': -1,
    },
    {
        'cart_id': 2057,
        'location': 'Bristol',
        'reported_by': 'Gavin Weinmeister',
        'incident_date': _iso_days_from_now(-4),
        'description': 'Roof scrape under low garage door. Bubble top scuffed, no structural damage visible.',
        'severity': 'minor',
        'status': 'repair_scheduled',
        'damage_areas': ['roof', 'top trim'],
        'notes': 'WO created for body shop assessment.',
        'created_days_ago': -4,
    },
]


async def backfill_demo_maintenance_sheets(connection: aiosqlite.Connection) -> None:
    demo_sheets = {
        wo['title']: wo['maintenance_sheet']
        for wo in DEMO_WORK_ORDERS
        if wo.get('maintenance_sheet')
    }
    connection.row_factory = aiosqlite.Row
    cursor = await connection.execute(
        """
        SELECT id, title, maintenance_sheet FROM work_orders
        WHERE maintenance_sheet IS NULL OR maintenance_sheet = '' OR maintenance_sheet = '{}'
        """
    )
    rows = await cursor.fetchall()
    for row in rows:
        sheet = demo_sheets.get(row['title'])
        if sheet:
            await connection.execute(
                'UPDATE work_orders SET maintenance_sheet = ? WHERE id = ?',
                (json.dumps(sheet), row['id']),
            )
    await connection.commit()


async def seed_demo_data() -> None:
    carts_by_id = {cart.id: cart for cart in app.state.carts}

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT COUNT(*) FROM work_orders')
        if (await cursor.fetchone())[0] == 0:
            for wo in DEMO_WORK_ORDERS:
                cart = carts_by_id.get(wo['cart_id'])
                serial = cart.serial if cart else ''
                created = _iso_days_from_now(-5)
                completed = _iso_days_from_now(-5) if wo['status'] == 'completed' else None
                await db.execute(
                    '''
                    INSERT INTO work_orders (
                        cart_id, cart_serial, title, description, priority, status, type,
                        assigned_to, location, created_date, due_date, completed_date,
                        labor_minutes, parts_used, comments, maintenance_sheet
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        wo['cart_id'],
                        serial,
                        wo['title'],
                        wo['description'],
                        wo['priority'],
                        wo['status'],
                        wo['type'],
                        wo['assigned_to'],
                        wo['location'],
                        created,
                        wo['due_date'],
                        completed,
                        wo['labor_minutes'],
                        json.dumps(wo['parts_used']),
                        json.dumps(wo['comments']),
                        json.dumps(wo.get('maintenance_sheet', {})),
                    ),
                )

        cursor = await db.execute('SELECT COUNT(*) FROM pm_records')
        if (await cursor.fetchone())[0] == 0:
            for rec in DEMO_PM_RECORDS:
                await db.execute(
                    '''
                    INSERT INTO pm_records (
                        template_id, template_name, description, cart_id, location,
                        scheduled_date, completed_date, status, checklist_results,
                        tech_name, labor_minutes, linked_wo_ids
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        rec['template_id'],
                        rec['template_name'],
                        rec['description'],
                        rec['cart_id'],
                        rec['location'],
                        rec['scheduled_date'],
                        rec.get('completed_date'),
                        rec['status'],
                        json.dumps(rec['checklist_results']),
                        rec.get('tech_name', ''),
                        rec.get('labor_minutes', 0),
                        json.dumps([]),
                    ),
                )

        cursor = await db.execute('SELECT COUNT(*) FROM accident_reports')
        if (await cursor.fetchone())[0] == 0:
            for acc in DEMO_ACCIDENTS:
                cart = carts_by_id.get(acc['cart_id'])
                serial = cart.serial if cart else ''
                await db.execute(
                    '''
                    INSERT INTO accident_reports (
                        cart_id, cart_serial, location, reported_by, incident_date,
                        description, severity, status, damage_areas, photos, notes,
                        linked_wo_id, created_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        acc['cart_id'],
                        serial,
                        acc['location'],
                        acc['reported_by'],
                        acc['incident_date'],
                        acc['description'],
                        acc['severity'],
                        acc['status'],
                        json.dumps(acc['damage_areas']),
                        json.dumps([]),
                        acc.get('notes', ''),
                        acc.get('linked_wo_id'),
                        _iso_days_from_now(acc.get('created_days_ago', -2)),
                    ),
                )

        await db.commit()


def accident_from_row(row: Any) -> AccidentReport:
    data = dict(row)
    return AccidentReport(**{
        **data,
        'damage_areas': json.loads(data.get('damage_areas') or '[]'),
        'photos': json.loads(data.get('photos') or '[]'),
    })


async def get_accident_row(accident_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT * FROM accident_reports WHERE id = ?',
            (accident_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Accident report not found')
        return dict(row)


def delete_photo_files(photo_paths: List[str]) -> None:
    for rel_path in photo_paths:
        target = ROOT_DIR / rel_path
        if target.exists() and target.is_file():
            target.unlink()


@app.get('/api/carts', response_model=List[CartItem])
async def list_carts() -> List[CartItem]:
    return app.state.carts


@app.get('/api/wo/templates', response_model=List[WoTemplate])
async def list_wo_templates() -> List[WoTemplate]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT * FROM wo_templates WHERE active = 1 ORDER BY id'
        )
        rows = await cursor.fetchall()
    return [
        WoTemplate(**{
            **dict(row),
            'maintenance_sheet': json.loads(row['maintenance_sheet'] or '{}'),
            'active': bool(row['active']),
        })
        for row in rows
    ]


@app.post('/api/wo/templates', response_model=WoTemplate)
async def create_wo_template(item: WoTemplateCreate) -> WoTemplate:
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute('SELECT COUNT(*) FROM wo_templates')
        count = (await cursor.fetchone())[0]
        template_id = f'WO-TPL-{count + 1:03d}'
        await connection.execute(
            '''
            INSERT INTO wo_templates (
                id, name, description, default_title, default_type,
                default_priority, maintenance_sheet, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                template_id,
                item.name,
                item.description,
                item.default_title,
                item.default_type,
                item.default_priority,
                json.dumps(item.maintenance_sheet or {}),
                1 if item.active else 0,
            ),
        )
        await connection.commit()
    return WoTemplate(id=template_id, **item.model_dump())


@app.get('/api/workorders', response_model=List[WorkOrder])
async def list_work_orders(
    status: Optional[str] = Query(None),
    cart_id: Optional[int] = Query(None),
    limit: Optional[int] = Query(None),
) -> List[WorkOrder]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        query = 'SELECT * FROM work_orders'
        conditions = []
        params: List[Any] = []
        if status:
            conditions.append('status = ?')
            params.append(status)
        if cart_id is not None:
            conditions.append('cart_id = ?')
            params.append(cart_id)
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        query += ' ORDER BY id DESC'
        if limit is not None:
            query += f' LIMIT {int(limit)}'
        cursor = await connection.execute(query, params)
        rows = await cursor.fetchall()

    return [parse_work_order_row(row) for row in rows]


@app.post('/api/workorders', response_model=WorkOrder)
async def create_work_order(item: WorkOrderCreate) -> WorkOrder:
    created_date = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            '''
            INSERT INTO work_orders (
                cart_id, cart_serial, title, description, priority, status, type,
                assigned_to, location, created_date, due_date, completed_date,
                labor_minutes, parts_used, comments, maintenance_sheet
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                item.cart_id,
                next((cart.serial for cart in app.state.carts if cart.id == item.cart_id), ''),
                item.title,
                item.description,
                item.priority,
                item.status,
                item.type,
                item.assigned_to,
                item.location,
                created_date,
                item.due_date,
                None,
                item.labor_minutes,
                json.dumps(item.parts_used or []),
                json.dumps(item.comments or []),
                json.dumps(item.maintenance_sheet or {}),
            ),
        )
        await connection.commit()
        row_id = cursor.lastrowid

    return WorkOrder(**{
        'id': row_id,
        'cart_id': item.cart_id,
        'cart_serial': next((cart.serial for cart in app.state.carts if cart.id == item.cart_id), ''),
        'title': item.title,
        'description': item.description,
        'priority': item.priority,
        'status': item.status,
        'type': item.type,
        'assigned_to': item.assigned_to,
        'location': item.location,
        'created_date': created_date,
        'due_date': item.due_date,
        'completed_date': None,
        'labor_minutes': item.labor_minutes,
        'parts_used': item.parts_used,
        'comments': item.comments,
        'maintenance_sheet': item.maintenance_sheet or {},
    })


@app.put('/api/workorders/{workorder_id}', response_model=WorkOrder)
async def update_work_order(workorder_id: int, item: WorkOrderUpdate) -> WorkOrder:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute('SELECT * FROM work_orders WHERE id = ?', (workorder_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Work order not found')

        existing = dict(row)
        updated = {**existing}
        if item.title is not None:
            updated['title'] = item.title
        if item.description is not None:
            updated['description'] = item.description
        if item.priority is not None:
            updated['priority'] = item.priority
        if item.type is not None:
            updated['type'] = item.type
        if item.cart_id is not None:
            updated['cart_id'] = item.cart_id
            updated['cart_serial'] = next(
                (cart.serial for cart in app.state.carts if cart.id == item.cart_id),
                updated.get('cart_serial', ''),
            )
        if item.status is not None:
            updated['status'] = item.status
            if item.status == 'completed' and not updated.get('completed_date'):
                updated['completed_date'] = datetime.utcnow().isoformat()
            elif item.status not in ('completed', 'closed'):
                updated['completed_date'] = None
        if item.assigned_to is not None:
            updated['assigned_to'] = item.assigned_to
        if item.location is not None:
            updated['location'] = item.location
        if item.due_date is not None:
            updated['due_date'] = item.due_date if item.due_date else None
        if item.completed_date is not None:
            updated['completed_date'] = item.completed_date if item.completed_date else None
        if item.labor_minutes is not None:
            updated['labor_minutes'] = item.labor_minutes
        if item.parts_used is not None:
            updated['parts_used'] = json.dumps(item.parts_used)
        if item.comments is not None:
            updated['comments'] = json.dumps(item.comments)
        if item.maintenance_sheet is not None:
            updated['maintenance_sheet'] = json.dumps(item.maintenance_sheet)

        await connection.execute(
            '''
            UPDATE work_orders SET
                cart_id = ?,
                cart_serial = ?,
                title = ?,
                description = ?,
                priority = ?,
                status = ?,
                type = ?,
                assigned_to = ?,
                location = ?,
                due_date = ?,
                completed_date = ?,
                labor_minutes = ?,
                parts_used = ?,
                comments = ?,
                maintenance_sheet = ?
            WHERE id = ?
            ''',
            (
                updated['cart_id'],
                updated['cart_serial'],
                updated['title'],
                updated['description'],
                updated['priority'],
                updated['status'],
                updated['type'],
                updated['assigned_to'],
                updated['location'],
                updated['due_date'],
                updated['completed_date'],
                updated['labor_minutes'],
                updated['parts_used'],
                updated['comments'],
                updated.get('maintenance_sheet') or '{}',
                workorder_id,
            ),
        )
        await connection.commit()

    updated['parts_used'] = json.loads(updated['parts_used'] or '[]')
    updated['comments'] = json.loads(updated['comments'] or '[]')
    updated['maintenance_sheet'] = json.loads(updated.get('maintenance_sheet') or '{}')
    return WorkOrder(**updated)


@app.get('/api/pm/templates', response_model=List[PMTemplate])
async def list_pm_templates() -> List[PMTemplate]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute('SELECT * FROM pm_templates ORDER BY id DESC')
        rows = await cursor.fetchall()

    return [PMTemplate(**{**dict(row), 'applies_to': json.loads(row['applies_to'] or '{}'), 'checklist': json.loads(row['checklist'] or '[]')}) for row in rows]


@app.post('/api/pm/templates', response_model=PMTemplate)
async def create_pm_template(item: PMTemplateCreate) -> PMTemplate:
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute('SELECT COUNT(*) FROM pm_templates')
        count = (await cursor.fetchone())[0]
        template_id = f'PM-TPL-{count + 1:03d}'
        await connection.execute(
            '''
            INSERT INTO pm_templates (
                id, name, description, applies_to, trigger_type,
                interval_value, checklist, estimated_labor_minutes, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                template_id,
                item.name,
                item.description,
                json.dumps(item.applies_to),
                item.trigger_type,
                item.interval_value,
                json.dumps(item.checklist),
                item.estimated_labor_minutes,
                1 if item.active else 0,
            ),
        )
        await connection.commit()

    return PMTemplate(**{
        'id': template_id,
        'name': item.name,
        'description': item.description,
        'applies_to': item.applies_to,
        'trigger_type': item.trigger_type,
        'interval_value': item.interval_value,
        'checklist': item.checklist,
        'estimated_labor_minutes': item.estimated_labor_minutes,
        'active': item.active,
    })


@app.put('/api/pm/templates/{template_id}')
async def update_pm_template(template_id: str, update: dict) -> dict:
    json_fields = {'applies_to', 'checklist'}
    async with aiosqlite.connect(DB_PATH) as db:
        fields = {k: v for k, v in update.items() if k != 'id'}
        for key in json_fields:
            if key in fields and not isinstance(fields[key], str):
                fields[key] = json.dumps(fields[key])
        if 'active' in fields:
            fields['active'] = 1 if fields['active'] else 0
        set_clause = ', '.join(f'{k} = :{k}' for k in fields)
        fields['tid'] = template_id
        await db.execute(f'UPDATE pm_templates SET {set_clause} WHERE id = :tid', fields)
        await db.commit()
    return {'id': template_id, **update}


@app.get('/api/pm/records', response_model=List[PMRecord])
async def list_pm_records(status: Optional[str] = Query(None)) -> List[PMRecord]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        query = 'SELECT * FROM pm_records'
        params: List[Any] = []
        if status:
            query += ' WHERE status = ?'
            params.append(status)
        query += ' ORDER BY scheduled_date ASC'
        cursor = await connection.execute(query, params)
        rows = await cursor.fetchall()

    return [PMRecord(**{**dict(row), 'checklist_results': json.loads(row['checklist_results'] or '[]'), 'linked_wo_ids': json.loads(row['linked_wo_ids'] or '[]')}) for row in rows]


@app.post('/api/pm/records', response_model=PMRecord)
async def create_pm_record(item: PMRecordCreate) -> PMRecord:
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            '''
            INSERT INTO pm_records (
                template_id, template_name, description, cart_id, location,
                scheduled_date, completed_date, status, checklist_results,
                tech_name, labor_minutes, linked_wo_ids
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                item.template_id,
                item.template_name,
                item.description,
                item.cart_id,
                item.location,
                item.scheduled_date,
                item.completed_date,
                item.status,
                json.dumps(item.checklist_results or []),
                item.tech_name,
                item.labor_minutes,
                json.dumps(item.linked_wo_ids or []),
            ),
        )
        await connection.commit()
        row_id = cursor.lastrowid

    return PMRecord(**{
        'id': row_id,
        **item.dict(),
    })


@app.put('/api/pm/records/{record_id}')
async def update_pm_record(record_id: str, update: dict) -> dict:
    json_fields = {'checklist_results', 'linked_wo_ids'}
    async with aiosqlite.connect(DB_PATH) as db:
        fields = {k: v for k, v in update.items() if k != 'id'}
        for key in json_fields:
            if key in fields and not isinstance(fields[key], str):
                fields[key] = json.dumps(fields[key])
        set_clause = ', '.join(f'{k} = :{k}' for k in fields)
        fields['rid'] = record_id
        await db.execute(f'UPDATE pm_records SET {set_clause} WHERE id = :rid', fields)
        await db.commit()
    return {'id': record_id, **update}


@app.delete('/api/workorders/{workorder_id}')
async def delete_work_order(workorder_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute('SELECT id FROM work_orders WHERE id = ?', (workorder_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail='Work order not found')
        await connection.execute('DELETE FROM work_orders WHERE id = ?', (workorder_id,))
        await connection.commit()
    return {'deleted': workorder_id}


@app.delete('/api/pm/records/{record_id}')
async def delete_pm_record(record_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute('SELECT id FROM pm_records WHERE id = ?', (record_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail='PM record not found')
        await connection.execute('DELETE FROM pm_records WHERE id = ?', (record_id,))
        await connection.commit()
    return {'deleted': record_id}


@app.get('/api/accidents', response_model=List[AccidentReport])
async def list_accidents(
    status: Optional[str] = Query(None),
    cart_id: Optional[int] = Query(None),
) -> List[AccidentReport]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        query = 'SELECT * FROM accident_reports'
        conditions = []
        params: List[Any] = []
        if status:
            conditions.append('status = ?')
            params.append(status)
        if cart_id is not None:
            conditions.append('cart_id = ?')
            params.append(cart_id)
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        query += ' ORDER BY incident_date DESC, id DESC'
        cursor = await connection.execute(query, params)
        rows = await cursor.fetchall()
    return [accident_from_row(row) for row in rows]


@app.get('/api/accidents/{accident_id}', response_model=AccidentReport)
async def get_accident(accident_id: int) -> AccidentReport:
    row = await get_accident_row(accident_id)
    return accident_from_row(row)


@app.post('/api/accidents', response_model=AccidentReport)
async def create_accident(item: AccidentReportCreate) -> AccidentReport:
    created_date = datetime.utcnow().isoformat()
    cart_serial = next(
        (cart.serial for cart in app.state.carts if cart.id == item.cart_id),
        '',
    )
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            '''
            INSERT INTO accident_reports (
                cart_id, cart_serial, location, reported_by, incident_date,
                description, severity, status, damage_areas, photos, notes,
                linked_wo_id, created_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                item.cart_id,
                cart_serial,
                item.location,
                item.reported_by,
                item.incident_date or created_date,
                item.description,
                item.severity,
                item.status,
                json.dumps(item.damage_areas or []),
                json.dumps(item.photos or []),
                item.notes,
                item.linked_wo_id,
                created_date,
            ),
        )
        await connection.commit()
        row_id = cursor.lastrowid

    return AccidentReport(**{
        'id': row_id,
        'cart_id': item.cart_id,
        'cart_serial': cart_serial,
        'location': item.location,
        'reported_by': item.reported_by,
        'incident_date': item.incident_date or created_date,
        'description': item.description,
        'severity': item.severity,
        'status': item.status,
        'damage_areas': item.damage_areas,
        'photos': item.photos,
        'notes': item.notes,
        'linked_wo_id': item.linked_wo_id,
        'created_date': created_date,
    })


@app.put('/api/accidents/{accident_id}', response_model=AccidentReport)
async def update_accident(accident_id: int, item: AccidentReportUpdate) -> AccidentReport:
    existing = await get_accident_row(accident_id)
    updated = {**existing}
    payload = item.model_dump(exclude_unset=True)

    if 'cart_id' in payload:
        updated['cart_id'] = payload['cart_id']
        updated['cart_serial'] = next(
            (cart.serial for cart in app.state.carts if cart.id == payload['cart_id']),
            updated.get('cart_serial', ''),
        )
    for field in ('location', 'reported_by', 'incident_date', 'description', 'severity', 'status', 'notes', 'linked_wo_id'):
        if field in payload:
            updated[field] = payload[field]
    if 'damage_areas' in payload:
        updated['damage_areas'] = json.dumps(payload['damage_areas'])

    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            '''
            UPDATE accident_reports SET
                cart_id = ?, cart_serial = ?, location = ?, reported_by = ?,
                incident_date = ?, description = ?, severity = ?, status = ?,
                damage_areas = ?, notes = ?, linked_wo_id = ?
            WHERE id = ?
            ''',
            (
                updated['cart_id'],
                updated['cart_serial'],
                updated['location'],
                updated['reported_by'],
                updated['incident_date'],
                updated['description'],
                updated['severity'],
                updated['status'],
                updated['damage_areas'] if isinstance(updated['damage_areas'], str) else json.dumps(updated['damage_areas']),
                updated['notes'],
                updated['linked_wo_id'],
                accident_id,
            ),
        )
        await connection.commit()

    updated['damage_areas'] = json.loads(updated['damage_areas'] or '[]')
    updated['photos'] = json.loads(updated['photos'] or '[]')
    return AccidentReport(**updated)


@app.post('/api/accidents/{accident_id}/photos')
async def upload_accident_photo(accident_id: int, file: UploadFile = File(...)) -> dict:
    row = await get_accident_row(accident_id)
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail='Only image files are allowed')

    ext = Path(file.filename or 'photo.jpg').suffix.lower()
    if ext not in {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif'}:
        ext = '.jpg'

    accident_dir = UPLOADS_DIR / str(accident_id)
    accident_dir.mkdir(parents=True, exist_ok=True)
    filename = f'{uuid.uuid4().hex}{ext}'
    dest = accident_dir / filename

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail='Image must be under 10 MB')

    dest.write_bytes(contents)
    rel_path = f'uploads/accidents/{accident_id}/{filename}'
    photos = json.loads(row['photos'] or '[]')
    photos.append(rel_path)

    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            'UPDATE accident_reports SET photos = ? WHERE id = ?',
            (json.dumps(photos), accident_id),
        )
        await connection.commit()

    return {'path': rel_path, 'photos': photos}


@app.delete('/api/accidents/{accident_id}/photos')
async def delete_accident_photo(accident_id: int, path: str = Query(...)) -> dict:
    row = await get_accident_row(accident_id)
    photos = json.loads(row['photos'] or '[]')
    if path not in photos:
        raise HTTPException(status_code=404, detail='Photo not found on this report')

    delete_photo_files([path])
    photos = [p for p in photos if p != path]

    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            'UPDATE accident_reports SET photos = ? WHERE id = ?',
            (json.dumps(photos), accident_id),
        )
        await connection.commit()

    return {'photos': photos}


@app.delete('/api/accidents/{accident_id}')
async def delete_accident(accident_id: int) -> dict:
    row = await get_accident_row(accident_id)
    photos = json.loads(row['photos'] or '[]')
    delete_photo_files(photos)

    accident_dir = UPLOADS_DIR / str(accident_id)
    if accident_dir.exists():
        for leftover in accident_dir.iterdir():
            leftover.unlink(missing_ok=True)
        accident_dir.rmdir()

    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute('DELETE FROM accident_reports WHERE id = ?', (accident_id,))
        await connection.commit()

    return {'deleted': accident_id}


@app.get('/api/stats')
async def get_stats() -> dict:
    now = datetime.utcnow().isoformat()
    week_end = datetime.utcnow().timestamp() + 7 * 86400
    week_end_iso = datetime.utcfromtimestamp(week_end).isoformat()

    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row

        cursor = await connection.execute(
            "SELECT COUNT(*) as total FROM work_orders WHERE status = 'open'"
        )
        open_wo = (await cursor.fetchone())['total']

        cursor = await connection.execute(
            """
            SELECT COUNT(*) as total FROM work_orders
            WHERE due_date IS NOT NULL
              AND due_date < ?
              AND status NOT IN ('completed', 'closed')
            """,
            (now,),
        )
        overdue_wo = (await cursor.fetchone())['total']

        cursor = await connection.execute(
            """
            SELECT COUNT(*) as total FROM pm_records
            WHERE status = 'scheduled'
              AND scheduled_date IS NOT NULL
              AND scheduled_date <= ?
            """,
            (week_end_iso,),
        )
        pm_week = (await cursor.fetchone())['total']

        cursor = await connection.execute(
            """
            SELECT COUNT(*) as total FROM pm_records
            WHERE scheduled_date IS NOT NULL
              AND scheduled_date < ?
              AND status NOT IN ('completed', 'skipped')
            """,
            (now,),
        )
        pm_overdue = (await cursor.fetchone())['total']

        cursor = await connection.execute(
            """
            SELECT COUNT(*) as total FROM accident_reports
            WHERE status NOT IN ('resolved')
            """
        )
        open_accidents = (await cursor.fetchone())['total']

    return {
        'open_work_orders': open_wo,
        'overdue_work_orders': overdue_wo,
        'pm_due_this_week': pm_week,
        'pm_overdue': pm_overdue,
        'open_accidents': open_accidents,
    }


class LoginRequest(BaseModel):
    password: str


@app.get('/api/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


@app.post('/api/auth/login')
def login(body: LoginRequest, request: Request, response: Response) -> dict[str, bool]:
    if not APP_PASSWORD:
        return {'ok': True}
    if not hmac.compare_digest(body.password, APP_PASSWORD):
        raise HTTPException(status_code=401, detail='Incorrect password')

    token = create_session_token()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite='lax',
        max_age=SESSION_MAX_AGE,
        secure=request.url.scheme == 'https',
    )
    return {'ok': True}


@app.post('/api/auth/logout')
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(SESSION_COOKIE)
    return {'ok': True}


@app.get('/')
def root() -> FileResponse:
    index_html = ROOT_DIR / 'index.html'
    if not index_html.exists():
        raise HTTPException(status_code=404, detail='Index page not found')
    return FileResponse(index_html)


@app.get('/{path:path}')
def serve_file(path: str) -> FileResponse:
    target = ROOT_DIR / path
    if target.exists() and target.is_file():
        return FileResponse(target)
    raise HTTPException(status_code=404, detail='File not found')


if __name__ == '__main__':
    import uvicorn

    uvicorn.run('server:app', host='127.0.0.1', port=8000, reload=True)
