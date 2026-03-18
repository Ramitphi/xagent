#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests


SUPPORTED_CHAINS = {
    "ethereum",
    "polygon",
    "bsc",
    "arbitrum",
    "optimism",
    "base",
    "avalanche",
}

DEFAULT_API_URL = "https://esraarlhpxraucslsdle.supabase.co/functions/v1/onchain-analysis"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run On-Chain Wizard analysis via async submit/poll API")
    parser.add_argument("--contract-address", required=True, help="0x-prefixed EVM contract address")
    parser.add_argument("--chain", required=True, help="Supported chain name")
    parser.add_argument("--abi-file", help="Path to ABI JSON file for unverified contracts")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Override analysis API URL")
    parser.add_argument("--poll-interval", type=int, default=20, help="Poll interval in seconds")
    parser.add_argument("--max-wait", type=int, default=420, help="Max wait time in seconds")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds")
    return parser.parse_args()


def validate_contract(contract_address: str) -> None:
    if not (
        contract_address.startswith("0x")
        and len(contract_address) == 42
        and all(ch in "0123456789abcdefABCDEF" for ch in contract_address[2:])
    ):
        raise ValueError("contract address must be a full 0x-prefixed 40-byte hex string")


def load_abi(path: str | None) -> Any | None:
    if not path:
        return None
    raw = Path(path).read_text(encoding="utf-8")
    return json.loads(raw)


def run_analysis(
    *,
    contract_address: str,
    chain: str,
    abi: Any | None,
    api_url: str,
    poll_interval: int,
    max_wait: int,
    timeout: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contractAddress": contract_address,
        "chain": chain,
    }
    if abi is not None:
        payload["abi"] = abi

    session = requests.Session()
    submit_response = session.post(api_url, json=payload, timeout=timeout)
    submit_response.raise_for_status()
    submit_data = submit_response.json()

    poll_url = submit_data.get("pollUrl")
    if not poll_url:
        job_id = submit_data.get("jobId")
        if not job_id:
            raise ValueError("submit response missing both pollUrl and jobId")
        poll_url = f"{api_url}?jobId={job_id}"

    start = time.time()
    while True:
        poll_response = session.get(poll_url, timeout=timeout)
        poll_response.raise_for_status()
        poll_data = poll_response.json()
        status = poll_data.get("status")

        if status in {"completed", "failed"}:
            return poll_data

        if (time.time() - start) > max_wait:
            return {
                "status": "failed",
                "error": "Analysis timed out while waiting for completion",
                "jobId": poll_data.get("jobId"),
                "phase": poll_data.get("phase"),
            }

        time.sleep(poll_interval)


def main() -> int:
    args = parse_args()
    chain = args.chain.lower().strip()

    try:
        validate_contract(args.contract_address)
        if chain not in SUPPORTED_CHAINS:
            raise ValueError(
                "unsupported chain; use one of: " + ", ".join(sorted(SUPPORTED_CHAINS))
            )
        abi = load_abi(args.abi_file)
        result = run_analysis(
            contract_address=args.contract_address,
            chain=chain,
            abi=abi,
            api_url=args.api_url,
            poll_interval=args.poll_interval,
            max_wait=args.max_wait,
            timeout=args.timeout,
        )
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
