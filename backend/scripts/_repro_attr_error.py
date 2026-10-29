"""One-off: reproduce the 'temporarily unavailable (AttributeError)' chat failure.

Runs the real orchestrator path against the live DB with the same AI employee
the chat route would bind — for a text turn AND an image turn.
"""
import os
import sys
import base64
import traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


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


load_env(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.core.database import SessionLocal  # noqa: E402
from app.models.ai_employee import AIEmployee  # noqa: E402
from app.ai.orchestrator import execute_turn  # noqa: E402

db = SessionLocal()
org_id = "58c5ca74-582f-411d-94a1-846804b11208"
employee = (
    db.query(AIEmployee)
    .filter(AIEmployee.organization_id == org_id)
    .order_by(AIEmployee.created_at)
    .first()
)
print("employee:", employee.name, "| role:", employee.role, "| model:", employee.model)

# 1) Plain text turn (control).
try:
    reply, key = execute_turn(
        db, org_id, "00000000-0000-0000-0000-000000000000", None,
        "list my leads", employee, history_messages=[], model=None,
    )
    print("TEXT OK:", reply[:120].replace("\n", " "))
except Exception:
    print("TEXT TURN CRASHED:")
    traceback.print_exc()

# 2) Image turn — 1x1 red PNG data URI (the multimodal path).
tiny_png = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c4944415408d763f8cfc000000301010018dd8db00000000049454e44ae426082"
)).decode()
image_part = {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{tiny_png}"}}

try:
    reply, key = execute_turn(
        db, org_id, "00000000-0000-0000-0000-000000000000", None,
        "What color is this image?", employee,
        history_messages=[], model=None, images=[image_part],
    )
    print("IMAGE OK:", reply[:120].replace("\n", " "))
except Exception:
    print("IMAGE TURN CRASHED:")
    traceback.print_exc()

db.close()
