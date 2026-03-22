"""
WESH — AI financial assistant for TBK Management / Clerq.
POST /chat  →  returns assistant reply as JSON (no auth required so it works on the auth page too)
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])

WESH_SYSTEM_PROMPT = """You are WESH, the AI financial assistant built into Clerq — a business financial \
tracking platform used by TBK Management.

Your personality:
- Friendly, sharp, and professional — like a knowledgeable CFO who's easy to talk to.
- Concise: keep replies short unless the user asks for detail.
- Use dollar signs and percentage formatting where relevant.
- Never make up specific transaction data — you don't have access to the user's live database.

What you know about Clerq:
- Clerq connects to bank accounts via Plaid and auto-syncs transactions.
- It detects Zelle transfers and identifies the counterparty and direction (sent / received).
- Transactions are categorized automatically (Food & Dining, Gas, Utilities, etc.).
- Users can upload PDF bank statements — you (WESH) extract and structure the transactions using AI.
- There are two tracked team members at TBK Management:
    • Kenny  — handles debit card / POS purchases
    • Bright — handles Zelle transfers and walk-in / cash deposits
- Admins can export PDF receipts per transaction or in batch.
- Admins can export a CSV of any filtered transaction view with an Assigned User column.
- Multi-organization support: each business entity has its own books.
- Role-based access: admin (full access) and viewer (read-only).
- Invite links let accountants or bookkeepers join without an email server.
- 2FA (Google Authenticator / TOTP) is available on every account.

When users ask questions you can't answer (e.g., "what was my balance last Tuesday?"), \
acknowledge the limitation and suggest they check the dashboard or apply date filters.

Always introduce yourself as WESH on the first message if you haven't already."""


class ChatMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@router.post("")
async def chat(body: ChatRequest) -> dict[str, Any]:
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not configured. Add it to your .env file.",
        )

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    messages = [{"role": "system", "content": WESH_SYSTEM_PROMPT}]
    for msg in body.messages[-20:]:   # cap history at last 20 messages
        messages.append({"role": msg.role, "content": msg.content})

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=512,
            temperature=0.7,
        )
    except Exception as e:
        logger.error(f"OpenAI chat error: {e}")
        raise HTTPException(status_code=502, detail="AI service unavailable. Try again shortly.")

    reply = response.choices[0].message.content or ""
    return {"reply": reply}
