# X Mentions Auto-Reply Agent

This project runs a bot that:
1. Polls mentions of your X account.
2. Reads mention context (mention + parent tweet when available).
3. Uses OpenAI to understand intent and extract contract/chain when possible.
4. Runs async `onchain-analysis` (submit + poll) for on-chain requests.
5. Uses OpenAI to draft both on-chain results and general social replies (`hi`, `introduce yourself`, etc.).
6. Falls back to regex/onchain routing and safe default social replies when needed.

## LLM Routing + Reply Drafting

LLM-first pipeline:
1. `understand_mention(context)` classifies intent (`onchain_analysis` or `general`) and extracts contract, chain, confidence.
2. If confidence >= `LLM_CONFIDENCE_THRESHOLD` and contract exists:
- If chain missing, ask the user for chain.
- If chain present, run async on-chain analysis.
3. Non-onchain mentions are handled by `draft_general_reply(context, agent_prompt)` for human-like conversation.
4. `draft_onchain_reply(context, payload)` drafts final analysis tweet.
5. Deterministic guardrails validate chain/address, remove unsafe internal error text, and preserve full URLs.
6. Per-user cooldown and variation logic reduce duplicate-content reply failures on X.

Fallback pipeline:
- Any LLM failure, timeout, parse error, or low-confidence result falls back to regex chain/address detection.
- If no on-chain intent is found, agent uses LLM general social reply mode.

## 1) Setup (Local with uv)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
uv sync
cp .env.example .env
```

Fill `.env` with your credentials and endpoint values.

## 2) Environment Variables

Required:
- `X_API_KEY`
- `X_API_KEY_SECRET`
- `X_ACCESS_TOKEN`
- `X_ACCESS_TOKEN_SECRET`
- `X_BOT_USER_ID`

LLM settings (enable LLM mode):
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default `gpt-4.1-mini`)
- `LLM_TIMEOUT_SECONDS` (default `20`)
- `LLM_CONFIDENCE_THRESHOLD` (default `0.65`)
- `LLM_MAX_CONTEXT_CHARS` (default `4000`)
- `GENERAL_REPLY_ENABLED` (default `true`)
- `GENERAL_REPLY_COOLDOWN_SECONDS` (default `600`)
- `GENERAL_REPLY_MAX_REGEN_ATTEMPTS` (default `1`)
- `PERSONA_FILE` (default `agent.md`)
- `SKIP_EXISTING_MENTIONS_ON_STARTUP` (default `true`)
- `PROCESSED_MENTIONS_CACHE_SIZE` (default `2000`)

If `OPENAI_API_KEY` is missing, agent runs in fallback mode only.

Optional API + runtime settings:
- `ONCHAIN_ANALYSIS_URL` (default provided in `.env.example`)
- `ONCHAIN_POLL_INTERVAL_SECONDS` (default `20`)
- `ONCHAIN_MAX_WAIT_SECONDS` (default `420`)
- `POLL_INTERVAL_SECONDS` (default `60`)
- `MAX_MENTIONS_PER_POLL` (default `10`)
- `REQUEST_TIMEOUT_SECONDS` (default `20`)
- `STATE_FILE` (default `state.json`)

## 3) Run (Local)

Single run:

```bash
uv run python -m src.x_mentions_agent.main --once
```

Continuous polling:

```bash
uv run python -m src.x_mentions_agent.main
```

Run tests:

```bash
uv run python -m unittest discover -s tests -v
```

Run credentials self-test:

```bash
uv run python -m src.x_mentions_agent.main --self-test
```

## 4) Run with Docker

```bash
cp .env.example .env
mkdir -p state logs
docker compose up --build -d
```

View logs:

```bash
docker compose logs -f x-mentions-agent
```

Stop:

```bash
docker compose down
```

## Example Mention Flows

1. Clear on-chain request:
- Mention: "Analyze 0x... on base"
- LLM detects on-chain intent + address + chain.
- Agent posts ack, polls async API, posts final summary.

2. General social mention:
- Mention: "hi @OWAIbot introduce yourself"
- Agent replies directly using LLM + `agent.md` persona.

3. Ambiguous mention:
- LLM returns low confidence for on-chain intent.
- Agent still replies via general social path (or fallback API if configured).

4. Missing chain:
- Contract found but chain absent.
- Agent asks: "Which chain is it on?"

5. LLM outage:
- OpenAI call fails.
- Agent logs error and uses fallback path; no silent drops.

6. Retry in same thread:
- User says "try again" without repeating contract/chain.
- Agent reuses the last contract+chain remembered for that conversation and reruns analysis.

## Notes

- `state/state.json` stores `last_seen_id` so only new mentions are processed.
- On first run, startup sync skips old backlog mentions by default (`SKIP_EXISTING_MENTIONS_ON_STARTUP=true`).
- The agent keeps a processed mention id cache to avoid accidental duplicate replies after restart.
- Replies are posted as threaded chunks when output exceeds 280 chars (no truncation).
- On-chain analysis is async and usually takes 2-5 minutes.
