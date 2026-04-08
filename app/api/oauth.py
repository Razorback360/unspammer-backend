import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.crud.oauth import exchange_ms_code, refresh_ms_token, revoke_oauth_account
from app.models.oauth import OAuthAccount
from app.schemas.oauth import (
    OAuthAccountResponse,
    OAuthRefreshRequest,
    OAuthTokenExchange,
)
from app.utils.dependencies import DbSession

logger = logging.getLogger(__name__)

router = APIRouter()


def _create_subscription_bg(db: Session, oauth_account: OAuthAccount) -> None:
    """Background task: create a Graph inbox subscription after the OAuth response is sent."""
    if not settings.webhook_notification_url:
        return
    try:
        from app.crud.subscription import create_graph_subscription
        create_graph_subscription(db, oauth_account)
    except Exception:
        logger.exception(
            "Background: failed to create Graph subscription for OAuth account %s.",
            oauth_account.id,
        )


@router.post(
    "/token", response_model=OAuthAccountResponse, status_code=status.HTTP_200_OK
)
def token_exchange(payload: OAuthTokenExchange, db: DbSession, background_tasks: BackgroundTasks):
    """Exchange a Microsoft authorization code for tokens and link them to the given FCM device."""
    try:
        oauth_account, _ = exchange_ms_code(
            db,
            payload.fcm_token_id,
            payload.code,
            payload.redirect_uri,
            getattr(payload, "code_verifier", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    background_tasks.add_task(_create_subscription_bg, db, oauth_account)
    return oauth_account


@router.post("/refresh", response_model=OAuthAccountResponse)
def refresh_token(payload: OAuthRefreshRequest, db: DbSession):
    """Refresh the Microsoft access token for an OAuth account using its stored refresh token."""
    try:
        oauth_account = refresh_ms_token(db, payload.oauth_account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return oauth_account


@router.delete("/revoke/{oauth_account_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(oauth_account_id: str, db: DbSession):
    """Revoke an OAuth account: deletes the record and unlinks all associated FCM tokens."""
    revoked = revoke_oauth_account(db, oauth_account_id)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="OAuth account not found"
        )
