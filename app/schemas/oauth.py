from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class OAuthTokenExchange(BaseModel):
    fcm_token_id: str
    code: str
    redirect_uri: str
    code_verifier: Optional[str] = None


class OAuthRefreshRequest(BaseModel):
    oauth_account_id: str


class OAuthAccountResponse(BaseModel):
    id: str
    microsoft_user_id: str
    token_type: str
    expires_at: datetime
    scope: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
