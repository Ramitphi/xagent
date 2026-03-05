from __future__ import annotations

import logging
import re
import time
import hashlib
from pathlib import Path
from typing import Any

from .config import Settings
from .llm_client import LLMClient
from .onchain_analysis_client import OnchainAnalysisClient
from .state import StateStore
from .twitter_client import TwitterClient

logger = logging.getLogger(__name__)

CONTRACT_RE = re.compile(r"0x[a-fA-F0-9]{40}")
SUPPORTED_CHAINS = {"ethereum", "polygon", "bsc", "arbitrum", "optimism", "base", "avalanche"}
RETRY_RE = re.compile(r"\b(again|retry|try again|rerun|re-run|recheck|re-analy[sz]e)\b", re.IGNORECASE)
GREETING_RE = re.compile(r"\b(hi|hello|hey|gm|good morning|yo|hola)\b", re.IGNORECASE)
INTRO_RE = re.compile(r"\b(introduce yourself|who are you|about you|what do you do)\b", re.IGNORECASE)
SELF_HANDLE_RE = re.compile(r"@OWAIbot\b", re.IGNORECASE)

DEFAULT_PERSONA_PROMPT = (
    "You are OWAIbot, a friendly human-like analyst on X. "
    "You help with onchain analysis and also converse naturally in short, helpful replies."
)

CHAIN_PATTERNS = {
    "ethereum": [r"\beth(?:ereum)?\b", r"\bmainnet\b"],
    "polygon": [r"\bpolygon\b", r"\bmatic\b"],
    "bsc": [r"\bbsc\b", r"\bbinance smart chain\b"],
    "arbitrum": [r"\barbitrum\b", r"\barb\b"],
    "optimism": [r"\boptimism\b", r"\bop mainnet\b"],
    "base": [r"\bon\s+base\b", r"\bbase\s+chain\b", r"\b#base\b"],
    "avalanche": [r"\bavalanche\b", r"\bavax\b"],
}


