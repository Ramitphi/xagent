from __future__ import annotations

from typing import Any

import requests

from .config import Settings


class AnalysisClient:
    def __init__(self, settings: Settings) -> None:
        self._url = settings.analysis_api_url
        self._timeout = settings.request_timeout_seconds
        self._header_name = settings.analysis_api_key_header
        self._api_key = settings.analysis_api_key
        self._session = requests.Session()

    def build_reply(self, mention: dict[str, Any]) -> str:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            if self._header_name.lower() == "authorization":
                headers[self._header_name] = f"Bearer {self._api_key}"
            else:
                headers[self._header_name] = self._api_key

        payload = {"mention": mention}
        response = self._session.post(
            self._url,
            json=payload,
            headers=headers,
            timeout=self._timeout,
        )
        response.raise_for_status()

        data = response.json()
        reply_text = data.get("reply_text") or data.get("reply")
        if not reply_text:
            raise ValueError("Analysis API response missing 'reply_text' (or 'reply') field")

        return str(reply_text)
