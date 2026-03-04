from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    x_api_key: str
    x_api_key_secret: str
    x_access_token: str
    x_access_token_secret: str
    x_bot_user_id: str
    openai_api_key: str | None
    openai_model: str
    llm_timeout_seconds: int
    llm_confidence_threshold: float
    llm_max_context_chars: int
    general_reply_enabled: bool
    general_reply_cooldown_seconds: int
    general_reply_max_regen_attempts: int
    persona_file: str
    skip_existing_mentions_on_startup: bool
    processed_mentions_cache_size: int
    onchain_analysis_url: str
    onchain_poll_interval_seconds: int
    onchain_max_wait_seconds: int
    poll_interval_seconds: int
    max_mentions_per_poll: int
    request_timeout_seconds: int
    state_file: str
    log_level: str

    @staticmethod
    def from_env() -> "Settings":
        required = {
            "X_API_KEY": os.getenv("X_API_KEY"),
            "X_API_KEY_SECRET": os.getenv("X_API_KEY_SECRET"),
            "X_ACCESS_TOKEN": os.getenv("X_ACCESS_TOKEN"),
            "X_ACCESS_TOKEN_SECRET": os.getenv("X_ACCESS_TOKEN_SECRET"),
            "X_BOT_USER_ID": os.getenv("X_BOT_USER_ID"),
        }

        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        return Settings(
            x_api_key=required["X_API_KEY"] or "",
            x_api_key_secret=required["X_API_KEY_SECRET"] or "",
            x_access_token=required["X_ACCESS_TOKEN"] or "",
            x_access_token_secret=required["X_ACCESS_TOKEN_SECRET"] or "",
            x_bot_user_id=required["X_BOT_USER_ID"] or "",
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            llm_timeout_seconds=int(
                os.getenv("LLM_TIMEOUT_SECONDS", os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
            ),
            llm_confidence_threshold=float(os.getenv("LLM_CONFIDENCE_THRESHOLD", "0.65")),
            llm_max_context_chars=int(os.getenv("LLM_MAX_CONTEXT_CHARS", "4000")),
            general_reply_enabled=os.getenv("GENERAL_REPLY_ENABLED", "true").lower() == "true",
            general_reply_cooldown_seconds=int(os.getenv("GENERAL_REPLY_COOLDOWN_SECONDS", "600")),
            general_reply_max_regen_attempts=int(os.getenv("GENERAL_REPLY_MAX_REGEN_ATTEMPTS", "1")),
            persona_file=os.getenv("PERSONA_FILE", "agent.md"),
            skip_existing_mentions_on_startup=os.getenv(
                "SKIP_EXISTING_MENTIONS_ON_STARTUP", "true"
            ).lower()
            == "true",
            processed_mentions_cache_size=int(os.getenv("PROCESSED_MENTIONS_CACHE_SIZE", "2000")),
            onchain_analysis_url=os.getenv(
                "ONCHAIN_ANALYSIS_URL",
                "https://esraarlhpxraucslsdle.supabase.co/functions/v1/onchain-analysis",
            ),
            onchain_poll_interval_seconds=int(os.getenv("ONCHAIN_POLL_INTERVAL_SECONDS", "20")),
            onchain_max_wait_seconds=int(os.getenv("ONCHAIN_MAX_WAIT_SECONDS", "420")),
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "60")),
            max_mentions_per_poll=int(os.getenv("MAX_MENTIONS_PER_POLL", "10")),
            request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
            state_file=os.getenv("STATE_FILE", "state.json"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
