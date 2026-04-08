from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SubscriptionResponse(BaseModel):
    id: str
    oauth_account_id: str
    resource: str
    change_type: str
    notification_url: str
    expires_at: datetime
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
