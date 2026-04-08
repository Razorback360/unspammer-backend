import base64
import json
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
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


def encrypt_for_device(public_key_str: str, plaintext: bytes) -> str:
    """Encrypt *plaintext* for a device using X25519 ECDH + HKDF-SHA256 + AES-256-GCM.

    The device's public key must be a base64-encoded raw 32-byte X25519 public key,
    exactly as produced by the Flutter ``X25519().newKeyPair()`` / ``extractPublicKey().bytes``.

    Protocol:
    1. Deserialise the device's X25519 public key.
    2. Generate an ephemeral X25519 key pair.
    3. Perform ECDH → 32-byte shared secret.
    4. HKDF-SHA256 (info=b"email-encryption") → 32-byte AES key.
    5. AES-256-GCM encrypt *plaintext*.
    6. Return a base64-encoded JSON envelope:
        {
            "ephemeral_public": "<base64 32-byte X25519 public key>",
            "nonce":            "<base64 12-byte GCM nonce>",
            "ciphertext":       "<base64>",
            "tag":              "<base64 16-byte GCM tag>"
        }

    Flutter decryption (mirror):
        sharedSecret = X25519().sharedSecretKey(deviceKeyPair, ephemeralPublicKey)
        aesKey       = Hkdf(Hmac.sha256(), 32).deriveKey(sharedSecret, info: 'email-encryption')
        plaintext    = AesGcm.with256bits().decrypt(SecretBox(ciphertext, nonce, Mac(tag)), aesKey)
    """
    # Load the device's X25519 public key from raw bytes.
    public_key_bytes = base64.b64decode(public_key_str)
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
    device_public_key = X25519PublicKey.from_public_bytes(public_key_bytes)

    # Ephemeral key pair for this message only.
    ephemeral_private = X25519PrivateKey.generate()
    ephemeral_public = ephemeral_private.public_key()

    # ECDH shared secret.
    shared_secret = ephemeral_private.exchange(device_public_key)

    # HKDF → 32-byte AES-256 key.
    aes_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"email-encryption",
    ).derive(shared_secret)

    # AES-256-GCM encryption.
    nonce = os.urandom(12)
    aesgcm = AESGCM(aes_key)
    # AESGCM.encrypt returns ciphertext || tag (last 16 bytes).
    ct_with_tag = aesgcm.encrypt(nonce, plaintext, None)
    ciphertext = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]

    # Serialise ephemeral public key as raw 32 bytes.
    ephemeral_public_bytes = ephemeral_public.public_bytes(
        encoding=Encoding.Raw,
        format=PublicFormat.Raw,
    )

    envelope = {
        "ephemeral_public": base64.b64encode(ephemeral_public_bytes).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
        "tag": base64.b64encode(tag).decode(),
    }
    return base64.b64encode(json.dumps(envelope).encode()).decode()