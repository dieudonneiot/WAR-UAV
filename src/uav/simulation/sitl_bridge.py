from __future__ import annotations


class SitlBridge:
    def __init__(self, endpoint: str = "udp:127.0.0.1:14550") -> None:
        self.endpoint = endpoint

