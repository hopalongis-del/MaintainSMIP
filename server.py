from __future__ import annotations
import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import tempfile
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
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware

ROOT_DIR = Path(__file__).parent.resolve()
DATA_DIR = Path(os.environ.get('DATA_DIR', str(ROOT_DIR))).resolve()
DB_PATH = DATA_DIR / 'maintainsmip.db'
CART_DATA_PATH = ROOT_DIR / 'cart_data.js'
UPLOADS_DIR = DATA_DIR / 'uploads' / 'accidents'
LEGACY_DB_PATH = ROOT_DIR / 'maintainsmip.db'
LEGACY_UPLOADS_DIR = ROOT_DIR / 'uploads'
APP_PASSWORD = os.environ.get('APP_PASSWORD', 'WeLoveRacing!')
APP_SECRET = os.environ.get('APP_SECRET', 'maintainsmip-session-secret')
BACKUP_TOKEN = os.environ.get('BACKUP_TOKEN', '').strip()
SESSION_COOKIE = 'ms_session'
SESSION_MAX_AGE = 7 * 24 * 3600
MASTER_USERNAME = 'admin'
USER_ROLES = ('admin', 'manager', 'technician', 'readonly')
WRITE_ROLES = ('admin', 'manager', 'technician')
PUBLIC_PATHS = {
    '/login.html',
    '/api/auth/login',
    '/api/health',
    '/api/push/vapid-public-key',
    '/shared.css',
    '/logo1.png',
    '/service-worker.js',
}

VAPID_EMAIL = os.environ.get('VAPID_EMAIL', 'mailto:support@smiproperties.com')
VAPID_KEYS_PATH = DATA_DIR / 'vapid_keys.json'
NOTIFICATION_CHECK_INTERVAL_SEC = int(os.environ.get('NOTIFICATION_CHECK_INTERVAL_SEC', '1800'))

TECHNICIAN_ACCOUNTS = [
    ('gavin.weinmeister', 'Gavin Weinmeister', 'technician'),
    ('kevin.stellman', 'Kevin Stellman', 'technician'),
    ('cory.yeager', 'Cory Yeager', 'technician'),
    ('mike.casady', 'Mike Casady', 'admin'),
    ('dusty.hixson', 'Dusty Hixson', 'admin'),
    ('brian.lachance', 'Brian Lachance', 'admin'),
    ('chelsie', 'Chelsie', 'admin'),
    ('stephen.hering', 'Stephen Hering', 'technician'),
    ('mark.hixson', 'Mark Hixson', 'technician'),
]

PRIVILEGED_ROLE_OVERRIDES = {
    'mike.casady': 'admin',
    'dusty.hixson': 'admin',
    'brian.lachance': 'admin',
    'chelsie': 'admin',
}

