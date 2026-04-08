from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import api_router, webhook_router
from app.database import db_engine
from app.middleware import add_middlewares
from app.models import Base
from app.scheduler import start_scheduler, stop_scheduler
from app.services.fcm import init_firebase


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=db_engine)
    init_firebase()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(lifespan=lifespan)
add_middlewares(app)
app.include_router(api_router, prefix="/api")
app.include_router(webhook_router)  # /webhook/notifications at root


@app.get("/")
def root():
    return {"message": "Enhanced FastAPI App"}
