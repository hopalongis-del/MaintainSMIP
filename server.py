from __future__ import annotations
import asyncio
import base64
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shutil
import smtplib
import sqlite3
import tempfile
import time
from email.message import EmailMessage
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional
from urllib.parse import quote, urlencode
from urllib.request import Request as UrlRequest, urlopen

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
SEED_DEMO_DATA = os.environ.get('SEED_DEMO_DATA', 'false').strip().lower() in ('1', 'true', 'yes')
SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com').strip()
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USER = os.environ.get('SMTP_USER', '').strip()
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '').strip()
SMTP_FROM = os.environ.get('SMTP_FROM', SMTP_USER).strip()
NOTIFY_EMAIL_RECIPIENTS = [
    item.strip()
    for item in os.environ.get('NOTIFY_EMAIL_RECIPIENTS', '').split(',')
    if item.strip()
]
CART_EXTENDED_FIELDS = (
    'barcode',
    'vin',
    'meter_hours',
    'purchase_date',
    'warranty_expires',
    'acquisition_cost',
    'home_location',
)
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
    '/logo.svg',
    '/logo1.png',
    '/service-worker.js',
}
STATIC_PUBLIC_SUFFIXES = (
    '.js',
    '.css',
    '.png',
    '.jpg',
    '.jpeg',
    '.gif',
    '.webp',
    '.ico',
    '.svg',
    '.woff',
    '.woff2',
    '.json',
)


def is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return path.endswith(STATIC_PUBLIC_SUFFIXES)

VAPID_EMAIL = os.environ.get('VAPID_EMAIL', 'mailto:admin@localhost')
VAPID_KEYS_PATH = DATA_DIR / 'vapid_keys.json'
NOTIFICATION_CHECK_INTERVAL_SEC = int(os.environ.get('NOTIFICATION_CHECK_INTERVAL_SEC', '1800'))

# Product-owner account (simple username — not first.last).
OWNER_USERNAME = 'mike'
OWNER_DISPLAY_NAME = 'Mike'
OWNER_PASSWORD = 'mike'

# Seeded team accounts: (username, display_name, role, initial_password|None)
# None password → APP_PASSWORD + password_changed=0 (must set personal password).
# Explicit password → hashed as given + password_changed=1 (no forced change).
TECHNICIAN_ACCOUNTS = [
    (OWNER_USERNAME, OWNER_DISPLAY_NAME, 'admin', OWNER_PASSWORD),
]

PRIVILEGED_ROLE_OVERRIDES = {
    OWNER_USERNAME: 'admin',
}

LEGACY_OWNER_USERNAMES = ('mike.casady',)

# One-time purge of former-customer demo data (fleet, WO/PM/accidents, team logins).
FORMER_CUSTOMER_PURGE_KEY = 'former_customer_purge_v1'
OPERATIONAL_TABLES_TO_PURGE = (
    'work_orders',
    'pm_records',
    'accident_reports',
    'carts',
    'audit_log',
    'push_subscriptions',
    'notification_dedup',
    'pm_automation_rules',
    'vendors',
    'parts',
    'purchase_orders',
    'lease_units',
    'leases',
    'sales',
)

SEEDED_USERNAMES = {MASTER_USERNAME, *(account[0] for account in TECHNICIAN_ACCOUNTS)}


def account_seed_password(account: tuple) -> tuple[str, int]:
    """Return (password, password_changed_flag) for a TECHNICIAN_ACCOUNTS row."""
    if len(account) >= 4 and account[3]:
        return str(account[3]), 1
    return (APP_PASSWORD or 'WeLoveRacing!'), 0


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
        'password_changed': bool(row.get('password_changed')),
    }


async def fetch_user_by_id(user_id: int) -> Optional[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT id, username, display_name, role, active, password_changed FROM users WHERE id = ?',
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
            for account in TECHNICIAN_ACCOUNTS:
                username, display_name, role = account[0], account[1], account[2]
                password, changed = account_seed_password(account)
                await connection.execute(
                    '''
                    INSERT INTO users (username, display_name, role, password_hash, active, password_changed, created_date)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    ''',
                    (username, display_name, role, hash_password(password), changed, now),
                )
            await connection.commit()
        return

    if active_admins == 0:
        master_password = APP_PASSWORD or 'WeLoveRacing!'
        await upsert_master_admin(master_password)

    await apply_privileged_role_overrides()


async def apply_privileged_role_overrides() -> None:
    """Keep product-owner accounts at the configured privilege level."""
    async with aiosqlite.connect(DB_PATH) as connection:
        for username, role in PRIVILEGED_ROLE_OVERRIDES.items():
            await connection.execute(
                'UPDATE users SET role = ? WHERE username = ?',
                (role, username),
            )
        await connection.commit()


async def ensure_seeded_team_accounts() -> None:
    """Insert any missing TECHNICIAN_ACCOUNTS rows (used after purge / upgrades)."""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        for account in TECHNICIAN_ACCOUNTS:
            username, display_name, role = account[0], account[1], account[2]
            password, changed = account_seed_password(account)
            cursor = await connection.execute(
                'SELECT id FROM users WHERE username = ?',
                (username,),
            )
            if await cursor.fetchone():
                continue
            await connection.execute(
                '''
                INSERT INTO users (username, display_name, role, password_hash, active, password_changed, created_date)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                ''',
                (username, display_name, role, hash_password(password), changed, now),
            )
        await connection.commit()


async def ensure_owner_account() -> None:
    """Rename legacy first.last owner logins and pin username/password to mike / mike."""
    password_hash = hash_password(OWNER_PASSWORD)
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            'SELECT id FROM users WHERE username = ?',
            (OWNER_USERNAME,),
        )
        owner_exists = await cursor.fetchone()

        for legacy in LEGACY_OWNER_USERNAMES:
            if owner_exists:
                # Prefer the simple username; drop leftover first.last account.
                await connection.execute(
                    'DELETE FROM users WHERE username = ?',
                    (legacy,),
                )
            else:
                await connection.execute(
                    '''
                    UPDATE users
                    SET username = ?, display_name = ?, role = 'admin', active = 1
                    WHERE username = ?
                    ''',
                    (OWNER_USERNAME, OWNER_DISPLAY_NAME, legacy),
                )

        cursor = await connection.execute(
            'SELECT id FROM users WHERE username = ?',
            (OWNER_USERNAME,),
        )
        existing = await cursor.fetchone()
        if existing:
            await connection.execute(
                '''
                UPDATE users
                SET display_name = ?, role = 'admin', password_hash = ?,
                    password_changed = 1, active = 1
                WHERE username = ?
                ''',
                (OWNER_DISPLAY_NAME, password_hash, OWNER_USERNAME),
            )
        else:
            await connection.execute(
                '''
                INSERT INTO users (username, display_name, role, password_hash, active, password_changed, created_date)
                VALUES (?, ?, 'admin', ?, 1, 1, ?)
                ''',
                (OWNER_USERNAME, OWNER_DISPLAY_NAME, password_hash, now),
            )
        await connection.commit()


async def purge_former_customer_data_once() -> None:
    """Wipe SMI Properties demo/customer data once after the deal fell through.

    Keeps schema, PM/WO templates, master admin, and product-owner seed accounts.
    Safe to re-run: gated by app_meta key.
    """
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            'CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
        )
        cursor = await connection.execute(
            'SELECT value FROM app_meta WHERE key = ?',
            (FORMER_CUSTOMER_PURGE_KEY,),
        )
        if await cursor.fetchone():
            return

        for table in OPERATIONAL_TABLES_TO_PURGE:
            try:
                await connection.execute(f'DELETE FROM {table}')
            except Exception:
                pass

        keep_usernames = {MASTER_USERNAME, *(account[0] for account in TECHNICIAN_ACCOUNTS)}
        placeholders = ','.join('?' for _ in keep_usernames)
        await connection.execute(
            f'DELETE FROM users WHERE username NOT IN ({placeholders})',
            tuple(keep_usernames),
        )

        await connection.execute(
            'INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)',
            (FORMER_CUSTOMER_PURGE_KEY, datetime.utcnow().isoformat()),
        )
        await connection.commit()

    # Drop uploaded accident photos from the former customer demo.
    for uploads_root in (DATA_DIR / 'uploads' / 'accidents', ROOT_DIR / 'uploads' / 'accidents'):
        if uploads_root.exists():
            shutil.rmtree(uploads_root, ignore_errors=True)
        uploads_root.mkdir(parents=True, exist_ok=True)


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
        if is_public_path(path):
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
    await purge_former_customer_data_once()
    await seed_carts_from_file()
    app.state.carts = await fetch_all_carts()
    await seed_pm_templates()
    await seed_wo_templates()
    await ensure_wo_templates_seeded()
    await ensure_users_seeded()
    await ensure_seeded_team_accounts()
    await ensure_owner_account()
    if SEED_DEMO_DATA:
        await seed_demo_data()
    notification_task = asyncio.create_task(notification_loop())
    yield
    notification_task.cancel()
    try:
        await notification_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title='Fleet Maintain API', version='1.0', lifespan=lifespan)
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
    barcode: Optional[str] = None
    vin: Optional[str] = None
    meter_hours: Optional[float] = None
    purchase_date: Optional[str] = None
    warranty_expires: Optional[str] = None
    acquisition_cost: Optional[float] = None
    home_location: Optional[str] = None


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
    barcode: Optional[str] = None
    vin: Optional[str] = None
    meter_hours: Optional[float] = None
    purchase_date: Optional[str] = None
    warranty_expires: Optional[str] = None
    acquisition_cost: Optional[float] = None
    home_location: Optional[str] = None


class CartUpdate(BaseModel):
    serial: Optional[str] = None
    model: Optional[str] = None
    year: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    barcode: Optional[str] = None
    vin: Optional[str] = None
    meter_hours: Optional[float] = None
    purchase_date: Optional[str] = None
    warranty_expires: Optional[str] = None
    acquisition_cost: Optional[float] = None
    home_location: Optional[str] = None

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
    labor_rate: float = 75.0
    part_cost: float = 0.0
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
    labor_rate: Optional[float] = None
    part_cost: Optional[float] = None
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


class VendorBase(BaseModel):
    name: str
    contact_name: Optional[str] = ''
    email: Optional[str] = ''
    phone: Optional[str] = ''
    account_number: Optional[str] = ''
    default_terms: Optional[str] = ''
    avid_vendor_id: Optional[str] = ''
    active: bool = True
    notes: Optional[str] = ''


class VendorCreate(VendorBase):
    pass


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    account_number: Optional[str] = None
    default_terms: Optional[str] = None
    avid_vendor_id: Optional[str] = None
    active: Optional[bool] = None
    notes: Optional[str] = None


class Vendor(VendorBase):
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PartBase(BaseModel):
    part_number: Optional[str] = ''
    description: str
    category: Optional[str] = ''
    vendor_id: Optional[int] = None
    vendor_part_number: Optional[str] = ''
    unit_of_measure: str = 'each'
    unit_cost: float = 0
    unit_price: float = 0
    on_hand: float = 0
    reorder_point: float = 0
    reorder_qty: float = 0
    location: Optional[str] = ''
    active: bool = True
    notes: Optional[str] = ''


class PartCreate(PartBase):
    pass


class PartUpdate(BaseModel):
    part_number: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    vendor_id: Optional[int] = None
    vendor_part_number: Optional[str] = None
    unit_of_measure: Optional[str] = None
    unit_cost: Optional[float] = None
    unit_price: Optional[float] = None
    on_hand: Optional[float] = None
    reorder_point: Optional[float] = None
    reorder_qty: Optional[float] = None
    location: Optional[str] = None
    active: Optional[bool] = None
    notes: Optional[str] = None


class Part(PartBase):
    id: int
    vendor_name: Optional[str] = None
    needs_reorder: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PartStockAdjust(BaseModel):
    delta: float
    note: Optional[str] = ''


class PurchaseOrderLine(BaseModel):
    part_id: Optional[int] = None
    part_number: Optional[str] = ''
    description: str = ''
    qty: float = 1
    unit_cost: float = 0


class PurchaseOrderBase(BaseModel):
    vendor_id: Optional[int] = None
    status: str = 'draft'
    lines: List[PurchaseOrderLine] = Field(default_factory=list)
    notes: Optional[str] = ''


class PurchaseOrderCreate(PurchaseOrderBase):
    pass


class PurchaseOrderUpdate(BaseModel):
    vendor_id: Optional[int] = None
    status: Optional[str] = None
    lines: Optional[List[PurchaseOrderLine]] = None
    notes: Optional[str] = None
    approved_by: Optional[str] = None


