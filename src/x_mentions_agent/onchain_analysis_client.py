from __future__ import annotations

import time
from typing import Any

import requests

from .config import Settings


class OnchainAnalysisClient:
    def __init__(self, settings: Settings) -> None:
        self._url = settings.onchain_analysis_url
        self._poll_interval_seconds = settings.onchain_poll_interval_seconds
        self._max_wait_seconds = settings.onchain_max_wait_seconds
        self._timeout = settings.request_timeout_seconds
        self._session = requests.Session()

    def run_analysis(self, contract_address: str, chain: str, abi: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "contractAddress": contract_address,
            "chain": chain,
        }
        if abi:
            payload["abi"] = abi

        submit_response = self._session.post(
            self._url,
            json=payload,
            timeout=self._timeout,
        )
        submit_response.raise_for_status()
        submit_data = submit_response.json()

        poll_url = submit_data.get("pollUrl")
        if not poll_url:
            job_id = submit_data.get("jobId")
            if not job_id:
                raise ValueError("Onchain analysis submit response missing both pollUrl and jobId")
            poll_url = f"{self._url}?jobId={job_id}"

        start = time.time()
        while True:
            poll_response = self._session.get(poll_url, timeout=self._timeout)
            poll_response.raise_for_status()
            poll_data = poll_response.json()

            status = poll_data.get("status")
            if status == "completed":
                return poll_data
            if status == "failed":
                return poll_data

            if (time.time() - start) > self._max_wait_seconds:
                return {
                    "status": "failed",
                    "error": "Analysis timed out while waiting for completion",
                    "jobId": poll_data.get("jobId"),
                    "phase": poll_data.get("phase"),
                }

            time.sleep(self._poll_interval_seconds)
