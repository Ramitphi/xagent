from __future__ import annotations

import types
import unittest
import sys
from unittest.mock import MagicMock, patch

from src.x_mentions_agent.llm_client import IntentDecision

# Allow importing agent module in environments without installed runtime deps.
if "tweepy" not in sys.modules:
    sys.modules["tweepy"] = types.SimpleNamespace(Client=object)


class TestAgentRouting(unittest.TestCase):
    def _settings(self) -> types.SimpleNamespace:
        return types.SimpleNamespace(
            x_api_key="k",
            x_api_key_secret="k",
            x_access_token="k",
            x_access_token_secret="k",
            x_bot_user_id="999",
            openai_api_key="sk-test",
            openai_model="gpt-4.1-mini",
            llm_timeout_seconds=20,
            llm_confidence_threshold=0.65,
            llm_max_context_chars=4000,
            general_reply_enabled=True,
            general_reply_cooldown_seconds=600,
            general_reply_max_regen_attempts=1,
            persona_file="agent.md",
            skip_existing_mentions_on_startup=True,
            processed_mentions_cache_size=2000,
            onchain_analysis_url="https://example.com/onchain",
            onchain_poll_interval_seconds=1,
            onchain_max_wait_seconds=10,
            poll_interval_seconds=1,
            max_mentions_per_poll=10,
            request_timeout_seconds=20,
            state_file="state.json",
            log_level="INFO",
        )

    @patch("src.x_mentions_agent.agent.LLMClient")
    @patch("src.x_mentions_agent.agent.OnchainAnalysisClient")
    @patch("src.x_mentions_agent.agent.TwitterClient")
    def test_llm_onchain_path_posts_ack_and_result(
        self,
        twitter_cls: MagicMock,
        onchain_cls: MagicMock,
        llm_cls: MagicMock,
    ) -> None:
        from src.x_mentions_agent.agent import MentionReplyAgent

        twitter = twitter_cls.return_value
        twitter.post_reply.side_effect = ["ack-1", "final-1"]

        onchain = onchain_cls.return_value
        onchain.run_analysis.return_value = {"status": "completed", "result": {"tldr": "ok"}}

        llm = llm_cls.return_value
        llm.enabled = True
        llm.understand_mention.return_value = IntentDecision(
            intent="onchain_analysis",
            contract_address="0x00000000009726632680FB29d3F7A9734E3010E2",
            chain="base",
            confidence=0.9,
            rationale="clear",
        )
        llm.draft_onchain_reply.return_value = "TLDR: done"
        llm.draft_general_reply.return_value = "hello"

        agent = MentionReplyAgent(self._settings())
        mention = {
            "id": "123",
            "text": "analyze 0x00000000009726632680FB29d3F7A9734E3010E2 on base",
            "author_id": "111",
            "reply_to_tweet_id": None,
            "conversation_id": "c1",
        }

        reply = agent._build_reply_for_mention(mention, {"last_seen_id": None})
        self.assertIsNone(reply)
        self.assertEqual(twitter.post_reply.call_count, 2)
        onchain.run_analysis.assert_called_once()

    @patch("src.x_mentions_agent.agent.LLMClient")
    @patch("src.x_mentions_agent.agent.OnchainAnalysisClient")
    @patch("src.x_mentions_agent.agent.TwitterClient")
    def test_missing_chain_prompts_user(
        self,
        twitter_cls: MagicMock,
        onchain_cls: MagicMock,
        llm_cls: MagicMock,
    ) -> None:
        from src.x_mentions_agent.agent import MentionReplyAgent

        llm = llm_cls.return_value
        llm.enabled = True
        llm.understand_mention.return_value = IntentDecision(
            intent="onchain_analysis",
            contract_address="0x00000000009726632680FB29d3F7A9734E3010E2",
            chain=None,
            confidence=0.95,
            rationale="chain missing",
        )
        llm.draft_general_reply.return_value = "hello"

        agent = MentionReplyAgent(self._settings())
        reply = agent._build_reply_for_mention(
            {
                "id": "123",
                "text": "analyze 0x00000000009726632680FB29d3F7A9734E3010E2",
                "author_id": "111",
                "reply_to_tweet_id": None,
                "conversation_id": "c1",
            },
            {"last_seen_id": None},
        )

        self.assertIn("Which chain", str(reply))
        onchain_cls.return_value.run_analysis.assert_not_called()

    @patch("src.x_mentions_agent.agent.LLMClient")
    @patch("src.x_mentions_agent.agent.OnchainAnalysisClient")
    @patch("src.x_mentions_agent.agent.TwitterClient")
    def test_llm_failure_falls_back_to_general_llm(
        self,
        twitter_cls: MagicMock,
        onchain_cls: MagicMock,
        llm_cls: MagicMock,
    ) -> None:
        from src.x_mentions_agent.agent import MentionReplyAgent

        llm = llm_cls.return_value
        llm.enabled = True
        llm.understand_mention.side_effect = RuntimeError("llm down")
        llm.draft_general_reply.return_value = "hello there"

        agent = MentionReplyAgent(self._settings())
        reply = agent._build_reply_for_mention(
            {
                "id": "123",
                "text": "hello team",
                "author_id": "111",
                "reply_to_tweet_id": None,
                "conversation_id": "c1",
            },
            {"last_seen_id": None},
        )

        self.assertEqual(reply, "hello there")
        onchain_cls.return_value.run_analysis.assert_not_called()

    @patch("src.x_mentions_agent.agent.LLMClient")
    @patch("src.x_mentions_agent.agent.OnchainAnalysisClient")
    @patch("src.x_mentions_agent.agent.TwitterClient")
    def test_general_mention_uses_llm_social_reply(
        self,
        twitter_cls: MagicMock,
        onchain_cls: MagicMock,
        llm_cls: MagicMock,
    ) -> None:
        from src.x_mentions_agent.agent import MentionReplyAgent

        llm = llm_cls.return_value
        llm.enabled = True
        llm.understand_mention.return_value = IntentDecision(
            intent="general",
            contract_address=None,
            chain=None,
            confidence=0.9,
            rationale="greeting",
        )
        llm.draft_general_reply.return_value = "Hi! I am OWAIbot."

        agent = MentionReplyAgent(self._settings())
        reply = agent._build_reply_for_mention(
            {
                "id": "300",
                "text": "hi @OWAIbot introduce yourself",
                "author_id": "111",
                "reply_to_tweet_id": None,
                "conversation_id": "cx",
            },
            {"last_seen_id": None},
        )

        self.assertEqual(reply, "Hi! I am OWAIbot.")
        onchain_cls.return_value.run_analysis.assert_not_called()

    @patch("src.x_mentions_agent.agent.LLMClient")
    @patch("src.x_mentions_agent.agent.OnchainAnalysisClient")
    @patch("src.x_mentions_agent.agent.TwitterClient")
    def test_general_cooldown_skips_second_reply(
        self,
        twitter_cls: MagicMock,
        onchain_cls: MagicMock,
        llm_cls: MagicMock,
    ) -> None:
        from src.x_mentions_agent.agent import MentionReplyAgent

        llm = llm_cls.return_value
        llm.enabled = True
        llm.understand_mention.return_value = IntentDecision(
            intent="general",
            contract_address=None,
            chain=None,
            confidence=0.9,
            rationale="greeting",
        )
        llm.draft_general_reply.return_value = "Hi! I am OWAIbot."

        settings = self._settings()
        settings.general_reply_cooldown_seconds = 600
        agent = MentionReplyAgent(settings)
        state = {"last_seen_id": None}
        first = agent._build_reply_for_mention(
            {
                "id": "301",
                "text": "hi",
                "author_id": "111",
                "reply_to_tweet_id": None,
                "conversation_id": "c1",
            },
            state,
        )
        second = agent._build_reply_for_mention(
            {
                "id": "302",
                "text": "hello again",
                "author_id": "111",
                "reply_to_tweet_id": None,
                "conversation_id": "c1",
            },
            state,
        )

        self.assertEqual(first, "Hi! I am OWAIbot.")
        self.assertIsNone(second)

    @patch("src.x_mentions_agent.agent.LLMClient")
    @patch("src.x_mentions_agent.agent.OnchainAnalysisClient")
    @patch("src.x_mentions_agent.agent.TwitterClient")
    def test_general_followup_not_blocked_by_greeting_cooldown(
        self,
        twitter_cls: MagicMock,
        onchain_cls: MagicMock,
        llm_cls: MagicMock,
    ) -> None:
        from src.x_mentions_agent.agent import MentionReplyAgent

        llm = llm_cls.return_value
        llm.enabled = True
        llm.understand_mention.return_value = IntentDecision(
            intent="general",
            contract_address=None,
            chain=None,
            confidence=0.9,
            rationale="social",
        )
        llm.draft_general_reply.side_effect = ["Hi! I am OWAIbot.", "Yes, I am up. How can I help?"]

        settings = self._settings()
        settings.general_reply_cooldown_seconds = 600
        agent = MentionReplyAgent(settings)
        state = {"last_seen_id": None}

        first = agent._build_reply_for_mention(
            {
                "id": "501",
                "text": "hi",
                "author_id": "111",
                "reply_to_tweet_id": None,
                "conversation_id": "c1",
            },
            state,
        )
        second = agent._build_reply_for_mention(
            {
                "id": "502",
                "text": "are you up",
                "author_id": "111",
                "reply_to_tweet_id": None,
                "conversation_id": "c1",
            },
            state,
        )

        self.assertEqual(first, "Hi! I am OWAIbot.")
        self.assertEqual(second, "Yes, I am up. How can I help?")

    @patch("src.x_mentions_agent.agent.LLMClient")
    @patch("src.x_mentions_agent.agent.OnchainAnalysisClient")
    @patch("src.x_mentions_agent.agent.TwitterClient")
    def test_default_social_reply_when_general_disabled_or_llm_off(
        self,
        twitter_cls: MagicMock,
        onchain_cls: MagicMock,
        llm_cls: MagicMock,
    ) -> None:
        from src.x_mentions_agent.agent import MentionReplyAgent

        llm = llm_cls.return_value
        llm.enabled = False

        settings = self._settings()
        settings.general_reply_enabled = False
        agent = MentionReplyAgent(settings)
        reply = agent._build_reply_for_mention(
            {
                "id": "401",
                "text": "hello",
                "author_id": "222",
                "reply_to_tweet_id": None,
                "conversation_id": "c2",
            },
            {"last_seen_id": None},
        )

        self.assertIn("On-Chain Wizard", reply)

    @patch("src.x_mentions_agent.agent.LLMClient")
    @patch("src.x_mentions_agent.agent.OnchainAnalysisClient")
    @patch("src.x_mentions_agent.agent.TwitterClient")
    @patch("src.x_mentions_agent.agent.StateStore")
    def test_startup_sync_skips_existing_mentions_on_empty_state(
        self,
        state_store_cls: MagicMock,
        twitter_cls: MagicMock,
        onchain_cls: MagicMock,
        llm_cls: MagicMock,
    ) -> None:
        from src.x_mentions_agent.agent import MentionReplyAgent

        llm = llm_cls.return_value
        llm.enabled = True
        llm.understand_mention.return_value = IntentDecision(
            intent="general",
            contract_address=None,
            chain=None,
            confidence=0.9,
            rationale="greeting",
        )
        llm.draft_general_reply.return_value = "Hi!"

        twitter = twitter_cls.return_value
        twitter.fetch_mentions.return_value = [
            {"id": "100", "text": "old hi", "author_id": "111", "conversation_id": "c1", "reply_to_tweet_id": None},
            {"id": "110", "text": "old intro", "author_id": "112", "conversation_id": "c2", "reply_to_tweet_id": None},
        ]

        state_store = state_store_cls.return_value
        state_store.load.return_value = {"last_seen_id": None}

        settings = self._settings()
        settings.skip_existing_mentions_on_startup = True
        agent = MentionReplyAgent(settings)
        agent.run_once()

        twitter.post_reply.assert_not_called()
        state_store.save.assert_called_once()
        saved_state = state_store.save.call_args.args[0]
        self.assertEqual(saved_state.get("last_seen_id"), "110")
        self.assertTrue(saved_state.get("startup_synced"))

    @patch("src.x_mentions_agent.agent.LLMClient")
    @patch("src.x_mentions_agent.agent.OnchainAnalysisClient")
    @patch("src.x_mentions_agent.agent.TwitterClient")
    def test_repeated_greeting_regenerates_before_skip(
        self,
        twitter_cls: MagicMock,
        onchain_cls: MagicMock,
        llm_cls: MagicMock,
    ) -> None:
        from src.x_mentions_agent.agent import MentionReplyAgent, _hash_text

        llm = llm_cls.return_value
        llm.enabled = True
        llm.understand_mention.return_value = IntentDecision(
            intent="general",
            contract_address=None,
            chain=None,
            confidence=0.9,
            rationale="greeting",
        )
        llm.draft_general_reply.side_effect = ["Hi there!", "Hey again! Good to see you."]

        agent = MentionReplyAgent(self._settings())
        state = {
            "last_seen_id": None,
            "recent_general_replies_by_user": {
                "111": {
                    "last_text": "Hi there!",
                    "last_text_hash": _hash_text("Hi there!"),
                    "last_mention_hash": _hash_text("hi"),
                    "last_social_hint": "greeting",
                    "last_timestamp": 9999999999,
                }
            },
        }
        reply = agent._build_reply_for_mention(
            {
                "id": "777",
                "text": "hi",
                "author_id": "111",
                "reply_to_tweet_id": None,
                "conversation_id": "c7",
            },
            state,
        )
        self.assertEqual(reply, "Hey again! Good to see you.")


if __name__ == "__main__":
    unittest.main()
