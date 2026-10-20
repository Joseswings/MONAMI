import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

password_hasher = PasswordHasher()
_dummy_hash = password_hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, stored_hash: str | None) -> bool:
    try:
        matches = password_hasher.verify(stored_hash or _dummy_hash, password)
    except (VerificationError, InvalidHashError):
        return False
    return matches and stored_hash is not None


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_token(ttl_minutes: int) -> tuple[str, datetime]:
    return secrets.token_urlsafe(32), datetime.now(UTC) + timedelta(minutes=ttl_minutes)
