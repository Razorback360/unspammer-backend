from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class FCMTokenRegister(BaseModel):
    fcm_token: str
    public_key: str


class FCMTokenUpdate(BaseModel):
    fcm_token: str
    public_key: str


class FCMTokenResponse(BaseModel):
    id: str
    fcm_token: str
    public_key: str
    oauth_account_id: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
