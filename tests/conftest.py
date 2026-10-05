"""Shared test configuration."""

import socket
from typing import Any

import pytest


class NetworkBlockedError(RuntimeError):
    """Raised when a test tries to open a network socket."""


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Fail any test that opens an internet socket (Unix sockets stay allowed)."""
    if request.node.get_closest_marker("allow_network"):
        return
    real_socket = socket.socket

    def guarded(family: int = socket.AF_INET, *args: Any, **kwargs: Any) -> socket.socket:
        if family in (socket.AF_INET, socket.AF_INET6):
            raise NetworkBlockedError("tests must not use the network; use FixtureTransport")
        return real_socket(family, *args, **kwargs)

    monkeypatch.setattr(socket, "socket", guarded)
