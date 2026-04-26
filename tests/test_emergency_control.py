from __future__ import annotations

from uav.control.emergency import (
    EmergencyCommandServer,
    request_command_via_local_server,
    request_loiter_via_local_server,
    request_rtl_via_local_server,
    request_status_via_local_server,
)


def test_emergency_server_accepts_rtl_command() -> None:
    requests: list[str] = []
    server = EmergencyCommandServer(lambda: requests.append("RTL") or "RTL requested", port=0)

    try:
        server.start()
        response = request_rtl_via_local_server(port=server.port)
    finally:
        server.stop()

    assert response == "OK RTL requested"
    assert requests == ["RTL"]


def test_emergency_server_accepts_loiter_command() -> None:
    requests: list[str] = []
    server = EmergencyCommandServer(
        lambda: "RTL requested",
        on_loiter=lambda: requests.append("LOITER") or "LOITER requested",
        port=0,
    )

    try:
        server.start()
        response = request_loiter_via_local_server(port=server.port)
    finally:
        server.stop()

    assert response == "OK LOITER requested"
    assert requests == ["LOITER"]


def test_emergency_server_rejects_unknown_command() -> None:
    server = EmergencyCommandServer(lambda: "RTL requested", port=0)

    try:
        server.start()
        response = request_command_via_local_server("LAND", port=server.port)
    finally:
        server.stop()

    assert response == "ERROR unknown command"


def test_emergency_server_returns_status() -> None:
    server = EmergencyCommandServer(
        lambda: "RTL requested",
        on_status=lambda: "phase=navigate mode=GUIDED",
        port=0,
    )

    try:
        server.start()
        response = request_status_via_local_server(port=server.port)
    finally:
        server.stop()

    assert response == "OK phase=navigate mode=GUIDED"


def test_emergency_request_returns_none_when_server_is_absent() -> None:
    assert request_rtl_via_local_server(port=9, timeout_s=0.1) is None
