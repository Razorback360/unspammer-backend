from typing import Optional

from sqlalchemy.orm import Session

from app.models.device import FCMToken


def get_fcm_token_by_id(db: Session, device_id: str) -> Optional[FCMToken]:
    return db.query(FCMToken).filter(FCMToken.id == device_id).first()


def get_fcm_token_by_value(db: Session, fcm_token: str) -> Optional[FCMToken]:
    return db.query(FCMToken).filter(FCMToken.fcm_token == fcm_token).first()


def create_fcm_token(db: Session, fcm_token: str, public_key: str) -> FCMToken:
    """Register a new FCM token. If the token already exists, updates its public key and returns it."""
    existing = get_fcm_token_by_value(db, fcm_token)
    if existing:
        existing.public_key = public_key
        db.commit()
        db.refresh(existing)
        return existing
    db_token = FCMToken(fcm_token=fcm_token, public_key=public_key)
    db.add(db_token)
    db.commit()
    db.refresh(db_token)
    return db_token


def update_fcm_token(
    db: Session, device_id: str, new_fcm_token: str, new_public_key: str
) -> Optional[FCMToken]:
    db_token = get_fcm_token_by_id(db, device_id)
    if not db_token:
        return None
    db_token.fcm_token = new_fcm_token
    db_token.public_key = new_public_key
    db.commit()
    db.refresh(db_token)
    return db_token


def delete_fcm_token(db: Session, device_id: str) -> bool:
    db_token = get_fcm_token_by_id(db, device_id)
    if not db_token:
        return False
    db.delete(db_token)
    db.commit()
    return True
