import logging
from typing import Annotated, Any, Dict, Optional

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import PlainTextResponse

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])


@router.post("/webhook/notifications")
async def handle_notifications(
    request: Request,
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
        received_state = notification.get("clientState", "")
        if received_state != settings.webhook_client_state:
            logger.warning(
                "Notification dropped — unexpected clientState: '%s'.", received_state
            )
            continue

        logger.info(
            "Graph notification received: subscriptionId=%s changeType=%s resource=%s",
            notification.get("subscriptionId"),
            notification.get("changeType"),
            notification.get("resource"),
        )

    return Response(status_code=202)
