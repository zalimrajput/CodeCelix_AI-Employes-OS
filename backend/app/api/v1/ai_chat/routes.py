from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.chat_access import (
    can_see_all_chats,
    user_can_access_conversation,
    allowed_agent_roles,
)
from app.ai.guardrails import is_flagged, refuse_reply, sanitize_input
from app.ai.orchestrator import execute_turn
from app.ai.memory import remember
from app.api.v1._crud import require_org_member
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.ai_conversation import AIConversation
from app.models.ai_employee import AIEmployee
from app.models.ai_message import AIMessage


router = APIRouter(
    prefix="/ai-chat",
    tags=["AI Chat"]
)


class ConversationCreate(BaseModel):
    ai_employee_id: UUID | None = None
    title: str | None = None


class ImageUrlInput(BaseModel):
    url: str


class ImageInput(BaseModel):
    """OpenAI-style image part; url must be a ``data:image/...;base64,...`` URI."""

    type: Literal["image_url"] = "image_url"
    image_url: ImageUrlInput


_MAX_IMAGES = 4
_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


def _validate_images(images: list[ImageInput]) -> list[dict]:
    """Validate image attachments and return OpenAI-style image_url parts."""
    if len(images) > _MAX_IMAGES:
        raise HTTPException(status_code=422, detail=f"At most {_MAX_IMAGES} images per message")
    parts: list[dict] = []
    for img in images:
        url = img.image_url.url
        if not url.startswith("data:image/") or "," not in url:
            raise HTTPException(status_code=422, detail="Image must be a data:image URI")
        mime = url[5:].split(";")[0].strip().lower()
        if mime not in _ALLOWED_IMAGE_MIMES:
            raise HTTPException(status_code=422, detail=f"Unsupported image type: {mime}")
        if len(url.split(",", 1)[1]) * 3 // 4 > _MAX_IMAGE_BYTES:
            raise HTTPException(status_code=422, detail="Image too large (max 5 MB)")
        parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts


class MessageCreate(BaseModel):
    conversation_id: UUID
    content: str | None = None
    message: str | None = None
    images: list[ImageInput] = []

    def text(self) -> str:
        return self.content or self.message or ""


class ConversationOut(BaseModel):
    id: UUID
    ai_employee_id: UUID | None
    title: str | None
    status: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    message: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class VoiceMessageOut(MessageOut):
    """Assistant reply plus the transcribed text so the caller can verify it."""

    transcribed_text: str | None = None


