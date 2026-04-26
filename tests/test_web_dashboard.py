from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_dashboard_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "web_dashboard.py"
    spec = importlib.util.spec_from_file_location("web_dashboard", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_status_extracts_dashboard_fields() -> None:
    dashboard = _load_dashboard_module()

    fields = dashboard.parse_status(
        "phase=navigate mode=GUIDED lat=35.3630000 lon=149.1650000 "
        "alt=50.2m wp_dist=123.4m age=0.1s"
    )

    assert fields["phase"] == "navigate"
    assert fields["mode"] == "GUIDED"
    assert fields["alt"] == "50.2m"
    assert fields["wp_dist"] == "123.4m"


def test_strip_ok_removes_command_prefix() -> None:
    dashboard = _load_dashboard_module()

    assert dashboard.strip_ok("OK RTL requested") == "RTL requested"
    assert dashboard.strip_ok("ERROR unknown command") == "ERROR unknown command"

