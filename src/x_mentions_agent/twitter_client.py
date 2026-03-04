from __future__ import annotations

import logging
from typing import Any

import requests
import tweepy
from requests_oauthlib import OAuth1

from .config import Settings

logger = logging.getLogger(__name__)


class TwitterClient:
    def __init__(self, settings: Settings) -> None:
        self._consumer_key = settings.x_api_key
        self._consumer_secret = settings.x_api_key_secret
        self._access_token = settings.x_access_token
        self._access_token_secret = settings.x_access_token_secret
        self._client = tweepy.Client(
            consumer_key=self._consumer_key,
            consumer_secret=self._consumer_secret,
            access_token=self._access_token,
            access_token_secret=self._access_token_secret,
            wait_on_rate_limit=True,
        )
        self._bot_user_id = settings.x_bot_user_id

    def credentials_self_test(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "auth_ok": False,
            "auth_user_id": None,
            "auth_username": None,
            "configured_bot_user_id": self._bot_user_id,
            "mentions_read_ok": False,
            "reply_write": "unknown",
            "access_level": None,
            "v1_verify_credentials_ok": False,
            "v1_verify_credentials_status": None,
            "errors": [],
        }

        try:
            me = self._client.get_me(user_auth=True)
            if me and me.data:
                result["auth_ok"] = True
                result["auth_user_id"] = str(me.data.id)
                result["auth_username"] = getattr(me.data, "username", None)
        except Exception as exc:
            detail = _extract_http_error_detail(exc)
            result["errors"].append(f"auth_failed: {detail}")
            self._probe_v1_verify_credentials(result)
            return result

        try:
            raw = self._client.request("GET", "/2/users/me", user_auth=True)
            access_level = raw.headers.get("x-access-level")
            result["access_level"] = access_level
            if access_level:
                normalized = access_level.lower()
                if "write" in normalized or "read-write" in normalized:
                    result["reply_write"] = "yes"
                elif "read" in normalized:
                    result["reply_write"] = "no"
        except Exception as exc:
            detail = _extract_http_error_detail(exc)
            result["errors"].append(f"access_level_probe_failed: {detail}")

        try:
            self._fetch_mentions_raw(since_id=None, max_results=5)
            result["mentions_read_ok"] = True
        except Exception as exc:
            detail = _extract_http_error_detail(exc)
            result["errors"].append(f"mentions_read_failed: {detail}")

        self._probe_v1_verify_credentials(result)

        return result

    def _probe_v1_verify_credentials(self, result: dict[str, Any]) -> None:
        try:
            response = requests.get(
                "https://api.twitter.com/1.1/account/verify_credentials.json",
                auth=OAuth1(
                    self._consumer_key,
                    self._consumer_secret,
                    self._access_token,
                    self._access_token_secret,
                ),
                timeout=15,
            )
            result["v1_verify_credentials_status"] = response.status_code
            if response.status_code == 200:
                result["v1_verify_credentials_ok"] = True
            else:
                snippet = (response.text or "").strip().replace("\n", " ")
                if len(snippet) > 180:
                    snippet = snippet[:177] + "..."
                result["errors"].append(
                    f"v1_verify_credentials_failed: status={response.status_code} body={snippet}"
                )
        except Exception as exc:
            result["errors"].append(f"v1_verify_credentials_probe_error: {exc}")

    def fetch_mentions(self, since_id: str | None, max_results: int) -> list[dict[str, Any]]:
        response = self._fetch_mentions_raw(since_id=since_id, max_results=max_results)

        if not response or not response.data:
            return []

        mentions: list[dict[str, Any]] = []
        for tweet in response.data:
            reply_to_id = None
            if tweet.referenced_tweets:
                for ref in tweet.referenced_tweets:
                    if ref.type == "replied_to":
                        reply_to_id = str(ref.id)
                        break

            mentions.append(
                {
                    "id": str(tweet.id),
                    "text": tweet.text,
                    "author_id": str(tweet.author_id) if tweet.author_id else None,
                    "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
                    "conversation_id": str(tweet.conversation_id) if tweet.conversation_id else None,
                    "reply_to_tweet_id": reply_to_id,
                }
            )

        return mentions

    def _fetch_mentions_raw(self, since_id: str | None, max_results: int) -> Any:
        params = {
            "id": self._bot_user_id,
            "since_id": since_id,
            "max_results": max(5, min(max_results, 100)),
            "tweet_fields": ["author_id", "created_at", "conversation_id", "referenced_tweets"],
            "user_auth": True,
        }

        try:
            return self._client.get_users_mentions(**params)
        except tweepy.Forbidden:
            # Most common cause is mismatched X_BOT_USER_ID vs auth tokens.
            me = self._client.get_me(user_auth=True)
            if me and me.data and str(me.data.id) != self._bot_user_id:
                old_id = self._bot_user_id
                self._bot_user_id = str(me.data.id)
                logger.warning(
                    "X_BOT_USER_ID (%s) mismatched auth user id (%s). Retrying with auth user id.",
                    old_id,
                    self._bot_user_id,
                )
                params["id"] = self._bot_user_id
                return self._client.get_users_mentions(**params)
            raise

    def fetch_tweet_text(self, tweet_id: str) -> str | None:
        response = self._client.get_tweet(tweet_id, tweet_fields=["text"], user_auth=True)
        if not response or not response.data:
            return None
        return response.data.text

    def post_reply(self, text: str, in_reply_to_tweet_id: str) -> str:
        try:
            response = self._client.create_tweet(
                text=text,
                in_reply_to_tweet_id=in_reply_to_tweet_id,
                user_auth=True,
            )
            return str(response.data["id"])
        except tweepy.Forbidden as exc:
            if _is_duplicate_tweet_error(exc):
                logger.warning("Skipping duplicate reply for tweet %s", in_reply_to_tweet_id)
                return ""
            raise


def _extract_http_error_detail(exc: Exception) -> str:
    try:
        response = getattr(exc, "response", None)
        if response is None:
            return str(exc)
        status = getattr(response, "status_code", "unknown")
        body = (getattr(response, "text", "") or "").strip().replace("\n", " ")
        if len(body) > 180:
            body = body[:177] + "..."
        return f"{exc} status={status} body={body}"
    except Exception:
        return str(exc)


def _is_duplicate_tweet_error(exc: Exception) -> bool:
    detail = _extract_http_error_detail(exc).lower()
    return "duplicate content" in detail or "duplicate" in detail
