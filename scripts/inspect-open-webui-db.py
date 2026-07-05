"""Inspect Open WebUI knowledge collections (local diagnostic)."""
import sqlite3
import json
from pathlib import Path

DB = Path(r"C:\Users\hopal\AppData\Roaming\open-webui\data\webui.db")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=== KNOWLEDGE COLLECTIONS ===")
for row in cur.execute("SELECT id, name, description FROM knowledge ORDER BY name"):
    print(f"  {row['name']}")
    print(f"    id: {row['id']}")
    print(f"    desc: {row['description']}")
    files = cur.execute(
        """
        SELECT f.filename, f.meta
        FROM knowledge_file kf
        JOIN file f ON f.id = kf.file_id
        WHERE kf.knowledge_id = ?
        ORDER BY f.filename
        """,
        (row["id"],),
    ).fetchall()
    print(f"    files ({len(files)}):")
    for f in files:
        print(f"      - {f['filename']}")
    print()

print("=== MaintainSMIP MODEL CONFIG ===")
row = cur.execute(
    "SELECT id, base_model_id, meta, params FROM model WHERE id = 'maintainsmip'"
).fetchone()
if row:
    meta = json.loads(row["meta"] or "{}")
    print(f"  base: {row['base_model_id']}")
    print(f"  capabilities: {json.dumps(meta.get('capabilities', {}), indent=2)}")
    print(f"  knowledge attached: {json.dumps(meta.get('knowledge', []), indent=2)}")
    print(f"  toolIds: {meta.get('toolIds', [])}")
    print(f"  builtin_tools: {meta.get('builtin_tools', meta.get('builtinTools', 'N/A'))}")
else:
    print("  maintainsmip model not found")

conn.close()