class PurchaseOrder(PurchaseOrderBase):
    id: int
    po_number: Optional[str] = None
    subtotal: float = 0
    total: float = 0
    requested_by: Optional[str] = None
    approved_by: Optional[str] = None
    avid_po_id: Optional[str] = None
    avid_status: Optional[str] = None
    idempotency_key: Optional[str] = None
    vendor_name: Optional[str] = None
    created_at: Optional[str] = None
    approved_at: Optional[str] = None
    submitted_at: Optional[str] = None
    last_synced_at: Optional[str] = None


LEASE_UNIT_STATUSES = ('available', 'leased', 'maintenance', 'retired')
LEASE_STATUSES = ('active', 'returned', 'cancelled')
SALE_STATUSES = ('completed', 'void')


class LeaseUnitBase(BaseModel):
    unit_code: str
    serial: Optional[str] = ''
    model: Optional[str] = ''
    year: Optional[str] = ''
    condition: str = 'good'
    status: str = 'available'
    venue: Optional[str] = ''
    daily_rate: float = 0
    fleet_cart_id: Optional[str] = None
    notes: Optional[str] = ''


class LeaseUnitCreate(LeaseUnitBase):
    pass


class LeaseUnitUpdate(BaseModel):
    unit_code: Optional[str] = None
    serial: Optional[str] = None
    model: Optional[str] = None
    year: Optional[str] = None
    condition: Optional[str] = None
    status: Optional[str] = None
    venue: Optional[str] = None
    daily_rate: Optional[float] = None
    fleet_cart_id: Optional[str] = None
    notes: Optional[str] = None


class LeaseUnit(LeaseUnitBase):
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class LeaseBase(BaseModel):
    unit_id: int
    customer_name: str
    customer_phone: Optional[str] = ''
    customer_email: Optional[str] = ''
    start_date: str
    expected_return: Optional[str] = ''
    daily_rate: float = 0
    deposit: float = 0
    notes: Optional[str] = ''


class LeaseCreate(LeaseBase):
    pass


class LeaseUpdate(BaseModel):
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    start_date: Optional[str] = None
    expected_return: Optional[str] = None
    actual_return: Optional[str] = None
    daily_rate: Optional[float] = None
    deposit: Optional[float] = None
    total_charged: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class LeaseReturn(BaseModel):
    actual_return: Optional[str] = None
    total_charged: Optional[float] = None
    condition: Optional[str] = None
    notes: Optional[str] = ''


class Lease(LeaseBase):
    id: int
    lease_number: Optional[str] = None
    actual_return: Optional[str] = None
    total_charged: float = 0
    status: str = 'active'
    unit_code: Optional[str] = None
    unit_model: Optional[str] = None
    unit_serial: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SaleLine(BaseModel):
    part_id: Optional[int] = None
    part_number: Optional[str] = ''
    description: str = ''
    qty: float = 1
    unit_price: float = 0


class SaleCreate(BaseModel):
    customer_name: Optional[str] = ''
    customer_phone: Optional[str] = ''
    lines: List[SaleLine] = Field(default_factory=list)
    notes: Optional[str] = ''
    payment_method: Optional[str] = 'cash'


class Sale(BaseModel):
    id: int
    sale_number: Optional[str] = None
    customer_name: Optional[str] = ''
    customer_phone: Optional[str] = ''
    status: str = 'completed'
    lines: List[SaleLine] = Field(default_factory=list)
    subtotal: float = 0
    total: float = 0
    payment_method: Optional[str] = 'cash'
    notes: Optional[str] = ''
    sold_by: Optional[str] = None
    created_at: Optional[str] = None
    voided_at: Optional[str] = None


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
    meter_hours = data.get('meter_hours')
    acquisition_cost = data.get('acquisition_cost')
    return CartItem(
        id=raw_id,
        serial=data.get('serial'),
        model=data.get('model'),
        year=data.get('year'),
        location=data.get('location'),
        status=data.get('status'),
        notes=data.get('notes'),
        barcode=data.get('barcode'),
        vin=data.get('vin'),
        meter_hours=float(meter_hours) if meter_hours not in (None, '') else None,
        purchase_date=data.get('purchase_date'),
        warranty_expires=data.get('warranty_expires'),
        acquisition_cost=float(acquisition_cost) if acquisition_cost not in (None, '') else None,
        home_location=data.get('home_location'),
    )


async def fetch_all_carts() -> List[CartItem]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            '''
            SELECT id, serial, model, year, location, status, notes,
                   barcode, vin, meter_hours, purchase_date, warranty_expires,
                   acquisition_cost, home_location
            FROM carts ORDER BY id
            '''
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


def normalize_cart_optional_fields(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    for field in CART_EXTENDED_FIELDS:
        if field not in normalized:
            continue
        value = normalized[field]
        if value in (None, ''):
            normalized[field] = None
        elif field in ('meter_hours', 'acquisition_cost'):
            try:
                normalized[field] = float(value)
            except (TypeError, ValueError):
                normalized[field] = None
        else:
            normalized[field] = str(value).strip() or None
    return normalized


def cart_values_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    base = {
        'serial': str(payload.get('serial', '')).strip(),
        'model': str(payload.get('model', '')).strip(),
        'year': str(payload.get('year', '')).strip(),
        'location': str(payload.get('location', '')).strip(),
        'status': str(payload.get('status', 'active')).strip(),
        'notes': str(payload.get('notes', '')).strip(),
    }
    extras = normalize_cart_optional_fields(payload)
    for field in CART_EXTENDED_FIELDS:
        base[field] = extras.get(field)
    return base


def smtp_configured() -> bool:
    return bool(SMTP_USER and SMTP_PASSWORD and SMTP_FROM and NOTIFY_EMAIL_RECIPIENTS)


def send_email_sync(subject: str, body: str, recipients: list[str]) -> None:
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = SMTP_FROM
    message['To'] = ', '.join(recipients)
    message.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(message)


async def send_management_digest_email(counts: dict[str, int]) -> None:
    if not smtp_configured():
        return
    lines = [
        'MaintainSMIP daily operations digest',
        '',
        f"Open work orders: {counts['open_wo']}",
        f"Overdue work orders: {counts['overdue_wo']}",
        f"PM due soon: {counts['pm_due']}",
        f"PM overdue: {counts['pm_overdue']}",
        f"Open accident reports: {counts['open_accidents']}",
        '',
        f"Dashboard: https://maintainsmip.onrender.com",
    ]
    body = '\n'.join(lines)
    subject = f"MaintainSMIP digest — {counts['overdue_wo']} overdue WO, {counts['pm_overdue']} overdue PM"
    try:
        await asyncio.to_thread(
            send_email_sync,
            subject,
            body,
            NOTIFY_EMAIL_RECIPIENTS,
        )
    except Exception:
        pass


class PmAutomationRuleCreate(BaseModel):
    name: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    enabled: bool = True
    scope_type: str = 'all'
    scope_values: List[str] = Field(default_factory=list)
    lead_days: int = Field(default=14, ge=1, le=365)


class PmAutomationRuleUpdate(BaseModel):
    name: Optional[str] = None
    template_id: Optional[str] = None
    enabled: Optional[bool] = None
    scope_type: Optional[str] = None
    scope_values: Optional[List[str]] = None
    lead_days: Optional[int] = Field(default=None, ge=1, le=365)


def parse_pm_rule_row(row: Any) -> dict[str, Any]:
    data = dict(row)
    return {
        'id': data['id'],
        'name': data['name'],
        'template_id': data['template_id'],
        'enabled': bool(data['enabled']),
        'scope_type': data['scope_type'],
        'scope_values': json.loads(data.get('scope_values') or '[]'),
        'lead_days': data['lead_days'],
        'last_run_at': data.get('last_run_at'),
        'created_at': data.get('created_at'),
        'updated_at': data.get('updated_at'),
    }


def cart_matches_pm_scope(cart: CartItem, scope_type: str, scope_values: list[str]) -> bool:
    if scope_type == 'all' or not scope_type:
        return True
    if scope_type == 'location':
        return cart.location in scope_values
    if scope_type == 'model':
        return cart.model in scope_values
    return False


async def fetch_pm_template(template_id: str) -> Optional[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT * FROM pm_templates WHERE id = ? AND active = 1',
            (template_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def has_open_pm_for_cart_template(cart_id: Any, template_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            '''
            SELECT COUNT(*) FROM pm_records
            WHERE cart_id = ? AND template_id = ?
              AND status IN ('scheduled', 'in_progress', 'overdue')
            ''',
            (cart_id, template_id),
        )
        return (await cursor.fetchone())[0] > 0


async def latest_pm_record_for_cart_template(cart_id: Any, template_id: str) -> Optional[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            '''
            SELECT * FROM pm_records
            WHERE cart_id = ? AND template_id = ?
            ORDER BY COALESCE(completed_date, scheduled_date, '') DESC, id DESC
            LIMIT 1
            ''',
            (cart_id, template_id),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


def calculate_next_pm_date(template: dict[str, Any], latest: Optional[dict[str, Any]]) -> datetime:
    interval_days = int(template.get('interval_value') or 90)
    if latest and latest.get('status') == 'completed' and latest.get('completed_date'):
        anchor = datetime.fromisoformat(str(latest['completed_date']).replace('Z', ''))
    elif latest and latest.get('scheduled_date'):
        anchor = datetime.fromisoformat(str(latest['scheduled_date']).replace('Z', ''))
    else:
        anchor = datetime.utcnow()
    return anchor + timedelta(days=interval_days)


async def create_pm_record_from_template(
    template: dict[str, Any],
    cart: CartItem,
    scheduled_date: datetime,
) -> None:
    checklist = json.loads(template.get('checklist') or '[]')
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            '''
            INSERT INTO pm_records (
                template_id, template_name, description, cart_id, location,
                scheduled_date, completed_date, status, checklist_results,
                tech_name, labor_minutes, linked_wo_ids
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                template['id'],
                template['name'],
                template.get('description', ''),
                cart.id,
                cart.location,
                scheduled_date.isoformat(),
                None,
                'scheduled',
                json.dumps([
                    {
                        'task_id': item.get('id'),
                        'task': item.get('task'),
                        'passed': False,
                        'note': '',
                    }
                    for item in checklist
                ]),
                '',
                int(template.get('estimated_labor_minutes') or 0),
                json.dumps([]),
            ),
        )
        await connection.commit()


async def run_pm_automation(trigger: str = 'scheduled') -> dict[str, int]:
    created = 0
    skipped = 0
    now = datetime.utcnow()
    today = now.date()

    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT * FROM pm_automation_rules WHERE enabled = 1 ORDER BY id',
        )
        rules = await cursor.fetchall()

    carts = await fetch_all_carts()
    for rule_row in rules:
        rule = parse_pm_rule_row(rule_row)
        template = await fetch_pm_template(rule['template_id'])
        if not template:
            continue

        for cart in carts:
            if str(cart.status or '').lower() == 'retired':
                skipped += 1
                continue
            if not cart_matches_pm_scope(cart, rule['scope_type'], rule['scope_values']):
                continue
            if await has_open_pm_for_cart_template(cart.id, rule['template_id']):
                skipped += 1
                continue

            latest = await latest_pm_record_for_cart_template(cart.id, rule['template_id'])
            next_due = calculate_next_pm_date(template, latest)
            days_until_due = (next_due.date() - today).days
            if days_until_due > rule['lead_days']:
                skipped += 1
                continue

            await create_pm_record_from_template(template, cart, next_due)
            created += 1

        async with aiosqlite.connect(DB_PATH) as connection:
            await connection.execute(
                'UPDATE pm_automation_rules SET last_run_at = ?, updated_at = ? WHERE id = ?',
                (now.isoformat(), now.isoformat(), rule['id']),
            )
            await connection.commit()

    return {'created': created, 'skipped': skipped, 'trigger': trigger}


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

        cursor = await connection.execute(
            '''
            SELECT COUNT(*) as total FROM work_orders
            WHERE status NOT IN ('completed', 'closed')
            '''
        )
        open_wo = (await cursor.fetchone())['total']

    return {
        'open_wo': open_wo,
        'overdue_wo': overdue_wo,
        'pm_due': pm_due,
        'pm_overdue': pm_overdue,
        'open_accidents': open_accidents,
    }


async def should_send_system_digest(alert_key: str) -> bool:
    today = datetime.utcnow().date().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            'SELECT 1 FROM notification_dedup WHERE user_id = 0 AND alert_key = ? AND sent_date = ?',
            (alert_key, today),
        )
        if await cursor.fetchone():
            return False
        await connection.execute(
            'INSERT INTO notification_dedup (user_id, alert_key, sent_date) VALUES (0, ?, ?)',
            (alert_key, today),
        )
        await connection.commit()
    return True


async def run_scheduled_notifications() -> None:
    if await should_send_system_digest('pm_automation'):
        try:
            await run_pm_automation()
        except Exception:
            pass

    counts = await compute_alert_counts()
    if await should_send_system_digest('email_digest'):
        await send_management_digest_email(counts)

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
            if 'labor_rate' not in wo_columns:
                await connection.execute('ALTER TABLE work_orders ADD COLUMN labor_rate REAL DEFAULT 75.0')
                await connection.commit()
            if 'part_cost' not in wo_columns:
                await connection.execute('ALTER TABLE work_orders ADD COLUMN part_cost REAL DEFAULT 0.0')
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
                maintenance_sheet TEXT,
                labor_rate REAL DEFAULT 75.0,
                part_cost REAL DEFAULT 0.0
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
                notes TEXT,
                barcode TEXT,
                vin TEXT,
                meter_hours REAL,
                purchase_date TEXT,
                warranty_expires TEXT,
                acquisition_cost REAL,
                home_location TEXT
            )
            '''
        )
        cursor = await connection.execute('PRAGMA table_info(carts)')
        cart_columns = {col[1] for col in await cursor.fetchall()}
        cart_migrations = {
            'barcode': 'TEXT',
            'vin': 'TEXT',
            'meter_hours': 'REAL',
            'purchase_date': 'TEXT',
            'warranty_expires': 'TEXT',
            'acquisition_cost': 'REAL',
            'home_location': 'TEXT',
        }
        for column, col_type in cart_migrations.items():
            if column not in cart_columns:
                await connection.execute(f'ALTER TABLE carts ADD COLUMN {column} {col_type}')
        await connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS pm_automation_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                template_id TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                scope_type TEXT NOT NULL DEFAULT 'all',
                scope_values TEXT NOT NULL DEFAULT '[]',
                lead_days INTEGER NOT NULL DEFAULT 14,
                last_run_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            '''
        )
        # --- Parts / procurement module (Phase 1: data model) ---
        # Generic schema so the shop manager can shape the UI later. The
        # avid_* columns are stubs for the AvidXchange adapter (Phase 3) so
        # wiring it in later needs no further migration.
        await connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS vendors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                contact_name TEXT,
                email TEXT,
                phone TEXT,
                account_number TEXT,
                default_terms TEXT,
                avid_vendor_id TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            '''
        )
        await connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_number TEXT,
                description TEXT NOT NULL,
                category TEXT,
                vendor_id INTEGER,
                vendor_part_number TEXT,
                unit_of_measure TEXT NOT NULL DEFAULT 'each',
                unit_cost REAL NOT NULL DEFAULT 0,
                on_hand REAL NOT NULL DEFAULT 0,
                reorder_point REAL NOT NULL DEFAULT 0,
                reorder_qty REAL NOT NULL DEFAULT 0,
                location TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            '''
        )
        await connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                po_number TEXT,
                vendor_id INTEGER,
                status TEXT NOT NULL DEFAULT 'draft',
                lines TEXT NOT NULL DEFAULT '[]',
                subtotal REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL DEFAULT 0,
                notes TEXT,
                requested_by TEXT,
                approved_by TEXT,
                avid_po_id TEXT,
                avid_status TEXT,
                idempotency_key TEXT,
                created_at TEXT,
                approved_at TEXT,
                submitted_at TEXT,
                last_synced_at TEXT
            )
            '''
        )
        # Retail sell price for store module (defaults to 0; UI can copy unit_cost).
        cursor = await connection.execute('PRAGMA table_info(parts)')
        part_cols = {row[1] for row in await cursor.fetchall()}
        if 'unit_price' not in part_cols:
            await connection.execute(
                'ALTER TABLE parts ADD COLUMN unit_price REAL NOT NULL DEFAULT 0',
            )

        await connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS lease_units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_code TEXT NOT NULL UNIQUE,
                serial TEXT,
                model TEXT,
                year TEXT,
                condition TEXT NOT NULL DEFAULT 'good',
                status TEXT NOT NULL DEFAULT 'available',
                venue TEXT,
                daily_rate REAL NOT NULL DEFAULT 0,
                fleet_cart_id TEXT,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            '''
        )
        await connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS leases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lease_number TEXT,
                unit_id INTEGER NOT NULL,
                customer_name TEXT NOT NULL,
                customer_phone TEXT,
                customer_email TEXT,
                start_date TEXT NOT NULL,
                expected_return TEXT,
                actual_return TEXT,
                daily_rate REAL NOT NULL DEFAULT 0,
                deposit REAL NOT NULL DEFAULT 0,
                total_charged REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                notes TEXT,
                created_by TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            '''
        )
        await connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_number TEXT,
                customer_name TEXT,
                customer_phone TEXT,
                status TEXT NOT NULL DEFAULT 'completed',
                lines TEXT NOT NULL DEFAULT '[]',
                subtotal REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL DEFAULT 0,
                payment_method TEXT,
                notes TEXT,
                sold_by TEXT,
                created_at TEXT,
                voided_at TEXT
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


