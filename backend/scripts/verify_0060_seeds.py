"""Verify migration 0060 seeds against the live DB.

Reads DATABASE_URL from backend/.env, then prints counts for:
- the 10 company roles (per org)
- the 12 AI employees (per org)
- the 14 dashboards + dashboard_role_access mapping
- platform layer tables
"""
import os
import sys

from sqlalchemy import create_engine, text

NEW_ROLES = (
    "'Company Admin', 'CEO / Executive', 'Sales Manager', 'Sales Executive', "
    "'HR Manager', 'Finance Manager', 'Accountant', 'Customer Support', "
    "'Marketing Manager', 'Operations Manager'"
)


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

    engine = create_engine(url)
    queries = {
        "total_orgs": "SELECT COUNT(*) FROM organizations",
        "orgs_with_11_roles": (
            "SELECT COUNT(*) FROM ("
            "  SELECT organization_id FROM roles"
            f"  WHERE name IN ({NEW_ROLES})"
            "  GROUP BY organization_id"
            f"  HAVING COUNT(DISTINCT name) = 11"
            ") t"
        ),
        "distinct_new_role_names": (
            f"SELECT COUNT(DISTINCT name) FROM roles WHERE name IN ({NEW_ROLES})"
        ),
        "total_roles_rows": "SELECT COUNT(*) FROM roles",
        "ai_employees_min_per_org": (
            "SELECT COALESCE(MIN(n), 0) FROM ("
            "  SELECT organization_id, COUNT(*) n FROM ai_employees GROUP BY organization_id"
            ") t"
        ),
        "ai_employees_max_per_org": (
            "SELECT COALESCE(MAX(n), 0) FROM ("
            "  SELECT organization_id, COUNT(*) n FROM ai_employees GROUP BY organization_id"
            ") t"
        ),
        "ai_employee_orgs": "SELECT COUNT(DISTINCT organization_id) FROM ai_employees",
        "dashboards_min_per_org": (
            "SELECT COALESCE(MIN(n), 0) FROM ("
            "  SELECT organization_id, COUNT(*) n FROM dashboards GROUP BY organization_id"
            ") t"
        ),
        "dashboards_max_per_org": (
            "SELECT COALESCE(MAX(n), 0) FROM ("
            "  SELECT organization_id, COUNT(*) n FROM dashboards GROUP BY organization_id"
            ") t"
        ),
        "dashboard_role_access_rows": "SELECT COUNT(*) FROM dashboard_role_access",
        "platform_settings_rows": "SELECT COUNT(*) FROM platform_settings",
        "platform_logs_rows": "SELECT COUNT(*) FROM platform_logs",
        "super_admin_count": "SELECT COUNT(*) FROM platform_roles",
    }

    with engine.connect() as conn:
        for label, sql in queries.items():
            try:
                print(f"{label}: {conn.execute(text(sql)).scalar()}")
            except Exception as exc:  # noqa: BLE001
                print(f"{label}: ERROR {type(exc).__name__}: {exc}")

    # Per-org breakdown for the first org, to eyeball exact names.
    with engine.connect() as conn:
        try:
            rows = conn.execute(
                text(
                    f"SELECT name FROM roles WHERE name IN ({NEW_ROLES}) "
                    "ORDER BY organization_id, name LIMIT 40"
                )
            ).fetchall()
            names = sorted({r[0] for r in rows})
            print("new_role_names_seen:", ", ".join(names) if names else "(none)")
        except Exception as exc:  # noqa: BLE001
            print(f"role_names_seen: ERROR {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
