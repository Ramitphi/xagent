from __future__ import annotations

import logging
import time

from .analysis_client import AnalysisClient
from .config import Settings
from .state import StateStore
from .twitter_client import TwitterClient

logger = logging.getLogger(__name__)


class MentionReplyAgent:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._twitter = TwitterClient(settings)
        self._analysis = AnalysisClient(settings)
        self._state_store = StateStore(settings.state_file)

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

        mentions = self._twitter.fetch_mentions(
            since_id=since_id,
            max_results=self._settings.max_mentions_per_poll,
        )

        if not mentions:
            logger.debug("No new mentions")
            return

        mentions.sort(key=lambda m: int(m["id"]))
        latest_seen_id = since_id

        for mention in mentions:
            mention_id = mention["id"]
            latest_seen_id = mention_id

            if mention.get("author_id") == self._settings.x_bot_user_id:
                logger.info("Skipping own mention %s", mention_id)
                continue

            logger.info("Processing mention %s", mention_id)
            reply_text = self._analysis.build_reply(mention)
            if len(reply_text) > 280:
                reply_text = reply_text[:277] + "..."

            reply_id = self._twitter.post_reply(reply_text, in_reply_to_tweet_id=mention_id)
            logger.info("Posted reply %s to mention %s", reply_id, mention_id)

        state["last_seen_id"] = latest_seen_id
        self._state_store.save(state)
