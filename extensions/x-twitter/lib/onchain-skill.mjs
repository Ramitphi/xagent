import { runOnchainAnalysis } from "../../../skills/on-chain-wizard/scripts/run_onchain_analysis.mjs";

export async function analyzeContract({ contractAddress, chain }) {
  return runOnchainAnalysis({
    contractAddress,
    chain,
    abi: null,
    apiUrl: process.env.ONCHAIN_ANALYSIS_URL || "https://esraarlhpxraucslsdle.supabase.co/functions/v1/onchain-analysis",
    pollIntervalSeconds: Number(process.env.ONCHAIN_POLL_INTERVAL_SECONDS || "20"),
    maxWaitSeconds: Number(process.env.ONCHAIN_MAX_WAIT_SECONDS || "420"),
    timeoutSeconds: Number(process.env.REQUEST_TIMEOUT_SECONDS || "20")
  });
}
