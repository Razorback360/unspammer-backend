from fastapi import APIRouter

from app.api import admin, devices, emails, webhook
from app.api import oauth as oauth_api

api_router = APIRouter()

api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(oauth_api.router, prefix="/oauth", tags=["oauth"])
api_router.include_router(emails.router, prefix="/emails", tags=["emails"])

# Webhook router is exposed at the root (no /api prefix) so the public
# URL is simply /webhook/notifications as required by Microsoft Graph.
webhook_router = APIRouter()
webhook_router.include_router(webhook.router)