@router.get("/conversations", response_model=list[ConversationOut])
# Protected endpoint: lists the caller's organization AI conversations.
def list_conversations(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = require_org_member(db, current_user)
    # Department isolation: users only see conversations they own or that are
    # bound to their department's AI employee. Admins see all org chats.
    conversations = (
        db.query(AIConversation)
        .filter(AIConversation.organization_id == me.organization_id)
        .order_by(AIConversation.created_at.desc())
        .all()
    )
    is_admin = can_see_all_chats(db, me)
    if is_admin:
        return conversations
    allowed = allowed_agent_roles(db, me)
    return [
        c
        for c in conversations
        if user_can_access_conversation(
            conversation=c, is_owner=(c.user_id == me.id), is_admin=False, allowed_roles=allowed
        )
    ]


@router.post("/conversations", response_model=ConversationOut, status_code=201)
# Protected endpoint: creates an AI conversation inside the caller's org.
def create_conversation(
    data: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = require_org_member(db, current_user)
    if data.ai_employee_id is not None:
        employee = db.query(AIEmployee).filter(
            AIEmployee.id == data.ai_employee_id,
            AIEmployee.organization_id == me.organization_id,
        ).first()
        if employee is None:
            raise HTTPException(status_code=404, detail="AI employee not found")
        # Department isolation — same rule as read/send. The owner bypass does
        # NOT apply here: the creator becomes the owner, so allowing it would
        # nullify the check and let any member start chats with other
        # departments' AI employees.
        if not can_see_all_chats(db, me) and employee.role not in allowed_agent_roles(db, me):
            raise HTTPException(status_code=403, detail="You don't have access to this AI employee")
    elif not can_see_all_chats(db, me):
        # Non-admins must bind a concrete employee of their own department —
        # an unbound conversation falls back to the default agent.
        raise HTTPException(status_code=403, detail="Choose an AI employee of your department")
    conversation = AIConversation(
        organization_id=me.organization_id,
        user_id=me.id,
        ai_employee_id=data.ai_employee_id,
        title=data.title or "New conversation",
        status="active",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
# Protected endpoint: lists the messages of one org-scoped conversation.
def list_messages(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = require_org_member(db, current_user)
    conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.organization_id == me.organization_id,
    ).first()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not user_can_access_conversation(
        conversation=conversation,
        is_owner=(conversation.user_id == me.id),
        is_admin=can_see_all_chats(db, me),
        allowed_roles=allowed_agent_roles(db, me),
    ):
        raise HTTPException(status_code=403, detail="You don't have access to this conversation")
    return (
        db.query(AIMessage)
        .filter(AIMessage.conversation_id == conversation_id)
        .order_by(AIMessage.created_at)
        .all()
    )


@router.post("/messages", response_model=MessageOut, status_code=201)
# Protected endpoint: sends a message; stores the user message and a reply.
def send_message(
    data: MessageCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = require_org_member(db, current_user)
    conversation = db.query(AIConversation).filter(
        AIConversation.id == data.conversation_id,
        AIConversation.organization_id == me.organization_id,
    ).first()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not user_can_access_conversation(
        conversation=conversation,
        is_owner=(conversation.user_id == me.id),
        is_admin=can_see_all_chats(db, me),
        allowed_roles=allowed_agent_roles(db, me),
    ):
        raise HTTPException(status_code=403, detail="You don't have access to this conversation")

    image_parts = _validate_images(data.images)
    text = sanitize_input(data.text())
    if text is None and not image_parts:
        raise HTTPException(status_code=422, detail="Message must be 1-16000 chars")
    # Allow an images-only message ("what does this screenshot show?").
    if text is None:
        text = "Describe the attached image(s)."

    # The conversation already joined-loads its AI employee.
    employee = conversation.ai_employee

    user_message = AIMessage(
        organization_id=me.organization_id,
        conversation_id=conversation.id,
        role="user",
        message=text,
    )
    db.add(user_message)

    if is_flagged(text):
        reply_text = refuse_reply()
    else:
        history = (
            db.query(AIMessage)
            .filter(AIMessage.conversation_id == conversation.id)
            .order_by(AIMessage.created_at)
            .limit(20)
            .all()
        )
        reply_text, _agent_key = execute_turn(
            db,
            me.organization_id,
            str(me.id),
            conversation,
            text,
            employee=employee,
            history_messages=history,
            images=image_parts,
        )
        if employee is not None:
            remember(
                db, me.organization_id, str(employee.id), f"{text} -> {reply_text}"
            )

    reply = AIMessage(
        organization_id=me.organization_id,
        conversation_id=conversation.id,
        role="assistant",
        message=reply_text,
    )
    db.add(reply)
    db.commit()
    db.refresh(reply)
    return reply


def _complete_turn(db, me, conversation, text, *, source: str = "text"):
    """Run the shared user->assistant turn when the message already has text.

    Mirrors the send_message body so voice and text messages follow the exact
    same orchestration path; only the user message's origin marker differs.
    """
    # The conversation already joined-loads its AI employee.
    employee = conversation.ai_employee

    user_message = AIMessage(
        organization_id=me.organization_id,
        conversation_id=conversation.id,
        role="user",
        message=text,
    )
    if source == "voice":
        user_message.message_metadata = {"source": "voice"}
    db.add(user_message)

    if is_flagged(text):
        reply_text = refuse_reply()
    else:
        history = (
            db.query(AIMessage)
            .filter(AIMessage.conversation_id == conversation.id)
            .order_by(AIMessage.created_at)
            .limit(20)
            .all()
        )
        reply_text, _agent_key = execute_turn(
            db,
            me.organization_id,
            str(me.id),
            conversation,
            text,
            employee=employee,
            history_messages=history,
        )
        if employee is not None:
            remember(
                db, me.organization_id, str(employee.id), f"{text} -> {reply_text}"
            )

    reply = AIMessage(
        organization_id=me.organization_id,
        conversation_id=conversation.id,
        role="assistant",
        message=reply_text,
    )
    db.add(reply)
    db.commit()
    db.refresh(reply)
    return reply


@router.post("/messages/voice", response_model=VoiceMessageOut, status_code=201)
# Protected endpoint: same chat flow, but the input is a spoken audio file.
def send_voice_message(
    conversation_id: UUID = Form(...),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = require_org_member(db, current_user)
    conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.organization_id == me.organization_id,
    ).first()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not user_can_access_conversation(
        conversation=conversation,
        is_owner=(conversation.user_id == me.id),
        is_admin=can_see_all_chats(db, me),
        allowed_roles=allowed_agent_roles(db, me),
    ):
        raise HTTPException(status_code=403, detail="You don't have access to this conversation")

    audio_bytes = audio.file.read() if audio else b""
    filename = (audio.filename or "voice-recording.webm").rsplit("/", 1)[-1]
    mime_type = audio.content_type or None

    from app.integrations.transcription.client import (
        TranscriptionError,
        TranscriptionNotConfiguredError,
        transcribe_audio,
    )

    try:
        transcription = transcribe_audio(audio_bytes, filename, mime_type)
    except TranscriptionNotConfiguredError:
        raise HTTPException(
            status_code=422,
            detail="Voice input isn't configured — set OPENAI_API_KEY",
        )
    except TranscriptionError as exc:
        raise HTTPException(status_code=422, detail=f"Voice transcription failed: {exc}")

    transcribed = str(transcription.get("text") or "").strip()
    if not transcribed:
        raise HTTPException(status_code=422, detail="No speech recognized in audio")

    text = sanitize_input(transcribed)
    if text is None:
        raise HTTPException(status_code=422, detail="Message must be 1-16000 chars")

    reply = _complete_turn(db, me, conversation, text, source="voice")
    return {
        "id": reply.id,
        "conversation_id": reply.conversation_id,
        "role": reply.role,
        "message": reply.message,
        "created_at": reply.created_at,
        "transcribed_text": transcribed,
    }


@router.get("/conversations/{conversation_id}/stream")
# Protected endpoint: streams assistant output (SSE) for a conversation turn.
def stream_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = require_org_member(db, current_user)
    conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.organization_id == me.organization_id,
    ).first()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not user_can_access_conversation(
        conversation=conversation,
        is_owner=(conversation.user_id == me.id),
        is_admin=can_see_all_chats(db, me),
        allowed_roles=allowed_agent_roles(db, me),
    ):
        raise HTTPException(status_code=403, detail="You don't have access to this conversation")
    from fastapi.responses import StreamingResponse

    employee = conversation.ai_employee

    last_message = (
        db.query(AIMessage)
        .filter(AIMessage.conversation_id == conversation.id)
        .order_by(AIMessage.created_at.desc())
        .first()
    )

    def _emit():
        from app.ai.model_router import stream as model_stream

        model = employee.model if employee else None
        prompt = last_message.message if last_message else "Hello"
        try:
            for chunk in model_stream(
                [{"role": "user", "content": prompt}],
                model=model,
                temperature=0.3,
            ):
                yield chunk
        except Exception as exc:  # noqa: BLE001
            yield f"\n\n[stream error: {exc.__class__.__name__}]"

    return StreamingResponse(_emit(), media_type="text/event-stream")
