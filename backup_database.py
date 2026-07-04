"""Download a MaintainSMIP database backup to a local folder.

One-time setup:
  1. Copy backup_config.example.json to backup_config.local.json
  2. Fill in base_url, backup_dir, and either username/password OR backup_token
  3. For scheduled backups, set BACKUP_TOKEN on Render and put the same value in backup_token

Manual run:
  python backup_database.py

Windows Task Scheduler (daily example):
  Program: python
  Arguments: "C:\\Claude Code\\backup_database.py"
  Start in: C:\\Claude Code
  Trigger: Daily (e.g. 2:00 AM)
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / 'backup_config.local.json'
EXAMPLE_PATH = ROOT / 'backup_config.example.json'


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f'Missing {CONFIG_PATH.name}. Copy {EXAMPLE_PATH.name} and edit it first.')
        sys.exit(1)
    with CONFIG_PATH.open(encoding='utf-8') as handle:
        return json.load(handle)


def request_json(url: str, payload: dict | None = None, headers: dict | None = None) -> tuple[int, dict | bytes]:
    data = None
    req_headers = {'Accept': 'application/json'}
    if headers:
        req_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        req_headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, data=data, headers=req_headers, method='POST' if payload is not None else 'GET')
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read()
            if 'application/json' in response.headers.get('Content-Type', ''):
                return response.status, json.loads(body.decode('utf-8'))
            return response.status, body
    except urllib.error.HTTPError as err:
        body = err.read()
        try:
            detail = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            detail = {'detail': body.decode('utf-8', errors='replace')}
        return err.code, detail


def login_session(base_url: str, username: str, password: str) -> str:
    import http.cookiejar

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    payload = json.dumps({'username': username, 'password': password}).encode('utf-8')
    request = urllib.request.Request(
        f'{base_url.rstrip("/")}/api/auth/login',
        data=payload,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        method='POST',
    )
    with opener.open(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f'Login failed with status {response.status}')
        body = json.loads(response.read().decode('utf-8'))
        if not body.get('ok'):
            raise RuntimeError('Login failed')

    cookie = next((item.value for item in jar if item.name == 'ms_session'), '')
    if not cookie:
        raise RuntimeError('Login succeeded but no session cookie was returned')
    return cookie


def download_backup(base_url: str, backup_dir: Path, session_cookie: str = '', backup_token: str = '') -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    filename = f'maintainsmip-backup-{timestamp}.db'
    destination = backup_dir / filename

    headers = {'Accept': 'application/x-sqlite3, application/octet-stream'}
    if backup_token:
        headers['Authorization'] = f'Bearer {backup_token}'
    elif session_cookie:
        headers['Cookie'] = f'ms_session={session_cookie}'

    request = urllib.request.Request(
        f'{base_url.rstrip("/")}/api/admin/backup',
        headers=headers,
        method='GET',
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        if response.status != 200:
            raise RuntimeError(f'Backup download failed with status {response.status}')
        data = response.read()

    if not data.startswith(b'SQLite format 3'):
        raise RuntimeError('Downloaded file does not look like a SQLite database')

    destination.write_bytes(data)
    return destination


def prune_old_backups(backup_dir: Path, keep_days: int) -> int:
    if keep_days <= 0:
        return 0
    cutoff = datetime.now() - timedelta(days=keep_days)
    removed = 0
    pattern = re.compile(r'^maintainsmip-backup-\d{8}-\d{6}\.db$')
    for path in backup_dir.glob('maintainsmip-backup-*.db'):
        if not pattern.match(path.name):
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime)
        if modified < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def main() -> None:
    config = load_config()
    base_url = str(config.get('base_url', '')).strip()
    backup_dir = Path(str(config.get('backup_dir', '')).strip())
    keep_days = int(config.get('keep_days', 30))
    backup_token = str(config.get('backup_token', '')).strip()
    username = str(config.get('username', '')).strip()
    password = str(config.get('password', '')).strip()

    if not base_url:
        print('base_url is required in backup_config.local.json')
        sys.exit(1)
    if not backup_dir:
        print('backup_dir is required in backup_config.local.json')
        sys.exit(1)

    session_cookie = ''
    if backup_token:
        print('Using backup token authentication.')
    else:
        if not username or not password:
            print('Set username/password or backup_token in backup_config.local.json')
            sys.exit(1)
        print(f'Logging in as {username}…')
        session_cookie = login_session(base_url, username, password)

    print(f'Downloading backup from {base_url}…')
    saved = download_backup(base_url, backup_dir, session_cookie=session_cookie, backup_token=backup_token)
    removed = prune_old_backups(backup_dir, keep_days)
    size_kb = saved.stat().st_size / 1024
    print(f'Saved {saved} ({size_kb:.1f} KB)')
    if removed:
        print(f'Removed {removed} backup(s) older than {keep_days} days')


if __name__ == '__main__':
    main()