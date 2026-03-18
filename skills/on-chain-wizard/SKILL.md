---
name: on-chain-wizard
description: Use On-Chain Wizard to analyze verified EVM smart contracts on ethereum, polygon, bsc, arbitrum, optimism, base, or avalanche. Submit the contract address and chain to the existing async analysis API, poll until completion, and summarize the returned TLDR, dashboard URL, top methods, and raw Dune links. Use this when the user wants to understand what a contract does, who uses it, function usage, caller behavior, or contract analytics.
---

# On-Chain Wizard

Use this skill when the user wants analysis of an EVM smart contract. The skill wraps the same async API already used by the X bot and is the preferred path over ad hoc reasoning.

## Inputs

- `contractAddress`: required, `0x`-prefixed 40-byte EVM address
- `chain`: required, one of `ethereum`, `polygon`, `bsc`, `arbitrum`, `optimism`, `base`, `avalanche`
- `abi`: optional, raw ABI JSON string for unverified contracts

If the user gives only an address, ask for the chain. Do not guess the chain.

## Workflow

1. Validate the address format before calling the API.
2. Validate the chain against the supported list.
3. Run the bundled script:

```bash
node skills/on-chain-wizard/scripts/run_onchain_analysis.mjs \
  --contract-address 0x... \
  --chain base
```

Optional ABI:

```bash
node skills/on-chain-wizard/scripts/run_onchain_analysis.mjs \
  --contract-address 0x... \
  --chain base \
  --api-url https://esraarlhpxraucslsdle.supabase.co/functions/v1/onchain-analysis
```

4. The script handles submit and poll. Do not reimplement the polling loop unless the script is unavailable.
5. Present the result:
- lead with the TLDR
- include the full dashboard URL without truncating it
- mention one or two top method insights if present
- include raw table Dune links when useful
- if the API returns `Could not fetch ABI`, ask the user for the ABI JSON

## Output expectations

- Never fabricate onchain data.
- Keep conclusions tied to the returned payload.
- Preserve full URLs.
- If results are sparse, say the contract has low observable activity instead of over-interpreting.

## Failure handling

- Missing chain: ask which supported chain the contract is on.
- Invalid address: ask for a valid full `0x...` contract address.
- Unsupported chain: list the supported chains and ask again.
- Timed out polling: report that analysis is still running or timed out and suggest retrying.