SEEDED_USERNAMES = {MASTER_USERNAME, *(account[0] for account in TECHNICIAN_ACCOUNTS)}


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 120_000)
    return f'pbkdf2_sha256${salt}${digest.hex()}'


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, salt, digest_hex = stored_hash.split('$', 2)
        if scheme != 'pbkdf2_sha256':
            return False
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 120_000)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_session_token(user_id: int) -> str:
    expires = int(time.time()) + SESSION_MAX_AGE
    payload = f'{expires}.{user_id}'
    signature = hmac.new(APP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f'{payload}.{signature}'


def verify_session_token(token: str) -> Optional[int]:
    try:
        parts = token.split('.')
        if len(parts) == 2:
            expires_str, signature = parts
            expires = int(expires_str)
            if expires < time.time():
                return None
            expected = hmac.new(APP_SECRET.encode(), expires_str.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return None
            return 0
        if len(parts) != 3:
            return None
        expires_str, user_id_str, signature = parts
        expires = int(expires_str)
        if expires < time.time():
            return None
        payload = f'{expires_str}.{user_id_str}'
        expected = hmac.new(APP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        return int(user_id_str)
    except (ValueError, TypeError):
        return None


def user_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        'id': row['id'],
        'username': row['username'],
        'display_name': row['display_name'],
        'role': row['role'],
    }


async def fetch_user_by_id(user_id: int) -> Optional[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT id, username, display_name, role, active FROM users WHERE id = ?',
            (user_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def fetch_user_auth_record(user_id: int) -> Optional[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT id, username, display_name, role, active, password_hash, password_changed FROM users WHERE id = ?',
            (user_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def fetch_user_by_username(username: str) -> Optional[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT id, username, display_name, role, active, password_hash, password_changed FROM users WHERE username = ?',
            (username,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def authenticate_user(username: str, password: str) -> Optional[dict[str, Any]]:
    user = await fetch_user_by_username(username.lower())
    if not user or not user.get('active'):
        return None
    if not verify_password(password, user['password_hash']):
        return None
    return user


async def resync_seeded_user_password(username: str, password: str) -> Optional[dict[str, Any]]:
    """Let seeded team accounts sign in with APP_PASSWORD until they choose a new password."""
    normalized = username.strip().lower()
    if normalized not in SEEDED_USERNAMES or not APP_PASSWORD:
        return None
    if not hmac.compare_digest(password, APP_PASSWORD):
        return None

    user = await fetch_user_by_username(normalized)
    if not user or not user.get('active') or user.get('password_changed'):
        return None

    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            'UPDATE users SET password_hash = ? WHERE id = ?',
            (hash_password(password), user['id']),
        )
        await connection.commit()

    return await fetch_user_by_id(user['id'])


async def upsert_master_admin(password: str) -> dict[str, Any]:
    password_hash = hash_password(password)
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT id FROM users WHERE username = ?',
            (MASTER_USERNAME,),
        )
        existing = await cursor.fetchone()
        if existing:
            await connection.execute(
                '''
                UPDATE users
                SET display_name = ?, role = 'admin', password_hash = ?, active = 1
                WHERE username = ?
                ''',
                ('Master Admin', password_hash, MASTER_USERNAME),
            )
            user_id = existing['id']
        else:
            cursor = await connection.execute(
                '''
                INSERT INTO users (username, display_name, role, password_hash, active, created_date)
                VALUES (?, ?, 'admin', ?, 1, ?)
                ''',
                (MASTER_USERNAME, 'Master Admin', password_hash, now),
            )
            user_id = cursor.lastrowid
        await connection.commit()
        cursor = await connection.execute(
            'SELECT id, username, display_name, role, active FROM users WHERE id = ?',
            (user_id,),
        )
        row = await cursor.fetchone()
        return dict(row)


async def ensure_users_seeded() -> None:
    """Seed accounts on first boot; always keep a reachable master admin."""
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute('SELECT COUNT(*) FROM users')
        total_users = (await cursor.fetchone())[0]
        cursor = await connection.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1",
        )
        active_admins = (await cursor.fetchone())[0]

    if total_users == 0:
        master_password = APP_PASSWORD or 'WeLoveRacing!'
        await upsert_master_admin(master_password)
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(DB_PATH) as connection:
            for username, display_name, role in TECHNICIAN_ACCOUNTS:
                await connection.execute(
                    '''
                    INSERT INTO users (username, display_name, role, password_hash, active, created_date)
                    VALUES (?, ?, ?, ?, 1, ?)
                    ''',
                    (username, display_name, role, hash_password(master_password), now),
                )
            await connection.commit()
        return

    if active_admins == 0:
        master_password = APP_PASSWORD or 'WeLoveRacing!'
        await upsert_master_admin(master_password)

    await apply_privileged_role_overrides()


async def apply_privileged_role_overrides() -> None:
    """Keep leadership accounts at the right privilege level; add Chelsie if missing."""
    master_password = APP_PASSWORD or 'WeLoveRacing!'
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        for username, role in PRIVILEGED_ROLE_OVERRIDES.items():
            await connection.execute(
                'UPDATE users SET role = ? WHERE username = ?',
                (role, username),
            )

        cursor = await connection.execute(
            'SELECT id FROM users WHERE username = ?',
            ('chelsie',),
        )
        if not await cursor.fetchone():
            await connection.execute(
                '''
                INSERT INTO users (username, display_name, role, password_hash, active, created_date)
                VALUES (?, ?, 'admin', ?, 1, ?)
                ''',
                ('chelsie', 'Chelsie', hash_password(master_password), now),
            )

        await connection.commit()


def get_request_user(request: Request) -> Optional[dict[str, Any]]:
    return getattr(request.state, 'user', None)


def require_authenticated_user(request: Request) -> dict[str, Any]:
    user = get_request_user(request)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    return user


def require_write_access(request: Request) -> dict[str, Any]:
    user = require_authenticated_user(request)
    if user['role'] not in WRITE_ROLES:
        raise HTTPException(status_code=403, detail='Read-only account cannot change data')
    return user


def require_admin(request: Request) -> dict[str, Any]:
    user = require_authenticated_user(request)
    if user['role'] != 'admin':
        raise HTTPException(status_code=403, detail='Admin access required')
    return user


async def record_audit(
    request: Request,
    action: str,
    entity_type: str,
    entity_id: Any,
    summary: str,
    details: Optional[dict[str, Any]] = None,
) -> None:
    user = get_request_user(request) or {}
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            '''
            INSERT INTO audit_log (
                created_at, user_id, username, display_name,
                action, entity_type, entity_id, summary, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                datetime.utcnow().isoformat(),
                user.get('id'),
                user.get('username'),
                user.get('display_name') or 'System',
                action,
                entity_type,
                str(entity_id),
                summary,
                json.dumps(details) if details else None,
            ),
        )
        await connection.commit()


def _format_field_change(label: str, old_value: Any, new_value: Any) -> Optional[str]:
    if old_value == new_value:
        return None
    old_text = '—' if old_value in (None, '') else str(old_value).replace('_', ' ')
    new_text = '—' if new_value in (None, '') else str(new_value).replace('_', ' ')
    return f'{label}: {old_text} → {new_text}'


def summarize_work_order_update(existing: dict[str, Any], item: WorkOrderUpdate) -> tuple[str, dict[str, Any]]:
    changes: list[str] = []
    payload = item.model_dump(exclude_unset=True)
    field_labels = {
        'title': 'title',
        'status': 'status',
        'priority': 'priority',
        'type': 'type',
        'assigned_to': 'assigned to',
        'location': 'location',
        'cart_id': 'cart',
    }
    for field, label in field_labels.items():
        if field in payload:
            change = _format_field_change(label, existing.get(field), payload[field])
            if change:
                changes.append(change)

    details: dict[str, Any] = {'changes': changes}
    if 'maintenance_sheet' in payload and isinstance(payload['maintenance_sheet'], dict):
        checklist = payload['maintenance_sheet'].get('checklist') or []
        done = sum(1 for entry in checklist if entry.get('checked'))
        changes.append(f'maintenance sheet ({done}/{len(checklist)} checked)')
        details['sheet_progress'] = {'done': done, 'total': len(checklist)}
    if 'comments' in payload:
        changes.append('added comment')
    if 'parts_used' in payload:
        changes.append('updated parts list')

    if not changes:
        return 'Updated work order', details
    return 'Updated ' + ', '.join(changes), details


def summarize_accident_update(existing: dict[str, Any], payload: dict[str, Any]) -> str:
    changes: list[str] = []
    for field, label in (
        ('status', 'status'),
        ('severity', 'severity'),
        ('location', 'location'),
        ('reported_by', 'reported by'),
        ('cart_id', 'cart'),
    ):
        if field in payload:
            change = _format_field_change(label, existing.get(field), payload[field])
            if change:
                changes.append(change)
    if 'description' in payload and payload['description'] != existing.get('description'):
        changes.append('updated description')
    if 'damage_areas' in payload:
        changes.append('updated damage areas')
    if not changes:
        return 'Updated accident report'
    return 'Updated ' + ', '.join(changes)


def summarize_cart_update(existing: dict[str, Any], payload: dict[str, Any]) -> str:
    changes: list[str] = []
    for field, label in (
        ('serial', 'serial'),
        ('model', 'model'),
        ('year', 'year'),
        ('location', 'location'),
        ('status', 'status'),
    ):
        if field in payload:
            change = _format_field_change(label, existing.get(field), payload[field])
            if change:
                changes.append(change)
    if 'notes' in payload and payload['notes'] != existing.get('notes'):
        changes.append('updated notes')
    cart_label = existing.get('id')
    if payload.get('status') == 'retired' and existing.get('status') != 'retired':
        return f'Retired cart #{cart_label}'
    if not changes:
        return f'Updated cart #{cart_label}'
    return f'Updated cart #{cart_label}: ' + ', '.join(changes)


class AuthMiddleware(BaseHTTPMiddleware):
    @staticmethod
    def _backup_token_valid(request: Request) -> bool:
        if not BACKUP_TOKEN:
            return False
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return False
        provided = auth[7:].strip()
        if not provided:
            return False
        return secrets.compare_digest(provided, BACKUP_TOKEN)

    async def dispatch(self, request: Request, call_next):
        request.state.user = None
        if not APP_PASSWORD:
            return await call_next(request)

        path = request.url.path
        if path in PUBLIC_PATHS:
            return await call_next(request)

        token = request.cookies.get(SESSION_COOKIE)
        user_id = verify_session_token(token) if token else None
        if user_id is not None:
            if user_id == 0:
                master = await fetch_user_by_username(MASTER_USERNAME)
                if master and master.get('active'):
                    request.state.user = master
                    return await call_next(request)
            else:
                user = await fetch_user_by_id(user_id)
                if user and user.get('active'):
                    request.state.user = user
                    return await call_next(request)

        if (
            path in ('/api/admin/backup', '/api/admin/backup/info')
            and BACKUP_TOKEN
            and self._backup_token_valid(request)
        ):
            master = await fetch_user_by_username(MASTER_USERNAME)
            if master and master.get('active'):
                request.state.user = master
                return await call_next(request)

        if path.startswith('/api/'):
            return JSONResponse(status_code=401, content={'detail': 'Authentication required'})

        next_path = path if path != '/' else '/index.html'
        return RedirectResponse(f'/login.html?next={quote(next_path)}', status_code=302)


def ensure_persistent_storage() -> None:
    """Prepare DATA_DIR and migrate legacy local files on first boot."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    if DATA_DIR.resolve() == ROOT_DIR.resolve():
        return

    if LEGACY_DB_PATH.exists() and not DB_PATH.exists():
        shutil.copy2(LEGACY_DB_PATH, DB_PATH)

    if LEGACY_UPLOADS_DIR.exists():
        for src in LEGACY_UPLOADS_DIR.rglob('*'):
            if not src.is_file():
                continue
            rel = src.relative_to(LEGACY_UPLOADS_DIR)
            dest = DATA_DIR / 'uploads' / rel
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


def resolve_data_path(rel_path: str) -> Path:
    normalized = Path(rel_path)
    data_target = (DATA_DIR / normalized).resolve()
    if data_target.exists():
        return data_target
    return (ROOT_DIR / normalized).resolve()


def resolve_static_file(path: str) -> Optional[Path]:
    for base in (DATA_DIR, ROOT_DIR):
        base_resolved = base.resolve()
        target = (base_resolved / path).resolve()
        try:
            target.relative_to(base_resolved)
        except ValueError:
            continue
        if target.exists() and target.is_file():
            return target
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_persistent_storage()
    await migrate_schema()
    await create_tables()
    await seed_carts_from_file()
    app.state.carts = await fetch_all_carts()
    await seed_pm_templates()
    await seed_wo_templates()
    await ensure_wo_templates_seeded()
    await ensure_users_seeded()
    await seed_demo_data()
    notification_task = asyncio.create_task(notification_loop())
    yield
    notification_task.cancel()
    try:
        await notification_task
    except asyncio.CancelledError:
        pass


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


REQUIRED_CART_FIELDS = ('serial', 'model', 'year', 'location', 'status')
CART_FIELD_LABELS = {
    'serial': 'Serial',
    'model': 'Model',
    'year': 'Year',
    'location': 'Location',
    'status': 'Status',
}


def validate_required_cart_fields(data: dict[str, Any]) -> None:
    missing = [
        CART_FIELD_LABELS[field]
        for field in REQUIRED_CART_FIELDS
        if not str(data.get(field, '')).strip()
    ]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Can't save — required field missing: {', '.join(missing)}",
        )


class CartCreate(BaseModel):
    id: Any
    serial: str = Field(min_length=1)
    model: str = Field(min_length=1)
    year: str = Field(min_length=1)
    location: str = Field(min_length=1)
    status: str = Field(min_length=1, default='active')
    notes: str = ''


class CartUpdate(BaseModel):
    serial: Optional[str] = None
    model: Optional[str] = None
    year: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None

    @field_validator('serial', 'model', 'year', 'location', 'status')
    @classmethod
    def reject_blank_values(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not str(value).strip():
            raise ValueError('cannot be empty')
        return value


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


class AuditEntry(BaseModel):
    id: int
    created_at: str
    user_id: Optional[int] = None
    username: Optional[str] = None
    display_name: str
    action: str
    entity_type: str
    entity_id: str
    summary: str
    details: Optional[dict[str, Any]] = None


class NotificationPrefsUpdate(BaseModel):
    notify_overdue_wo: bool = True
    notify_pm_due: bool = True
    notify_accidents: bool = True


class PushSubscriptionCreate(BaseModel):
    endpoint: str
    keys: dict[str, str] = Field(default_factory=dict)


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


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


def cart_id_str(cart_id: Any) -> str:
    return str(cart_id).strip()


def cart_row_to_item(row: Any) -> CartItem:
    data = dict(row)
    raw_id = data['id']
    if isinstance(raw_id, str) and raw_id.isdigit():
        raw_id = int(raw_id)
    return CartItem(
        id=raw_id,
        serial=data.get('serial'),
        model=data.get('model'),
        year=data.get('year'),
        location=data.get('location'),
        status=data.get('status'),
        notes=data.get('notes'),
    )


async def fetch_all_carts() -> List[CartItem]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT id, serial, model, year, location, status, notes FROM carts ORDER BY id'
        )
        rows = await cursor.fetchall()
    return [cart_row_to_item(row) for row in rows]


async def fetch_cart_row(cart_id: Any) -> Optional[dict[str, Any]]:
    normalized = cart_id_str(cart_id)
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT * FROM carts WHERE id = ?',
            (normalized,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def lookup_cart_serial(cart_id: Any) -> str:
    row = await fetch_cart_row(cart_id)
    return row.get('serial', '') if row else ''


async def seed_carts_from_file() -> None:
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute('SELECT COUNT(*) FROM carts')
        if (await cursor.fetchone())[0] > 0:
            return
        items = parse_cart_data()
        if not items:
            return
        for cart in items:
            await connection.execute(
                '''
                INSERT INTO carts (id, serial, model, year, location, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    cart_id_str(cart.id),
                    cart.serial or '',
                    cart.model or '',
                    cart.year or '',
                    cart.location or '',
                    cart.status or 'active',
                    cart.notes or '',
                ),
            )
        await connection.commit()


async def refresh_carts_cache() -> None:
    app.state.carts = await fetch_all_carts()


DEFAULT_NOTIFICATION_PREFS = {
    'notify_overdue_wo': True,
    'notify_pm_due': True,
    'notify_accidents': True,
}


def _load_vapid_keys() -> tuple[str, str]:
    public = os.environ.get('VAPID_PUBLIC_KEY', '').strip()
    private = os.environ.get('VAPID_PRIVATE_KEY', '').strip()
    if public and private:
        return public, private

    if VAPID_KEYS_PATH.exists():
        data = json.loads(VAPID_KEYS_PATH.read_text(encoding='utf-8'))
        return data['public_key'], data['private_key']

    from py_vapid import Vapid01, b64urlencode
    from cryptography.hazmat.primitives import serialization

    vapid = Vapid01()
    vapid.generate_keys()
    private_key = vapid.private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key = vapid.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    keys = {
        'public_key': b64urlencode(public_key),
        'private_key': b64urlencode(private_key),
    }
    VAPID_KEYS_PATH.write_text(json.dumps(keys), encoding='utf-8')
    return keys['public_key'], keys['private_key']


VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY = _load_vapid_keys()


def parse_notification_prefs(raw: Optional[str]) -> dict[str, bool]:
    if not raw:
        return dict(DEFAULT_NOTIFICATION_PREFS)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return dict(DEFAULT_NOTIFICATION_PREFS)
    return {
        'notify_overdue_wo': bool(data.get('notify_overdue_wo', True)),
        'notify_pm_due': bool(data.get('notify_pm_due', True)),
        'notify_accidents': bool(data.get('notify_accidents', True)),
    }


async def fetch_notification_prefs(user_id: int) -> dict[str, bool]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT notification_prefs FROM users WHERE id = ?',
            (user_id,),
        )
        row = await cursor.fetchone()
    if not row:
        return dict(DEFAULT_NOTIFICATION_PREFS)
    return parse_notification_prefs(row['notification_prefs'])


async def save_notification_prefs(user_id: int, prefs: dict[str, bool]) -> dict[str, bool]:
    normalized = {
        'notify_overdue_wo': bool(prefs.get('notify_overdue_wo', True)),
        'notify_pm_due': bool(prefs.get('notify_pm_due', True)),
        'notify_accidents': bool(prefs.get('notify_accidents', True)),
    }
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            'UPDATE users SET notification_prefs = ? WHERE id = ?',
            (json.dumps(normalized), user_id),
        )
        await connection.commit()
    return normalized


async def upsert_push_subscription(
    user_id: int,
    endpoint: str,
    p256dh: str,
    auth_key: str,
    user_agent: str = '',
) -> None:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            '''
            INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, user_agent, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(endpoint) DO UPDATE SET
                user_id = excluded.user_id,
                p256dh = excluded.p256dh,
                auth = excluded.auth,
                user_agent = excluded.user_agent,
                created_at = excluded.created_at
            ''',
            (user_id, endpoint, p256dh, auth_key, user_agent, now),
        )
        await connection.commit()


async def delete_push_subscription(endpoint: str) -> None:
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute('DELETE FROM push_subscriptions WHERE endpoint = ?', (endpoint,))
        await connection.commit()


async def fetch_push_subscriptions_for_user(user_id: int) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE user_id = ?',
            (user_id,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def count_push_subscriptions_for_user(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            'SELECT COUNT(*) FROM push_subscriptions WHERE user_id = ?',
            (user_id,),
        )
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


def _send_push_sync(subscription: dict[str, str], payload: dict[str, Any]) -> None:
    from pywebpush import WebPushException, webpush

    subscription_info = {
        'endpoint': subscription['endpoint'],
        'keys': {
            'p256dh': subscription['p256dh'],
            'auth': subscription['auth'],
        },
    }
    webpush(
        subscription_info=subscription_info,
        data=json.dumps(payload),
        vapid_private_key=VAPID_PRIVATE_KEY,
        vapid_claims={'sub': VAPID_EMAIL},
    )


async def send_push_to_user(user_id: int, payload: dict[str, Any]) -> int:
    from pywebpush import WebPushException

    subscriptions = await fetch_push_subscriptions_for_user(user_id)
    sent = 0
    for subscription in subscriptions:
        try:
            await asyncio.to_thread(_send_push_sync, subscription, payload)
            sent += 1
        except WebPushException as exc:
            if exc.response is not None and exc.response.status_code in (404, 410):
                await delete_push_subscription(subscription['endpoint'])
        except Exception:
            pass
    return sent


async def should_send_digest(user_id: int, alert_key: str) -> bool:
    today = datetime.utcnow().strftime('%Y-%m-%d')
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            '''
            SELECT 1 FROM notification_dedup
            WHERE user_id = ? AND alert_key = ? AND sent_date = ?
            ''',
            (user_id, alert_key, today),
        )
        if await cursor.fetchone():
            return False
        await connection.execute(
            '''
            INSERT INTO notification_dedup (user_id, alert_key, sent_date)
            VALUES (?, ?, ?)
            ''',
            (user_id, alert_key, today),
        )
        await connection.commit()
    return True


async def fetch_push_enabled_users() -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            '''
            SELECT DISTINCT u.id, u.username, u.display_name, u.notification_prefs
            FROM users u
            INNER JOIN push_subscriptions ps ON ps.user_id = u.id
            WHERE u.active = 1
            '''
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def compute_alert_counts() -> dict[str, int]:
    now = datetime.utcnow().isoformat()
    week_end = datetime.utcnow().timestamp() + 7 * 86400
    week_end_iso = datetime.utcfromtimestamp(week_end).isoformat()

    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            '''
            SELECT COUNT(*) as total FROM work_orders
            WHERE due_date IS NOT NULL
              AND due_date < ?
              AND status NOT IN ('completed', 'closed')
            ''',
            (now,),
        )
        overdue_wo = (await cursor.fetchone())['total']

        cursor = await connection.execute(
            '''
            SELECT COUNT(*) as total FROM pm_records
            WHERE status = 'scheduled'
              AND scheduled_date IS NOT NULL
              AND scheduled_date <= ?
            ''',
            (week_end_iso,),
        )
        pm_due = (await cursor.fetchone())['total']

        cursor = await connection.execute(
            '''
            SELECT COUNT(*) as total FROM pm_records
            WHERE scheduled_date IS NOT NULL
              AND scheduled_date < ?
              AND status NOT IN ('completed', 'skipped')
            ''',
            (now,),
        )
        pm_overdue = (await cursor.fetchone())['total']

        cursor = await connection.execute(
            '''
            SELECT COUNT(*) as total FROM accident_reports
            WHERE status NOT IN ('resolved')
            '''
        )
        open_accidents = (await cursor.fetchone())['total']

    return {
        'overdue_wo': overdue_wo,
        'pm_due': pm_due,
        'pm_overdue': pm_overdue,
        'open_accidents': open_accidents,
    }


