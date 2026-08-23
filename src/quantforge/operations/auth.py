"""Fail-closed bearer authentication and short-lived CSRF proof handling."""

import base64
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from pydantic import SecretStr


class DashboardAuthUnavailable(PermissionError):
    """Raised when no dashboard authentication material is configured."""


class DashboardAuthenticationFailed(PermissionError):
    """Raised when a bearer credential is absent or invalid."""


class CsrfValidationFailed(PermissionError):
    """Raised when a state-changing request has no valid CSRF proof."""


class DashboardAuthenticator:
    def __init__(
        self,
        access_token: SecretStr | None,
        csrf_secret: SecretStr | None,
        *,
        csrf_ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        self._access_token = access_token
        self._csrf_secret = csrf_secret
        self._csrf_ttl = csrf_ttl

    @property
    def configured(self) -> bool:
        return self._access_token is not None and self._csrf_secret is not None

    def authenticate(self, authorization: str | None) -> str:
        if not self.configured:
            raise DashboardAuthUnavailable("dashboard authentication is not configured")
        if authorization is None:
            raise DashboardAuthenticationFailed("bearer authentication is required")
        scheme, separator, supplied = authorization.partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not supplied:
            raise DashboardAuthenticationFailed("bearer authentication is required")
        assert self._access_token is not None
        expected = self._access_token.get_secret_value()
        if not secrets.compare_digest(supplied, expected):
            raise DashboardAuthenticationFailed("dashboard authentication failed")
        return sha256(supplied.encode()).hexdigest()[:16]

    def issue_csrf(self, actor_ref: str, *, now_utc: datetime) -> str:
        self._require_utc(now_utc)
        secret = self._csrf_value()
        expires = int((now_utc + self._csrf_ttl).timestamp())
        nonce = secrets.token_urlsafe(18)
        payload = f"{actor_ref}|{expires}|{nonce}".encode()
        encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
        signature = hmac.new(secret.encode(), encoded.encode(), sha256).hexdigest()
        return f"{encoded}.{signature}"

    def verify_csrf(self, csrf_token: str | None, actor_ref: str, *, now_utc: datetime) -> None:
        self._require_utc(now_utc)
        if not csrf_token:
            raise CsrfValidationFailed("CSRF proof is required")
        encoded, separator, supplied_signature = csrf_token.partition(".")
        if separator != ".":
            raise CsrfValidationFailed("CSRF proof is malformed")
        expected_signature = hmac.new(
            self._csrf_value().encode(), encoded.encode(), sha256
        ).hexdigest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise CsrfValidationFailed("CSRF proof is invalid")
        try:
            padding = "=" * (-len(encoded) % 4)
            decoded = base64.urlsafe_b64decode(encoded + padding).decode()
            proof_actor, expires_text, nonce = decoded.split("|", maxsplit=2)
            expires = int(expires_text)
        except (ValueError, UnicodeDecodeError) as exc:
            raise CsrfValidationFailed("CSRF proof is malformed") from exc
        if proof_actor != actor_ref or not nonce:
            raise CsrfValidationFailed("CSRF proof does not match the authenticated actor")
        if int(now_utc.timestamp()) > expires:
            raise CsrfValidationFailed("CSRF proof has expired")

    def _csrf_value(self) -> str:
        if not self.configured or self._csrf_secret is None:
            raise DashboardAuthUnavailable("dashboard authentication is not configured")
        return self._csrf_secret.get_secret_value()

    @staticmethod
    def _require_utc(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("authentication time must be UTC-aware")
