from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config.settings import settings


class EncryptionError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = settings.encryption_master_key
    if not key and settings.database_url.startswith("sqlite"):
        key = "Q4EcvvWCMFBCDyk82ITq-aqPvAwsMJG0ebDEoc1RXR4="
    if not key:
        raise EncryptionError("ENCRYPTION_MASTER_KEY is required for encrypted storage.")
    try:
        return Fernet(key.encode())
    except ValueError as exc:
        raise EncryptionError("ENCRYPTION_MASTER_KEY must be a valid Fernet key.") from exc


def encrypt_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_text(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise EncryptionError("Encrypted value cannot be decrypted with the configured key.") from exc


def encrypt_json(value: Any) -> str:
    serialized = json.dumps(value if value is not None else {}, separators=(",", ":"), sort_keys=True)
    encrypted = encrypt_text(serialized)
    if encrypted is None:
        raise EncryptionError("JSON encryption unexpectedly returned no value.")
    return encrypted


def decrypt_json(value: str | None) -> Any:
    if not value:
        return {}
    decrypted = decrypt_text(value)
    if not decrypted:
        return {}
    return json.loads(decrypted)
