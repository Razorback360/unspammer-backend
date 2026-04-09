import json
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func

from app.models.email_sync import EmailSync
from app.services.classifier import classify_email
from app.services.fcm import send_important_email_notification
from app.utils.dependencies import DbSession
from app.utils.encryption import encrypt_for_device

logger = logging.getLogger(__name__)

router = APIRouter()

_GRAPH_MESSAGE_URL = "https://graph.microsoft.com/v1.0/me/messages/{message_id}"
_GRAPH_MESSAGES_URL = "https://graph.microsoft.com/v1.0/me/messages"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ConfirmSyncRequest(BaseModel):
    device_id: str
    message_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_fcm_token_or_404(db, device_id: str):
    from app.models.device import FCMToken

    token = db.query(FCMToken).filter(FCMToken.id == device_id).first()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not found."
        )
    return token


def _get_oauth_account_or_404(fcm_token):
    if not fcm_token.oauth_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device is not linked to an OAuth account.",
        )
    return fcm_token.oauth_account


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/sync")
def sync_emails(device_id: str, db: DbSession):
    """Fetch all emails received since the device's last sync watermark, encrypt
    the full list as a single payload, then slide the watermark forward to now.

    Query params:
        device_id: The FCMToken ID representing the requesting device.
    """
    fcm_token = _get_fcm_token_or_404(db, device_id)
    oauth_account = _get_oauth_account_or_404(fcm_token)

    # Find the most recent sync record — it acts as the watermark.
    watermark_row = (
        db.query(EmailSync)
        .filter(EmailSync.fcm_token_id == device_id)
        .order_by(EmailSync.synced_at.desc())
        .first()
    )

    if watermark_row is None or watermark_row.synced_at is None:
        # No prior sync on record — nothing safe to fetch yet.
        encrypted_empty = encrypt_for_device(
            fcm_token.public_key,
            b"[]",
        )
        return {"data": encrypted_empty}

    cutoff = watermark_row.synced_at

    # Collect all message IDs already synced for this device so we can skip them.
    synced_ids: set[str] = {
        row.message_id
        for row in db.query(EmailSync.message_id).filter(
            EmailSync.fcm_token_id == device_id
        )
    }

    headers = {
        "Authorization": f"Bearer {oauth_account.access_token}",
        "Prefer": 'outlook.body-content-type="text"',
    }
    params = {
        "$filter": f"receivedDateTime ge {cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "$top": "100",
        "$orderby": "receivedDateTime asc",
    }

    # Paginate through all results.
    messages: list[dict] = []
    url: str | None = _GRAPH_MESSAGES_URL
    while url:
        response = httpx.get(
            url,
            headers=headers,
            params=params if url == _GRAPH_MESSAGES_URL else None,
            timeout=30,
        )
        if response.status_code != 200:
            logger.error("Graph API error during sync for device %s: %s", device_id, response.text)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to fetch emails from Microsoft Graph.",
            )
        page = response.json()
        messages.extend(page.get("value", []))
        url = page.get("@odata.nextLink")

    # Build payloads, excluding messages already synced.
    payloads: list[dict] = []
    for msg in messages:
        if msg.get("id") in synced_ids:
            continue

        from_address = (
            msg.get("from", {}).get("emailAddress", {}).get("address", "")
        )
        body = msg.get("body", {}).get("content", "")
        subject = msg.get("subject", "")
        # bodyPreview is the first ~255 characters — a natural summary.
        summary = msg.get("bodyPreview", "")

        classification_result = classify_email(
            sender=from_address,
            subject=subject,
            body_preview=body
        )
        logger.info("Heuristics ran for message, result %s", classification_result)

        payloads.append({
                "from_address": from_address,
                "body": body,
                "subject": subject,
                "summary": summary,
                "classification": classification_result["label"],
                "event_date": classification_result.get("event_date", ""),
            }
        )

    logger.info("Sync for device %s: %d new email(s) after cutoff.", device_id, len(payloads))

    encrypted = encrypt_for_device(
        fcm_token.public_key,
        json.dumps(payloads).encode(),
    )

    # Slide the watermark forward to now.
    watermark_row.synced_at = datetime.now(timezone.utc)
    db.commit()

    return {"data": encrypted}


@router.get("/{message_id}")
def get_email(message_id: str, device_id: str, db: DbSession, background_tasks: BackgroundTasks):
    """Fetch a specific email from Microsoft Graph, run stub heuristics, encrypt
    the result with the device's public key, and return it.

    Query params:
        device_id: The FCMToken ID representing the requesting device.
    """
    fcm_token = _get_fcm_token_or_404(db, device_id)
    oauth_account = _get_oauth_account_or_404(fcm_token)

    # Fetch the email from Microsoft Graph with plain-text body.
    headers = {
        "Authorization": f"Bearer {oauth_account.access_token}",
        "Prefer": 'outlook.body-content-type="text"',
    }
    url = _GRAPH_MESSAGE_URL.format(message_id=message_id)
    response = httpx.get(url, headers=headers, timeout=30)

    if response.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Email not found in Microsoft Graph."
        )
    if response.status_code != 200:
        logger.error("Graph API error fetching message %s: %s", message_id, response.text)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch email from Microsoft Graph.",
        )

    data = response.json()

    # Extract fields from the Graph response.
    from_address = (
        data.get("from", {}).get("emailAddress", {}).get("address", "")
    )
    body = data.get("body", {}).get("content", "")
    subject = data.get("subject", "")
    # bodyPreview is the first ~255 characters — a natural summary.
    summary = data.get("bodyPreview", "")

    # Run heuristic classification
    classification_result = classify_email(
        sender=from_address,
        subject=subject,
        body_preview=body
    )
    logger.info("Heuristics ran for message %s: Result %s", message_id, classification_result)

    email_payload = {
        "from_address": from_address,
        "body": body,
        "subject": subject,
        "summary": summary,
        "classification": classification_result["label"],
        "event_date": classification_result.get("event_date", ""),
    }

    encrypted = encrypt_for_device(
        fcm_token.public_key,
        json.dumps(email_payload).encode(),
    )

    if classification_result["label"] == "Important":
        background_tasks.add_task(
            send_important_email_notification, fcm_token.fcm_token, subject
        )

    return {"data": encrypted}


@router.post("/confirm-sync", status_code=status.HTTP_201_CREATED)
def confirm_sync(payload: ConfirmSyncRequest, db: DbSession):
    """Record that a device has successfully synced a specific email."""
    # Verify the device exists.
    _get_fcm_token_or_404(db, payload.device_id)

    sync = EmailSync(fcm_token_id=payload.device_id, message_id=payload.message_id)
    db.add(sync)
    db.commit()
    db.refresh(sync)

    return {"synced": True, "id": sync.id, "synced_at": sync.synced_at}
