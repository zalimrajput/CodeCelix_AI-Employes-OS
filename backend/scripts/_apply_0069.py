"""One-off: apply migration 0069_remove_employee_user_role.sql to the live DB.

Loads DATABASE_URL from backend/.env (same pattern as verify_0060_seeds.py),
prints before/after counts, then runs the migration inside one transaction.
"""
import os
import sys

import psycopg2

MIGRATION = os.path.join(
    os.path.dirname(__file__), "..", "..", "supabase", "migrations",
    "0069_remove_employee_user_role.sql",
)

CHECKS = [
    ("roles named 'Employee/User'", "SELECT count(*) FROM public.roles WHERE name = 'Employee/User'"),
    ("user_roles pointing at it", "SELECT count(*) FROM public.user_roles ur JOIN public.roles r ON r.id = ur.role_id WHERE r.name = 'Employee/User'"),
    ("dashboard_role_access rows", "SELECT count(*) FROM public.dashboard_role_access WHERE role_name = 'Employee/User'"),
    ("'Employee Dashboard' rows", "SELECT count(*) FROM public.dashboards WHERE name = 'Employee Dashboard'"),
    ("legacy 'Employee' roles kept", "SELECT count(*) FROM public.roles WHERE name = 'Employee'"),
]


def load_env(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main():
    load_env(os.path.join(os.path.dirname(__file__), "..", ".env"))
    url = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
    if not url:
        print("NO_DB_URL")
        sys.exit(1)
    # supabase:// style URLs need to be normalized for psycopg2.
    if url.startswith("postgres."):
        url = url.replace("postgres.", "postgres://", 1)

    conn = psycopg2.connect(url)
    conn.autocommit = False

    def snapshot(label):
        print(f"--- {label} ---")
        cur = conn.cursor()
        for name, sql in CHECKS:
            cur.execute(sql)
            print(f"{name}: {cur.fetchone()[0]}")
        cur.close()

    snapshot("BEFORE")

    with open(MIGRATION, encoding="utf-8") as fh:
        sql_file = fh.read()

    try:
        cur = conn.cursor()
        cur.execute(sql_file)
        cur.close()
        conn.commit()
        print("migration applied OK (transaction committed)")
    except Exception:
        conn.rollback()
        raise

    snapshot("AFTER")

    conn.close()


if __name__ == "__main__":
    main()
