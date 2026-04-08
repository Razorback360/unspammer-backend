from fastapi import APIRouter, HTTPException, Response, status

from app.crud.device import create_fcm_token, delete_fcm_token, get_fcm_token_by_id, update_fcm_token
from app.schemas.device import FCMTokenRegister, FCMTokenResponse, FCMTokenUpdate
from app.utils.dependencies import DbSession

router = APIRouter()


@router.post(
    "/register", response_model=FCMTokenResponse, status_code=status.HTTP_201_CREATED
)
def register_device(payload: FCMTokenRegister, db: DbSession):
    """Register an Android device by its FCM token. Returns the existing record if already registered."""
    return create_fcm_token(db, payload.fcm_token, payload.public_key)


@router.put("/{device_id}/fcm-token", response_model=FCMTokenResponse)
def update_device_fcm_token(device_id: str, payload: FCMTokenUpdate, db: DbSession):
    """Replace the FCM token for an existing registered device."""
    existing = get_fcm_token_by_id(db, device_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not found"
        )
    if existing.fcm_token == payload.fcm_token and existing.public_key == payload.public_key:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)
    return update_fcm_token(db, device_id, payload.fcm_token, payload.public_key)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def deregister_device(device_id: str, db: DbSession):
    """Unregister a device and remove its FCM token record."""
    deleted = delete_fcm_token(db, device_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not found"
        )
