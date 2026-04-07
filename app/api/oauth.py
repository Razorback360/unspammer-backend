from fastapi import APIRouter, HTTPException, status

from app.crud.oauth import exchange_ms_code, refresh_ms_token, revoke_oauth_account
from app.schemas.oauth import (
    OAuthAccountResponse,
    OAuthRefreshRequest,
    OAuthTokenExchange,
)
from app.utils.dependencies import DbSession

router = APIRouter()


@router.post(
    "/token", response_model=OAuthAccountResponse, status_code=status.HTTP_200_OK
)
def token_exchange(payload: OAuthTokenExchange, db: DbSession):
    """Exchange a Microsoft authorization code for tokens and link them to the given FCM device."""
    try:
        # Pass the code_verifier if your Flutter PKCE flow is sending it
        oauth_account, _ = exchange_ms_code(
            db, 
            payload.fcm_token_id, 
            payload.code, 
            payload.redirect_uri,
            getattr(payload, "code_verifier", None)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
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
