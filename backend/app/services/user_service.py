import httpx

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_role import UserRole
from app.models.role import Role
from app.core.config import settings
from app.core.validators import validate_password


def create_user(
    db: Session,
    data
):
    """Create a user: Supabase Auth user (admin API) + public.users profile row.

    No password is stored in the local database - Supabase Auth owns the
    credentials. The handle_new_user trigger creates the profile row when the
    auth user is inserted, so here we only fill in the org / profile fields.
    The requested role (must exist in the org; defaults to none assigned when
    omitted) is assigned via user_roles.
    """
    validate_password(
        data.password
    )

    url = f"{settings.SUPABASE_URL}/auth/v1/admin/users"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "email": data.email,
        "password": data.password,
        "email_confirm": True,
        "user_metadata": {
            "full_name": data.full_name or ""
        }
    }

    try:
        resp = httpx.post(
            url,
            json=payload,
            headers=headers,
            timeout=20
        )
    except httpx.HTTPError:
        raise ValueError(
            "Auth service unavailable"
        )

    if resp.status_code >= 400:
        msg = resp.text[:200]
        raise ValueError(
            f"Supabase user creation failed: {msg}"
        )

    auth_user = resp.json()
    auth_id = auth_user["id"]

    # The signup trigger may have already created the profile row.
    user = db.query(
        User
    ).filter(
        User.id == auth_id
    ).first()

    if user is None:
        user = User(
            id=auth_id,
            email=data.email
        )
        db.add(user)

    user.organization_id = data.organization_id
    user.full_name = data.full_name or user.full_name
    user.phone = data.phone or user.phone
    user.email = data.email

    db.flush()

    # Assign the requested role (optional; the frontend invite form always
    # sends one). The role must belong to the same organization; an empty or
    # unknown name means no role is assigned (the member can be updated later).
    role_name = (data.role_name or "").strip()
    role = db.query(Role).filter(
        Role.organization_id == data.organization_id,
        Role.name == role_name,
    ).first()

    if role is not None:
        already = db.query(UserRole).filter(
            UserRole.user_id == user.id,
            UserRole.role_id == role.id,
        ).first()
        if already is None:
            db.add(UserRole(
                user_id=user.id,
                role_id=role.id,
                organization_id=data.organization_id,
            ))

    db.commit()
    db.refresh(user)

    return user


def list_org_users(
    db: Session,
    organization_id
):
    """Return all users belonging to an organization (with their role names)."""
    users = db.query(User).filter(
        User.organization_id == organization_id
    ).order_by(User.created_at).all()

    return [
        {
            **{c.name: getattr(u, c.name) for c in User.__table__.columns},
            "roles": [
                ur.role.name
                for ur in u.user_roles
                if ur.role is not None
            ],
        }
        for u in users
    ]


def delete_user(
    db: Session,
    user_id,
    organization_id
):
    """Delete a user from the same organization (admin API + local rows).

    Raises ValueError if the user is not found or belongs to another org.
    """
    user = db.query(User).filter(
        User.id == user_id
    ).first()

    if user is None:
        raise ValueError("User not found")
    if str(user.organization_id) != str(organization_id):
        raise ValueError("User does not belong to this organization")

    url = f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    }

    try:
        resp = httpx.delete(url, headers=headers, timeout=20)
    except httpx.HTTPError:
        raise ValueError("Auth service unavailable")

    # Deleting the Auth user cascades to public.users (FK ON DELETE CASCADE)
    # and user_roles. If the auth delete failed for any reason other than
    # "already gone", raise so the caller knows the user was not removed.
    if resp.status_code not in (200, 204, 404):
        msg = resp.text[:200]
        raise ValueError(f"Supabase user deletion failed: {msg}")

    # Belt-and-braces: ensure the local profile row is gone even if the
    # auth delete returned 404 (user already deleted upstream).
    db.query(UserRole).filter(
        UserRole.user_id == user_id
    ).delete(synchronize_session=False)
    existing = db.query(User).filter(User.id == user_id).first()
    if existing is not None:
        db.delete(existing)
    db.commit()

    return {"id": str(user_id), "deleted": True}
