"""Early backend foundation for 合拍.

Not production-ready: public service must add provider-backed content
moderation, account abuse controls, migrations, monitoring, and legal review.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from bailian_client import BailianConfigurationError, BailianServiceError, chat_completion

load_dotenv()

APP_NAME = "合拍 API"
COOKIE_NAME = "hepai_session"
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
FERNET_KEY = os.getenv("DATA_ENCRYPTION_KEY", "")
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "30"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
CONSENT_VERSION = "memory-v1-2026-10"
TOPIC_IDS = ["goal", "relationship", "routine", "social", "communication", "values", "boundaries", "type", "range", "anything"]

if not SESSION_SECRET:
    raise RuntimeError("SESSION_SECRET must be set")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be set to a persistent database")
if not FERNET_KEY:
    raise RuntimeError("DATA_ENCRYPTION_KEY must be set; generate a Fernet key and keep it secret")

try:
    cipher = Fernet(FERNET_KEY.encode("ascii"))
except (ValueError, UnicodeEncodeError) as exc:
    raise RuntimeError("DATA_ENCRYPTION_KEY must be a valid Fernet key") from exc


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    memory_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wechat_openid_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    adult_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    body_enc: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class MemoryEvent(Base):
    __tablename__ = "memory_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(64))
    body_enc: Mapped[str] = mapped_column(Text)
    source_message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    confidence: Mapped[str] = mapped_column(String(16), default="未评估")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class TopicAnswer(Base):
    __tablename__ = "initial_topic_answers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[str] = mapped_column(String(32))
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
Base.metadata.create_all(engine)

app = FastAPI(title=APP_NAME, version="0.1.0")
allowed_origins = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "http://localhost:8000").split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)
WEB_PROTOTYPE = Path(__file__).resolve().parent.parent / "合拍-交互原型.html"


class ConsentRequest(BaseModel):
    accepted: bool


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    topic_id: str | None = None


def _seal(text: str) -> str:
    return cipher.encrypt(text.encode("utf-8")).decode("ascii")


def _open(value: str) -> str:
    try:
        return cipher.decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=500, detail="记录无法解密；请联系服务支持") from exc


def _session_token(user_id: str, expires: int) -> str:
    message = f"{user_id}.{expires}".encode("ascii")
    signature = hmac.new(SESSION_SECRET.encode("utf-8"), message, hashlib.sha256).digest()
    return f"{user_id}.{expires}.{base64.urlsafe_b64encode(signature).decode('ascii').rstrip('=')}"


def _read_session(request: Request) -> str:
    token = request.cookies.get(COOKIE_NAME, "")
    try:
        user_id, expires_text, signature_text = token.split(".", 2)
        expires = int(expires_text)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="请重新开始会话")
    if expires < int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(status_code=401, detail="会话已过期，请重新开始")
    expected = _session_token(user_id, expires).rsplit(".", 1)[1]
    if not hmac.compare_digest(signature_text, expected):
        raise HTTPException(status_code=401, detail="会话无效")
    return user_id


def _set_session(response: Response, user_id: str) -> None:
    expires = int((datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).timestamp())
    response.set_cookie(
        COOKIE_NAME,
        _session_token(user_id, expires),
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def _user(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="会话不存在，请重新开始")
    return user


def _recent_context(db: Session, user_id: str, query: str) -> list[dict[str, str]]:
    events = db.scalars(select(MemoryEvent).where(MemoryEvent.user_id == user_id).order_by(MemoryEvent.created_at.desc())).all()
    history = db.scalars(select(Message).where(Message.user_id == user_id).order_by(Message.created_at.desc()).limit(12)).all()
    query_terms = set(re.findall(r"[A-Za-z0-9]{2,}|[\u4e00-\u9fff]{2}", query))
    scored: list[tuple[int, MemoryEvent, str]] = []
    for event in events:
        text = _open(event.body_enc)
        terms = set(re.findall(r"[A-Za-z0-9]{2,}|[\u4e00-\u9fff]{2}", text))
        score = len(query_terms & terms)
        scored.append((score, event, text))
    selected = sorted(scored, key=lambda row: (row[0], row[1].created_at), reverse=True)[:18]
    memory_text = "\n".join(f"- [{e.created_at.date().isoformat()}; {e.category}; {e.confidence}] {text[:400]}" for _, e, text in selected)
    result: list[dict[str, str]] = [{
        "role": "system",
        "content": (
            "你是合拍的 AI 交友画像助手，使用中性、清楚的表达，不扮演朋友或恋人。用户可以主动问一般合法问题。"
            "逐步了解用户当前的生活、关系期待和偏好；不声称判断了用户的真实本质，不诊断、不贴道德标签、不判断用户装或说谎。"
            "根据长期交流中的具体依据形成暂时观察，时间较新或反复出现的内容更能代表当前状态；遇到矛盾时保留不同时间和语境，不覆盖历史。"
            "对约炮、一夜情、色情邀约及其常见变体，以及明显违法、赌博、毒品、恶意伤害等请求，警告并拒答，不给操作细节。普通约会和健康关系话题允许回答。AI 不是专业心理或紧急救助服务。"
            "以下是该用户自己的长期记忆，不得透露给别人，也不得从中推断超出证据的结论。"
            f"\n用户时间线记忆：\n{memory_text or '目前还没有长期记忆。'}"
        ),
    }]
    for message in reversed(history):
        result.append({"role": message.role, "content": _open(message.body_enc)})
    return result


def _safety_reply(text: str) -> str | None:
    """Small development-only safety gate; replace with a reviewed service before launch."""
    # Normal dating/romance terms are intentionally allowed; hookup and explicit requests are refused.
    normalized = re.sub(r"[\s\W_]+", "", text.lower())
    crisis_terms = ("自杀", "自残", "不想活", "想死", "结束生命", "伤害自己")
    refusal_terms = (
        '违法犯罪',
        '违法行为',
        '违法',
        '犯罪行为',
        '犯罪',
        '犯法',
        '非法',
        '色情',
        '淫秽',
        '聊黄色',
        '看黄色',
        '黄色内容',
        '黄色视频',
        '黄片',
        '黄赌毒',
        '黄段子',
        '成人影片',
        '成人内容',
        '约炮',
        '约个炮',
        '约一炮',
        '约pao',
        '约p',
        '炮友',
        '一夜情',
        '一夜关系',
        '约一夜',
        '约性',
        '约个睡',
        '约上床',
        '打炮',
        '床伴',
        '裸聊',
        '裸照',
        '性交易',
        '卖淫',
        '嫖娼',
        '招嫖',
        '强奸',
        '性侵',
        '杀人',
        '杀死',
        '谋杀',
        '故意伤害',
        '绑架',
        '拐卖',
        '贩卖人口',
        '盗窃',
        '偷窃',
        '抢劫',
        '诈骗',
        '电信诈骗',
        '网络诈骗',
        '敲诈',
        '勒索',
        '洗钱',
        '行贿',
        '受贿',
        '走私',
        '偷税',
        '逃税',
        '制毒',
        '贩毒',
        '运毒',
        '藏毒',
        '毒品',
        '吸毒',
        '大麻',
        '冰毒',
        '海洛因',
        '可卡因',
        '摇头丸',
        '芬太尼',
        '麻古',
        '赌博',
        '赌钱',
        '打赌',
        '赌注',
        '赌球',
        '赌马',
        '下注',
        '博彩',
        '赌场',
        '六合彩',
        '百家乐',
        '老虎机',
        '赌局',
        '炸弹',
        '爆炸物',
        '纵火',
        '放火',
        '投毒',
        '下毒',
        '枪支',
        '买凶',
        '雇凶',
        '销毁证据',
        '毁灭证据',
        '肇事逃逸',
        '黑客攻击',
        '入侵系统',
        '盗号',
        '钓鱼攻击',
        '勒索病毒',
        'pornography',
        'porn',
        'hookup',
        'casual sex',
        'one night stand',
        'fuckbuddy',
        'booty call',
        'friends with benefits',
        'nude',
        'gambling',
        'casino',
        'drug dealing',
        'drugs',
        'murder',
        'kill',
        'rape',
        'fraud',
        'scam',
        'robbery',
        'theft',
        'bomb',
        'weapons',
    )
    if any(term in normalized for term in crisis_terms):
        return "你提到的内容可能表示你正处于危险或强烈痛苦中。请尽快联系身边可信任的人；如果有立即危险，请联系当地紧急服务。这个原型不能提供紧急援助。"
    if any(re.sub(r"\s+", "", term.lower()) in normalized for term in refusal_terms):
        return "警告：我不提供约炮、一夜情、色情邀约或相关协助，也不回答违法犯罪、赌博、毒品等内容。普通约会和健康关系话题可以聊。"
    return None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": APP_NAME, "mode": "development-foundation"}


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(WEB_PROTOTYPE, media_type="text/html; charset=utf-8")


@app.post("/api/session")
def create_session(request: Request, response: Response) -> dict[str, str]:
    """Create a browser-local guest identity; it does not authorize real matching."""
    try:
        existing_id = _read_session(request)
        with SessionLocal() as db:
            if db.get(User, existing_id):
                return {"status": "guest", "user_id": existing_id}
    except HTTPException:
        pass
    user_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(User(id=user_id))
        db.commit()
    _set_session(response, user_id)
    return {"status": "guest", "user_id": user_id}


@app.post("/api/consent")
def set_memory_consent(payload: ConsentRequest, request: Request) -> dict[str, str | bool]:
    user_id = _read_session(request)
    with SessionLocal() as db:
        user = _user(db, user_id)
        if payload.accepted:
            user.memory_consent_at = datetime.now(timezone.utc)
            user.consent_version = CONSENT_VERSION
        else:
            user.memory_consent_at = None
            user.consent_version = None
        db.commit()
    return {"memory_enabled": payload.accepted, "consent_version": CONSENT_VERSION if payload.accepted else ""}


@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request) -> dict[str, str | int | bool]:
    # Hard server-side guard: billing/ledger/payment verification are not implemented.
    # Do not rely on the frontend gate; direct API requests must not consume the operator's model account.
    raise HTTPException(status_code=503, detail="付费 AI 服务尚未上线，当前不会调用模型")
    user_id = _read_session(request)
    safety_reply = _safety_reply(payload.text)
    if safety_reply:
        return {"reply": safety_reply, "memory_saved": False, "answered_topics": 0, "safety": True}
    persistent = False
    with SessionLocal() as db:
        user = _user(db, user_id)
        persistent = bool(user.memory_consent_at)
        if persistent:
            user_message = Message(id=str(uuid.uuid4()), user_id=user_id, role="user", body_enc=_seal(payload.text))
            db.add(user_message)
            db.flush()
            answers = db.scalars(select(TopicAnswer).where(TopicAnswer.user_id == user_id)).all()
            expected = TOPIC_IDS[len(answers)] if len(answers) < len(TOPIC_IDS) else None
            category = "交流记录"
            if payload.topic_id and payload.topic_id == expected:
                db.add(TopicAnswer(user_id=user_id, topic_id=payload.topic_id, message_id=user_message.id))
                category = "初始交流"
            db.add(MemoryEvent(id=str(uuid.uuid4()), user_id=user_id, category=category, body_enc=_seal(payload.text), source_message_id=user_message.id, confidence="用户原话"))
            messages = _recent_context(db, user_id, payload.text)
            db.commit()
        else:
            messages = [{"role": "system", "content": "你是合拍 AI 交友画像助手，语气中性。用户可以主动提问。约炮、一夜情、色情邀约及其常见变体，还有违法、赌博、毒品、恶意伤害等请求应警告并拒答；普通约会和健康关系话题可以回答。此请求未授权长期记忆，不得保存或引用以前的交流。"}]
            messages.append({"role": "user", "content": payload.text})
    try:
        reply = await chat_completion(messages)
    except BailianConfigurationError as exc:
        raise HTTPException(status_code=503, detail="大陆模型服务尚未配置") from exc
    except BailianServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    with SessionLocal() as db:
        if persistent:
            db.add(Message(id=str(uuid.uuid4()), user_id=user_id, role="assistant", body_enc=_seal(reply)))
            count = len(db.scalars(select(TopicAnswer).where(TopicAnswer.user_id == user_id)).all())
            db.commit()
        else:
            count = 0
    return {"reply": reply, "memory_saved": persistent, "answered_topics": count, "matching_unlocked": persistent and count >= len(TOPIC_IDS)}


@app.get("/api/memory")
def get_memory(request: Request) -> dict[str, object]:
    user_id = _read_session(request)
    with SessionLocal() as db:
        user = _user(db, user_id)
        messages = db.scalars(select(Message).where(Message.user_id == user_id).order_by(Message.created_at)).all()
        events = db.scalars(select(MemoryEvent).where(MemoryEvent.user_id == user_id).order_by(MemoryEvent.created_at)).all()
        topics = db.scalars(select(TopicAnswer).where(TopicAnswer.user_id == user_id).order_by(TopicAnswer.created_at)).all()
        return {
            "memory_enabled": bool(user.memory_consent_at),
            "consent_version": user.consent_version,
            "answered_topics": [topic.topic_id for topic in topics],
            "messages": [{"role": m.role, "text": _open(m.body_enc), "created_at": m.created_at.isoformat()} for m in messages],
            "timeline": [{"id": e.id, "category": e.category, "text": _open(e.body_enc), "confidence": e.confidence, "created_at": e.created_at.isoformat()} for e in events],
        }


@app.delete("/api/memory/{event_id}")
def delete_memory_event(event_id: str, request: Request) -> dict[str, bool]:
    """Remove one item from the user's memory timeline without erasing chat history."""
    user_id = _read_session(request)
    with SessionLocal() as db:
        event = db.scalar(select(MemoryEvent).where(MemoryEvent.id == event_id, MemoryEvent.user_id == user_id))
        if not event:
            raise HTTPException(status_code=404, detail="找不到这条记忆")
        db.delete(event)
        db.commit()
    return {"deleted": True}


@app.delete("/api/me/data")
def delete_account_data(request: Request, response: Response) -> dict[str, bool]:
    user_id = _read_session(request)
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user:
            # Delete explicitly so local SQLite development behaves like PostgreSQL
            # even when SQLite foreign-key cascades have not been enabled.
            db.execute(delete(TopicAnswer).where(TopicAnswer.user_id == user_id))
            db.execute(delete(MemoryEvent).where(MemoryEvent.user_id == user_id))
            db.execute(delete(Message).where(Message.user_id == user_id))
            db.delete(user)
            db.commit()
    response.delete_cookie(COOKIE_NAME, path="/", secure=COOKIE_SECURE, httponly=True, samesite="lax")
    return {"deleted": True}
