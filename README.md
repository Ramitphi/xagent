# XAgent OpenClaw Workspace

This repo is now structured as an OpenClaw-native workspace:

1. `extensions/x-twitter/` runs the X mentions poller inside the OpenClaw gateway process.
2. `skills/on-chain-wizard/` is the separate on-chain analysis skill.
3. `agent.md` remains the persona source for replies.
4. The old Python worker under `src/x_mentions_agent/` is retained only as legacy reference during migration.

## Layout

- `extensions/x-twitter/`: local OpenClaw plugin for X polling, parent tweet loading, threaded replies, dedupe, retry context, and human-like social/on-chain routing
- `skills/on-chain-wizard/`: async submit/poll contract analysis skill
- `skills/x-research-skill/`: optional research skill retained
- `openclaw/openclaw.json.example`: example gateway config
- `scripts/start-openclaw.sh`: container entrypoint

## Required Environment Variables

- `X_API_KEY`
- `X_API_KEY_SECRET`
- `X_ACCESS_TOKEN`
- `X_ACCESS_TOKEN_SECRET`
- `OPENAI_API_KEY` or your chosen gateway model provider credential

Optional:

- `OPENAI_MODEL` default `gpt-4.1-mini`
- `LLM_TIMEOUT_SECONDS` default `20`
- `REQUEST_TIMEOUT_SECONDS` default `20`
- `ONCHAIN_ANALYSIS_URL`
- `ONCHAIN_POLL_INTERVAL_SECONDS`
- `ONCHAIN_MAX_WAIT_SECONDS`
- `OPENCLAW_HOME`
- `OPENCLAW_STATE_DIR`

## OpenClaw Config

Copy [openclaw.json.example](/Users/ramit/Downloads/xagent/openclaw/openclaw.json.example) to your gateway config path, typically `~/.openclaw/openclaw.json`, then edit `channels.x-twitter`.

Minimum shape:

```json5
{
  "plugins": {
    "load": {
      "paths": ["/app/extensions/x-twitter"]
    },
    "entries": {
      "x-twitter": {
        "enabled": true
      }
    }
  },
  "agents": {
    "defaults": {
      "workspace": "/app",
      "model": {
        "primary": "openai/gpt-4.1-mini"
      }
    }
  },
  "channels": {
    "x-twitter": {
      "enabled": true,
      "botUserId": "2028217683330973697",
      "pollIntervalSeconds": 60,
      "maxMentionsPerPoll": 10,
      "skipExistingOnStartup": true
    }
  }
}
```

## Run Locally

Install the OpenClaw CLI and point it at this workspace:

```bash
npm install -g openclaw@latest
cp .env.example .env
mkdir -p .openclaw
cp openclaw/openclaw.json.example .openclaw/openclaw.json
OPENCLAW_HOME=$PWD/.openclaw OPENCLAW_STATE_DIR=$PWD/.openclaw/state ./scripts/start-openclaw.sh
```

## Run with Docker

```bash
cp .env.example .env
mkdir -p openclaw-data logs
docker compose up --build -d
```

## Validate

Syntax and tests:

```bash
npm run check:x-twitter
npm run check:onchain-skill
npm test
```

## Notes

- The `x-twitter` plugin currently ports the existing `xagent` behavior directly into the gateway process.
- The `x-twitter` plugin no longer calls OpenAI directly; inference now runs through `openclaw agent --local`, so model/provider selection stays with the OpenClaw runtime.
- On-chain analysis still posts an immediate ack and then a final result in-thread.
- Full dashboard URLs are preserved.
- The old Python runtime is no longer the primary deployment target.