# Generic sample demo rows used only when SEED_DEMO_DATA=true (not customer data).
DEMO_WORK_ORDERS = [
    {
        'cart_id': 1002,
        'title': 'Brake squeal under load',
        'description': 'Operator reports grinding noise when descending hills. Inspect pads and rear drum.',
        'priority': 'high',
        'status': 'in_progress',
        'type': 'repair',
        'assigned_to': 'Mike Casady',
        'location': 'Shop',
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
        'cart_id': 1001,
        'title': 'Battery terminal corrosion',
        'description': 'Green buildup on positive terminal. Clean, test load, verify charger output.',
        'priority': 'medium',
        'status': 'open',
        'type': 'battery',
        'assigned_to': '',
        'location': 'Shop',
        'due_date': _iso_days_from_now(4),
        'labor_minutes': 30,
        'parts_used': [],
        'comments': [],
    },
    {
        'cart_id': 1003,
        'title': 'Steering wander at speed',
        'description': 'Cart drifts right above 12 mph on service roads. Check toe alignment and tire wear.',
        'priority': 'critical',
        'status': 'open',
        'type': 'repair',
        'assigned_to': '',
        'location': 'Yard',
        'due_date': _iso_days_from_now(-3),
        'labor_minutes': 0,
        'parts_used': [],
        'comments': [],
    },
]


DEMO_PM_RECORDS = [
    {
        'template_id': 'PM-TPL-001',
        'template_name': '90-Day Inspection',
        'description': 'Full inspection every 90 days',
        'cart_id': 1001,
        'location': 'Shop',
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
        'cart_id': 1002,
        'location': 'Shop',
        'scheduled_date': _iso_days_from_now(5),
        'status': 'scheduled',
        'checklist_results': [
            {'task_id': 1, 'task': 'Check water levels', 'passed': False, 'note': ''},
            {'task_id': 2, 'task': 'Clean terminals', 'passed': False, 'note': ''},
            {'task_id': 3, 'task': 'Load test', 'passed': False, 'note': ''},
        ],
    },
]


