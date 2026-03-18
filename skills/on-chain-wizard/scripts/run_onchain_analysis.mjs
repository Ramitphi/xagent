import process from "node:process";

const SUPPORTED_CHAINS = new Set([
  "ethereum",
  "polygon",
  "bsc",
  "arbitrum",
  "optimism",
  "base",
  "avalanche"
]);

export async function runOnchainAnalysis({
  contractAddress,
  chain,
  abi = null,
  apiUrl = "https://esraarlhpxraucslsdle.supabase.co/functions/v1/onchain-analysis",
  pollIntervalSeconds = 20,
  maxWaitSeconds = 420,
  timeoutSeconds = 20
}) {
  if (!contractAddress?.startsWith("0x") || contractAddress.length !== 42) {
    throw new Error("contract address must be a full 0x-prefixed 40-byte hex string");
  }
  if (!SUPPORTED_CHAINS.has(chain)) {
    throw new Error(`unsupported chain; use one of: ${Array.from(SUPPORTED_CHAINS).sort().join(", ")}`);
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutSeconds * 1000);
  try {
    const payload = {
      contractAddress,
      chain
    };
    if (abi) {
      payload.abi = abi;
    }
    const submit = await fetch(apiUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload),
      signal: controller.signal
    });
    if (!submit.ok) {
      throw new Error(`submit failed: ${submit.status} ${await submit.text()}`);
    }
    const submitData = await submit.json();
    let pollUrl = submitData.pollUrl;
    if (!pollUrl) {
      if (!submitData.jobId) {
        throw new Error("submit response missing both pollUrl and jobId");
      }
      pollUrl = `${apiUrl}?jobId=${submitData.jobId}`;
    }

    const started = Date.now();
    while (true) {
      const pollResponse = await fetch(pollUrl, {
        method: "GET",
        signal: AbortSignal.timeout(timeoutSeconds * 1000)
      });
      if (!pollResponse.ok) {
        throw new Error(`poll failed: ${pollResponse.status} ${await pollResponse.text()}`);
      }
      const pollData = await pollResponse.json();
      if (pollData.status === "completed" || pollData.status === "failed") {
        return pollData;
      }
      if ((Date.now() - started) > (maxWaitSeconds * 1000)) {
        return {
          status: "failed",
          error: "Analysis timed out while waiting for completion",
          jobId: pollData.jobId,
          phase: pollData.phase
        };
      }
      await new Promise((resolve) => setTimeout(resolve, pollIntervalSeconds * 1000));
    }
  } finally {
    clearTimeout(timer);
  }
}

function parseArgs(argv) {
  const args = {
    contractAddress: "",
    chain: "",
    apiUrl: "https://esraarlhpxraucslsdle.supabase.co/functions/v1/onchain-analysis",
    pollIntervalSeconds: 20,
    maxWaitSeconds: 420,
    timeoutSeconds: 20,
    abi: null
  };

  for (let index = 2; index < argv.length; index += 1) {
    const token = argv[index];
    const value = argv[index + 1];
    if (token === "--contract-address") {
      args.contractAddress = value;
      index += 1;
    } else if (token === "--chain") {
      args.chain = value;
      index += 1;
    } else if (token === "--api-url") {
      args.apiUrl = value;
      index += 1;
    } else if (token === "--poll-interval") {
      args.pollIntervalSeconds = Number(value);
      index += 1;
    } else if (token === "--max-wait") {
      args.maxWaitSeconds = Number(value);
      index += 1;
    } else if (token === "--timeout") {
      args.timeoutSeconds = Number(value);
      index += 1;
    }
  }
  return args;
}

if (process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href) {
  const args = parseArgs(process.argv);
  runOnchainAnalysis(args)
    .then((result) => {
      console.log(JSON.stringify(result, null, 2));
    })
    .catch((error) => {
      console.error(JSON.stringify({ status: "failed", error: error.message || String(error) }));
      process.exitCode = 1;
    });
}
