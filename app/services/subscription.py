import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.crud.oauth import refresh_ms_token
from app.crud.subscription import renew_graph_subscription
from app.models.oauth import OAuthAccount
from app.models.subscription import GraphSubscription

logger = logging.getLogger(__name__)


def auto_renew_expiring_subscriptions(db: Session) -> None:
    """
    Renew all Graph subscriptions that expire within the next 24 hours.

    If the linked OAuth token is also near expiry it is refreshed first,
    so the PATCH call to Microsoft Graph uses a valid access token.
    """
    cutoff = datetime.now(timezone.utc) + timedelta(hours=24)
    expiring: list[GraphSubscription] = (
        db.query(GraphSubscription)
        .filter(GraphSubscription.expires_at <= cutoff)
        .all()
    )

    if not expiring:
        logger.info("No Graph subscriptions need renewal.")
        return

    logger.info("Renewing %d expiring Graph subscription(s).", len(expiring))
    for sub in expiring:
        try:
            oauth_account = sub.oauth_account
            token_cutoff = datetime.now(timezone.utc) + timedelta(minutes=5)
            if oauth_account.expires_at <= token_cutoff:
                oauth_account = refresh_ms_token(db, oauth_account.id)
            renew_graph_subscription(db, sub, oauth_account.access_token)
            logger.info("Renewed subscription %s for OAuth account %s.", sub.id, oauth_account.id)
        except Exception:
            logger.exception("Failed to renew subscription %s.", sub.id)


def auto_refresh_expiring_tokens(db: Session) -> None:
    """
    Refresh OAuth access tokens that expire within the next 30 minutes.

    Only accounts that still have a refresh token are processed.
    """
    cutoff = datetime.now(timezone.utc) + timedelta(minutes=30)
    expiring: list[OAuthAccount] = (
        db.query(OAuthAccount)
        .filter(
            OAuthAccount.expires_at <= cutoff,
            OAuthAccount.refresh_token.isnot(None),
        )
        .all()
    )

    if not expiring:
        logger.info("No OAuth tokens need refresh.")
        return

    logger.info("Refreshing %d expiring OAuth token(s).", len(expiring))
    for account in expiring:
        try:
            refresh_ms_token(db, account.id)
            logger.info("Refreshed OAuth token for account %s.", account.id)
        except Exception:
            logger.exception("Failed to refresh token for account %s.", account.id)