DEMO_ACCIDENTS = [
    {
        'cart_id': 1002,
        'location': 'Shop',
        'reported_by': 'Mike Casady',
        'incident_date': _iso_days_from_now(-1),
        'description': 'Rear corner impact with loading dock post. Cracked body panel and bent rear bumper bracket.',
        'severity': 'moderate',
        'status': 'under_review',
        'damage_areas': ['rear bumper', 'right rear panel', 'tail light'],
        'notes': 'Operator reported during yard move.',
        'created_days_ago': -1,
    },
    {
        'cart_id': 1003,
        'location': 'Yard',
        'reported_by': 'Mike Casady',
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
@app.get('/api/carts/{cart_id}/timeline')
async def get_cart_timeline(cart_id: str) -> List[dict]:
    try:
        cart_numeric = int(cart_id)
    except ValueError:
        cart_numeric = -1

    timeline = []

    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row

        # 1. Work Orders
        cursor = await connection.execute(
            'SELECT * FROM work_orders WHERE cart_id = ? OR cart_id = ?',
            (cart_id, cart_numeric)
        )
        for row in await cursor.fetchall():
            wo = dict(row)
            if wo.get('created_date'):
                timeline.append({
                    'date': wo['created_date'],
                    'type': 'workorder_created',
                    'title': 'Work Order Opened',
                    'description': f"WO-{wo['id']}: {wo['title']} (Priority: {wo['priority'].capitalize()}) opened by {wo.get('assigned_to') or 'unassigned'}.",
                    'ref_id': wo['id']
                })
            if wo.get('completed_date') and wo.get('status') in ('completed', 'closed'):
                timeline.append({
                    'date': wo['completed_date'],
                    'type': 'workorder_completed',
                    'title': 'Work Order Completed',
                    'description': f"WO-{wo['id']}: {wo['title']} completed in {wo.get('labor_minutes') or 0} mins.",
                    'ref_id': wo['id']
                })

        # 2. PM Records
        cursor = await connection.execute(
            'SELECT * FROM pm_records WHERE cart_id = ? OR cart_id = ?',
            (cart_id, cart_numeric)
        )
        for row in await cursor.fetchall():
            pm = dict(row)
            if pm.get('scheduled_date') and pm.get('status') != 'completed':
                timeline.append({
                    'date': pm['scheduled_date'],
                    'type': 'pm_scheduled',
                    'title': 'PM Scheduled',
                    'description': f"PM: {pm['template_name']} scheduled.",
                    'ref_id': pm['id']
                })
            if pm.get('completed_date') and pm.get('status') == 'completed':
                timeline.append({
                    'date': pm['completed_date'],
                    'type': 'pm_completed',
                    'title': 'PM Completed',
                    'description': f"PM: {pm['template_name']} completed by {pm.get('tech_name') or 'technician'}.",
                    'ref_id': pm['id']
                })

        # 3. Accidents
        cursor = await connection.execute(
            'SELECT * FROM accident_reports WHERE cart_id = ? OR cart_id = ?',
            (cart_id, cart_numeric)
        )
        for row in await cursor.fetchall():
            acc = dict(row)
            date = acc.get('incident_date') or acc.get('created_date')
            if date:
                timeline.append({
                    'date': date,
                    'type': 'accident',
                    'title': 'Accident Damage Reported',
                    'description': f"Accident-{acc['id']}: {acc['description']} (Severity: {acc['severity'].capitalize()}) reported by {acc.get('reported_by') or 'unknown'}.",
                    'ref_id': acc['id']
                })

        # 4. Leases
        cursor = await connection.execute(
            '''
            SELECT l.*, u.unit_code 
            FROM leases l 
            JOIN lease_units u ON l.unit_id = u.id 
            WHERE u.fleet_cart_id = ? OR u.fleet_cart_id = ?
            ''',
            (cart_id, str(cart_numeric))
        )
        for row in await cursor.fetchall():
            lease = dict(row)
            if lease.get('start_date'):
                timeline.append({
                    'date': lease['start_date'],
                    'type': 'lease_started',
                    'title': 'Lease Checkout',
                    'description': f"Lease-{lease['id']}: Checked out to {lease['customer_name']}.",
                    'ref_id': lease['id']
                })
            if lease.get('actual_return') and lease.get('status') == 'returned':
                timeline.append({
                    'date': lease['actual_return'],
                    'type': 'lease_returned',
                    'title': 'Lease Returned',
                    'description': f"Lease-{lease['id']}: Returned by {lease['customer_name']}.",
                    'ref_id': lease['id']
                })

    timeline.sort(key=lambda x: x['date'], reverse=True)
    return timeline



@app.post('/api/carts', response_model=CartItem)
async def create_cart(request: Request, item: CartCreate) -> CartItem:
    require_write_access(request)
    normalized_id = cart_id_str(item.id)
    if not normalized_id:
        raise HTTPException(status_code=400, detail='Cart ID is required')
    if await fetch_cart_row(normalized_id):
        raise HTTPException(status_code=409, detail=f'Cart #{normalized_id} already exists')

    cart_values = cart_values_from_payload(item.model_dump())
    validate_required_cart_fields(cart_values)

    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            '''
            INSERT INTO carts (
                id, serial, model, year, location, status, notes,
                barcode, vin, meter_hours, purchase_date, warranty_expires,
                acquisition_cost, home_location
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                normalized_id,
                cart_values['serial'],
                cart_values['model'],
                cart_values['year'],
                cart_values['location'],
                cart_values['status'],
                cart_values['notes'],
                cart_values['barcode'],
                cart_values['vin'],
                cart_values['meter_hours'],
                cart_values['purchase_date'],
                cart_values['warranty_expires'],
                cart_values['acquisition_cost'],
                cart_values['home_location'],
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
    merged_values = cart_values_from_payload(updated)
    validate_required_cart_fields(merged_values)

    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            '''
            UPDATE carts SET
                serial = ?, model = ?, year = ?, location = ?, status = ?, notes = ?,
                barcode = ?, vin = ?, meter_hours = ?, purchase_date = ?,
                warranty_expires = ?, acquisition_cost = ?, home_location = ?
            WHERE id = ?
            ''',
            (
                merged_values['serial'],
                merged_values['model'],
                merged_values['year'],
                merged_values['location'],
                merged_values['status'],
                merged_values['notes'],
                merged_values['barcode'],
                merged_values['vin'],
                merged_values['meter_hours'],
                merged_values['purchase_date'],
                merged_values['warranty_expires'],
                merged_values['acquisition_cost'],
                merged_values['home_location'],
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
                labor_minutes, parts_used, comments, maintenance_sheet, labor_rate, part_cost
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                item.labor_rate,
                item.part_cost,
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
        'labor_rate': item.labor_rate,
        'part_cost': item.part_cost,
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
        if item.labor_rate is not None:
            updated['labor_rate'] = item.labor_rate
        if item.part_cost is not None:
            updated['part_cost'] = item.part_cost
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
                maintenance_sheet = ?,
                labor_rate = ?,
                part_cost = ?
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
                updated.get('labor_rate', 75.0),
                updated.get('part_cost', 0.0),
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
    if item.template_id and await has_open_pm_for_cart_template(item.cart_id, item.template_id):
        raise HTTPException(
            status_code=409,
            detail=f'Cart #{item.cart_id} already has an open PM for template {item.template_name}',
        )
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


# --- Parts / procurement ---

PO_STATUSES = ('draft', 'approved', 'submitted', 'received', 'cancelled')


def vendor_row_to_item(row: Any) -> Vendor:
    data = dict(row)
    return Vendor(
        id=data['id'],
        name=data.get('name') or '',
        contact_name=data.get('contact_name') or '',
        email=data.get('email') or '',
        phone=data.get('phone') or '',
        account_number=data.get('account_number') or '',
        default_terms=data.get('default_terms') or '',
        avid_vendor_id=data.get('avid_vendor_id') or '',
        active=bool(data.get('active', 1)),
        notes=data.get('notes') or '',
        created_at=data.get('created_at'),
        updated_at=data.get('updated_at'),
    )


def part_row_to_item(row: Any) -> Part:
    data = dict(row)
    on_hand = float(data.get('on_hand') or 0)
    reorder_point = float(data.get('reorder_point') or 0)
    unit_cost = float(data.get('unit_cost') or 0)
    unit_price = float(data.get('unit_price') or 0)
    if unit_price <= 0 and unit_cost > 0:
        unit_price = unit_cost
    return Part(
        id=data['id'],
        part_number=data.get('part_number') or '',
        description=data.get('description') or '',
        category=data.get('category') or '',
        vendor_id=data.get('vendor_id'),
        vendor_part_number=data.get('vendor_part_number') or '',
        unit_of_measure=data.get('unit_of_measure') or 'each',
        unit_cost=unit_cost,
        unit_price=unit_price,
        on_hand=on_hand,
        reorder_point=reorder_point,
        reorder_qty=float(data.get('reorder_qty') or 0),
        location=data.get('location') or '',
        active=bool(data.get('active', 1)),
        notes=data.get('notes') or '',
        vendor_name=data.get('vendor_name'),
        needs_reorder=on_hand <= reorder_point,
        created_at=data.get('created_at'),
        updated_at=data.get('updated_at'),
    )


def po_row_to_item(row: Any) -> PurchaseOrder:
    data = dict(row)
    raw_lines = data.get('lines') or '[]'
    if isinstance(raw_lines, str):
        try:
            parsed = json.loads(raw_lines)
        except json.JSONDecodeError:
            parsed = []
    else:
        parsed = raw_lines
    lines = [PurchaseOrderLine(**line) if isinstance(line, dict) else line for line in parsed]
    return PurchaseOrder(
        id=data['id'],
        po_number=data.get('po_number'),
        vendor_id=data.get('vendor_id'),
        status=data.get('status') or 'draft',
        lines=lines,
        subtotal=float(data.get('subtotal') or 0),
        total=float(data.get('total') or 0),
        notes=data.get('notes') or '',
        requested_by=data.get('requested_by'),
        approved_by=data.get('approved_by'),
        avid_po_id=data.get('avid_po_id'),
        avid_status=data.get('avid_status'),
        idempotency_key=data.get('idempotency_key'),
        vendor_name=data.get('vendor_name'),
        created_at=data.get('created_at'),
        approved_at=data.get('approved_at'),
        submitted_at=data.get('submitted_at'),
        last_synced_at=data.get('last_synced_at'),
    )


def po_lines_totals(lines: List[PurchaseOrderLine]) -> tuple[list[dict[str, Any]], float]:
    serialized: list[dict[str, Any]] = []
    subtotal = 0.0
    for line in lines:
        payload = line.model_dump() if isinstance(line, PurchaseOrderLine) else dict(line)
        qty = float(payload.get('qty') or 0)
        unit_cost = float(payload.get('unit_cost') or 0)
        subtotal += qty * unit_cost
        serialized.append(payload)
    return serialized, subtotal


async def fetch_vendor(vendor_id: int) -> Optional[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute('SELECT * FROM vendors WHERE id = ?', (vendor_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def fetch_part(part_id: int) -> Optional[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            '''
            SELECT p.*, v.name AS vendor_name
            FROM parts p
            LEFT JOIN vendors v ON v.id = p.vendor_id
            WHERE p.id = ?
            ''',
            (part_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def fetch_po(po_id: int) -> Optional[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            '''
            SELECT po.*, v.name AS vendor_name
            FROM purchase_orders po
            LEFT JOIN vendors v ON v.id = po.vendor_id
            WHERE po.id = ?
            ''',
            (po_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


@app.get('/api/parts/stats')
async def parts_stats(request: Request) -> dict[str, Any]:
    require_authenticated_user(request)
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT COUNT(*) AS total FROM parts WHERE active = 1'
        )
        active_parts = (await cursor.fetchone())['total']
        cursor = await connection.execute(
            '''
            SELECT COUNT(*) AS total FROM parts
            WHERE active = 1 AND on_hand <= reorder_point
            '''
        )
        low_stock = (await cursor.fetchone())['total']
        cursor = await connection.execute(
            'SELECT COUNT(*) AS total FROM vendors WHERE active = 1'
        )
        active_vendors = (await cursor.fetchone())['total']
        cursor = await connection.execute(
            "SELECT COUNT(*) AS total FROM purchase_orders WHERE status = 'draft'"
        )
        draft_pos = (await cursor.fetchone())['total']
        cursor = await connection.execute(
            '''
            SELECT COALESCE(SUM(on_hand * unit_cost), 0) AS value
            FROM parts WHERE active = 1
            '''
        )
        inventory_value = float((await cursor.fetchone())['value'] or 0)
    return {
        'active_parts': active_parts,
        'low_stock': low_stock,
        'active_vendors': active_vendors,
        'draft_pos': draft_pos,
        'inventory_value': round(inventory_value, 2),
    }


@app.get('/api/vendors', response_model=List[Vendor])
async def list_vendors(
    request: Request,
    active: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
) -> List[Vendor]:
    require_authenticated_user(request)
    clauses: list[str] = []
    params: list[Any] = []
    if active in ('0', '1', 'true', 'false'):
        clauses.append('active = ?')
        params.append(1 if active in ('1', 'true') else 0)
    if search:
        clauses.append('(name LIKE ? OR contact_name LIKE ? OR account_number LIKE ?)')
        like = f'%{search.strip()}%'
        params.extend([like, like, like])
    where = f'WHERE {" AND ".join(clauses)}' if clauses else ''
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            f'SELECT * FROM vendors {where} ORDER BY name COLLATE NOCASE',
            params,
        )
        rows = await cursor.fetchall()
    return [vendor_row_to_item(row) for row in rows]


@app.get('/api/vendors/{vendor_id}', response_model=Vendor)
async def get_vendor(request: Request, vendor_id: int) -> Vendor:
    require_authenticated_user(request)
    row = await fetch_vendor(vendor_id)
    if not row:
        raise HTTPException(status_code=404, detail='Vendor not found')
    return vendor_row_to_item(row)


@app.post('/api/vendors', response_model=Vendor)
async def create_vendor(request: Request, item: VendorCreate) -> Vendor:
    require_write_access(request)
    name = (item.name or '').strip()
    if not name:
        raise HTTPException(status_code=400, detail='Vendor name is required')
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            '''
            INSERT INTO vendors (
                name, contact_name, email, phone, account_number, default_terms,
                avid_vendor_id, active, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                name,
                (item.contact_name or '').strip(),
                (item.email or '').strip(),
                (item.phone or '').strip(),
                (item.account_number or '').strip(),
                (item.default_terms or '').strip(),
                (item.avid_vendor_id or '').strip(),
                1 if item.active else 0,
                (item.notes or '').strip(),
                now,
                now,
            ),
        )
        vendor_id = cursor.lastrowid
        await connection.commit()
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute('SELECT * FROM vendors WHERE id = ?', (vendor_id,))
        row = await cursor.fetchone()
    await record_audit(
        request,
        'created',
        'vendor',
        vendor_id,
        f'Added vendor {name}',
        {'name': name},
    )
    return vendor_row_to_item(row)


@app.put('/api/vendors/{vendor_id}', response_model=Vendor)
async def update_vendor(request: Request, vendor_id: int, item: VendorUpdate) -> Vendor:
    require_write_access(request)
    existing = await fetch_vendor(vendor_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Vendor not found')
    payload = item.model_dump(exclude_unset=True)
    if 'name' in payload:
        payload['name'] = (payload['name'] or '').strip()
        if not payload['name']:
            raise HTTPException(status_code=400, detail='Vendor name is required')
    if 'active' in payload:
        payload['active'] = 1 if payload['active'] else 0
    for key in ('contact_name', 'email', 'phone', 'account_number', 'default_terms', 'avid_vendor_id', 'notes'):
        if key in payload and payload[key] is not None:
            payload[key] = str(payload[key]).strip()
    if not payload:
        return vendor_row_to_item(existing)
    payload['updated_at'] = datetime.utcnow().isoformat()
    columns = ', '.join(f'{key} = ?' for key in payload)
    values = list(payload.values()) + [vendor_id]
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(f'UPDATE vendors SET {columns} WHERE id = ?', values)
        await connection.commit()
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute('SELECT * FROM vendors WHERE id = ?', (vendor_id,))
        row = await cursor.fetchone()
    await record_audit(
        request,
        'updated',
        'vendor',
        vendor_id,
        f'Updated vendor {row["name"]}',
        payload,
    )
    return vendor_row_to_item(row)


@app.delete('/api/vendors/{vendor_id}')
async def delete_vendor(request: Request, vendor_id: int) -> dict[str, Any]:
    require_write_access(request)
    existing = await fetch_vendor(vendor_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Vendor not found')
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            'UPDATE vendors SET active = 0, updated_at = ? WHERE id = ?',
            (datetime.utcnow().isoformat(), vendor_id),
        )
        await connection.commit()
    await record_audit(
        request,
        'deactivated',
        'vendor',
        vendor_id,
        f'Deactivated vendor {existing.get("name")}',
    )
    return {'deactivated': vendor_id}


@app.get('/api/parts', response_model=List[Part])
async def list_parts(
    request: Request,
    active: Optional[str] = Query(None),
    low_stock: Optional[str] = Query(None),
    vendor_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
) -> List[Part]:
    require_authenticated_user(request)
    clauses: list[str] = []
    params: list[Any] = []
    if active in ('0', '1', 'true', 'false'):
        clauses.append('p.active = ?')
        params.append(1 if active in ('1', 'true') else 0)
    if low_stock in ('1', 'true'):
        clauses.append('p.on_hand <= p.reorder_point')
    if vendor_id is not None:
        clauses.append('p.vendor_id = ?')
        params.append(vendor_id)
    if category:
        clauses.append('p.category = ?')
        params.append(category.strip())
    if search:
        clauses.append(
            '(p.part_number LIKE ? OR p.description LIKE ? OR p.location LIKE ? OR p.vendor_part_number LIKE ?)'
        )
        like = f'%{search.strip()}%'
        params.extend([like, like, like, like])
    where = f'WHERE {" AND ".join(clauses)}' if clauses else ''
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            f'''
            SELECT p.*, v.name AS vendor_name
            FROM parts p
            LEFT JOIN vendors v ON v.id = p.vendor_id
            {where}
            ORDER BY p.description COLLATE NOCASE
            ''',
            params,
        )
        rows = await cursor.fetchall()
    return [part_row_to_item(row) for row in rows]


@app.get('/api/parts/{part_id}', response_model=Part)
async def get_part(request: Request, part_id: int) -> Part:
    require_authenticated_user(request)
    row = await fetch_part(part_id)
    if not row:
        raise HTTPException(status_code=404, detail='Part not found')
    return part_row_to_item(row)


@app.post('/api/parts', response_model=Part)
async def create_part(request: Request, item: PartCreate) -> Part:
    require_write_access(request)
    description = (item.description or '').strip()
    if not description:
        raise HTTPException(status_code=400, detail='Part description is required')
    if item.vendor_id is not None:
        vendor = await fetch_vendor(item.vendor_id)
        if not vendor:
            raise HTTPException(status_code=400, detail='Vendor not found')
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            '''
            INSERT INTO parts (
                part_number, description, category, vendor_id, vendor_part_number,
                unit_of_measure, unit_cost, unit_price, on_hand, reorder_point, reorder_qty,
                location, active, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                (item.part_number or '').strip(),
                description,
                (item.category or '').strip(),
                item.vendor_id,
                (item.vendor_part_number or '').strip(),
                (item.unit_of_measure or 'each').strip() or 'each',
                float(item.unit_cost or 0),
                float(item.unit_price if item.unit_price is not None else 0),
                float(item.on_hand or 0),
                float(item.reorder_point or 0),
                float(item.reorder_qty or 0),
                (item.location or '').strip(),
                1 if item.active else 0,
                (item.notes or '').strip(),
                now,
                now,
            ),
        )
        part_id = cursor.lastrowid
        await connection.commit()
    row = await fetch_part(part_id)
    await record_audit(
        request,
        'created',
        'part',
        part_id,
        f'Added part {item.part_number or description}',
        {'description': description, 'part_number': item.part_number},
    )
    return part_row_to_item(row)


@app.put('/api/parts/{part_id}', response_model=Part)
async def update_part(request: Request, part_id: int, item: PartUpdate) -> Part:
    require_write_access(request)
    existing = await fetch_part(part_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Part not found')
    payload = item.model_dump(exclude_unset=True)
    if 'description' in payload:
        payload['description'] = (payload['description'] or '').strip()
        if not payload['description']:
            raise HTTPException(status_code=400, detail='Part description is required')
    if 'vendor_id' in payload and payload['vendor_id'] is not None:
        vendor = await fetch_vendor(payload['vendor_id'])
        if not vendor:
            raise HTTPException(status_code=400, detail='Vendor not found')
    if 'active' in payload:
        payload['active'] = 1 if payload['active'] else 0
    for key in ('part_number', 'category', 'vendor_part_number', 'unit_of_measure', 'location', 'notes'):
        if key in payload and payload[key] is not None:
            payload[key] = str(payload[key]).strip()
    for key in ('unit_cost', 'unit_price', 'on_hand', 'reorder_point', 'reorder_qty'):
        if key in payload and payload[key] is not None:
            payload[key] = float(payload[key])
    if not payload:
        return part_row_to_item(existing)
    payload['updated_at'] = datetime.utcnow().isoformat()
    columns = ', '.join(f'{key} = ?' for key in payload)
    values = list(payload.values()) + [part_id]
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(f'UPDATE parts SET {columns} WHERE id = ?', values)
        await connection.commit()
    row = await fetch_part(part_id)
    await record_audit(
        request,
        'updated',
        'part',
        part_id,
        f'Updated part {row.get("part_number") or row.get("description")}',
        payload,
    )
    return part_row_to_item(row)


@app.post('/api/parts/{part_id}/adjust', response_model=Part)
async def adjust_part_stock(request: Request, part_id: int, body: PartStockAdjust) -> Part:
    require_write_access(request)
    existing = await fetch_part(part_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Part not found')
    delta = float(body.delta)
    new_qty = float(existing.get('on_hand') or 0) + delta
    if new_qty < 0:
        raise HTTPException(status_code=400, detail='Stock cannot go below zero')
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            'UPDATE parts SET on_hand = ?, updated_at = ? WHERE id = ?',
            (new_qty, now, part_id),
        )
        await connection.commit()
    row = await fetch_part(part_id)
    await record_audit(
        request,
        'stock_adjust',
        'part',
        part_id,
        f'Adjusted stock on {row.get("part_number") or row.get("description")}: {delta:+g} → {new_qty:g}',
        {'delta': delta, 'on_hand': new_qty, 'note': body.note or ''},
    )
    return part_row_to_item(row)


@app.delete('/api/parts/{part_id}')
async def delete_part(request: Request, part_id: int) -> dict[str, Any]:
    require_write_access(request)
    existing = await fetch_part(part_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Part not found')
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            'UPDATE parts SET active = 0, updated_at = ? WHERE id = ?',
            (datetime.utcnow().isoformat(), part_id),
        )
        await connection.commit()
    await record_audit(
        request,
        'deactivated',
        'part',
        part_id,
        f'Deactivated part {existing.get("part_number") or existing.get("description")}',
    )
    return {'deactivated': part_id}


@app.get('/api/purchase-orders', response_model=List[PurchaseOrder])
async def list_purchase_orders(
    request: Request,
    status: Optional[str] = Query(None),
    vendor_id: Optional[int] = Query(None),
) -> List[PurchaseOrder]:
    require_authenticated_user(request)
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append('po.status = ?')
        params.append(status.strip())
    if vendor_id is not None:
        clauses.append('po.vendor_id = ?')
        params.append(vendor_id)
    where = f'WHERE {" AND ".join(clauses)}' if clauses else ''
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            f'''
            SELECT po.*, v.name AS vendor_name
            FROM purchase_orders po
            LEFT JOIN vendors v ON v.id = po.vendor_id
            {where}
            ORDER BY po.id DESC
            ''',
            params,
        )
        rows = await cursor.fetchall()
    return [po_row_to_item(row) for row in rows]


@app.post('/api/purchase-orders', response_model=PurchaseOrder)
async def create_purchase_order(request: Request, item: PurchaseOrderCreate) -> PurchaseOrder:
    user = require_write_access(request)
    status = (item.status or 'draft').strip().lower()
    if status not in PO_STATUSES:
        raise HTTPException(status_code=400, detail=f'Invalid status. Use one of: {", ".join(PO_STATUSES)}')
    if item.vendor_id is not None:
        vendor = await fetch_vendor(item.vendor_id)
        if not vendor:
            raise HTTPException(status_code=400, detail='Vendor not found')
    lines, subtotal = po_lines_totals(item.lines or [])
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            '''
            INSERT INTO purchase_orders (
                po_number, vendor_id, status, lines, subtotal, total, notes,
                requested_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                None,
                item.vendor_id,
                status,
                json.dumps(lines),
                subtotal,
                subtotal,
                (item.notes or '').strip(),
                user.get('display_name') or user.get('username'),
                now,
            ),
        )
        po_id = cursor.lastrowid
        po_number = f'PO-{po_id:05d}'
        await connection.execute(
            'UPDATE purchase_orders SET po_number = ? WHERE id = ?',
            (po_number, po_id),
        )
        await connection.commit()
    row = await fetch_po(po_id)
    await record_audit(
        request,
        'created',
        'purchase_order',
        po_id,
        f'Created {po_number}',
        {'status': status, 'total': subtotal, 'lines': len(lines)},
    )
    return po_row_to_item(row)


