from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Annotated type alias — use this in route signatures instead of `db: Session = Depends(get_db)`
DbSession = Annotated[Session, Depends(get_db)]