async def run_scheduled_notifications() -> None:
    counts = await compute_alert_counts()
    users = await fetch_push_enabled_users()

    for user in users:
        prefs = parse_notification_prefs(user.get('notification_prefs'))
        user_id = user['id']

        if prefs['notify_overdue_wo'] and counts['overdue_wo'] > 0:
            if await should_send_digest(user_id, 'overdue_wo'):
                await send_push_to_user(user_id, {
                    'title': 'Overdue Work Orders',
                    'body': f'{counts["overdue_wo"]} work order(s) are past due.',
                    'url': '/workorders.html?overdue=1',
                    'tag': 'overdue-wo',
                })

        if prefs['notify_pm_due'] and (counts['pm_due'] > 0 or counts['pm_overdue'] > 0):
            if await should_send_digest(user_id, 'pm_due'):
                parts = []
                if counts['pm_overdue'] > 0:
                    parts.append(f'{counts["pm_overdue"]} overdue')
                if counts['pm_due'] > 0:
                    parts.append(f'{counts["pm_due"]} due soon')
                await send_push_to_user(user_id, {
                    'title': 'PM Reminder',
                    'body': 'PM schedule: ' + ', '.join(parts) + '.',
                    'url': '/pm.html?due=week',
                    'tag': 'pm-due',
                })


