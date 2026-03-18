#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.x_mentions_agent.llm_client import LLMClient  # noqa: E402
from src.x_mentions_agent.onchain_analysis_client import OnchainAnalysisClient  # noqa: E402


SUPPORTED_CHAINS = {
    "ethereum",
    "polygon",
    "bsc",
    "arbitrum",
    "optimism",
    "base",
    "avalanche",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run xagent routing and reply logic as a local tool")
    parser.add_argument("--mention-text", required=True, help="Mention text to process")
    parser.add_argument("--parent-text", default="", help="Optional parent tweet text")
    parser.add_argument("--author-username", default="", help="Mention author username")
    parser.add_argument("--persona-file", default="agent.md", help="Persona file path")
    parser.add_argument("--execute-onchain", action="store_true", help="Run onchain analysis if requested")
    return parser.parse_args()


def load_persona(persona_file: str) -> str:
    path = Path(persona_file)
    if not path.is_absolute():
        path = REPO_ROOT / path
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return (
        "You are OWAIbot, a friendly human-like analyst on X. "
        "You help with onchain analysis and also converse naturally in short, helpful replies."
    )


def llm_settings() -> SimpleNamespace:
    import os

    return SimpleNamespace(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))),
        llm_max_context_chars=int(os.getenv("LLM_MAX_CONTEXT_CHARS", "4000")),
    )


def onchain_settings() -> SimpleNamespace:
    import os

    return SimpleNamespace(
        onchain_analysis_url=os.getenv(
            "ONCHAIN_ANALYSIS_URL",
            "https://esraarlhpxraucslsdle.supabase.co/functions/v1/onchain-analysis",
        ),
        onchain_poll_interval_seconds=int(os.getenv("ONCHAIN_POLL_INTERVAL_SECONDS", "20")),
        onchain_max_wait_seconds=int(os.getenv("ONCHAIN_MAX_WAIT_SECONDS", "420")),
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
    )


def build_context(args: argparse.Namespace, max_chars: int) -> dict[str, str]:
    mention_text = args.mention_text.strip()
    parent_text = args.parent_text.strip()
    context_text = f"{mention_text}\n{parent_text}".strip()
    return {
        "mention_text": mention_text[:max_chars],
        "parent_text": parent_text[:max_chars],
        "context_text": context_text[:max_chars],
        "author_username": args.author_username.strip(),
        "social_hint": social_hint(mention_text),
    }


def social_hint(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ["introduce yourself", "who are you", "what do you do", "about you"]):
        return "intro"
    if any(token in lowered for token in ["hi", "hello", "hey", "gm", "yo", "hola"]):
        return "greeting"
    return "general"


def normalize_onchain_reply(payload: dict[str, Any], llm: LLMClient, context: dict[str, Any]) -> str:
    text = llm.draft_onchain_reply(context, payload).strip()
    return " ".join(text.split())


def missing_contract_reply() -> str:
    return (
        "Share the full contract address (0x...) and chain, and I will run the analysis and send back the dashboard."
    )


def missing_chain_reply() -> str:
    return (
        "I found a contract address. Which chain is it on? Supported: ethereum, polygon, "
        "bsc, arbitrum, optimism, base, avalanche."
    )


def main() -> int:
    if load_dotenv is not None:
        load_dotenv(REPO_ROOT / ".env")
    args = parse_args()
    llm = LLMClient(llm_settings())
    if not llm.enabled:
        print(json.dumps({"status": "failed", "error": "OPENAI_API_KEY is required for xagent tool layer"}))
        return 1

    context = build_context(args, llm_settings().llm_max_context_chars)
    persona = load_persona(args.persona_file)
    decision = llm.understand_mention(context)
    result: dict[str, Any] = {
        "status": "ok",
        "decision": {
            "intent": decision.intent,
            "contract_address": decision.contract_address,
            "chain": decision.chain,
            "confidence": decision.confidence,
            "rationale": decision.rationale,
        },
        "route": "",
        "reply": "",
    }

    if decision.intent != "onchain_analysis":
        result["route"] = "general"
        result["reply"] = llm.draft_general_reply(context, persona)
        print(json.dumps(result, indent=2))
        return 0

    contract = decision.contract_address
    chain = decision.chain
    if not contract:
        result["route"] = "needs_more_info"
        result["reply"] = missing_contract_reply()
        print(json.dumps(result, indent=2))
        return 0
    if not chain or chain not in SUPPORTED_CHAINS:
        result["route"] = "needs_more_info"
        result["reply"] = missing_chain_reply()
        print(json.dumps(result, indent=2))
        return 0

    result["route"] = "onchain_analysis"
    if not args.execute_onchain:
        result["reply"] = (
            f"Onchain analysis requested for {contract} on {chain}. "
            "Run again with --execute-onchain to execute the async analysis flow."
        )
        print(json.dumps(result, indent=2))
        return 0

    client = OnchainAnalysisClient(onchain_settings())
    payload = client.run_analysis(contract_address=contract, chain=chain)
    result["analysis"] = payload
    result["reply"] = normalize_onchain_reply(payload, llm, context)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
