import logging

logger = logging.getLogger(__name__)

_firebase_app = None


def init_firebase() -> None:
    """Initialise the Firebase Admin SDK using the service-account JSON path from settings.

    If ``firebase_service_account`` is not set, FCM sending will be skipped at
    runtime and a warning is logged — useful in dev/testing environments.
    """
    global _firebase_app
    from app.config import settings

    if not settings.firebase_service_account:
        logger.warning(
            "firebase_service_account is not configured — FCM notifications will be skipped."
        )
        return

    try:
        import firebase_admin
        from firebase_admin import credentials

        cred = credentials.Certificate(settings.firebase_service_account)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialised.")
    except Exception:
        logger.exception("Failed to initialise Firebase Admin SDK.")


def send_new_email_notification(fcm_token: str, message_id: str) -> None:
    """Send an FCM data message to a device telling it to pull a specific email.

    The Flutter app should listen for ``type == "new_email"`` and call
    ``GET /api/emails/{message_id}?device_id=...`` when it receives it.
    """
    if _firebase_app is None:
        logger.debug(
            "FCM not initialised — skipping notification for message %s.", message_id
        )
        return

    try:
        from firebase_admin import messaging

        message = messaging.Message(
            data={
                "type": "new_email",
                "message_id": message_id,
            },
            token=fcm_token,
        )
        response = messaging.send(message)
        logger.info(
            "FCM notification sent for message %s → FCM response: %s", message_id, response
        )
    except Exception:
        logger.exception(
            "Failed to send FCM notification for message %s to token %s.",
            message_id,
            fcm_token,
        )
