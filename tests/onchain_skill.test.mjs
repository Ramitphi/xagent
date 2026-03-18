import test from "node:test";
import assert from "node:assert/strict";

import { runOnchainAnalysis } from "../skills/on-chain-wizard/scripts/run_onchain_analysis.mjs";

test("runOnchainAnalysis rejects invalid contract", async () => {
  await assert.rejects(
    () => runOnchainAnalysis({ contractAddress: "0x123", chain: "base" }),
    /contract address/
  );
});

test("runOnchainAnalysis rejects unsupported chain", async () => {
  await assert.rejects(
    () => runOnchainAnalysis({
      contractAddress: "0x0000000000000000000000000000000000000000",
      chain: "solana"
    }),
    /unsupported chain/
  );
});