class MentionReplyAgent:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._twitter = TwitterClient(settings)
        self._onchain = OnchainAnalysisClient(settings)
        self._llm = LLMClient(settings)
        self._state_store = StateStore(settings.state_file)
        self._persona_prompt = self._load_persona_prompt(settings.persona_file)

        if not self._llm.enabled:
            logger.warning("OPENAI_API_KEY not set. Running in fallback mode (regex + default social replies).")

    def run_startup_self_test(self) -> dict[str, Any]:
        result = self._twitter.credentials_self_test()
        logger.info(
            "credentials self-test auth_ok=%s auth_user_id=%s auth_username=%s configured_bot_user_id=%s "
            "mentions_read_ok=%s reply_write=%s access_level=%s",
            result.get("auth_ok"),
            result.get("auth_user_id"),
            result.get("auth_username"),
            result.get("configured_bot_user_id"),
            result.get("mentions_read_ok"),
            result.get("reply_write"),
            result.get("access_level"),
        )
        errors = result.get("errors") or []
        for err in errors:
            logger.warning("credentials self-test detail: %s", err)
        return result

    def run_forever(self) -> None:
        logger.info("Starting mention-reply agent")
        while True:
            try:
                self.run_once()
            except Exception:
                logger.exception("Agent poll failed")
            time.sleep(self._settings.poll_interval_seconds)

    def run_once(self) -> None:
        state = self._state_store.load()
        since_id = state.get("last_seen_id")
        processed_ids = self._get_processed_mentions(state)

        mentions = self._twitter.fetch_mentions(
            since_id=since_id,
            max_results=self._settings.max_mentions_per_poll,
        )

        if not mentions:
            logger.debug("No new mentions")
            return

        mentions.sort(key=lambda m: int(m["id"]))
        if (
            since_id is None
            and self._settings.skip_existing_mentions_on_startup
            and not state.get("startup_synced")
        ):
            newest = mentions[-1]["id"]
            state["last_seen_id"] = newest
            state["startup_synced"] = True
            self._state_store.save(state)
            logger.info(
                "Startup sync enabled; skipping %s existing mention(s) and setting last_seen_id=%s",
                len(mentions),
                newest,
            )
            return

        for mention in mentions:
            mention_id = mention["id"]
            try:
                if mention_id in processed_ids:
                    logger.info("Skipping previously processed mention %s", mention_id)
                    continue
                if mention.get("author_id") == self._settings.x_bot_user_id:
                    logger.info("Skipping own mention %s", mention_id)
                else:
                    logger.info("Processing mention %s", mention_id)
                    reply_text = self._build_reply_for_mention(mention, state)
                    if reply_text:
                        posted_ids = self._post_text_as_thread(reply_text, in_reply_to_tweet_id=mention_id)
                        if posted_ids:
                            logger.info("Posted %s reply tweet(s) to mention %s", len(posted_ids), mention_id)
                        else:
                            logger.info("Skipped reply for mention %s (duplicate content)", mention_id)
            except Exception:
                # Continue processing remaining mentions, but still checkpoint this mention id
                # to prevent repeated replies after service restarts.
                logger.exception("Failed processing mention %s", mention_id)
            finally:
                state["last_seen_id"] = mention_id
                self._mark_mention_processed(state, mention_id)
                self._state_store.save(state)

    def _build_reply_for_mention(self, mention: dict[str, str | None], state: dict[str, Any]) -> str | None:
        context = self._build_context(mention)
        mention_text = str(context.get("mention_text") or "")
        context_text = str(context.get("context_text") or "")
        conversation_id = str(mention.get("conversation_id") or "")
        convo_contract, convo_chain = self._get_conversation_contract_chain(state, conversation_id)
        author_id = str(mention.get("author_id") or "")
        social_hint = _social_intent_hint(mention_text)
        context["social_hint"] = social_hint

        # LLM-first routing.
        if self._llm.enabled:
            try:
                decision = self._llm.understand_mention(context)
                logger.info(
                    "LLM decision intent=%s confidence=%.2f contract=%s chain=%s",
                    decision.intent,
                    decision.confidence,
                    decision.contract_address,
                    decision.chain,
                )

                if (
                    decision.intent == "onchain_analysis"
                    and decision.confidence >= self._settings.llm_confidence_threshold
                ):
                    contract = decision.contract_address
                    chain = decision.chain
                    if not contract and convo_contract and _is_retry_request(mention_text):
                        contract = convo_contract
                    if not chain and convo_chain and _is_retry_request(mention_text):
                        chain = convo_chain
                    if not contract:
                        return self._missing_contract_reply(context=context, mention_text=mention_text)
                    if not chain:
                        return self._missing_chain_reply()
                    if chain not in SUPPORTED_CHAINS:
                        return self._missing_chain_reply()
                    return self._run_onchain_flow(
                        mention=mention,
                        contract=contract,
                        chain=chain,
                        context=context,
                        state=state,
                    )
                if self._settings.general_reply_enabled:
                    general_reply = self._build_general_reply(context=context, state=state, author_id=author_id)
                    if general_reply:
                        logger.info(
                            "route=general reply_action=posted reason=llm_general social_hint=%s", social_hint
                        )
                        return general_reply
                    logger.info(
                        "route=general reply_action=skipped reason=cooldown_or_duplicate social_hint=%s",
                        social_hint,
                    )
                    return None
            except Exception:
                logger.exception("LLM understanding failed, switching to fallback routing")

        # Fallback regex router.
        contract = _extract_contract_address(context_text)
        if contract:
            chain = _extract_chain(context_text)
            if not chain:
                return self._missing_chain_reply()
            return self._run_onchain_flow(
                mention=mention,
                contract=contract,
                chain=chain,
                context=context,
                state=state,
            )

        if convo_contract and convo_chain and _is_retry_request(mention_text):
            return self._run_onchain_flow(
                mention=mention,
                contract=convo_contract,
                chain=convo_chain,
                context=context,
                state=state,
            )

        if self._settings.general_reply_enabled:
            try:
                general_reply = self._build_general_reply(context=context, state=state, author_id=author_id)
                if general_reply:
                    logger.info("route=general reply_action=posted reason=llm_general_fallback")
                    return general_reply
                logger.info("route=general reply_action=skipped reason=cooldown_or_duplicate")
                return None
            except Exception:
                logger.exception("General LLM reply failed, using default social fallback")

        logger.info("route=fallback reply_action=posted reason=default_social")
        return (
            "Hey! 🧙‍♂️ On-Chain Wizard here. I can chat and help break down any EVM contract. "
            "Share address + chain and I will take it from there."
        )

    def _build_context(self, mention: dict[str, str | None]) -> dict[str, str]:
        mention_text = str(mention.get("text") or "")
        parent_text = ""

        reply_to_id = mention.get("reply_to_tweet_id")
        if reply_to_id:
            try:
                fetched = self._twitter.fetch_tweet_text(reply_to_id)
                if fetched:
                    parent_text = fetched
            except Exception:
                logger.exception("Failed to load parent tweet context for %s", reply_to_id)

        context_text = f"{mention_text}\n{parent_text}".strip()
        return {
            "mention_text": mention_text[: self._settings.llm_max_context_chars],
            "parent_text": parent_text[: self._settings.llm_max_context_chars],
            "context_text": context_text[: self._settings.llm_max_context_chars],
            "mention_id": str(mention.get("id") or ""),
            "author_id": str(mention.get("author_id") or ""),
            "conversation_id": str(mention.get("conversation_id") or ""),
        }

    def _run_onchain_flow(
        self,
        mention: dict[str, str | None],
        contract: str,
        chain: str,
        context: dict[str, str],
        state: dict[str, Any],
    ) -> None:
        if not _is_valid_contract(contract):
            return None
        if chain not in SUPPORTED_CHAINS:
            return None

        conversation_id = str(mention.get("conversation_id") or "")
        self._set_conversation_contract_chain(state, conversation_id, contract, chain)

        ack = (
            f"Starting on-chain analysis for {contract[:8]}... on {chain}. "
            "This usually takes 2-5 mins. I will post results shortly."
        )
        ack_ids = self._post_text_as_thread(ack, in_reply_to_tweet_id=str(mention["id"]))
        ack_id = ack_ids[-1] if ack_ids else ""
        reply_anchor_id = ack_id or str(mention["id"])

        result = self._onchain.run_analysis(contract_address=contract, chain=chain)
        final_reply = self._compose_final_onchain_reply(context, result)

        final_ids = self._post_text_as_thread(final_reply, in_reply_to_tweet_id=reply_anchor_id)
        if final_ids:
            logger.info(
                "Posted onchain result (%s tweet(s)) for mention %s",
                len(final_ids),
                mention.get("id"),
            )
        else:
            logger.info("Skipped onchain result reply for mention %s (duplicate content)", mention.get("id"))
        return None

    def _compose_final_onchain_reply(self, context: dict[str, str], payload: dict[str, Any]) -> str:
        llm_text = ""
        if self._llm.enabled:
            try:
                llm_text = self._llm.draft_onchain_reply(context, payload)
            except Exception:
                logger.exception("LLM reply drafting failed, using deterministic fallback")

        if llm_text:
            return _safe_tweet_text(llm_text)

        return self._format_onchain_result(payload)

    def _missing_chain_reply(self) -> str:
        return (
            "I found a contract address. Which chain is it on? Supported: ethereum, polygon, "
            "bsc, arbitrum, optimism, base, avalanche."
        )

    def _missing_contract_reply(self, context: dict[str, str], mention_text: str) -> str:
        tone = "Happy to jump in."
        if _is_retry_request(mention_text):
            tone = "I can rerun it right away."
        if _social_intent_hint(mention_text) == "greeting":
            tone = "Hey! Great to see you here."

        parent_text = str(context.get("parent_text") or "").strip()
        if parent_text:
            return (
                f"{tone} I can see the conversation context, but I still need the exact contract address "
                "(full 0x... address) and chain to run analysis. Supported chains: ethereum, polygon, "
                "bsc, arbitrum, optimism, base, avalanche."
            )

        return (
            f"{tone} Share the full contract address (0x...) and chain, and I will run the analysis and "
            "send you the dashboard. Supported chains: ethereum, polygon, bsc, arbitrum, optimism, "
            "base, avalanche."
        )

    def _format_onchain_result(self, payload: dict[str, object]) -> str:
        status = str(payload.get("status") or "")
        if status == "failed":
            error = str(payload.get("error") or "Unknown failure")
            if "Could not fetch ABI" in error:
                return "Analysis failed: ABI not verified. Reply with ABI JSON and I can retry."
            return _safe_tweet_text(f"Analysis failed: {error}")

        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        if not isinstance(result, dict):
            result = {}

        tldr = str(result.get("tldr") or "").replace("\n", " ").strip()
        dashboard = str(result.get("dashboardUrl") or payload.get("dashboardUrl") or "")

        top_methods = result.get("topMethods")
        top_line = ""
        if isinstance(top_methods, list) and top_methods:
            first = top_methods[0]
            if isinstance(first, dict):
                fn = str(first.get("function_name") or "unknown_fn")
                calls = first.get("call_count")
                callers = first.get("unique_callers")
                top_line = f" Top: {fn} ({calls} calls, {callers} callers)."

        summary = "TLDR: " + tldr if tldr else "Analysis completed."
        if dashboard:
            summary += f" Dashboard: {dashboard}."
        summary += top_line
        return _safe_tweet_text(summary)

    def _post_text_as_thread(self, text: str, in_reply_to_tweet_id: str) -> list[str]:
        chunks = _split_tweet_chunks(_safe_tweet_text(text))
        posted_ids: list[str] = []
        anchor = in_reply_to_tweet_id
        for chunk in chunks:
            reply_id = self._twitter.post_reply(chunk, in_reply_to_tweet_id=anchor)
            if reply_id:
                posted_ids.append(reply_id)
                anchor = reply_id
        return posted_ids

    def _get_conversation_contract_chain(
        self,
        state: dict[str, Any],
        conversation_id: str,
    ) -> tuple[str | None, str | None]:
        if not conversation_id:
            return None, None
        contexts = state.get("conversation_contexts")
        if not isinstance(contexts, dict):
            return None, None
        entry = contexts.get(conversation_id)
        if not isinstance(entry, dict):
            return None, None
        contract = entry.get("contract")
        chain = entry.get("chain")
        if isinstance(contract, str) and isinstance(chain, str):
            return contract, chain
        return None, None

    def _set_conversation_contract_chain(
        self,
        state: dict[str, Any],
        conversation_id: str,
        contract: str,
        chain: str,
    ) -> None:
        if not conversation_id:
            return
        contexts = state.setdefault("conversation_contexts", {})
        if isinstance(contexts, dict):
            contexts[conversation_id] = {"contract": contract, "chain": chain}

    def _load_persona_prompt(self, persona_file: str) -> str:
        try:
            path = Path(persona_file)
            if not path.is_absolute():
                path = Path.cwd() / path
            if path.exists():
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    logger.info("Loaded persona prompt from %s", path)
                    return text
            logger.warning("Persona file not found or empty at %s; using built-in persona", path)
            return DEFAULT_PERSONA_PROMPT
        except Exception:
            logger.exception("Failed to load persona file; using built-in persona")
            return DEFAULT_PERSONA_PROMPT

    def _build_general_reply(self, context: dict[str, str], state: dict[str, Any], author_id: str) -> str | None:
        if not self._llm.enabled:
            raise RuntimeError("LLM is required for general reply mode")

        recent = self._get_recent_general_reply(state, author_id)
        now_ts = int(time.time())
        social_hint = str(context.get("social_hint") or "general")
        mention_text = str(context.get("mention_text") or "")
        mention_hash = _hash_text(mention_text.lower().strip())
        is_in_cooldown = bool(
            recent and (now_ts - recent.get("last_timestamp", 0) < self._settings.general_reply_cooldown_seconds)
        )
        repeated_social_ping = False
        if recent and is_in_cooldown:
            recent_hint = str(recent.get("last_social_hint") or "")
            recent_mention_hash = str(recent.get("last_mention_hash") or "")
            is_social_ping = social_hint in {"greeting", "intro"}
            same_bucket = recent_hint == social_hint
            same_mention = recent_mention_hash == mention_hash
            repeated_social_ping = is_social_ping and (same_bucket or same_mention)

        avoid_text = ""
        recent_reply_hash = ""
        if recent:
            avoid_text = str(recent.get("last_text") or "")
            recent_reply_hash = str(recent.get("last_text_hash") or "")
            context["recent_interaction_hint"] = (
                "User has interacted recently. Acknowledge continuity naturally if it fits."
            )

        attempts = max(0, self._settings.general_reply_max_regen_attempts) + 1
        for idx in range(attempts):
            if avoid_text and idx > 0:
                context["avoid_text"] = avoid_text
            reply = _safe_tweet_text(self._llm.draft_general_reply(context, self._persona_prompt))
            if not reply:
                continue

            reply_hash = _hash_text(reply)
            if recent and reply_hash == recent_reply_hash and idx < (attempts - 1):
                logger.info("route=general reply_action=regen reason=duplicate_hash")
                continue
            if repeated_social_ping and recent and reply_hash == recent_reply_hash:
                logger.info(
                    "route=general reply_action=skipped_cooldown reason=repeated_social_ping author_id=%s",
                    author_id,
                )
                return None

            self._set_recent_general_reply(
                state=state,
                author_id=author_id,
                text=reply,
                text_hash=reply_hash,
                mention_hash=mention_hash,
                social_hint=social_hint,
                ts=now_ts,
            )
            return reply
        return None

    def _get_recent_general_reply(self, state: dict[str, Any], author_id: str) -> dict[str, Any] | None:
        if not author_id:
            return None
        store = state.get("recent_general_replies_by_user")
        if not isinstance(store, dict):
            return None
        entry = store.get(author_id)
        if isinstance(entry, dict):
            return entry
        return None

    def _set_recent_general_reply(
        self,
        state: dict[str, Any],
        author_id: str,
        text: str,
        text_hash: str,
        mention_hash: str,
        social_hint: str,
        ts: int,
    ) -> None:
        if not author_id:
            return
        store = state.setdefault("recent_general_replies_by_user", {})
        if isinstance(store, dict):
            store[author_id] = {
                "last_text": text,
                "last_text_hash": text_hash,
                "last_mention_hash": mention_hash,
                "last_social_hint": social_hint,
                "last_timestamp": ts,
            }

    def _get_processed_mentions(self, state: dict[str, Any]) -> set[str]:
        values = state.get("processed_mention_ids")
        if isinstance(values, list):
            return {str(v) for v in values}
        return set()

    def _mark_mention_processed(self, state: dict[str, Any], mention_id: str) -> None:
        values = state.get("processed_mention_ids")
        if not isinstance(values, list):
            values = []
        values.append(str(mention_id))
        max_size = max(100, self._settings.processed_mentions_cache_size)
        if len(values) > max_size:
            values = values[-max_size:]
        state["processed_mention_ids"] = values


