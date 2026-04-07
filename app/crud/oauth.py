import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Tuple

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.device import FCMToken
from app.models.oauth import OAuthAccount


def _decode_id_token_payload(id_token: str) -> dict:
    """Base64-decode the payload section of a JWT without signature verification."""
    payload_b64 = id_token.split(".")[1]
    # Restore padding stripped by base64url encoding
    padding_needed = 4 - len(payload_b64) % 4
    if padding_needed != 4:
        payload_b64 += "=" * padding_needed
    return json.loads(base64.urlsafe_b64decode(payload_b64))


def exchange_ms_code(
    db: Session, fcm_token_id: str, code: str, redirect_uri: str
) -> Tuple[OAuthAccount, FCMToken]:
    """Exchange a Microsoft authorization code for tokens, store them encrypted, and link the FCM token."""
    fcm_record = db.query(FCMToken).filter(FCMToken.id == fcm_token_id).first()
    if not fcm_record:
        raise ValueError(f"FCM token with id '{fcm_token_id}' not found")

    url = f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}/oauth2/v2.0/token"
    response = httpx.post(
        url,
        data={
            "client_id": settings.microsoft_client_id,
            "client_secret": settings.microsoft_client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Microsoft token exchange failed: {response.text}")

    token_data = response.json()

    id_token = token_data.get("id_token")
    if not id_token:
        raise RuntimeError(
            "Microsoft did not return an id_token; ensure the 'openid' scope is requested"
        )
    claims = _decode_id_token_payload(id_token)
    microsoft_user_id = claims.get("oid") or claims.get("sub")
    if not microsoft_user_id:
        raise RuntimeError("Could not determine Microsoft user ID from id_token claims")

    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=token_data["expires_in"]
    )

    # Upsert OAuthAccount keyed on microsoft_user_id
    oauth_account = (
        db.query(OAuthAccount)
        .filter(OAuthAccount.microsoft_user_id == microsoft_user_id)
        .first()
    )
    if oauth_account:
        oauth_account.access_token = token_data["access_token"]
        if token_data.get("refresh_token"):
            oauth_account.refresh_token = token_data["refresh_token"]
        oauth_account.token_type = token_data.get("token_type", "Bearer")
        oauth_account.expires_at = expires_at
        oauth_account.scope = token_data.get("scope")
    else:
        oauth_account = OAuthAccount(
            microsoft_user_id=microsoft_user_id,
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_type=token_data.get("token_type", "Bearer"),
            expires_at=expires_at,
            scope=token_data.get("scope"),
        )
        db.add(oauth_account)
        db.flush()  # Assign the PK before linking the FCM token

    fcm_record.oauth_account_id = oauth_account.id
    db.commit()
    db.refresh(oauth_account)
    db.refresh(fcm_record)
    return oauth_account, fcm_record


def refresh_ms_token(db: Session, oauth_account_id: str) -> OAuthAccount:
    """Use the stored refresh token to obtain a new Microsoft access token."""
    oauth_account = (
        db.query(OAuthAccount).filter(OAuthAccount.id == oauth_account_id).first()
    )
    if not oauth_account:
        raise ValueError(f"OAuth account '{oauth_account_id}' not found")
    if not oauth_account.refresh_token:
        raise ValueError(
            f"OAuth account '{oauth_account_id}' has no refresh token stored; "
            "the user must re-authenticate"
        )

    url = f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}/oauth2/v2.0/token"
    # TypeDecorator auto-decrypts refresh_token on read
    response = httpx.post(
        url,
        data={
            "client_id": settings.microsoft_client_id,
            "client_secret": settings.microsoft_client_secret,
            "refresh_token": oauth_account.refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Microsoft token refresh failed: {response.text}")

    token_data = response.json()
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=token_data["expires_in"]
    )

    oauth_account.access_token = token_data["access_token"]
    if token_data.get("refresh_token"):
        oauth_account.refresh_token = token_data["refresh_token"]
    oauth_account.expires_at = expires_at
    oauth_account.scope = token_data.get("scope", oauth_account.scope)
    db.commit()
    db.refresh(oauth_account)
    return oauth_account


def revoke_oauth_account(db: Session, oauth_account_id: str) -> bool:
    """Delete an OAuth account and null out the FK on all linked FCM tokens."""
    oauth_account = (
        db.query(OAuthAccount).filter(OAuthAccount.id == oauth_account_id).first()
    )
    if not oauth_account:
        return False

    # Explicit nullification for SQLite compatibility (FK cascade may not be active)
    db.query(FCMToken).filter(FCMToken.oauth_account_id == oauth_account_id).update(
        {"oauth_account_id": None}
    )
    db.delete(oauth_account)
    db.commit()
    return True
