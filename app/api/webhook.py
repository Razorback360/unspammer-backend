import logging
from typing import Annotated, Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Query, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.utils.dependencies import DbSession

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])


def _dispatch_fcm_notifications(
    db: Session, subscription_id: str, message_id: str
) -> None:
    """Background task: look up the subscription's FCM tokens and fire FCM pushes."""
    from app.models.subscription import GraphSubscription
    from app.services.fcm import send_new_email_notification

    subscription = (
        db.query(GraphSubscription)
        .filter(GraphSubscription.id == subscription_id)
        .first()
    )
    if not subscription:
        logger.warning(
            "Received notification for unknown subscription %s — skipping FCM dispatch.",
            subscription_id,
        )
        return

    fcm_tokens = subscription.oauth_account.fcm_tokens
    if not fcm_tokens:
        logger.info(
            "Subscription %s has no linked FCM tokens — skipping FCM dispatch.",
            subscription_id,
        )
        return

    logger.info(
        "Dispatching FCM notifications for message %s to %d device(s).",
        message_id,
        len(fcm_tokens),
    )
    for token in fcm_tokens:
        send_new_email_notification(token.fcm_token, message_id)


@router.post("/webhook/notifications")
async def handle_notifications(
    request: Request,
    background_tasks: BackgroundTasks,
    db: DbSession,
    validation_token: Annotated[Optional[str], Query(alias="validationToken")] = None,
) -> Response:
    """
    Microsoft Graph change-notification endpoint.

    Validation handshake (subscription creation):
        Microsoft sends ?validationToken=<token>. Respond 200 with the token
        as plain text so Graph confirms the endpoint is reachable.

    Change notifications (new email):
        Microsoft POSTs a JSON payload. Validate clientState to ensure the
        request is legitimate, log the notification, and respond 202 Accepted.
    """
    if validation_token:
        logger.info("Graph webhook validation request received.")
        return PlainTextResponse(content=validation_token, status_code=200)

    body: Dict[str, Any] = await request.json()
    notifications = body.get("value", [])

    for notification in notifications:
        client_state = notification.get("clientState")
        if client_state != settings.webhook_client_state:
            logger.warning(
                "Received notification with invalid clientState '%s' — ignoring.",
                client_state,
            )
            continue

        subscription_id = notification.get("subscriptionId")
        # resourceData.id carries the message ID directly — no string parsing needed.
        message_id = notification.get("resourceData", {}).get("id")

        if not subscription_id or not message_id:
            logger.warning(
                "Notification missing subscriptionId or resourceData.id — skipping: %s",
                notification,
            )
            continue

        logger.info(
            "New email notification: subscription=%s message=%s",
            subscription_id,
            message_id,
        )
        background_tasks.add_task(
            _dispatch_fcm_notifications, db, subscription_id, message_id
        )

    return Response(status_code=202)
