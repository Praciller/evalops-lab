"""Process-local bootstrap and loopback request security."""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass


class WorkspaceSecurityError(ValueError):
    """Base error with a stable safe code and no secret-bearing detail."""

    code = "workspace_security_error"


class BootstrapSecurityError(WorkspaceSecurityError):
    code = "invalid_bootstrap"


class UnauthenticatedError(WorkspaceSecurityError):
    code = "unauthenticated"


class InvalidHostError(WorkspaceSecurityError):
    code = "invalid_host"


class InvalidOriginError(WorkspaceSecurityError):
    code = "invalid_origin"


@dataclass(frozen=True)
class WorkspaceOrigin:
    host: str
    port: int

    @property
    def http_origin(self) -> str:
        return f"http://{self.host}:{self.port}"


class BootstrapSessionManager:
    """Keep bootstrap and authenticated sessions only in process memory."""

    def __init__(self, *, bootstrap_nonce: str | None = None) -> None:
        self._bootstrap_nonce = bootstrap_nonce or secrets.token_urlsafe(32)
        self._sessions: set[str] = set()

    @property
    def bootstrap_nonce(self) -> str:
        return self._bootstrap_nonce

    def consume_bootstrap_nonce(self, value: str) -> str:
        if not hmac.compare_digest(value, self._bootstrap_nonce):
            raise BootstrapSecurityError("invalid bootstrap nonce")
        session_id = secrets.token_urlsafe(32)
        self._sessions.add(session_id)
        self._bootstrap_nonce = secrets.token_urlsafe(32)
        return session_id

    def validate_session(self, session_id: str) -> bool:
        return session_id in self._sessions

    def invalidate_all(self) -> None:
        self._sessions.clear()
        self._bootstrap_nonce = secrets.token_urlsafe(32)

    def __repr__(self) -> str:
        return "BootstrapSessionManager()"


def validate_host_header(host_header: str, expected: WorkspaceOrigin) -> None:
    if host_header != f"{expected.host}:{expected.port}":
        raise InvalidHostError("request host is not the local workspace origin")


def validate_mutating_origin(origin_header: str | None, expected: WorkspaceOrigin) -> None:
    if origin_header != expected.http_origin:
        raise InvalidOriginError("request origin is not the local workspace origin")