async def broadcast_accident_push(accident_id: int, cart_id: int, reported_by: str) -> None:
    users = await fetch_push_enabled_users()
    for user in users:
        prefs = parse_notification_prefs(user.get('notification_prefs'))
        if not prefs['notify_accidents']:
            continue
        await send_push_to_user(user['id'], {
            'title': 'New Accident Report',
            'body': f'ACC-{accident_id} reported for cart #{cart_id} by {reported_by}.',
            'url': f'/accidents.html?id={accident_id}',
            'tag': f'accident-{accident_id}',
        })


async def notification_loop() -> None:
    await asyncio.sleep(30)
    while True:
        try:
            await run_scheduled_notifications()
        except Exception:
            pass
        await asyncio.sleep(NOTIFICATION_CHECK_INTERVAL_SEC)


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
        await connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                password_changed INTEGER NOT NULL DEFAULT 0,
                created_date TEXT
            )
            '''
        )
        cursor = await connection.execute('PRAGMA table_info(users)')
        user_columns = [col[1] for col in await cursor.fetchall()]
        if 'password_changed' not in user_columns:
            await connection.execute(
                'ALTER TABLE users ADD COLUMN password_changed INTEGER NOT NULL DEFAULT 0',
            )
        cursor = await connection.execute('PRAGMA table_info(users)')
        user_columns = [col[1] for col in await cursor.fetchall()]
        if 'notification_prefs' not in user_columns:
            await connection.execute(
                'ALTER TABLE users ADD COLUMN notification_prefs TEXT',
            )
        await connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                endpoint TEXT NOT NULL UNIQUE,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                user_agent TEXT,
                created_at TEXT
            )
            '''
        )
        await connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS notification_dedup (
                user_id INTEGER NOT NULL,
                alert_key TEXT NOT NULL,
                sent_date TEXT NOT NULL,
                PRIMARY KEY (user_id, alert_key, sent_date)
            )
            '''
        )
        await connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                user_id INTEGER,
                username TEXT,
                display_name TEXT,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                details TEXT
            )
            '''
        )
        await connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS carts (
                id TEXT PRIMARY KEY,
                serial TEXT,
                model TEXT,
                year TEXT,
                location TEXT,
                status TEXT,
                notes TEXT
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


async def ensure_wo_templates_seeded() -> None:
    """Re-seed default template if persistent disk has an empty templates table."""
    if not WO_TEMPLATE_PATH.exists():
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT COUNT(*) FROM wo_templates')
        if (await cursor.fetchone())[0] > 0:
            return
    await seed_wo_templates()


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


ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.gif'}


def is_allowed_image_upload(file: UploadFile) -> bool:
    if file.content_type and file.content_type.startswith('image/'):
        return True
    ext = Path(file.filename or '').suffix.lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS


def delete_photo_files(photo_paths: List[str]) -> None:
    for rel_path in photo_paths:
        target = resolve_data_path(rel_path)
        if target.exists() and target.is_file():
            target.unlink()


@app.get('/api/carts', response_model=List[CartItem])
async def list_carts() -> List[CartItem]:
    return await fetch_all_carts()


@app.get('/api/carts/{cart_id}', response_model=CartItem)
async def get_cart(cart_id: str) -> CartItem:
    row = await fetch_cart_row(cart_id)
    if not row:
        raise HTTPException(status_code=404, detail='Cart not found')
    return cart_row_to_item(row)


@app.post('/api/carts', response_model=CartItem)
async def create_cart(request: Request, item: CartCreate) -> CartItem:
    require_write_access(request)
    normalized_id = cart_id_str(item.id)
    if not normalized_id:
        raise HTTPException(status_code=400, detail='Cart ID is required')
    if await fetch_cart_row(normalized_id):
        raise HTTPException(status_code=409, detail=f'Cart #{normalized_id} already exists')

    cart_values = {
        'serial': item.serial.strip(),
        'model': item.model.strip(),
        'year': item.year.strip(),
        'location': item.location.strip(),
        'status': item.status.strip(),
        'notes': (item.notes or '').strip(),
    }
    validate_required_cart_fields(cart_values)

    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            '''
            INSERT INTO carts (id, serial, model, year, location, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                normalized_id,
                cart_values['serial'],
                cart_values['model'],
                cart_values['year'],
                cart_values['location'],
                cart_values['status'],
                cart_values['notes'],
            ),
        )
        await connection.commit()

    await refresh_carts_cache()
    await record_audit(
        request,
        'created',
        'cart',
        normalized_id,
        f'Added cart #{normalized_id} ({item.model or "unknown model"})',
        {'location': item.location, 'status': item.status},
    )
    row = await fetch_cart_row(normalized_id)
    return cart_row_to_item(row)


@app.put('/api/carts/{cart_id}', response_model=CartItem)
async def update_cart(request: Request, cart_id: str, item: CartUpdate) -> CartItem:
    require_write_access(request)
    existing = await fetch_cart_row(cart_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Cart not found')

    payload = item.model_dump(exclude_unset=True)
    updated = {**existing, **payload}
    for field in (*REQUIRED_CART_FIELDS, 'notes'):
        if field in updated and isinstance(updated[field], str):
            updated[field] = updated[field].strip()
    validate_required_cart_fields(updated)

    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            '''
            UPDATE carts SET serial = ?, model = ?, year = ?, location = ?, status = ?, notes = ?
            WHERE id = ?
            ''',
            (
                updated.get('serial', ''),
                updated.get('model', ''),
                updated.get('year', ''),
                updated.get('location', ''),
                updated.get('status', ''),
                updated.get('notes', ''),
                cart_id_str(cart_id),
            ),
        )
        await connection.commit()

    await refresh_carts_cache()
    summary = summarize_cart_update(existing, payload)
    await record_audit(request, 'updated', 'cart', cart_id_str(cart_id), summary, payload)
    row = await fetch_cart_row(cart_id)
    return cart_row_to_item(row)


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
async def create_wo_template(request: Request, item: WoTemplateCreate) -> WoTemplate:
    require_write_access(request)
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
async def create_work_order(request: Request, item: WorkOrderCreate) -> WorkOrder:
    user = require_write_access(request)
    if not item.assigned_to:
        item = item.model_copy(update={'assigned_to': user['display_name']})
    created_date = datetime.utcnow().isoformat()
    cart_serial = await lookup_cart_serial(item.cart_id)
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
                cart_serial,
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

    await record_audit(
        request,
        'created',
        'work_order',
        row_id,
        f'Created WO-{row_id} for cart #{item.cart_id}',
        {'title': item.title, 'status': item.status},
    )

    return WorkOrder(**{
        'id': row_id,
        'cart_id': item.cart_id,
        'cart_serial': cart_serial,
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
async def update_work_order(request: Request, workorder_id: int, item: WorkOrderUpdate) -> WorkOrder:
    require_write_access(request)
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
            updated['cart_serial'] = await lookup_cart_serial(item.cart_id) or updated.get('cart_serial', '')
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
    summary, details = summarize_work_order_update(existing, item)
    await record_audit(request, 'updated', 'work_order', workorder_id, summary, details)
    return WorkOrder(**updated)


@app.get('/api/pm/templates', response_model=List[PMTemplate])
async def list_pm_templates() -> List[PMTemplate]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute('SELECT * FROM pm_templates ORDER BY id DESC')
        rows = await cursor.fetchall()

    return [PMTemplate(**{**dict(row), 'applies_to': json.loads(row['applies_to'] or '{}'), 'checklist': json.loads(row['checklist'] or '[]')}) for row in rows]


@app.post('/api/pm/templates', response_model=PMTemplate)
async def create_pm_template(request: Request, item: PMTemplateCreate) -> PMTemplate:
    require_write_access(request)
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
async def update_pm_template(request: Request, template_id: str, update: dict) -> dict:
    require_write_access(request)
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
async def create_pm_record(request: Request, item: PMRecordCreate) -> PMRecord:
    user = require_write_access(request)
    if not item.tech_name:
        item = item.model_copy(update={'tech_name': user['display_name']})
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

    await record_audit(
        request,
        'created',
        'pm_record',
        row_id,
        f'Created PM-{row_id} for cart #{item.cart_id}',
        {'template_name': item.template_name, 'status': item.status},
    )

    return PMRecord(**{
        'id': row_id,
        **item.dict(),
    })


@app.put('/api/pm/records/{record_id}')
async def update_pm_record(request: Request, record_id: str, update: dict) -> dict:
    require_write_access(request)
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
    summary = f'Updated PM-{record_id}'
    if 'status' in update:
        summary = f'Updated PM-{record_id}: status → {str(update["status"]).replace("_", " ")}'
    await record_audit(request, 'updated', 'pm_record', record_id, summary, update)
    return {'id': record_id, **update}


@app.delete('/api/workorders/{workorder_id}')
async def delete_work_order(request: Request, workorder_id: int) -> dict:
    require_write_access(request)
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute('SELECT id FROM work_orders WHERE id = ?', (workorder_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail='Work order not found')
        await connection.execute('DELETE FROM work_orders WHERE id = ?', (workorder_id,))
        await connection.commit()
    await record_audit(request, 'deleted', 'work_order', workorder_id, f'Deleted WO-{workorder_id}')
    return {'deleted': workorder_id}


@app.delete('/api/pm/records/{record_id}')
async def delete_pm_record(request: Request, record_id: int) -> dict:
    require_write_access(request)
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute('SELECT id FROM pm_records WHERE id = ?', (record_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail='PM record not found')
        await connection.execute('DELETE FROM pm_records WHERE id = ?', (record_id,))
        await connection.commit()
    await record_audit(request, 'deleted', 'pm_record', record_id, f'Deleted PM-{record_id}')
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
async def create_accident(request: Request, item: AccidentReportCreate) -> AccidentReport:
    user = require_write_access(request)
    if not item.reported_by:
        item = item.model_copy(update={'reported_by': user['display_name']})
    created_date = datetime.utcnow().isoformat()
    cart_serial = await lookup_cart_serial(item.cart_id)
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

    await record_audit(
        request,
        'created',
        'accident',
        row_id,
        f'Reported ACC-{row_id} for cart #{item.cart_id}',
        {'severity': item.severity, 'status': item.status},
    )
    await broadcast_accident_push(row_id, item.cart_id, item.reported_by or user['display_name'])

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
async def update_accident(request: Request, accident_id: int, item: AccidentReportUpdate) -> AccidentReport:
    require_write_access(request)
    existing = await get_accident_row(accident_id)
    updated = {**existing}
    payload = item.model_dump(exclude_unset=True)

    if 'cart_id' in payload:
        updated['cart_id'] = payload['cart_id']
        updated['cart_serial'] = await lookup_cart_serial(payload['cart_id']) or updated.get('cart_serial', '')
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
    summary = summarize_accident_update(existing, payload)
    await record_audit(request, 'updated', 'accident', accident_id, summary, payload)
    return AccidentReport(**updated)


@app.post('/api/accidents/{accident_id}/photos')
async def upload_accident_photo(request: Request, accident_id: int, file: UploadFile = File(...)) -> dict:
    require_write_access(request)
    row = await get_accident_row(accident_id)
    if not is_allowed_image_upload(file):
        raise HTTPException(status_code=400, detail='Only image files are allowed')

    ext = Path(file.filename or 'photo.jpg').suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
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

    await record_audit(
        request,
        'photo_added',
        'accident',
        accident_id,
        f'Added damage photo to ACC-{accident_id}',
        {'path': rel_path},
    )
    return {'path': rel_path, 'photos': photos}


@app.delete('/api/accidents/{accident_id}/photos')
async def delete_accident_photo(request: Request, accident_id: int, path: str = Query(...)) -> dict:
    require_write_access(request)
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

    await record_audit(
        request,
        'photo_removed',
        'accident',
        accident_id,
        f'Removed damage photo from ACC-{accident_id}',
        {'path': path},
    )
    return {'photos': photos}


@app.delete('/api/accidents/{accident_id}')
async def delete_accident(request: Request, accident_id: int) -> dict:
    require_write_access(request)
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

    await record_audit(request, 'deleted', 'accident', accident_id, f'Deleted ACC-{accident_id}')
    return {'deleted': accident_id}


@app.get('/api/audit', response_model=List[AuditEntry])
async def list_audit_entries(
    request: Request,
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    days: Optional[int] = Query(None, ge=1, le=365),
    limit: int = Query(25, ge=1, le=200),
) -> List[dict[str, Any]]:
    require_authenticated_user(request)
    query = 'SELECT * FROM audit_log'
    conditions: list[str] = []
    params: list[Any] = []
    if entity_type:
        conditions.append('entity_type = ?')
        params.append(entity_type)
    if entity_id is not None:
        conditions.append('entity_id = ?')
        params.append(str(entity_id))
    if action:
        conditions.append('action = ?')
        params.append(action)
    if username:
        conditions.append('username = ?')
        params.append(username)
    if days is not None:
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        conditions.append('created_at >= ?')
        params.append(since)
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    query += ' ORDER BY id DESC LIMIT ?'
    params.append(limit)

    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(query, params)
        rows = await cursor.fetchall()

    entries: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        details_raw = data.get('details')
        data['details'] = json.loads(details_raw) if details_raw else None
        entries.append(data)
    return entries


@app.get('/api/push/vapid-public-key')
async def get_vapid_public_key() -> dict[str, str]:
    return {'public_key': VAPID_PUBLIC_KEY}


@app.get('/api/push/status')
async def get_push_status(request: Request) -> dict[str, Any]:
    user = require_authenticated_user(request)
    count = await count_push_subscriptions_for_user(user['id'])
    return {
        'subscribed': count > 0,
        'subscription_count': count,
        'push_supported': True,
    }


@app.post('/api/push/subscribe')
async def subscribe_push(request: Request, item: PushSubscriptionCreate) -> dict[str, Any]:
    user = require_authenticated_user(request)
    p256dh = item.keys.get('p256dh', '').strip()
    auth_key = item.keys.get('auth', '').strip()
    if not item.endpoint or not p256dh or not auth_key:
        raise HTTPException(status_code=400, detail='Invalid push subscription payload')

    user_agent = request.headers.get('user-agent', '')
    await upsert_push_subscription(user['id'], item.endpoint, p256dh, auth_key, user_agent)
    return {'subscribed': True}


@app.delete('/api/push/subscribe')
async def unsubscribe_push(request: Request, item: PushUnsubscribeRequest) -> dict[str, Any]:
    user = require_authenticated_user(request)
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            'DELETE FROM push_subscriptions WHERE endpoint = ? AND user_id = ?',
            (item.endpoint, user['id']),
        )
        await connection.commit()
    return {'subscribed': False}


@app.post('/api/push/test')
async def send_test_push(request: Request) -> dict[str, Any]:
    user = require_authenticated_user(request)
    sent = await send_push_to_user(user['id'], {
        'title': 'MaintainSMIP Test Alert',
        'body': 'Push notifications are working on this device.',
        'url': '/index.html',
        'tag': 'push-test',
    })
    if sent == 0:
        raise HTTPException(status_code=400, detail='No active push subscription found for your account')
    return {'sent': sent}


@app.get('/api/notifications/preferences')
async def get_notification_preferences(request: Request) -> dict[str, bool]:
    user = require_authenticated_user(request)
    return await fetch_notification_prefs(user['id'])


@app.put('/api/notifications/preferences')
async def update_notification_preferences(
    request: Request,
    item: NotificationPrefsUpdate,
) -> dict[str, bool]:
    user = require_authenticated_user(request)
    return await save_notification_prefs(user['id'], item.model_dump())


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
    username: Optional[str] = ''
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserPublic(BaseModel):
    id: int
    username: str
    display_name: str
    role: str


class UserCreate(BaseModel):
    username: str
    display_name: str
    role: str = 'technician'
    password: str


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None


@app.get('/api/health')
def health() -> dict[str, Any]:
    return {
        'status': 'ok',
        'data_dir': str(DATA_DIR),
        'db_path': str(DB_PATH),
        'db_exists': DB_PATH.exists(),
        'uploads_dir': str(UPLOADS_DIR),
        'persistent_storage': DATA_DIR.resolve() != ROOT_DIR.resolve(),
    }


@app.post('/api/auth/login')
async def login(body: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    if not APP_PASSWORD:
        return {'ok': True, 'user': None}

    username = (body.username or '').strip().lower()
    password = body.password
    user: Optional[dict[str, Any]] = None

    if username:
        user = await authenticate_user(username, password)
        if not user:
            user = await resync_seeded_user_password(username, password)
        if not user and username == MASTER_USERNAME and hmac.compare_digest(password, APP_PASSWORD):
            user = await upsert_master_admin(APP_PASSWORD)
    elif hmac.compare_digest(password, APP_PASSWORD):
        user = await upsert_master_admin(APP_PASSWORD)
        user = await fetch_user_by_username(MASTER_USERNAME)

    if not user:
        raise HTTPException(status_code=401, detail='Incorrect username or password')

    token = create_session_token(user['id'])
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite='lax',
        max_age=SESSION_MAX_AGE,
        secure=request.url.scheme == 'https',
    )
    return {'ok': True, 'user': user_public(user)}


@app.get('/api/auth/me', response_model=UserPublic)
async def auth_me(request: Request) -> dict[str, Any]:
    user = require_authenticated_user(request)
    return user_public(user)


@app.post('/api/auth/change-password')
async def change_password(request: Request, body: ChangePasswordRequest) -> dict[str, bool]:
    user = require_authenticated_user(request)
    record = await fetch_user_auth_record(user['id'])
    if not record or not record.get('active'):
        raise HTTPException(status_code=401, detail='Authentication required')

    if not verify_password(body.current_password, record['password_hash']):
        raise HTTPException(status_code=400, detail='Current password is incorrect')

    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail='New password must be at least 8 characters')

    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail='New password must be different from your current password')

    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            'UPDATE users SET password_hash = ?, password_changed = 1 WHERE id = ?',
            (hash_password(body.new_password), user['id']),
        )
        await connection.commit()

    return {'ok': True}


@app.post('/api/auth/logout')
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(SESSION_COOKIE)
    return {'ok': True}


def create_database_backup_file() -> tuple[Path, str]:
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail='Database file not found')

    timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    filename = f'maintainsmip-backup-{timestamp}.db'
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    tmp_path = Path(tmp.name)
    tmp.close()

    src = sqlite3.connect(str(DB_PATH))
    try:
        dest = sqlite3.connect(str(tmp_path))
        try:
            src.backup(dest)
            dest.commit()
        finally:
            dest.close()
    finally:
        src.close()

    return tmp_path, filename


def remove_backup_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


@app.get('/api/admin/backup/info')
async def database_backup_info(request: Request) -> dict[str, Any]:
    require_admin(request)
    if not DB_PATH.exists():
        return {
            'exists': False,
            'size_bytes': 0,
            'updated_at': None,
            'path': str(DB_PATH),
            'automated_backup_supported': bool(BACKUP_TOKEN),
        }

    stat = DB_PATH.stat()
    return {
        'exists': True,
        'size_bytes': stat.st_size,
        'updated_at': datetime.utcfromtimestamp(stat.st_mtime).isoformat() + 'Z',
        'path': str(DB_PATH),
        'automated_backup_supported': bool(BACKUP_TOKEN),
    }


@app.get('/api/admin/backup')
async def download_database_backup(request: Request) -> FileResponse:
    admin = require_admin(request)
    tmp_path, filename = create_database_backup_file()
    await record_audit(
        request,
        'exported',
        'database',
        'maintainsmip',
        f'Database backup downloaded by {admin["username"]}',
        {'filename': filename},
    )
    return FileResponse(
        path=tmp_path,
        filename=filename,
        media_type='application/x-sqlite3',
        background=BackgroundTask(remove_backup_file, tmp_path),
    )


@app.get('/api/users', response_model=List[UserPublic])
async def list_users(request: Request) -> List[dict[str, Any]]:
    require_admin(request)
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT id, username, display_name, role, active FROM users ORDER BY display_name',
        )
        rows = await cursor.fetchall()
    return [user_public(dict(row)) for row in rows if row['active']]


@app.post('/api/users', response_model=UserPublic)
async def create_user(request: Request, body: UserCreate) -> dict[str, Any]:
    require_admin(request)
    username = body.username.strip().lower()
    if not username:
        raise HTTPException(status_code=400, detail='Username is required')
    if body.role not in USER_ROLES:
        raise HTTPException(status_code=400, detail='Invalid role')
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail='Password must be at least 8 characters')

    existing = await fetch_user_by_username(username)
    if existing:
        raise HTTPException(status_code=409, detail='Username already exists')

    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            '''
            INSERT INTO users (username, display_name, role, password_hash, active, created_date)
            VALUES (?, ?, ?, ?, 1, ?)
            ''',
            (username, body.display_name.strip(), body.role, hash_password(body.password), now),
        )
        user_id = cursor.lastrowid
        await connection.commit()
        cursor = await connection.execute(
            'SELECT id, username, display_name, role, active FROM users WHERE id = ?',
            (user_id,),
        )
        row = await cursor.fetchone()
    return user_public(dict(row))


@app.put('/api/users/{user_id}', response_model=UserPublic)
async def update_user(request: Request, user_id: int, body: UserUpdate) -> dict[str, Any]:
    require_admin(request)
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='User not found')
        current = dict(row)

        if body.role is not None and body.role not in USER_ROLES:
            raise HTTPException(status_code=400, detail='Invalid role')

        next_active = current['active'] if body.active is None else int(body.active)
        next_role = body.role or current['role']
        if current['role'] == 'admin' and (next_active == 0 or next_role != 'admin'):
            cursor = await connection.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1 AND id != ?",
                (user_id,),
            )
            remaining_admins = (await cursor.fetchone())[0]
            if remaining_admins == 0:
                raise HTTPException(status_code=400, detail='Cannot remove the last active admin')

        fields: list[str] = []
        values: list[Any] = []
        if body.display_name is not None:
            fields.append('display_name = ?')
            values.append(body.display_name.strip())
        if body.role is not None:
            fields.append('role = ?')
            values.append(body.role)
        if body.active is not None:
            fields.append('active = ?')
            values.append(int(body.active))
        password_reset = False
        if body.password:
            if not body.password.strip():
                raise HTTPException(status_code=400, detail='Password cannot be empty')
            fields.append('password_hash = ?')
            values.append(hash_password(body.password))
            fields.append('password_changed = ?')
            values.append(1)
            password_reset = True

        if fields:
            values.append(user_id)
            await connection.execute(
                f"UPDATE users SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            await connection.commit()

        cursor = await connection.execute(
            'SELECT id, username, display_name, role, active FROM users WHERE id = ?',
            (user_id,),
        )
        updated = await cursor.fetchone()

    if password_reset:
        await record_audit(
            request,
            'updated',
            'user',
            user_id,
            f'Reset password for {current["username"]}',
        )
    elif fields:
        changes: dict[str, Any] = {}
        if body.display_name is not None and body.display_name.strip() != current['display_name']:
            changes['display_name'] = body.display_name.strip()
        if body.role is not None and body.role != current['role']:
            changes['role'] = body.role
        if body.active is not None and int(body.active) != current['active']:
            changes['active'] = bool(body.active)
        if changes:
            await record_audit(
                request,
                'updated',
                'user',
                user_id,
                f'Updated user {current["username"]}',
                changes,
            )

    return user_public(dict(updated))


@app.delete('/api/users/{user_id}')
async def delete_user(request: Request, user_id: int) -> dict[str, bool]:
    admin = require_admin(request)
    if admin['id'] == user_id:
        raise HTTPException(status_code=400, detail='You cannot delete your own account')

    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='User not found')
        current = dict(row)

        if not current['active']:
            return {'ok': True}

        if current['role'] == 'admin':
            cursor = await connection.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1 AND id != ?",
                (user_id,),
            )
            remaining_admins = (await cursor.fetchone())[0]
            if remaining_admins == 0:
                raise HTTPException(status_code=400, detail='Cannot remove the last active admin')

        await connection.execute('UPDATE users SET active = 0 WHERE id = ?', (user_id,))
        await connection.commit()

    await record_audit(
        request,
        'deleted',
        'user',
        user_id,
        f'Deactivated account {current["username"]}',
    )
    return {'ok': True}


@app.get('/')
def root() -> FileResponse:
    index_html = ROOT_DIR / 'index.html'
    if not index_html.exists():
        raise HTTPException(status_code=404, detail='Index page not found')
    return FileResponse(index_html)


@app.get('/{path:path}')
def serve_file(path: str) -> FileResponse:
    target = resolve_static_file(path)
    if target:
        return FileResponse(target)
    raise HTTPException(status_code=404, detail='File not found')


if __name__ == '__main__':
    import uvicorn

    uvicorn.run('server:app', host='127.0.0.1', port=8000, reload=True)
