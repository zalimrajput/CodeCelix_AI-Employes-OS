"""Seed demo accounts for the 3-role login setup.

Creates (idempotently):
  * superadmin@demo.com  — platform Super Admin (no org, platform_roles row)
  * orgadmin@demo.com    — Company Admin of "Demo Company"   * employee@demo.com    — Customer Support member of "Demo Company"

The org is created via a plain INSERT so the trg_seed_default_roles trigger
(0059/0060) seeds the 11 roles + 12 AI employees + 14 dashboards for it.

Run from backend/:
    python scripts/seed_demo_users.py
"""

import os
import uuid

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings

DEMO_ORG = {"name": "Demo Company", "slug": "demo-company", "country": "United States", "industry": "Technology"}

DEMO_ACCOUNTS = [
    {
        "email": "superadmin@demo.com",
        "password": "SuperAdmin@123",
        "full_name": "Demo Super Admin",
        "kind": "super_admin",
    },
    {
        "email": "orgadmin@demo.com",
        "password": "OrgAdmin@123",
        "full_name": "Demo Org Admin",
        "kind": "org_admin",
    },
    {
        "email": "employee@demo.com",
        "password": "Employee@123",
        "full_name": "Demo Employee",
        "kind": "employee",
    },
]


def create_auth_user(email: str, password: str, full_name: str) -> dict:
    """Create (or fetch) a Supabase Auth user via the admin API."""
    url = f"{settings.SUPABASE_URL}/auth/v1/admin/users"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": {"full_name": full_name},
    }
    resp = httpx.post(url, json=payload, headers=headers, timeout=20)
    if resp.status_code in (200, 201):
        return resp.json()
    # Already exists → look it up by email.
    if resp.status_code in (400, 409, 422):
        found = httpx.get(
            f"{url}?email={email}",
            headers={"apikey": settings.SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}"},
            timeout=20,
        )
        if found.status_code == 200 and found.json().get("users"):
            return found.json()["users"][0]
    raise RuntimeError(f"Auth user creation failed for {email}: {resp.status_code} {resp.text[:300]}")


def main() -> None:
    engine = create_engine(settings.DATABASE_URL)
    with Session(engine) as db:
        # 1) Demo Company org (idempotent).
        org = db.execute(
            text("SELECT * FROM organizations WHERE slug = :slug"), {"slug": DEMO_ORG["slug"]}
        ).mappings().first()
        if org is None:
            result = db.execute(
                text(
                    """INSERT INTO organizations (name, slug, industry, country, timezone, settings, created_by)
                       VALUES (:name, :slug, :industry, :country, 'UTC', '{}'::jsonb, NULL)
                       RETURNING *"""
                ),
                DEMO_ORG,
            ).mappings().first()
            db.commit()
            org = result
            print(f"[org] created '{org['name']}' ({org['id']})")
        else:
            print(f"[org] found '{org['name']}' ({org['id']})")

        org_id = org["id"]

        # 2) Demo accounts.
        for acct in DEMO_ACCOUNTS:
            auth_user = create_auth_user(acct["email"], acct["password"], acct["full_name"])
            user_id = uuid.UUID(auth_user["id"])

            # Profile row (the handle_new_user trigger may have created it).
            db.execute(
                text(
                    """INSERT INTO users (id, email, full_name, organization_id, status)
                       VALUES (:id, :email, :full_name, :org_id, 'active')
                       ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email,
                           full_name = EXCLUDED.full_name,
                           organization_id = COALESCE(EXCLUDED.organization_id, users.organization_id),
                           status = 'active'"""
                ),
                {
                    "id": user_id,
                    "email": acct["email"],
                    "full_name": acct["full_name"],
                    "org_id": None if acct["kind"] == "super_admin" else org_id,
                },
            )

            if acct["kind"] == "super_admin":
                # Platform role — no org membership.
                db.execute(
                    text(
                        """INSERT INTO platform_roles (user_id, role)
                           VALUES (:uid, 'Super Admin') ON CONFLICT (user_id) DO NOTHING"""
                    ),
                    {"uid": user_id},
                )
                print(f"[super_admin] {acct['email']} (no org)")
            else:
                # Company role for the demo org.
                role_name = (
                    "Company Admin" if acct["kind"] == "org_admin" else "Customer Support"
                )
                role = db.execute(
                    text("SELECT id FROM roles WHERE organization_id = :oid AND name = :rn"),
                    {"oid": org_id, "rn": role_name},
                ).mappings().first()
                if role is None:
                    raise RuntimeError(f"Role '{role_name}' not found for Demo Company — run migrations 0059/0060 first.")
                db.execute(
                    text(
                        """INSERT INTO user_roles (user_id, role_id, organization_id)
                           VALUES (:uid, :rid, :oid) ON CONFLICT DO NOTHING"""
                    ),
                    {"uid": user_id, "rid": role["id"], "oid": org_id},
                )
                print(f"[{acct['kind']}] {acct['email']} -> {role_name} ({org['name']})")

        db.commit()

    print("\nDemo logins ready:")
    for acct in DEMO_ACCOUNTS:
        print(f"  {acct['email']} / {acct['password']}")


if __name__ == "__main__":
    main()