def _extract_contract_address(text: str) -> str | None:
    match = CONTRACT_RE.search(text)
    return match.group(0) if match else None


def _extract_chain(text: str) -> str | None:
    lowered = text.lower()
    for chain, patterns in CHAIN_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, lowered):
                return chain
    return None


def _is_valid_contract(value: str) -> bool:
    return bool(CONTRACT_RE.fullmatch(value))


def _safe_tweet_text(text: str) -> str:
    cleaned = " ".join(str(text).split())
    cleaned = SELF_HANDLE_RE.sub("", cleaned)
    cleaned = " ".join(cleaned.split())
    if "traceback" in cleaned.lower():
        cleaned = "Analysis failed due to an internal error. Please retry shortly."
    return cleaned


def _clip_tweet(text: str) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= 280:
        return normalized
    return normalized[:277] + "..."


def _split_tweet_chunks(text: str, max_len: int = 280) -> list[str]:
    normalized = " ".join(text.split())
    if len(normalized) <= max_len:
        return [normalized]

    words = normalized.split(" ")
    chunks: list[str] = []
    current = ""
    for word in words:
        # If a single token exceeds the limit, hard-split it.
        if len(word) > max_len:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(word), max_len):
                chunks.append(word[i : i + max_len])
            continue

        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= max_len:
            current = candidate
        else:
            chunks.append(current)
            current = word

    if current:
        chunks.append(current)
    return chunks


def _is_retry_request(text: str) -> bool:
    return bool(RETRY_RE.search(text))


def _social_intent_hint(text: str) -> str:
    if INTRO_RE.search(text):
        return "intro"
    if GREETING_RE.search(text):
        return "greeting"
    return "general"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
