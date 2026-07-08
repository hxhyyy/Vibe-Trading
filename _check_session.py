import sqlite3
from pathlib import Path

con = sqlite3.connect(Path.home() / ".vibe-trading" / "sessions.db")
con.row_factory = sqlite3.Row
msgs = con.execute(
    'select role, content from messages where session_id=? order by rowid',
    ("72dbfa076848",),
).fetchall()
out = Path("_session_dump.txt")
parts = []
for i, m in enumerate(msgs):
    parts.append(f"\n===== MSG {i} ({m['role']}) =====\n")
    parts.append(m["content"])
out.write_text("".join(parts), encoding="utf-8")
print("wrote", out, "chars", sum(len(p) for p in parts))
