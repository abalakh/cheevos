"""Keep native secret redaction within the session's lifetime."""

import logging

import pytest

from cheevos.core.ra_client import redact


@pytest.mark.parametrize("already_installed", [False, True])
def test_repeated_scopes_restore_host_factory_and_secrets(monkeypatch, already_installed):
    monkeypatch.setattr(logging, "_logRecordFactory", logging.LogRecord)
    monkeypatch.setattr(redact, "_secrets", {"host-secret"})
    monkeypatch.setattr(redact, "_installed", False)
    if already_installed:
        redact.install_redaction("host-secret")
    host_factory = logging.getLogRecordFactory()

    for _ in range(3):
        with redact.scoped():
            redact.install_redaction("session-secret")
            factory = logging.getLogRecordFactory()
            record = factory("test", logging.INFO, "test.py", 1, "session-secret", (), None)
            assert record.getMessage() == "***"
            assert "session-secret" in redact._secrets
        assert logging.getLogRecordFactory() is host_factory
        assert redact._installed is already_installed
        assert redact._secrets == {"host-secret"}


def test_scope_restores_redaction_after_failure(monkeypatch):
    monkeypatch.setattr(logging, "_logRecordFactory", logging.LogRecord)
    monkeypatch.setattr(redact, "_secrets", set())
    monkeypatch.setattr(redact, "_installed", False)

    def broken_session():
        with redact.scoped():
            redact.install_redaction("session-secret")
            raise RuntimeError("injected failure")

    with pytest.raises(RuntimeError, match="injected failure"):
        broken_session()
    assert logging.getLogRecordFactory() is logging.LogRecord
    assert not redact._installed
    assert not redact._secrets
