import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.oauth import OAuthAccount
from app.models.subscription import GraphSubscription

logger = logging.getLogger(__name__)

_SUBSCRIPTION_LIFETIME_DAYS = 3
_GRAPH_SUBSCRIPTIONS_URL = "https://graph.microsoft.com/v1.0/subscriptions"


def create_graph_subscription(db: Session, oauth_account: OAuthAccount) -> GraphSubscription:
    """
    Create a Microsoft Graph inbox subscription for the given OAuth account.

    If the account already has a non-expired subscription, return it immediately
    to avoid duplicate Graph API registrations on repeated logins.
    """
    now = datetime.now(timezone.utc)
    existing = (
        db.query(GraphSubscription)
        .filter(
            GraphSubscription.oauth_account_id == oauth_account.id,
            GraphSubscription.expires_at > now,
        )
        .first()
    )
    if existing:
        return existing

    expiration = now + timedelta(days=_SUBSCRIPTION_LIFETIME_DAYS)
    payload = {
        "changeType": "created",
        "notificationUrl": settings.webhook_notification_url,
        "resource": "me/mailFolders('Inbox')/messages",
        "expirationDateTime": expiration.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "clientState": settings.webhook_client_state,
        "latestSupportedTlsVersion": "v1_2",
    }
    headers = {
        "Authorization": f"Bearer {oauth_account.access_token}",
        "Content-Type": "application/json",
    }

    response = httpx.post(_GRAPH_SUBSCRIPTIONS_URL, json=payload, headers=headers, timeout=30)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Graph subscription creation failed: {response.text}")

    data = response.json()
    subscription_id = data["id"]
    expires_at = datetime.fromisoformat(data["expirationDateTime"].replace("Z", "+00:00"))

    # Upsert in case a retry returns the same Microsoft subscription ID.
    subscription = db.query(GraphSubscription).filter(GraphSubscription.id == subscription_id).first()
    if subscription:
        subscription.expires_at = expires_at
        subscription.notification_url = data["notificationUrl"]
    else:
        subscription = GraphSubscription(
            id=subscription_id,
            oauth_account_id=oauth_account.id,
            resource=data["resource"],
            change_type=data["changeType"],
            notification_url=data["notificationUrl"],
            expires_at=expires_at,
            client_state=settings.webhook_client_state,
        )
        db.add(subscription)

    db.commit()
    db.refresh(subscription)
    return subscription


def renew_graph_subscription(
    db: Session, subscription: GraphSubscription, access_token: str
) -> GraphSubscription:
    """PATCH an existing Graph subscription to extend its expiry by another 3 days."""
    new_expiration = datetime.now(timezone.utc) + timedelta(days=_SUBSCRIPTION_LIFETIME_DAYS)
    payload = {"expirationDateTime": new_expiration.strftime("%Y-%m-%dT%H:%M:%SZ")}
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    response = httpx.patch(
        f"{_GRAPH_SUBSCRIPTIONS_URL}/{subscription.id}",
        json=payload,
        headers=headers,
        timeout=30,
    )
    if response.status_code not in (200, 204):
        raise RuntimeError(
            f"Graph subscription renewal failed (id={subscription.id}): {response.text}"
        )

    subscription.expires_at = new_expiration
    db.commit()
    db.refresh(subscription)
    return subscription
