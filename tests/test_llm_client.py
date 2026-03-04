from __future__ import annotations

import unittest

from src.x_mentions_agent.llm_client import (
    _ensure_full_dashboard_url,
    _is_valid_contract,
    _parse_intent_response,
)


class TestLlmClientParsing(unittest.TestCase):
    def test_parse_valid_onchain_response(self) -> None:
        text = """INTENT: onchain_analysis
CONTRACT: 0x00000000009726632680FB29d3F7A9734E3010E2
CHAIN: base
CONFIDENCE: 0.89
RATIONALE: Contract and chain are explicit.
"""
        decision = _parse_intent_response(text)
        self.assertEqual(decision.intent, "onchain_analysis")
        self.assertEqual(decision.contract_address, "0x00000000009726632680FB29d3F7A9734E3010E2")
        self.assertEqual(decision.chain, "base")
        self.assertAlmostEqual(decision.confidence, 0.89, places=2)

    def test_parse_malformed_response_falls_back(self) -> None:
        decision = _parse_intent_response("not formatted output")
        self.assertEqual(decision.intent, "general")
        self.assertIsNone(decision.contract_address)
        self.assertIsNone(decision.chain)
        self.assertEqual(decision.confidence, 0.0)

    def test_contract_validator(self) -> None:
        self.assertTrue(_is_valid_contract("0x00000000009726632680FB29d3F7A9734E3010E2"))
        self.assertFalse(_is_valid_contract("0x1234"))

    def test_dashboard_url_is_restored_when_missing(self) -> None:
        payload = {"result": {"dashboardUrl": "https://onchainwizard.ai/shared/abc-123"}}
        fixed = _ensure_full_dashboard_url("TLDR: done.", payload)
        self.assertIn("https://onchainwizard.ai/shared/abc-123", fixed)


if __name__ == "__main__":
    unittest.main()
