from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - exercised only when dependency is missing
    OpenAI = None  # type: ignore[assignment]

from .config import Settings

logger = logging.getLogger(__name__)

SUPPORTED_CHAINS = {
    "ethereum",
    "polygon",
    "bsc",
    "arbitrum",
    "optimism",
    "base",
    "avalanche",
}

CONTRACT_RE = re.compile(r"0x[a-fA-F0-9]{40}")


@dataclass(frozen=True)
class IntentDecision:
    intent: str
    contract_address: str | None
    chain: str | None
    confidence: float
    rationale: str


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        sdk_available = OpenAI is not None
        if settings.openai_api_key and not sdk_available:
            logger.warning("OPENAI_API_KEY is set but openai SDK is not installed. LLM mode disabled.")

        self._enabled = bool(settings.openai_api_key and sdk_available)
        self._model = settings.openai_model
        self._timeout = settings.llm_timeout_seconds
        self._max_context_chars = settings.llm_max_context_chars
        self._client = OpenAI(api_key=settings.openai_api_key) if self._enabled and OpenAI else None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def understand_mention(self, context: dict[str, Any]) -> IntentDecision:
        if not self._enabled or not self._client:
            raise RuntimeError("LLM client is not enabled")

        prompt = self._build_intent_prompt(context)
        text = self._chat(prompt)
        decision = _parse_intent_response(text)

        if decision.contract_address and not _is_valid_contract(decision.contract_address):
            decision = IntentDecision(
                intent=decision.intent,
                contract_address=None,
                chain=decision.chain,
                confidence=min(decision.confidence, 0.4),
                rationale=f"{decision.rationale} Contract address invalid format.",
            )

        if decision.chain and decision.chain not in SUPPORTED_CHAINS:
            decision = IntentDecision(
                intent=decision.intent,
                contract_address=decision.contract_address,
                chain=None,
                confidence=min(decision.confidence, 0.4),
                rationale=f"{decision.rationale} Chain unsupported.",
            )

        return decision

    def draft_onchain_reply(self, mention_context: dict[str, Any], onchain_payload: dict[str, Any]) -> str:
        if not self._enabled or not self._client:
            raise RuntimeError("LLM client is not enabled")

        prompt = self._build_reply_prompt(mention_context, onchain_payload)
        text = " ".join(self._chat(prompt).split()).strip()
        return _ensure_full_dashboard_url(text, onchain_payload)

    def draft_general_reply(self, context: dict[str, Any], agent_prompt: str | None) -> str:
        if not self._enabled or not self._client:
            raise RuntimeError("LLM client is not enabled")

        prompt = self._build_general_reply_prompt(context, agent_prompt)
        return " ".join(self._chat(prompt).split()).strip()

    def _chat(self, prompt: str) -> str:
        assert self._client is not None
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            timeout=self._timeout,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise assistant. Follow output format exactly. "
                        "Do not provide financial advice."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned empty content")
        return str(content)

    def _build_intent_prompt(self, context: dict[str, Any]) -> str:
        mention_text = str(context.get("mention_text") or "")
        parent_text = str(context.get("parent_text") or "")
        merged = f"MENTION:\n{mention_text}\n\nPARENT:\n{parent_text}"
        merged = merged[: self._max_context_chars]

        return (
            "Classify if this tweet context is asking for EVM smart-contract onchain analysis. "
            "Allowed chains: ethereum, polygon, bsc, arbitrum, optimism, base, avalanche. "
            "If uncertain, confidence must be low.\n\n"
            "Return EXACTLY 5 lines with this format:\n"
            "INTENT: onchain_analysis|general\n"
            "CONTRACT: <0x... or NONE>\n"
            "CHAIN: <ethereum|polygon|bsc|arbitrum|optimism|base|avalanche|NONE>\n"
            "CONFIDENCE: <0.00-1.00>\n"
            "RATIONALE: <short reason>\n\n"
            f"Context:\n{merged}"
        )

    def _build_reply_prompt(self, mention_context: dict[str, Any], onchain_payload: dict[str, Any]) -> str:
        mention_text = str(mention_context.get("mention_text") or "")
        status = str(onchain_payload.get("status") or "")
        result = onchain_payload.get("result")
        dashboard_url = ""
        if isinstance(result, dict):
            dashboard_url = str(result.get("dashboardUrl") or onchain_payload.get("dashboardUrl") or "")

        return (
            "Draft one X reply for this analysis result. "
            "Start with TLDR if available. Include dashboard URL if present. "
            "Mention one key method stat if available. Keep factual and concise. "
            "NEVER truncate, shorten, or ellipsize URLs. Always include the full dashboard URL exactly. "
            "No markdown, no hashtags unless already in source text, no financial advice.\n\n"
            f"Original mention: {mention_text[:800]}\n"
            f"Analysis status: {status}\n"
            f"Dashboard URL: {dashboard_url}\n"
            f"Analysis payload JSON: {onchain_payload}"
        )

    def _build_general_reply_prompt(self, context: dict[str, Any], agent_prompt: str | None) -> str:
        mention_text = str(context.get("mention_text") or "")
        parent_text = str(context.get("parent_text") or "")
        username = str(context.get("author_username") or "")
        avoid_text = str(context.get("avoid_text") or "")
        social_hint = str(context.get("social_hint") or "")
        recent_interaction_hint = str(context.get("recent_interaction_hint") or "")

        persona = (
            (agent_prompt or "").strip()
            or "You are OWAIbot: a friendly onchain analyst who also chats naturally with people on X."
        )
        persona = persona[:3000]

        variation_rule = ""
        if avoid_text:
            variation_rule = (
                f"Do not reuse this prior reply wording: {avoid_text[:400]}. "
                "Use different sentence structure while keeping meaning."
            )

        intent_guidance = (
            "If social intent is intro: introduce yourself as On-Chain Wizard, mention what you can do, and end with a clear CTA. "
            "If social intent is greeting: give a warm hello and offer help in one or two lines. "
            "If social intent is general: answer the user's current line first, then mention capabilities if useful."
        )

        style_exemplar = (
            "Style exemplar (do not copy verbatim): "
            "\"Hi there! 🧙‍♂️ On-Chain Wizard here, ready to help you analyze any EVM smart contract. "
            "Share a contract address + chain and I’ll take it from there.\""
        )

        return (
            "Write one reply tweet to a mention on X. "
            "Always reply to greetings and self-introduction requests. "
            "Be human, warm, concise, and factual. "
            "Use varied openings, avoid robotic repetition, and sound like a real person. "
            "No financial promises. No fabricated onchain data. "
            "Do not include stack traces or internal errors.\n\n"
            f"Persona instructions:\n{persona}\n\n"
            f"{intent_guidance}\n"
            f"{style_exemplar}\n"
            f"Mention author username: {username}\n"
            f"Mention text: {mention_text[:1200]}\n"
            f"Parent tweet text: {parent_text[:1200]}\n"
            f"Social intent hint: {social_hint}\n"
            f"Recent interaction hint: {recent_interaction_hint[:400]}\n"
            f"{variation_rule}"
        )


