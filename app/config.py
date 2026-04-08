from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./test.db"
    secret_key: str = "supersecret"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Fernet encryption key for storing OAuth tokens at rest.
    # Must be a URL-safe base64-encoded 32-byte key (generate with: Fernet.generate_key()).
    # CHANGE THIS in production via the ENCRYPTION_KEY environment variable.
    encryption_key: str = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

    # Microsoft Azure AD / Entra ID application credentials
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant_id: str = "common"
    microsoft_redirect_uri: str = ""

    # Microsoft Graph webhook settings
    # webhook_notification_url: Public URL Microsoft will POST change notifications to.
    # webhook_client_state: Secret echoed back in every notification for verification.
    webhook_notification_url: str = ""
    webhook_client_state: str = "secretClientValue"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
