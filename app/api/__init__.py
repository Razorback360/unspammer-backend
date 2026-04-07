from fastapi import APIRouter

from app.api import admin, devices
from app.api import oauth as oauth_api

api_router = APIRouter()

api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(oauth_api.router, prefix="/oauth", tags=["oauth"])
