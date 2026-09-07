from __future__ import annotations

import pytest

from evalops.workspace.security import (
    BootstrapSessionManager,
    InvalidHostError,
    InvalidOriginError,
    WorkspaceOrigin,
    validate_host_header,
    validate_mutating_origin,
)


def test_default_bootstrap_nonces_are_random_and_not_in_repr() -> None:
    first = BootstrapSessionManager()
    second = BootstrapSessionManager()

    assert first.bootstrap_nonce != second.bootstrap_nonce
    assert first.bootstrap_nonce not in repr(first)
    assert second.bootstrap_nonce not in repr(second)


def test_bootstrap_nonce_is_one_time_and_session_is_process_local() -> None:
    manager = BootstrapSessionManager(bootstrap_nonce="test-bootstrap")

    session_id = manager.consume_bootstrap_nonce("test-bootstrap")

    assert manager.validate_session(session_id)
    assert session_id not in repr(manager)
    with pytest.raises(ValueError, match="invalid bootstrap"):
        manager.consume_bootstrap_nonce("test-bootstrap")
    assert not manager.validate_session("unknown-session")


def test_invalidate_all_rejects_existing_sessions() -> None:
    manager = BootstrapSessionManager(bootstrap_nonce="test-bootstrap")
    session_id = manager.consume_bootstrap_nonce("test-bootstrap")

    manager.invalidate_all()

    assert not manager.validate_session(session_id)


def test_host_validation_requires_exact_loopback_origin() -> None:
    origin = WorkspaceOrigin(host="127.0.0.1", port=8123)

    validate_host_header("127.0.0.1:8123", origin)

    with pytest.raises(InvalidHostError):
        validate_host_header("localhost:8123", origin)
    with pytest.raises(InvalidHostError):
        validate_host_header("127.0.0.1:8124", origin)


def test_mutating_origin_validation_requires_exact_http_origin() -> None:
    origin = WorkspaceOrigin(host="127.0.0.1", port=8123)

    validate_mutating_origin("http://127.0.0.1:8123", origin)

    with pytest.raises(InvalidOriginError):
        validate_mutating_origin(None, origin)
    with pytest.raises(InvalidOriginError):
        validate_mutating_origin("http://localhost:8123", origin)
    with pytest.raises(InvalidOriginError):
        validate_mutating_origin("https://127.0.0.1:8123", origin)
