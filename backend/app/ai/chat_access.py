"""Department-level access control for AI chat.

Every org member used to see every org conversation. This module scopes chat to
departments: a user sees their own conversations plus conversations with the AI
employees of their department (Sales users <-> AI Sales Assistant, Finance <-> AI
Finance Assistant / AI Accountant, ...). Company admins and platform super admins
see everything.

Mirrors the frontend mapping in frontend/src/lib/agents.ts (ROLE_TO_AGENT).
"""
from sqlalchemy.orm import Session

from app.models.platform import PlatformRole
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole

# Roles that may administer an organization (mirrors app.api.v1._crud).
ADMIN_ROLE_NAMES = {"Company Admin", "CEO / Executive", "Owner", "Admin"}

# Human role -> AI employee roles the user may chat with (department access).
# Departments with two agents (Finance, Operations) allow both.
HUMAN_ROLE_TO_AGENT_ROLES: dict[str, set[str]] = {
    "Sales Manager": {"Sales Assistant"},
    "Sales Executive": {"Sales Assistant"},
    "Finance Manager": {"Finance Assistant", "Accountant"},
    "Accountant": {"Accountant"},
    "HR Manager": {"HR Assistant"},
    "Customer Support": {"Customer Support Agent"},
    "Marketing Manager": {"Marketing Assistant"},
    "Operations Manager": {"Inventory Manager", "Procurement Assistant"},
    # Legacy migration-0059 "Employee" rows (the assignable Employee/User role
    # was removed) keep the personal Executive assistant mapping.
    "Employee": {"Executive Assistant"},
}


def user_roles_in_org(db: Session, user: User) -> set[str]:
    """The user's company role names for their org (e.g. Sales Executive)."""
    names = {
        rn
        for (rn,) in (
            db.query(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(
                UserRole.user_id == user.id,
                UserRole.organization_id == user.organization_id,
            )
            .all()
        )
    }
    return names


def is_platform_super_admin(db: Session, user: User) -> bool:
    """Whether the user holds the platform Super Admin role."""
    row = (
        db.query(PlatformRole)
        .filter(PlatformRole.user_id == user.id)
        .first()
    )
    return row is not None


def can_see_all_chats(db: Session, user: User) -> bool:
    """Admins (Company Admin, CEO, super admin, legacy Owner/Admin) see all."""
    names = user_roles_in_org(db, user)
    if names & ADMIN_ROLE_NAMES:
        return True
    return is_platform_super_admin(db, user)


def allowed_agent_roles(db: Session, user: User) -> set[str]:
    """AI employee roles this user's department may chat with."""
    allowed: set[str] = set()
    for role_name in user_roles_in_org(db, user):
        allowed.update(HUMAN_ROLE_TO_AGENT_ROLES.get(role_name, set()))
    # The owner can always keep chatting with agents they already used.
    return allowed


def user_can_access_conversation(
    *,
    conversation,
    is_owner: bool,
    is_admin: bool,
    allowed_roles: set[str],
) -> bool:
    """True when a user may open/send in a conversation.

    Owners always have access; admins and super admins see everything;
    everyone else may only access conversations with their department's
    AI employee.
    """
    if is_owner or is_admin:
        return True
    return (
        conversation.ai_employee is not None
        and conversation.ai_employee.role in allowed_roles
    )
