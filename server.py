from __future__ import annotations
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import aiosqlite
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).parent.resolve()
DB_PATH = ROOT_DIR / 'maintainsmip.db'
CART_DATA_PATH = ROOT_DIR / 'cart_data.js'

app = FastAPI(title='MaintainSMIP API', version='1.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)


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


class WorkOrderCreate(WorkOrderBase):
    pass


class WorkOrderUpdate(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None
    labor_minutes: Optional[int] = None
    parts_used: Optional[List[Any]] = None
    comments: Optional[List[Any]] = None


class WorkOrder(WorkOrderBase):
    id: int
    cart_serial: Optional[str] = None
    created_date: str
    completed_date: Optional[str] = None


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


async def migrate_schema() -> None:
    """Recreate tables that used an older integer-id schema."""
    async with aiosqlite.connect(DB_PATH) as connection:
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
                comments TEXT
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
        await connection.commit()


@app.on_event('startup')
async def startup_event() -> None:
    os.makedirs(ROOT_DIR, exist_ok=True)
    await migrate_schema()
    await create_tables()
    app.state.carts = parse_cart_data()

    await seed_pm_templates()


PM_TEMPLATE_SEED = [
    ('PM-TPL-001', '90-Day Inspection', 'Full inspection every 90 days', 'interval_days', 90, '{"all":true,"models":[],"locations":[]}', '[{"id":1,"task":"Check tire pressure","required":true},{"id":2,"task":"Inspect brakes","required":true},{"id":3,"task":"Test lights","required":true},{"id":4,"task":"Check battery connections","required":true},{"id":5,"task":"Inspect steering","required":true}]', 45, 1),
    ('PM-TPL-002', 'Annual Full Service', 'Complete annual service', 'interval_days', 365, '{"all":true,"models":[],"locations":[]}', '[{"id":1,"task":"Full brake service","required":true},{"id":2,"task":"Battery load test","required":true},{"id":3,"task":"Tire check","required":true},{"id":4,"task":"Motor inspection","required":true}]', 120, 1),
    ('PM-TPL-003', 'Battery Service', 'Battery check every 6 months', 'interval_days', 180, '{"all":true,"models":[],"locations":[]}', '[{"id":1,"task":"Check water levels","required":true},{"id":2,"task":"Clean terminals","required":true},{"id":3,"task":"Load test","required":true}]', 30, 1),
    ('PM-TPL-004', 'Brake Inspection', 'Brake check every 6 months', 'interval_days', 180, '{"all":true,"models":[],"locations":[]}', '[{"id":1,"task":"Check brake pads","required":true},{"id":2,"task":"Test brake response","required":true}]', 20, 1),
    ('PM-TPL-005', 'Roof Inspection', 'Annual roof and top check', 'interval_days', 365, '{"all":true,"models":[],"locations":[]}', '[{"id":1,"task":"Check for cracks","required":true},{"id":2,"task":"Check mounting hardware","required":true}]', 15, 1),
]


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


@app.get('/api/carts', response_model=List[CartItem])
async def list_carts() -> List[CartItem]:
    return app.state.carts


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

    return [WorkOrder(**{**dict(row), 'parts_used': json.loads(row['parts_used'] or '[]'), 'comments': json.loads(row['comments'] or '[]')}) for row in rows]


@app.post('/api/workorders', response_model=WorkOrder)
async def create_work_order(item: WorkOrderCreate) -> WorkOrder:
    created_date = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            '''
            INSERT INTO work_orders (
                cart_id, cart_serial, title, description, priority, status, type,
                assigned_to, location, created_date, due_date, completed_date,
                labor_minutes, parts_used, comments
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        if item.status is not None:
            updated['status'] = item.status
            if item.status == 'completed':
                updated['completed_date'] = datetime.utcnow().isoformat()
        if item.assigned_to is not None:
            updated['assigned_to'] = item.assigned_to
        if item.due_date is not None:
            updated['due_date'] = item.due_date
        if item.labor_minutes is not None:
            updated['labor_minutes'] = item.labor_minutes
        if item.parts_used is not None:
            updated['parts_used'] = json.dumps(item.parts_used)
        if item.comments is not None:
            updated['comments'] = json.dumps(item.comments)

        await connection.execute(
            '''
            UPDATE work_orders SET
                status = ?,
                assigned_to = ?,
                due_date = ?,
                completed_date = ?,
                labor_minutes = ?,
                parts_used = ?,
                comments = ?
            WHERE id = ?
            ''',
            (
                updated['status'],
                updated['assigned_to'],
                updated['due_date'],
                updated['completed_date'],
                updated['labor_minutes'],
                updated['parts_used'],
                updated['comments'],
                workorder_id,
            ),
        )
        await connection.commit()

    return WorkOrder(**{**updated, 'parts_used': json.loads(updated['parts_used'] or '[]'), 'comments': json.loads(updated['comments'] or '[]')})


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

    return {
        'open_work_orders': open_wo,
        'overdue_work_orders': overdue_wo,
        'pm_due_this_week': pm_week,
        'pm_overdue': pm_overdue,
    }


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
