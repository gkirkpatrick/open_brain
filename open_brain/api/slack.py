import asyncio
import hashlib
import hmac
import json
import time

import httpx
from fastapi import APIRouter, HTTPException, Request

from open_brain.config import settings
from open_brain.db.session import get_pool
from open_brain.services.embeddings import generate_embedding
from open_brain.services.metadata import extract_metadata

router = APIRouter(prefix="/api/slack")


def verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    """Verify Slack request signature."""
    if not settings.slack_signing_secret:
        return False

    if abs(time.time() - int(timestamp)) > 300:
        return False

    sig_basestring = f"v0:{timestamp}:{body.decode()}"
    computed = "v0=" + hmac.new(
        settings.slack_signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, signature)


@router.post("/webhook")
async def slack_webhook(request: Request):
    """Handle Slack events (message capture)."""
    body = await request.body()
    payload = json.loads(body)

    # Handle Slack URL verification challenge
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    # Verify signature
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    if settings.slack_signing_secret and not verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    # Process message events
    if payload.get("type") == "event_callback":
        event = payload.get("event", {})

        # Ignore bot messages and message edits
        if event.get("bot_id") or event.get("subtype"):
            return {"ok": True}

        if event.get("type") == "message":
            text = event.get("text", "").strip()
            if not text:
                return {"ok": True}

            # Process in background
            asyncio.create_task(_process_slack_message(text, event))

    return {"ok": True}


async def _process_slack_message(text: str, event: dict):
    """Process a Slack message: generate embedding, extract metadata, store."""
    import uuid
    from datetime import datetime, timezone

    embedding, metadata = await asyncio.gather(
        generate_embedding(text),
        extract_metadata(text),
    )

    metadata["source"] = "slack"
    metadata["slack_ts"] = event.get("ts", "")
    metadata["slack_channel"] = event.get("channel", "")

    thought_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO thoughts (id, content, embedding, source, metadata, created_at, updated_at)
        VALUES ($1, $2, $3::vector, $4, $5::jsonb, $6, $6)
        """,
        thought_id,
        text,
        embedding_str,
        "slack",
        metadata,
        now,
    )

    # Post confirmation reply in thread
    if settings.slack_bot_token:
        async with httpx.AsyncClient() as client:
            topics = metadata.get("topics", [])
            thought_type = metadata.get("type", "observation")
            summary = metadata.get("summary", "")

            reply = f"Captured as *{thought_type}*"
            if topics:
                reply += f" | Topics: {', '.join(topics)}"
            if summary:
                reply += f"\n>{summary}"

            await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {settings.slack_bot_token}"},
                json={
                    "channel": event["channel"],
                    "thread_ts": event["ts"],
                    "text": reply,
                },
            )
