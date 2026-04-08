import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models import Base
from app.utils.encryption import EncryptedString

if TYPE_CHECKING:
    from app.models.oauth import OAuthAccount


class GraphSubscription(Base):
    __tablename__ = "graph_subscriptions"

    # Microsoft's own subscription UUID — use it as the PK so upserts are natural.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    oauth_account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("oauth_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource: Mapped[str] = mapped_column(String, nullable=False)
    change_type: Mapped[str] = mapped_column(String, nullable=False)
    notification_url: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Store clientState encrypted so it stays secret at rest.
    client_state: Mapped[Optional[str]] = mapped_column(EncryptedString(), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    oauth_account: Mapped["OAuthAccount"] = relationship(
        "OAuthAccount", back_populates="subscriptions"
    )
