import base64
import json
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
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


def _load_rsa_public_key(public_key_str: str):
    """Load an RSA public key from a PEM string or a base64-encoded DER blob."""
    # Try PEM first (starts with -----BEGIN)
    try:
        return serialization.load_pem_public_key(public_key_str.encode())
    except Exception:
        pass
    # Fall back to base64-encoded DER
    try:
        der_bytes = base64.b64decode(public_key_str)
        return serialization.load_der_public_key(der_bytes)
    except Exception:
        pass
    raise ValueError("Unable to load RSA public key — supply a PEM or base64-DER encoded key.")


def encrypt_for_device(public_key_str: str, plaintext: bytes) -> str:
    """Hybrid-encrypt *plaintext* for a device.

    1. Generate a random 256-bit AES-GCM key.
    2. Encrypt *plaintext* with AES-256-GCM → (nonce, ciphertext, tag).
    3. Encrypt the AES key with RSA-OAEP / SHA-256.
    4. Return a base64-encoded JSON envelope so the Flutter app can reverse the
       process with its stored private key.

    Returned JSON structure (base64-encoded as a single string):
        {
            "encrypted_key": "<base64>",   # RSA-OAEP-encrypted AES key
            "nonce":          "<base64>",   # 12-byte GCM nonce
            "ciphertext":     "<base64>",   # AES-GCM ciphertext
            "tag":            "<base64>"    # 16-byte authentication tag
        }
    """
    rsa_key = _load_rsa_public_key(public_key_str)

    # AES-256-GCM encryption
    aes_key = os.urandom(32)
    nonce = os.urandom(12)
    aesgcm = AESGCM(aes_key)
    # AESGCM.encrypt returns ciphertext || tag (last 16 bytes)
    ct_with_tag = aesgcm.encrypt(nonce, plaintext, None)
    ciphertext = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]

    # RSA-OAEP encryption of AES key
    encrypted_key = rsa_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    envelope = {
        "encrypted_key": base64.b64encode(encrypted_key).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
        "tag": base64.b64encode(tag).decode(),
    }
    return base64.b64encode(json.dumps(envelope).encode()).decode()
