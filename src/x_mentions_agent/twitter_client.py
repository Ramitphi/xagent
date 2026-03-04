from __future__ import annotations

from typing import Any

import tweepy

from .config import Settings


class TwitterClient:
    def __init__(self, settings: Settings) -> None:
        self._client = tweepy.Client(
            consumer_key=settings.x_api_key,
            consumer_secret=settings.x_api_key_secret,
            access_token=settings.x_access_token,
            access_token_secret=settings.x_access_token_secret,
            wait_on_rate_limit=True,
        )
        self._bot_user_id = settings.x_bot_user_id

    def fetch_mentions(self, since_id: str | None, max_results: int) -> list[dict[str, Any]]:
        response = self._client.get_users_mentions(
            id=self._bot_user_id,
            since_id=since_id,
            max_results=max(5, min(max_results, 100)),
            tweet_fields=["author_id", "created_at", "conversation_id", "referenced_tweets"],
        )

        if not response or not response.data:
            return []

        mentions: list[dict[str, Any]] = []
        for tweet in response.data:
            mentions.append(
                {
                    "id": str(tweet.id),
                    "text": tweet.text,
                    "author_id": str(tweet.author_id) if tweet.author_id else None,
                    "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
                    "conversation_id": str(tweet.conversation_id) if tweet.conversation_id else None,
                }
            )

        return mentions

    def post_reply(self, text: str, in_reply_to_tweet_id: str) -> str:
        response = self._client.create_tweet(
            text=text,
            in_reply_to_tweet_id=in_reply_to_tweet_id,
        )
        return str(response.data["id"])
