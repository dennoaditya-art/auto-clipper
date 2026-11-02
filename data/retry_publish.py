import sys, time, datetime
sys.path.insert(0, r"D:\clipper")
from autoclip.config import load_settings
from autoclip.db import connect, init_db
from autoclip.publish import publish_approved

s = load_settings(r"D:\clipper")
conn = connect(s.paths.database)
init_db(conn)

def pending():
    rows = conn.execute(
        """
        SELECT c.id FROM clips c
        LEFT JOIN publications p
          ON p.clip_id = c.id AND p.platform='youtube' AND p.account_id=c.account_id
        WHERE c.status='approved' AND (p.id IS NULL OR p.status != 'published')
        ORDER BY c.id
        """
    ).fetchall()
    return [int(r[0]) for r in rows]

for attempt in range(1, 41):
    ids = pending()
    if not ids:
        print("DONE semua terjadwal", flush=True)
        break
    print(attempt, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "pending", ids, flush=True)
    res = publish_approved(s, conn, only_auto=False, schedule=True)
    print("  published", res["published"], "errors", len(res["errors"]), flush=True)
    if not res["published"] and res["errors"]:
        time.sleep(40 * 60)
    else:
        time.sleep(5 * 60)
conn.close()

