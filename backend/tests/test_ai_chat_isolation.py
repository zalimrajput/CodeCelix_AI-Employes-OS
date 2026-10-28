"""Department-level chat isolation tests.

Sales users only see their own conversations + AI Sales Assistant chats;
Finance users only AI Finance/Accountant chats; company admins see all.
"""
import sys
import uuid

sys.path.insert(0, ".")

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.ai_chat.routes import ConversationCreate, create_conversation, list_conversations, list_messages


def _org(db):
    from app.models.organization import Organization

    org = Organization(
        name="Isolation Org",
        slug=f"iso-{uuid.uuid4().hex[:10]}",
        settings={},
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _teardown(db, org):
    deletes = [
        "DELETE FROM ai_messages WHERE organization_id = :id",
        "DELETE FROM ai_conversations WHERE organization_id = :id",
        "DELETE FROM ai_employees WHERE organization_id = :id",
        "DELETE FROM user_roles WHERE organization_id = :id",
        "DELETE FROM roles WHERE organization_id = :id",
        "DELETE FROM users WHERE organization_id = :id",
        "DELETE FROM organizations WHERE id = :id",
    ]
    for statement in deletes:
        db.execute(text(statement), {"id": org.id})
    db.commit()


def _user(db, org, name):
    from app.models.user import User

    user = User(organization_id=org.id, full_name=name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _role(db, org, name):
    from app.models.role import Role

    role = Role(organization_id=org.id, name=name)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def _assign_role(db, org, user, role_name):
    from app.models.role import Role
    from app.models.user_role import UserRole

    # Roles are unique per (organization_id, name) — reuse or create.
    role = (
        db.query(Role)
        .filter(Role.organization_id == org.id, Role.name == role_name)
        .first()
    )
    if role is None:
        role = Role(organization_id=org.id, name=role_name)
        db.add(role)
        db.commit()
        db.refresh(role)
    db.add(UserRole(user_id=user.id, role_id=role.id, organization_id=org.id))
    db.commit()


def _ai_employee(db, org, name, role):
    from app.models.ai_employee import AIEmployee

    # AI employee names are unique per org — reuse if the row exists.
    emp = (
        db.query(AIEmployee)
        .filter(AIEmployee.organization_id == org.id, AIEmployee.name == name)
        .first()
    )
    if emp is None:
        emp = AIEmployee(organization_id=org.id, name=name, role=role)
        db.add(emp)
        db.commit()
        db.refresh(emp)
    return emp


def _conversation(db, org, user, employee):
    from app.models.ai_conversation import AIConversation

    conv = AIConversation(
        organization_id=org.id,
        user_id=user.id,
        ai_employee_id=employee.id if employee is not None else None,
        title="Isolation test",
        status="active",
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@pytest.mark.db
def test_department_isolation_sales_versus_finance(db):
    # Clear any failed-transaction state from a previous run.
    db.rollback()
    org = _org(db)
    try:
        sales = _user(db, org, "Sales Executive")
        _assign_role(db, org, sales, "Sales Executive")
        finance = _user(db, org, "Finance Manager")
        _assign_role(db, org, finance, "Finance Manager")

        sales_emp = _ai_employee(db, org, "AI Sales Assistant", "Sales Assistant")
        finance_emp = _ai_employee(db, org, "AI Finance Assistant", "Finance Assistant")

        sales_conv = _conversation(db, org, sales, sales_emp)
        finance_conv = _conversation(db, org, finance, finance_emp)
        # A conversation with no AI employee (legacy) — only its owner sees it.
        legacy_conv = _conversation(db, org, sales, None)

        # Sales Executive: sees own chats + AI Sales Assistant chats only.
        sales_ids = {str(c.id) for c in list_conversations(db, {"sub": str(sales.id)})}
        assert str(sales_conv.id) in sales_ids
        assert str(legacy_conv.id) in sales_ids  # owner
        assert str(finance_conv.id) not in sales_ids  # NOT finance's chat

        # Finance Manager: sees own + AI Finance/Accountant chats only.
        finance_ids = {str(c.id) for c in list_conversations(db, {"sub": str(finance.id)})}
        assert str(finance_conv.id) in finance_ids
        assert str(sales_conv.id) not in finance_ids
        assert str(legacy_conv.id) not in finance_ids  # not the owner

        # Direct access attempts across departments are rejected.
        with pytest.raises(HTTPException) as excinfo:
            list_messages(
                conversation_id=sales_conv.id,
                db=db,
                current_user={"sub": str(finance.id)},
            )
        assert excinfo.value.status_code == 403

        # Owners and admins can always open their conversations.
        assert list_messages(
            conversation_id=sales_conv.id,
            db=db,
            current_user={"sub": str(sales.id)},
        ) == []
    finally:
        _teardown(db, org)


@pytest.mark.db
def test_create_conversation_department_gate(db):
    """Regression: POST /conversations must enforce the same department rule
    as read/send — non-admins cannot bind other departments' AI employees,
    and the owner bypass must not apply (the creator becomes the owner).
    """
    db.rollback()
    org = _org(db)
    try:
        finance = _user(db, org, "Finance User")
        _assign_role(db, org, finance, "Finance Manager")
        admin = _user(db, org, "Admin User")
        _assign_role(db, org, admin, "Company Admin")

        hr_emp = _ai_employee(db, org, "AI HR Assistant", "HR Assistant")
        fin_emp = _ai_employee(db, org, "AI Finance Assistant", "Finance Assistant")

        # 1) Finance user + HR Assistant -> 403 (cross-department).
        with pytest.raises(HTTPException) as excinfo:
            create_conversation(
                ConversationCreate(ai_employee_id=hr_emp.id, title="x"),
                db=db,
                current_user={"sub": str(finance.id)},
            )
        assert excinfo.value.status_code == 403

        # 2) Finance user + no employee -> 403 (would fall back to the
        #    default agent and dodge the department rule via owner bypass).
        with pytest.raises(HTTPException) as excinfo:
            create_conversation(
                ConversationCreate(ai_employee_id=None, title="x"),
                db=db,
                current_user={"sub": str(finance.id)},
            )
        assert excinfo.value.status_code == 403

        # 3) Finance user + Finance Assistant -> allowed.
        conv = create_conversation(
            ConversationCreate(ai_employee_id=fin_emp.id, title="ok"),
            db=db,
            current_user={"sub": str(finance.id)},
        )
        assert conv.id is not None

        # 4) Company Admin -> allowed with any employee in the org.
        conv2 = create_conversation(
            ConversationCreate(ai_employee_id=hr_emp.id, title="admin ok"),
            db=db,
            current_user={"sub": str(admin.id)},
        )
        assert conv2.id is not None
    finally:
        _teardown(db, org)


@pytest.mark.db
def test_cross_org_isolation_company_admin(db):
    """A Company Admin's 'see all chats' bypass is scoped to THEIR org —
    they must not see another company's conversations, and foreign
    conversation ids 404 before any admin check runs."""
    db.rollback()
    org_a = _org(db)
    org_b = _org(db)
    try:
        admin_a = _user(db, org_a, "Admin of A")
        _assign_role(db, org_a, admin_a, "Company Admin")
        hr_b = _user(db, org_b, "HR of B")
        _assign_role(db, org_b, hr_b, "HR Manager")

        emp_b = _ai_employee(db, org_b, "AI HR Assistant", "HR Assistant")
        conv_b = _conversation(db, org_b, hr_b, emp_b)

        # Org A admin's list contains ONLY org A conversations (none exist).
        admin_a_ids = {str(c.id) for c in list_conversations(db, {"sub": str(admin_a.id)})}
        assert str(conv_b.id) not in admin_a_ids

        # Direct read of the foreign conversation id -> 404 (org filter runs
        # before the admin bypass).
        with pytest.raises(HTTPException) as excinfo:
            list_messages(
                conversation_id=conv_b.id,
                db=db,
                current_user={"sub": str(admin_a.id)},
            )
        assert excinfo.value.status_code == 404
    finally:
        _teardown(db, org_b)
        _teardown(db, org_a)


@pytest.mark.db
def test_company_admin_sees_all_chats(db):
    db.rollback()
    org = _org(db)
    try:
        admin = _user(db, org, "Company Admin")
        _assign_role(db, org, admin, "Company Admin")
        sales = _user(db, org, "Sales Executive")
        _assign_role(db, org, sales, "Sales Executive")

        sales_emp = _ai_employee(db, org, "AI Sales Assistant", "Sales Assistant")
        hr_emp = _ai_employee(db, org, "AI HR Assistant", "HR Assistant")

        sales_conv = _conversation(db, org, sales, sales_emp)
        hr_conv = _conversation(db, org, sales, hr_emp)

        admin_ids = {str(c.id) for c in list_conversations(db, {"sub": str(admin.id)})}
        assert str(sales_conv.id) in admin_ids
        assert str(hr_conv.id) in admin_ids
    finally:
        _teardown(db, org)
