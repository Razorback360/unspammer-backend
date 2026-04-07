from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Import all models here so Base.metadata.create_all discovers every table
from app.models.user import User  # noqa: E402, F401
from app.models.item import Item  # noqa: E402, F401
from app.models.oauth import OAuthAccount  # noqa: E402, F401
from app.models.device import FCMToken  # noqa: E402, F401
