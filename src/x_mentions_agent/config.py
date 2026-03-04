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
    analysis_api_url: str
    analysis_api_key: str | None
    analysis_api_key_header: str
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
            "ANALYSIS_API_URL": os.getenv("ANALYSIS_API_URL"),
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
            analysis_api_url=required["ANALYSIS_API_URL"] or "",
            analysis_api_key=os.getenv("ANALYSIS_API_KEY"),
            analysis_api_key_header=os.getenv("ANALYSIS_API_KEY_HEADER", "Authorization"),
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "60")),
            max_mentions_per_poll=int(os.getenv("MAX_MENTIONS_PER_POLL", "10")),
            request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
            state_file=os.getenv("STATE_FILE", "state.json"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