@app.post('/api/purchase-orders/from-reorder', response_model=PurchaseOrder)
async def create_po_from_reorder(
    request: Request,
    vendor_id: Optional[int] = Query(None),
) -> PurchaseOrder:
    """Create a draft PO for all active parts at or below reorder point."""
    user = require_write_access(request)
    clauses = ['p.active = 1', 'p.on_hand <= p.reorder_point']
    params: list[Any] = []
    if vendor_id is not None:
        clauses.append('p.vendor_id = ?')
        params.append(vendor_id)
    where = ' AND '.join(clauses)
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            f'''
            SELECT p.*, v.name AS vendor_name
            FROM parts p
            LEFT JOIN vendors v ON v.id = p.vendor_id
            WHERE {where}
            ORDER BY p.vendor_id, p.description
            ''',
            params,
        )
        rows = await cursor.fetchall()
    if not rows:
        raise HTTPException(status_code=400, detail='No parts need reordering')

    chosen_vendor = vendor_id
    if chosen_vendor is None:
        vendor_ids = {row['vendor_id'] for row in rows if row['vendor_id'] is not None}
        if len(vendor_ids) == 1:
            chosen_vendor = next(iter(vendor_ids))
        elif len(vendor_ids) > 1:
            raise HTTPException(
                status_code=400,
                detail='Low-stock parts span multiple vendors — pick a vendor_id',
            )

    lines: list[PurchaseOrderLine] = []
    for row in rows:
        if chosen_vendor is not None and row['vendor_id'] not in (None, chosen_vendor):
            continue
        qty = float(row['reorder_qty'] or 0)
        if qty <= 0:
            qty = max(float(row['reorder_point'] or 0) - float(row['on_hand'] or 0), 1)
        lines.append(
            PurchaseOrderLine(
                part_id=row['id'],
                part_number=row['part_number'] or '',
                description=row['description'] or '',
                qty=qty,
                unit_cost=float(row['unit_cost'] or 0),
            )
        )
    if not lines:
        raise HTTPException(status_code=400, detail='No parts need reordering for that vendor')

    return await create_purchase_order(
        request,
        PurchaseOrderCreate(
            vendor_id=chosen_vendor,
            status='draft',
            lines=lines,
            notes=f'Draft from reorder — requested by {user.get("display_name") or user.get("username")}',
        ),
    )


@app.get('/api/purchase-orders/{po_id}', response_model=PurchaseOrder)
async def get_purchase_order(request: Request, po_id: int) -> PurchaseOrder:
    require_authenticated_user(request)
    row = await fetch_po(po_id)
    if not row:
        raise HTTPException(status_code=404, detail='Purchase order not found')
    return po_row_to_item(row)


