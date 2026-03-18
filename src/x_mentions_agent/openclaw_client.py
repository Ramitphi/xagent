from __future__ import annotations

from typing import Any

import requests

from .config import Settings


class OpenClawClient:
    def __init__(self, settings: Settings) -> None:
        self._enabled = bool(settings.openclaw_enabled and settings.openclaw_respond_url)
        self._url = settings.openclaw_respond_url or ""
        self._api_key = settings.openclaw_api_key
        self._timeout = settings.openclaw_timeout_seconds
        self._session = requests.Session()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def respond(self, context: dict[str, Any]) -> dict[str, Any]:
        if not self._enabled:
            raise RuntimeError("OpenClaw client is not enabled")

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        response = self._session.post(
            self._url,
            json={
                "channel": "x",
                "agent": "xagent",
                "context": context,
            },
            headers=headers,
            timeout=self._timeout,
        )
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("OpenClaw response must be a JSON object")
        return payload
