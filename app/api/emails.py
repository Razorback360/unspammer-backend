import json
import logging

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel

from app.models.email_sync import EmailSync
from app.services.classifier import classify_email
from app.utils.dependencies import DbSession
from app.utils.encryption import encrypt_for_device

logger = logging.getLogger(__name__)

router = APIRouter()

_GRAPH_MESSAGE_URL = "https://graph.microsoft.com/v1.0/me/messages/{message_id}"


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


@router.get("/{message_id}")
def get_email(message_id: str, device_id: str, db: DbSession):
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
