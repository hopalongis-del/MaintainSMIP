"""
title: MaintainSMIP Source Reader
description: |
  CRITICAL: You DO have full access to MaintainSMIP source code via this tool.
  You MUST call read_local_file or grep_local BEFORE saying you lack code access.
  Local root: C:/MaintainSMIP. GitHub fallback is public (no auth).
author: MaintainSMIP
version: 1.0.0
"""

import os
import re
import urllib.request
from typing import Optional

PROJECT_ROOT = r"C:\MaintainSMIP"
GITHUB_RAW = "https://raw.githubusercontent.com/hopalongis-del/MaintainSMIP/main"

ALLOWED_FILES = {
    "settings.js",
    "themes.js",
    "db.js",
    "admin.js",
    "admin.html",
    "index.html",
    "activity.js",
    "activity.html",
    "server.py",
    "shared.css",
    "test_smoke.py",
    "HANDOFF.md",
    "DEPLOY.md",
    "CODEBASE_DIGEST.md",
    "smi_events.js",
}


def _safe_path(filename: str) -> Optional[str]:
    name = os.path.basename(filename.replace("\\", "/").strip())
    if name not in ALLOWED_FILES:
        return None
    local = os.path.join(PROJECT_ROOT, name)
    if os.path.isfile(local):
        return local
    digest = os.path.join(PROJECT_ROOT, "open-webui-knowledge", name)
    if os.path.isfile(digest):
        return digest
    return None


class Tools:
    def __init__(self):
        pass

    def list_source_files(self) -> str:
        """
        List MaintainSMIP source files available locally. Call this first when unsure what exists.
        :return: Filenames readable via read_local_file / grep_local.
        """
        found = []
        for name in sorted(ALLOWED_FILES):
            if _safe_path(name):
                found.append(name)
        if not found:
            return f"No source files found under {PROJECT_ROOT}. Run sync-open-webui-knowledge.ps1"
        return "Readable source files:\n" + "\n".join(f"  - {n}" for n in found)

    def read_local_file(
        self,
        filename: str,
        start_line: int = 1,
        max_lines: int = 200,
    ) -> str:
        """
        Read lines from a MaintainSMIP source file on disk. REQUIRED before claiming no code access.
        :param filename: e.g. settings.js, server.py, CODEBASE_DIGEST.md
        :param start_line: 1-based line number to start (default 1)
        :param max_lines: max lines to return (default 200, cap 500)
        :return: Numbered file excerpt or error.
        """
        path = _safe_path(filename)
        if not path:
            allowed = ", ".join(sorted(ALLOWED_FILES))
            return f"Unknown or missing file: {filename}. Allowed: {allowed}"
        max_lines = min(max(max_lines, 1), 500)
        start_line = max(start_line, 1)
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError as e:
            return f"Read error for {filename}: {e}"

        end = min(start_line - 1 + max_lines, len(lines))
        if start_line > len(lines):
            return f"{filename} has only {len(lines)} lines; start_line {start_line} is past EOF."
        chunk = lines[start_line - 1 : end]
        body = "".join(f"{start_line + i:5d}| {line}" for i, line in enumerate(chunk))
        more = ""
        if end < len(lines):
            more = f"\n... ({len(lines) - end} more lines; call again with start_line={end + 1})"
        return f"=== {filename} ({path}) ===\n{body}{more}"

    def grep_local(
        self,
        pattern: str,
        filename: str = "",
        max_matches: int = 40,
    ) -> str:
        """
        Search MaintainSMIP source for a text pattern (case-insensitive substring).
        :param pattern: e.g. require_authenticated_user, applySettings, APP_VERSION
        :param filename: optional single file; empty = search all allowed files
        :param max_matches: cap on match lines (default 40)
        :return: file:line: text hits or no-match message.
        """
        if not pattern.strip():
            return "pattern is required"
        max_matches = min(max(max_matches, 1), 100)
        targets = [filename] if filename else sorted(ALLOWED_FILES)
        hits = []
        needle = pattern.lower()
        for name in targets:
            path = _safe_path(name)
            if not path:
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if needle in line.lower():
                            hits.append(f"{name}:{i}: {line.rstrip()}")
                            if len(hits) >= max_matches:
                                break
            except OSError:
                continue
            if len(hits) >= max_matches:
                break
        if not hits:
            scope = filename or "all source files"
            return f"No matches for '{pattern}' in {scope}"
        suffix = ""
        if len(hits) >= max_matches:
            suffix = f"\n(capped at {max_matches} matches)"
        return "\n".join(hits) + suffix

    def fetch_github_file(
        self,
        filename: str,
        start_line: int = 1,
        max_lines: int = 200,
    ) -> str:
        """
        Fetch a file from public GitHub raw (fallback if local disk read fails).
        :param filename: e.g. settings.js, server.py
        :param start_line: 1-based start line
        :param max_lines: lines to return (max 500)
        :return: Numbered excerpt from GitHub main branch.
        """
        name = os.path.basename(filename.replace("\\", "/").strip())
        if name not in ALLOWED_FILES:
            return f"Not allowed: {name}"
        url = f"{GITHUB_RAW}/{name}"
        max_lines = min(max(max_lines, 1), 500)
        start_line = max(start_line, 1)
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                text = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            return f"GitHub fetch failed for {url}: {e}"
        lines = text.splitlines(keepends=True)
        end = min(start_line - 1 + max_lines, len(lines))
        if start_line > len(lines):
            return f"{name} from GitHub has only {len(lines)} lines."
        chunk = lines[start_line - 1 : end]
        body = "".join(f"{start_line + i:5d}| {line}" for i, line in enumerate(chunk))
        more = ""
        if end < len(lines):
            more = f"\n... ({len(lines) - end} more lines; start_line={end + 1})"
        return f"=== {name} (GitHub main) ===\n{body}{more}"