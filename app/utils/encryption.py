from cryptography.fernet import Fernet
from sqlalchemy import types


class EncryptedString(types.TypeDecorator):
    """SQLAlchemy TypeDecorator that transparently encrypts on write and decrypts on read using Fernet."""

    impl = types.Text
    cache_ok = True

    def _get_fernet(self) -> Fernet:
        # Import here to avoid circular imports at module load time
        from app.config import settings

        key = settings.encryption_key
        if isinstance(key, str):
            key = key.encode()
        return Fernet(key)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return self._get_fernet().encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return self._get_fernet().decrypt(value.encode()).decode()