def _parse_intent_response(text: str) -> IntentDecision:
    fields = {
        "intent": None,
        "contract": None,
        "chain": None,
        "confidence": None,
        "rationale": "",
    }

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()

        if key == "intent":
            fields["intent"] = value.lower()
        elif key == "contract":
            fields["contract"] = None if value.upper() == "NONE" else value
        elif key == "chain":
            chain = value.lower()
            fields["chain"] = None if chain == "none" else chain
        elif key == "confidence":
            try:
                parsed = float(value)
            except ValueError:
                parsed = 0.0
            fields["confidence"] = max(0.0, min(1.0, parsed))
        elif key == "rationale":
            fields["rationale"] = value

    intent = fields["intent"] if fields["intent"] in {"onchain_analysis", "general"} else "general"
    confidence = fields["confidence"] if isinstance(fields["confidence"], float) else 0.0

    return IntentDecision(
        intent=intent,
        contract_address=fields["contract"] if isinstance(fields["contract"], str) else None,
        chain=fields["chain"] if isinstance(fields["chain"], str) else None,
        confidence=confidence,
        rationale=str(fields["rationale"] or ""),
    )


def _is_valid_contract(value: str) -> bool:
    return bool(CONTRACT_RE.fullmatch(value))


def _ensure_full_dashboard_url(text: str, payload: dict[str, Any]) -> str:
    result = payload.get("result")
    dashboard_url = ""
    if isinstance(result, dict):
        dashboard_url = str(result.get("dashboardUrl") or payload.get("dashboardUrl") or "").strip()
    elif payload.get("dashboardUrl"):
        dashboard_url = str(payload.get("dashboardUrl")).strip()

    if not dashboard_url:
        return text

    if dashboard_url in text:
        return text

    # LLM likely shortened/ellipsized URL; append the full canonical URL.
    if text:
        return f"{text} Dashboard: {dashboard_url}"
    return f"Dashboard: {dashboard_url}"
