import sys
from pathlib import Path

sys.path.insert(0, r"D:\clipper")
from autoclip.config import load_settings
from autoclip.db import connect, init_db
from autoclip.publish import publish_approved

s = load_settings(r"D:\clipper")
conn = connect(s.paths.database)
init_db(conn)
try:
    rows = conn.execute(
        """
        SELECT c.id FROM clips c
        LEFT JOIN publications p
          ON p.clip_id = c.id AND p.platform='youtube' AND p.account_id=c.account_id
        WHERE c.status='approved' AND (p.id IS NULL OR p.status != 'published')
        ORDER BY c.id
        """
    ).fetchall()
    pending = [int(r[0]) for r in rows]
    if not pending:
        print("tidak ada klip pending")
    else:
        res = publish_approved(s, conn, only_auto=False, schedule=True)
        print("pending", pending, "published", res["published"], "errors", len(res["errors"]))
finally:
    conn.close()