@app.put('/api/purchase-orders/{po_id}', response_model=PurchaseOrder)
async def update_purchase_order(
    request: Request,
    po_id: int,
    item: PurchaseOrderUpdate,
) -> PurchaseOrder:
    user = require_write_access(request)
    existing = await fetch_po(po_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Purchase order not found')
    payload = item.model_dump(exclude_unset=True)
    if 'status' in payload:
        status = (payload['status'] or '').strip().lower()
        if status not in PO_STATUSES:
            raise HTTPException(status_code=400, detail=f'Invalid status. Use one of: {", ".join(PO_STATUSES)}')
        payload['status'] = status
        if status == 'approved' and not existing.get('approved_at'):
            payload['approved_at'] = datetime.utcnow().isoformat()
            if not payload.get('approved_by'):
                payload['approved_by'] = user.get('display_name') or user.get('username')
        if status == 'submitted' and not existing.get('submitted_at'):
            payload['submitted_at'] = datetime.utcnow().isoformat()
    if 'vendor_id' in payload and payload['vendor_id'] is not None:
        vendor = await fetch_vendor(payload['vendor_id'])
        if not vendor:
            raise HTTPException(status_code=400, detail='Vendor not found')
    if 'lines' in payload and payload['lines'] is not None:
        line_models = [
            PurchaseOrderLine(**line) if isinstance(line, dict) else line
            for line in payload['lines']
        ]
        serialized, subtotal = po_lines_totals(line_models)
        payload['lines'] = json.dumps(serialized)
        payload['subtotal'] = subtotal
        payload['total'] = subtotal
    if 'notes' in payload and payload['notes'] is not None:
        payload['notes'] = str(payload['notes']).strip()
    if not payload:
        return po_row_to_item(existing)
    columns = ', '.join(f'{key} = ?' for key in payload)
    values = list(payload.values()) + [po_id]
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(f'UPDATE purchase_orders SET {columns} WHERE id = ?', values)
        await connection.commit()
    row = await fetch_po(po_id)
    await record_audit(
        request,
        'updated',
        'purchase_order',
        po_id,
        f'Updated {row.get("po_number") or f"PO-{po_id}"}',
        {k: v for k, v in payload.items() if k != 'lines'},
    )
    return po_row_to_item(row)


def lease_unit_row_to_item(row: Any) -> LeaseUnit:
    data = dict(row)
    return LeaseUnit(
        id=data['id'],
        unit_code=data.get('unit_code') or '',
        serial=data.get('serial') or '',
        model=data.get('model') or '',
        year=data.get('year') or '',
        condition=data.get('condition') or 'good',
        status=data.get('status') or 'available',
        venue=data.get('venue') or '',
        daily_rate=float(data.get('daily_rate') or 0),
        fleet_cart_id=str(data['fleet_cart_id']) if data.get('fleet_cart_id') is not None else None,
        notes=data.get('notes') or '',
        created_at=data.get('created_at'),
        updated_at=data.get('updated_at'),
    )


def lease_row_to_item(row: Any) -> Lease:
    data = dict(row)
    return Lease(
        id=data['id'],
        lease_number=data.get('lease_number') or f"LS-{data['id']}",
        unit_id=int(data['unit_id']),
        customer_name=data.get('customer_name') or '',
        customer_phone=data.get('customer_phone') or '',
        customer_email=data.get('customer_email') or '',
        start_date=data.get('start_date') or '',
        expected_return=data.get('expected_return') or '',
        actual_return=data.get('actual_return'),
        daily_rate=float(data.get('daily_rate') or 0),
        deposit=float(data.get('deposit') or 0),
        total_charged=float(data.get('total_charged') or 0),
        status=data.get('status') or 'active',
        notes=data.get('notes') or '',
        unit_code=data.get('unit_code'),
        unit_model=data.get('unit_model'),
        unit_serial=data.get('unit_serial'),
        created_by=data.get('created_by'),
        created_at=data.get('created_at'),
        updated_at=data.get('updated_at'),
    )


def sale_row_to_item(row: Any) -> Sale:
    data = dict(row)
    raw_lines = data.get('lines') or '[]'
    if isinstance(raw_lines, str):
        try:
            parsed = json.loads(raw_lines)
        except json.JSONDecodeError:
            parsed = []
    else:
        parsed = raw_lines
    lines = [SaleLine(**line) if isinstance(line, dict) else line for line in (parsed or [])]
    return Sale(
        id=data['id'],
        sale_number=data.get('sale_number') or f"SALE-{data['id']}",
        customer_name=data.get('customer_name') or '',
        customer_phone=data.get('customer_phone') or '',
        status=data.get('status') or 'completed',
        lines=lines,
        subtotal=float(data.get('subtotal') or 0),
        total=float(data.get('total') or 0),
        payment_method=data.get('payment_method') or 'cash',
        notes=data.get('notes') or '',
        sold_by=data.get('sold_by'),
        created_at=data.get('created_at'),
        voided_at=data.get('voided_at'),
    )


async def fetch_lease_unit(unit_id: int) -> Optional[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute('SELECT * FROM lease_units WHERE id = ?', (unit_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def fetch_lease(lease_id: int) -> Optional[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            '''
            SELECT l.*, u.unit_code, u.model AS unit_model, u.serial AS unit_serial
            FROM leases l
            LEFT JOIN lease_units u ON u.id = l.unit_id
            WHERE l.id = ?
            ''',
            (lease_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def fetch_sale(sale_id: int) -> Optional[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute('SELECT * FROM sales WHERE id = ?', (sale_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


@app.get('/api/lease/stats')
async def lease_stats(request: Request) -> dict[str, Any]:
    require_authenticated_user(request)
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        available = (await (await connection.execute(
            "SELECT COUNT(*) AS n FROM lease_units WHERE status = 'available'",
        )).fetchone())['n']
        leased = (await (await connection.execute(
            "SELECT COUNT(*) AS n FROM lease_units WHERE status = 'leased'",
        )).fetchone())['n']
        active = (await (await connection.execute(
            "SELECT COUNT(*) AS n FROM leases WHERE status = 'active'",
        )).fetchone())['n']
        units = (await (await connection.execute(
            'SELECT COUNT(*) AS n FROM lease_units',
        )).fetchone())['n']
    return {
        'units': units,
        'available': available,
        'leased': leased,
        'active_leases': active,
    }


@app.get('/api/lease/units', response_model=List[LeaseUnit])
async def list_lease_units(
    request: Request,
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
) -> List[LeaseUnit]:
    require_authenticated_user(request)
    clauses: list[str] = []
    params: list[Any] = []
    if status and status != 'all':
        clauses.append('status = ?')
        params.append(status.strip().lower())
    if search:
        like = f'%{search.strip()}%'
        clauses.append('(unit_code LIKE ? OR serial LIKE ? OR model LIKE ? OR venue LIKE ?)')
        params.extend([like, like, like, like])
    where = f'WHERE {" AND ".join(clauses)}' if clauses else ''
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            f'SELECT * FROM lease_units {where} ORDER BY unit_code COLLATE NOCASE',
            params,
        )
        rows = await cursor.fetchall()
    return [lease_unit_row_to_item(row) for row in rows]


@app.post('/api/lease/units', response_model=LeaseUnit)
async def create_lease_unit(request: Request, item: LeaseUnitCreate) -> LeaseUnit:
    require_write_access(request)
    code = (item.unit_code or '').strip()
    if not code:
        raise HTTPException(status_code=400, detail='Unit code is required')
    status = (item.status or 'available').strip().lower()
    if status not in LEASE_UNIT_STATUSES:
        raise HTTPException(status_code=400, detail=f'Invalid status. Use: {", ".join(LEASE_UNIT_STATUSES)}')
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        try:
            cursor = await connection.execute(
                '''
                INSERT INTO lease_units (
                    unit_code, serial, model, year, condition, status, venue,
                    daily_rate, fleet_cart_id, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    code,
                    (item.serial or '').strip(),
                    (item.model or '').strip(),
                    (item.year or '').strip(),
                    (item.condition or 'good').strip() or 'good',
                    status,
                    (item.venue or '').strip(),
                    float(item.daily_rate or 0),
                    str(item.fleet_cart_id).strip() if item.fleet_cart_id else None,
                    (item.notes or '').strip(),
                    now,
                    now,
                ),
            )
            unit_id = cursor.lastrowid
            await connection.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(status_code=409, detail=f'Unit code {code} already exists') from None
    row = await fetch_lease_unit(unit_id)
    await record_audit(request, 'created', 'lease_unit', unit_id, f'Added lease unit {code}')
    return lease_unit_row_to_item(row)


@app.put('/api/lease/units/{unit_id}', response_model=LeaseUnit)
async def update_lease_unit(request: Request, unit_id: int, item: LeaseUnitUpdate) -> LeaseUnit:
    require_write_access(request)
    existing = await fetch_lease_unit(unit_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Lease unit not found')
    payload = item.model_dump(exclude_unset=True)
    if 'status' in payload and payload['status'] is not None:
        status = str(payload['status']).strip().lower()
        if status not in LEASE_UNIT_STATUSES:
            raise HTTPException(status_code=400, detail=f'Invalid status. Use: {", ".join(LEASE_UNIT_STATUSES)}')
        payload['status'] = status
    if 'unit_code' in payload and payload['unit_code'] is not None:
        payload['unit_code'] = str(payload['unit_code']).strip()
        if not payload['unit_code']:
            raise HTTPException(status_code=400, detail='Unit code is required')
    for key in ('serial', 'model', 'year', 'condition', 'venue', 'notes'):
        if key in payload and payload[key] is not None:
            payload[key] = str(payload[key]).strip()
    if 'daily_rate' in payload and payload['daily_rate'] is not None:
        payload['daily_rate'] = float(payload['daily_rate'])
    if 'fleet_cart_id' in payload:
        payload['fleet_cart_id'] = (
            str(payload['fleet_cart_id']).strip() if payload['fleet_cart_id'] else None
        )
    if not payload:
        return lease_unit_row_to_item(existing)
    payload['updated_at'] = datetime.utcnow().isoformat()
    columns = ', '.join(f'{key} = ?' for key in payload)
    values = list(payload.values()) + [unit_id]
    async with aiosqlite.connect(DB_PATH) as connection:
        try:
            await connection.execute(f'UPDATE lease_units SET {columns} WHERE id = ?', values)
            await connection.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(status_code=409, detail='Unit code already exists') from None
    row = await fetch_lease_unit(unit_id)
    await record_audit(request, 'updated', 'lease_unit', unit_id, f'Updated lease unit {row.get("unit_code")}')
    return lease_unit_row_to_item(row)


@app.get('/api/leases', response_model=List[Lease])
async def list_leases(
    request: Request,
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
) -> List[Lease]:
    require_authenticated_user(request)
    clauses: list[str] = []
    params: list[Any] = []
    if status and status != 'all':
        clauses.append('l.status = ?')
        params.append(status.strip().lower())
    if search:
        like = f'%{search.strip()}%'
        clauses.append(
            '(l.customer_name LIKE ? OR l.lease_number LIKE ? OR u.unit_code LIKE ? OR l.customer_phone LIKE ?)',
        )
        params.extend([like, like, like, like])
    where = f'WHERE {" AND ".join(clauses)}' if clauses else ''
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            f'''
            SELECT l.*, u.unit_code, u.model AS unit_model, u.serial AS unit_serial
            FROM leases l
            LEFT JOIN lease_units u ON u.id = l.unit_id
            {where}
            ORDER BY l.id DESC
            ''',
            params,
        )
        rows = await cursor.fetchall()
    return [lease_row_to_item(row) for row in rows]


@app.post('/api/leases', response_model=Lease)
async def create_lease(request: Request, item: LeaseCreate) -> Lease:
    user = require_write_access(request)
    unit = await fetch_lease_unit(item.unit_id)
    if not unit:
        raise HTTPException(status_code=400, detail='Lease unit not found')
    if (unit.get('status') or '') != 'available':
        raise HTTPException(status_code=409, detail=f'Unit is not available (status: {unit.get("status")})')
    customer = (item.customer_name or '').strip()
    if not customer:
        raise HTTPException(status_code=400, detail='Customer name is required')
    start_date = (item.start_date or '').strip()
    if not start_date:
        raise HTTPException(status_code=400, detail='Start date is required')
    daily_rate = float(item.daily_rate if item.daily_rate is not None else unit.get('daily_rate') or 0)
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            '''
            INSERT INTO leases (
                lease_number, unit_id, customer_name, customer_phone, customer_email,
                start_date, expected_return, daily_rate, deposit, total_charged,
                status, notes, created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'active', ?, ?, ?, ?)
            ''',
            (
                None,
                item.unit_id,
                customer,
                (item.customer_phone or '').strip(),
                (item.customer_email or '').strip(),
                start_date,
                (item.expected_return or '').strip(),
                daily_rate,
                float(item.deposit or 0),
                (item.notes or '').strip(),
                user.get('display_name') or user.get('username'),
                now,
                now,
            ),
        )
        lease_id = cursor.lastrowid
        lease_number = f'LS-{lease_id:05d}'
        await connection.execute(
            'UPDATE leases SET lease_number = ? WHERE id = ?',
            (lease_number, lease_id),
        )
        await connection.execute(
            "UPDATE lease_units SET status = 'leased', updated_at = ? WHERE id = ?",
            (now, item.unit_id),
        )
        await connection.commit()
    row = await fetch_lease(lease_id)
    await record_audit(
        request,
        'created',
        'lease',
        lease_id,
        f'Started {lease_number} for {customer} ({unit.get("unit_code")})',
    )
    return lease_row_to_item(row)


@app.put('/api/leases/{lease_id}', response_model=Lease)
async def update_lease(request: Request, lease_id: int, item: LeaseUpdate) -> Lease:
    require_write_access(request)
    existing = await fetch_lease(lease_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Lease not found')
    payload = item.model_dump(exclude_unset=True)
    if 'status' in payload and payload['status'] is not None:
        status = str(payload['status']).strip().lower()
        if status not in LEASE_STATUSES:
            raise HTTPException(status_code=400, detail=f'Invalid status. Use: {", ".join(LEASE_STATUSES)}')
        payload['status'] = status
    for key in ('customer_name', 'customer_phone', 'customer_email', 'start_date', 'expected_return', 'actual_return', 'notes'):
        if key in payload and payload[key] is not None:
            payload[key] = str(payload[key]).strip()
    for key in ('daily_rate', 'deposit', 'total_charged'):
        if key in payload and payload[key] is not None:
            payload[key] = float(payload[key])
    if not payload:
        return lease_row_to_item(existing)
    payload['updated_at'] = datetime.utcnow().isoformat()
    columns = ', '.join(f'{key} = ?' for key in payload)
    values = list(payload.values()) + [lease_id]
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(f'UPDATE leases SET {columns} WHERE id = ?', values)
        await connection.commit()
    row = await fetch_lease(lease_id)
    await record_audit(request, 'updated', 'lease', lease_id, f'Updated {row.get("lease_number")}')
    return lease_row_to_item(row)


@app.post('/api/leases/{lease_id}/return', response_model=Lease)
async def return_lease(request: Request, lease_id: int, body: LeaseReturn) -> Lease:
    require_write_access(request)
    existing = await fetch_lease(lease_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Lease not found')
    if (existing.get('status') or '') != 'active':
        raise HTTPException(status_code=409, detail='Only active leases can be returned')
    now = datetime.utcnow().isoformat()
    actual_return = (body.actual_return or now).strip()
    total_charged = body.total_charged
    if total_charged is None:
        total_charged = float(existing.get('deposit') or 0)
    notes = (body.notes or '').strip()
    if notes:
        prior = (existing.get('notes') or '').strip()
        notes = f'{prior}\nReturn: {notes}'.strip() if prior else f'Return: {notes}'
    else:
        notes = existing.get('notes') or ''
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            '''
            UPDATE leases
            SET status = 'returned', actual_return = ?, total_charged = ?, notes = ?, updated_at = ?
            WHERE id = ?
            ''',
            (actual_return, float(total_charged), notes, now, lease_id),
        )
        unit_status = 'available'
        if body.condition and body.condition.strip().lower() in ('maintenance', 'fair', 'poor'):
            unit_status = 'maintenance'
        await connection.execute(
            'UPDATE lease_units SET status = ?, updated_at = ? WHERE id = ?',
            (unit_status, now, existing['unit_id']),
        )
        if body.condition:
            await connection.execute(
                'UPDATE lease_units SET condition = ? WHERE id = ?',
                (body.condition.strip(), existing['unit_id']),
            )
        await connection.commit()
    row = await fetch_lease(lease_id)
    await record_audit(
        request,
        'updated',
        'lease',
        lease_id,
        f'Returned {row.get("lease_number")}',
        {'total_charged': total_charged},
    )
    return lease_row_to_item(row)


@app.get('/api/sales/stats')
async def sales_stats(request: Request) -> dict[str, Any]:
    require_authenticated_user(request)
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        completed = (await (await connection.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(total), 0) AS revenue FROM sales WHERE status = 'completed'",
        )).fetchone())
        today = datetime.utcnow().date().isoformat()
        today_row = (await (await connection.execute(
            '''
            SELECT COUNT(*) AS n, COALESCE(SUM(total), 0) AS revenue
            FROM sales
            WHERE status = 'completed' AND created_at LIKE ?
            ''',
            (f'{today}%',),
        )).fetchone())
    return {
        'completed_sales': completed['n'],
        'revenue': round(float(completed['revenue'] or 0), 2),
        'today_sales': today_row['n'],
        'today_revenue': round(float(today_row['revenue'] or 0), 2),
    }


@app.get('/api/sales', response_model=List[Sale])
async def list_sales(
    request: Request,
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> List[Sale]:
    require_authenticated_user(request)
    clauses: list[str] = []
    params: list[Any] = []
    if status and status != 'all':
        clauses.append('status = ?')
        params.append(status.strip().lower())
    if search:
        like = f'%{search.strip()}%'
        clauses.append('(sale_number LIKE ? OR customer_name LIKE ? OR customer_phone LIKE ?)')
        params.extend([like, like, like])
    where = f'WHERE {" AND ".join(clauses)}' if clauses else ''
    params.append(limit)
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            f'SELECT * FROM sales {where} ORDER BY id DESC LIMIT ?',
            params,
        )
        rows = await cursor.fetchall()
    return [sale_row_to_item(row) for row in rows]


@app.post('/api/sales', response_model=Sale)
async def create_sale(request: Request, item: SaleCreate) -> Sale:
    user = require_write_access(request)
    if not item.lines:
        raise HTTPException(status_code=400, detail='Add at least one line item')
    now = datetime.utcnow().isoformat()
    normalized: list[dict[str, Any]] = []
    subtotal = 0.0

    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        for line in item.lines:
            qty = float(line.qty or 0)
            if qty <= 0:
                raise HTTPException(status_code=400, detail='Quantity must be greater than zero')
            part = None
            if line.part_id is not None:
                cursor = await connection.execute(
                    'SELECT * FROM parts WHERE id = ?',
                    (line.part_id,),
                )
                part = await cursor.fetchone()
                if not part:
                    raise HTTPException(status_code=400, detail=f'Part id {line.part_id} not found')
                on_hand = float(part['on_hand'] or 0)
                if on_hand < qty:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f'Insufficient stock for {part["part_number"] or part["description"]}: '
                            f'on hand {on_hand}, requested {qty}'
                        ),
                    )
            unit_price = float(line.unit_price or 0)
            if unit_price <= 0 and part is not None:
                unit_price = float(part['unit_price'] or part['unit_cost'] or 0)
            description = (line.description or '').strip()
            part_number = (line.part_number or '').strip()
            if part is not None:
                description = description or (part['description'] or '')
                part_number = part_number or (part['part_number'] or '')
            if not description:
                raise HTTPException(status_code=400, detail='Line description is required')
            line_total = round(qty * unit_price, 2)
            subtotal += line_total
            normalized.append({
                'part_id': line.part_id,
                'part_number': part_number,
                'description': description,
                'qty': qty,
                'unit_price': unit_price,
            })

        for line in normalized:
            if line['part_id'] is None:
                continue
            await connection.execute(
                '''
                UPDATE parts
                SET on_hand = on_hand - ?, updated_at = ?
                WHERE id = ?
                ''',
                (line['qty'], now, line['part_id']),
            )

        subtotal = round(subtotal, 2)
        cursor = await connection.execute(
            '''
            INSERT INTO sales (
                sale_number, customer_name, customer_phone, status, lines,
                subtotal, total, payment_method, notes, sold_by, created_at, voided_at
            ) VALUES (?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?, NULL)
            ''',
            (
                None,
                (item.customer_name or '').strip(),
                (item.customer_phone or '').strip(),
                json.dumps(normalized),
                subtotal,
                subtotal,
                (item.payment_method or 'cash').strip() or 'cash',
                (item.notes or '').strip(),
                user.get('display_name') or user.get('username'),
                now,
            ),
        )
        sale_id = cursor.lastrowid
        sale_number = f'SALE-{sale_id:05d}'
        await connection.execute(
            'UPDATE sales SET sale_number = ? WHERE id = ?',
            (sale_number, sale_id),
        )
        await connection.commit()

    row = await fetch_sale(sale_id)
    await record_audit(
        request,
        'created',
        'sale',
        sale_id,
        f'Completed {sale_number} · ${subtotal:.2f}',
        {'lines': len(normalized), 'total': subtotal},
    )
    return sale_row_to_item(row)


@app.post('/api/sales/{sale_id}/void', response_model=Sale)
async def void_sale(request: Request, sale_id: int) -> Sale:
    require_write_access(request)
    existing = await fetch_sale(sale_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Sale not found')
    if (existing.get('status') or '') != 'completed':
        raise HTTPException(status_code=409, detail='Only completed sales can be voided')
    raw_lines = existing.get('lines') or '[]'
    try:
        lines = json.loads(raw_lines) if isinstance(raw_lines, str) else (raw_lines or [])
    except json.JSONDecodeError:
        lines = []
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        for line in lines:
            part_id = line.get('part_id') if isinstance(line, dict) else None
            qty = float(line.get('qty') or 0) if isinstance(line, dict) else 0
            if part_id and qty:
                await connection.execute(
                    'UPDATE parts SET on_hand = on_hand + ?, updated_at = ? WHERE id = ?',
                    (qty, now, part_id),
                )
        await connection.execute(
            "UPDATE sales SET status = 'void', voided_at = ? WHERE id = ?",
            (now, sale_id),
        )
        await connection.commit()
    row = await fetch_sale(sale_id)
    await record_audit(request, 'updated', 'sale', sale_id, f'Voided {row.get("sale_number")}')
    return sale_row_to_item(row)


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
        'title': 'Fleet Maintain Test Alert',
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


NASCAR_SNAPSHOT_PATH = ROOT_DIR / 'data' / 'nascar_standings_snapshot.json'
WEATHER_CODES = {
    0: 'Clear sky',
    1: 'Mainly clear',
    2: 'Partly cloudy',
    3: 'Overcast',
    45: 'Fog',
    48: 'Depositing rime fog',
    51: 'Light drizzle',
    53: 'Drizzle',
    55: 'Dense drizzle',
    61: 'Slight rain',
    63: 'Rain',
    65: 'Heavy rain',
    71: 'Slight snow',
    73: 'Snow',
    75: 'Heavy snow',
    80: 'Rain showers',
    81: 'Rain showers',
    82: 'Violent rain showers',
    95: 'Thunderstorm',
    96: 'Thunderstorm with hail',
    99: 'Thunderstorm with heavy hail',
}


def _fetch_json_url(url: str, timeout: int = 12) -> Any:
    request = UrlRequest(
        url,
        headers={
            'User-Agent': 'MaintainSMIP/1.6 (+https://maintainsmip.onrender.com)',
            'Accept': 'application/json',
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def _load_nascar_snapshot() -> dict[str, Any]:
    if NASCAR_SNAPSHOT_PATH.exists():
        return json.loads(NASCAR_SNAPSHOT_PATH.read_text(encoding='utf-8'))
    return {
        'season': datetime.utcnow().year,
        'series': 'NASCAR Cup Series',
        'updated': datetime.utcnow().date().isoformat(),
        'source': 'snapshot',
        'drivers': [],
    }


def _try_live_nascar_standings() -> Optional[dict[str, Any]]:
    season = datetime.utcnow().year
    candidates = [
        f'https://cf.nascar.com/cacher/{season}/1/cup-series-standings-feed.json',
        f'https://cf.nascar.com/cacher/{season - 1}/1/cup-series-standings-feed.json',
    ]
    for url in candidates:
        try:
            payload = _fetch_json_url(url, timeout=8)
            standings = payload.get('standings') or []
            if not standings:
                continue
            drivers_raw = standings[0].get('driver_standings') or []
            drivers = []
            for row in drivers_raw[:10]:
                drivers.append({
                    'position': row.get('position') or row.get('rank') or len(drivers) + 1,
                    'driver': row.get('driver_name') or row.get('full_name') or 'Unknown',
                    'team': row.get('owner_name') or row.get('team') or '',
                    'points': row.get('points') or 0,
                })
            if drivers:
                return {
                    'season': season,
                    'series': 'NASCAR Cup Series',
                    'updated': datetime.utcnow().date().isoformat(),
                    'source': 'live',
                    'drivers': drivers,
                }
        except Exception:
            continue
    return None


@app.get('/api/widgets/weather')
async def widget_weather(
    request: Request,
    location: str = Query(''),
    lat: Optional[float] = Query(None),
    lon: Optional[float] = Query(None),
) -> dict[str, Any]:
    require_authenticated_user(request)
    resolved_lat = lat
    resolved_lon = lon
    resolved_name = location.strip()

    if resolved_lat is None or resolved_lon is None:
        if not resolved_name:
            raise HTTPException(status_code=400, detail='Provide a location or latitude/longitude.')
        resolved_name = re.sub(r'\s*,\s*', ', ', resolved_name)
        geo_url = (
            'https://geocoding-api.open-meteo.com/v1/search?'
            + urlencode({'name': resolved_name, 'count': 1, 'language': 'en', 'format': 'json'})
        )
        try:
            geo = await asyncio.to_thread(_fetch_json_url, geo_url, 10)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f'Weather lookup failed: {exc}') from exc
        results = geo.get('results') or []
        if not results:
            raise HTTPException(status_code=404, detail=f'No location found for "{resolved_name}".')
        hit = results[0]
        resolved_lat = float(hit['latitude'])
        resolved_lon = float(hit['longitude'])
        resolved_name = ', '.join(
            part for part in [hit.get('name'), hit.get('admin1'), hit.get('country_code')] if part
        )

    forecast_url = (
        'https://api.open-meteo.com/v1/forecast?'
        + urlencode({
            'latitude': resolved_lat,
            'longitude': resolved_lon,
            'current': 'temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m',
            'temperature_unit': 'fahrenheit',
            'wind_speed_unit': 'mph',
            'timezone': 'auto',
        })
    )
    try:
        forecast = await asyncio.to_thread(_fetch_json_url, forecast_url, 10)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f'Weather forecast failed: {exc}') from exc

    current = forecast.get('current') or {}
    code = int(current.get('weather_code') or 0)
    return {
        'location': resolved_name,
        'latitude': resolved_lat,
        'longitude': resolved_lon,
        'temperature_f': current.get('temperature_2m'),
        'wind_mph': current.get('wind_speed_10m'),
        'humidity': current.get('relative_humidity_2m'),
        'condition': WEATHER_CODES.get(code, 'Weather update'),
        'weather_code': code,
        'timezone': forecast.get('timezone'),
    }


@app.get('/api/widgets/nascar-standings')
async def widget_nascar_standings(request: Request) -> dict[str, Any]:
    require_authenticated_user(request)
    live = await asyncio.to_thread(_try_live_nascar_standings)
    if live:
        return live
    snapshot = await asyncio.to_thread(_load_nascar_snapshot)
    snapshot['source'] = 'snapshot'
    snapshot['live_url'] = 'https://www.nascar.com/standings/cup-series/'
    return snapshot


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
    password_changed: bool = False


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
        'seed_demo_data': SEED_DEMO_DATA,
        'smtp_configured': smtp_configured(),
        'email_recipients': len(NOTIFY_EMAIL_RECIPIENTS),
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


RESTORE_REQUIRED_TABLES = (
    'users',
    'carts',
    'work_orders',
    'audit_log',
    'pm_templates',
    'pm_records',
    'accident_reports',
)
RESTORE_MAX_BYTES = 50 * 1024 * 1024


def validate_restore_database(path: Path) -> None:
    header = path.read_bytes()[:16]
    if not header.startswith(b'SQLite format 3'):
        raise HTTPException(status_code=400, detail='File is not a valid SQLite database')

    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'",
            )
        }
        missing = [table for table in RESTORE_REQUIRED_TABLES if table not in tables]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f'Backup is missing required tables: {", ".join(missing)}',
            )

        user_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        if user_count < 1:
            raise HTTPException(status_code=400, detail='Backup has no user accounts')

        integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity != 'ok':
            raise HTTPException(status_code=400, detail=f'Backup failed integrity check: {integrity}')
    finally:
        conn.close()


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


@app.post('/api/admin/restore')
async def restore_database_backup(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    admin = require_admin(request)
    if not file.filename or not file.filename.lower().endswith('.db'):
        raise HTTPException(status_code=400, detail='Upload a .db SQLite backup file')

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail='Uploaded file is empty')
    if len(raw) > RESTORE_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f'Backup file exceeds {RESTORE_MAX_BYTES // (1024 * 1024)} MB limit',
        )
    if not raw.startswith(b'SQLite format 3'):
        raise HTTPException(status_code=400, detail='File is not a valid SQLite database')

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    tmp_path = Path(tmp.name)
    moved = False
    try:
        tmp.write(raw)
        tmp.close()
        validate_restore_database(tmp_path)

        pre_restore_backup: Optional[Path] = None
        if DB_PATH.exists():
            timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
            pre_restore_backup = DB_PATH.with_name(f'{DB_PATH.name}.pre-restore-{timestamp}.bak')
            shutil.copy2(DB_PATH, pre_restore_backup)

        os.replace(str(tmp_path), str(DB_PATH))
        moved = True

        await record_audit(
            request,
            'restored',
            'database',
            'maintainsmip',
            f'Database restored from {file.filename} by {admin["username"]}',
            {
                'filename': file.filename,
                'size_bytes': len(raw),
                'pre_restore_backup': pre_restore_backup.name if pre_restore_backup else None,
            },
        )
        return {
            'ok': True,
            'filename': file.filename,
            'size_bytes': len(raw),
            'pre_restore_backup': pre_restore_backup.name if pre_restore_backup else None,
        }
    finally:
        if not moved and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


@app.get('/api/users/team-members')
async def team_members(request: Request) -> List[dict[str, Any]]:
    require_authenticated_user(request)
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            '''
            SELECT username, display_name, role
            FROM users
            WHERE active = 1
            ORDER BY display_name
            ''',
        )
        rows = await cursor.fetchall()
    return [
        {
            'username': row['username'],
            'display_name': row['display_name'],
            'role': row['role'],
        }
        for row in rows
    ]


@app.get('/api/audit/usernames')
async def audit_usernames(request: Request, days: int = Query(365, ge=1, le=3650)) -> List[dict[str, str]]:
    require_authenticated_user(request)
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            '''
            SELECT DISTINCT username, display_name
            FROM audit_log
            WHERE created_at >= ? AND username IS NOT NULL AND username != ''
            ORDER BY display_name
            ''',
            (cutoff,),
        )
        rows = await cursor.fetchall()
    return [
        {'username': row['username'], 'display_name': row['display_name'] or row['username']}
        for row in rows
    ]


@app.get('/api/pm/automation-rules')
async def list_pm_automation_rules(request: Request) -> List[dict[str, Any]]:
    require_write_access(request)
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT * FROM pm_automation_rules ORDER BY name',
        )
        rows = await cursor.fetchall()
    return [parse_pm_rule_row(row) for row in rows]


@app.post('/api/pm/automation-rules')
async def create_pm_automation_rule(request: Request, body: PmAutomationRuleCreate) -> dict[str, Any]:
    require_write_access(request)
    if body.scope_type not in ('all', 'location', 'model'):
        raise HTTPException(status_code=400, detail='Invalid scope_type')
    template = await fetch_pm_template(body.template_id)
    if not template:
        raise HTTPException(status_code=404, detail='PM template not found')
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            '''
            INSERT INTO pm_automation_rules (
                name, template_id, enabled, scope_type, scope_values,
                lead_days, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                body.name.strip(),
                body.template_id,
                1 if body.enabled else 0,
                body.scope_type,
                json.dumps(body.scope_values),
                body.lead_days,
                now,
                now,
            ),
        )
        rule_id = cursor.lastrowid
        await connection.commit()
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT * FROM pm_automation_rules WHERE id = ?',
            (rule_id,),
        )
        row = await cursor.fetchone()
    await record_audit(
        request,
        'created',
        'pm_automation_rule',
        rule_id,
        f'Created PM automation rule {body.name.strip()}',
    )
    return parse_pm_rule_row(row)


@app.put('/api/pm/automation-rules/{rule_id}')
async def update_pm_automation_rule(
    request: Request,
    rule_id: int,
    body: PmAutomationRuleUpdate,
) -> dict[str, Any]:
    require_write_access(request)
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT * FROM pm_automation_rules WHERE id = ?',
            (rule_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Automation rule not found')
        current = parse_pm_rule_row(row)

    payload = body.model_dump(exclude_unset=True)
    if 'scope_type' in payload and payload['scope_type'] not in ('all', 'location', 'model'):
        raise HTTPException(status_code=400, detail='Invalid scope_type')
    if 'template_id' in payload:
        template = await fetch_pm_template(payload['template_id'])
        if not template:
            raise HTTPException(status_code=404, detail='PM template not found')

    next_rule = {**current, **payload}
    if 'scope_values' in payload:
        next_rule['scope_values'] = payload['scope_values']
    if 'enabled' in payload:
        next_rule['enabled'] = payload['enabled']

    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            '''
            UPDATE pm_automation_rules
            SET name = ?, template_id = ?, enabled = ?, scope_type = ?,
                scope_values = ?, lead_days = ?, updated_at = ?
            WHERE id = ?
            ''',
            (
                next_rule['name'],
                next_rule['template_id'],
                1 if next_rule['enabled'] else 0,
                next_rule['scope_type'],
                json.dumps(next_rule['scope_values']),
                next_rule['lead_days'],
                now,
                rule_id,
            ),
        )
        await connection.commit()
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            'SELECT * FROM pm_automation_rules WHERE id = ?',
            (rule_id,),
        )
        row = await cursor.fetchone()
    await record_audit(request, 'updated', 'pm_automation_rule', rule_id, f'Updated PM automation rule {next_rule["name"]}')
    return parse_pm_rule_row(row)


@app.delete('/api/pm/automation-rules/{rule_id}')
async def delete_pm_automation_rule(request: Request, rule_id: int) -> dict[str, bool]:
    require_write_access(request)
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            'SELECT name FROM pm_automation_rules WHERE id = ?',
            (rule_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Automation rule not found')
        await connection.execute('DELETE FROM pm_automation_rules WHERE id = ?', (rule_id,))
        await connection.commit()
    await record_audit(request, 'deleted', 'pm_automation_rule', rule_id, f'Deleted PM automation rule {row[0]}')
    return {'ok': True}


@app.post('/api/pm/automation-rules/run-now')
async def run_pm_automation_now(request: Request) -> dict[str, Any]:
    require_admin(request)
    result = await run_pm_automation(trigger='manual')
    await record_audit(
        request,
        'updated',
        'pm_automation_rule',
        'manual',
        f"Manual PM automation run created {result['created']} record(s)",
        result,
    )
    return result


FLEET_IMPORT_COLUMNS = {
    'id': 'id',
    'cart_id': 'id',
    'serial': 'serial',
    'model': 'model',
    'year': 'year',
    'location': 'location',
    'status': 'status',
    'notes': 'notes',
    'barcode': 'barcode',
    'vin': 'vin',
    'meter_hours': 'meter_hours',
    'purchase_date': 'purchase_date',
    'warranty_expires': 'warranty_expires',
    'acquisition_cost': 'acquisition_cost',
    'home_location': 'home_location',
}


@app.post('/api/admin/fleet-import')
async def import_fleet_csv(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    require_admin(request)
    if not file.filename or not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail='Upload a .csv file')

    raw = await file.read()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('latin-1')

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail='CSV has no header row')

    normalized_headers = {
        (name or '').strip().lower(): name
        for name in reader.fieldnames
        if name
    }
    created = 0
    updated = 0
    errors: list[str] = []

    for line_no, row in enumerate(reader, start=2):
        payload: dict[str, Any] = {}
        for source_key, target_key in FLEET_IMPORT_COLUMNS.items():
            header = normalized_headers.get(source_key)
            if header and row.get(header) not in (None, ''):
                payload[target_key] = row.get(header)

        cart_id = cart_id_str(payload.get('id', ''))
        if not cart_id:
            errors.append(f'Line {line_no}: missing cart id')
            continue

        try:
            values = cart_values_from_payload({
                'serial': payload.get('serial', ''),
                'model': payload.get('model', ''),
                'year': payload.get('year', ''),
                'location': payload.get('location', ''),
                'status': payload.get('status', 'active'),
                'notes': payload.get('notes', ''),
                **{field: payload.get(field) for field in CART_EXTENDED_FIELDS},
            })
            validate_required_cart_fields(values)
            existing = await fetch_cart_row(cart_id)
            async with aiosqlite.connect(DB_PATH) as connection:
                if existing:
                    await connection.execute(
                        '''
                        UPDATE carts SET
                            serial = ?, model = ?, year = ?, location = ?, status = ?, notes = ?,
                            barcode = ?, vin = ?, meter_hours = ?, purchase_date = ?,
                            warranty_expires = ?, acquisition_cost = ?, home_location = ?
                        WHERE id = ?
                        ''',
                        (
                            values['serial'], values['model'], values['year'], values['location'],
                            values['status'], values['notes'], values['barcode'], values['vin'],
                            values['meter_hours'], values['purchase_date'], values['warranty_expires'],
                            values['acquisition_cost'], values['home_location'], cart_id,
                        ),
                    )
                    updated += 1
                else:
                    await connection.execute(
                        '''
                        INSERT INTO carts (
                            id, serial, model, year, location, status, notes,
                            barcode, vin, meter_hours, purchase_date, warranty_expires,
                            acquisition_cost, home_location
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''',
                        (
                            cart_id, values['serial'], values['model'], values['year'],
                            values['location'], values['status'], values['notes'],
                            values['barcode'], values['vin'], values['meter_hours'],
                            values['purchase_date'], values['warranty_expires'],
                            values['acquisition_cost'], values['home_location'],
                        ),
                    )
                    created += 1
                await connection.commit()
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            errors.append(f'Line {line_no} ({cart_id}): {detail}')
        except Exception as exc:
            errors.append(f'Line {line_no} ({cart_id}): {exc}')

    await refresh_carts_cache()
    await record_audit(
        request,
        'updated',
        'fleet_import',
        'csv',
        f'Fleet CSV import: {created} created, {updated} updated',
        {'created': created, 'updated': updated, 'errors': errors[:20]},
    )
    return {'created': created, 'updated': updated, 'errors': errors}


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
            INSERT INTO users (username, display_name, role, password_hash, active, password_changed, created_date)
            VALUES (?, ?, ?, ?, 1, 0, ?)
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


def file_response_with_cache_policy(path: str, target: Path) -> FileResponse:
    response = FileResponse(target)
    if path.endswith(('.js', '.css', '.html')):
        response.headers['Cache-Control'] = 'no-cache, must-revalidate'
    return response


@app.get('/')
def root() -> FileResponse:
    index_html = ROOT_DIR / 'index.html'
    if not index_html.exists():
        raise HTTPException(status_code=404, detail='Index page not found')
    return file_response_with_cache_policy('index.html', index_html)


@app.get('/{path:path}')
def serve_file(path: str) -> FileResponse:
    target = resolve_static_file(path)
    if target:
        return file_response_with_cache_policy(path, target)
    raise HTTPException(status_code=404, detail='File not found')


if __name__ == '__main__':
    import uvicorn

    uvicorn.run('server:app', host='127.0.0.1', port=8000, reload=True)
