---
name: xagent-tool-layer
description: Use the existing xagent runtime as a local tool layer for X mention handling. It understands mention context, classifies whether a message needs onchain contract analysis or a general social reply, drafts human-style replies using the project persona, and can optionally execute the full onchain analysis flow and return the drafted result. Use this when OpenClaw should reuse the same behavior as the X bot instead of inventing a new reply path.
---

# XAgent Tool Layer

This skill exposes the current `xagent` behavior as a local tool for OpenClaw. It is the preferred path when you want the same reply logic, persona, and routing already used by the bot.

## When to use

- The user message is an X-style mention or reply and you want to reuse `xagent` behavior
- You need to decide whether a message is social chatter or an onchain-analysis request
- You want a human-style social reply using the current `agent.md` persona
- You want to run the full async onchain flow and draft the final reply

## Command

Run the bundled script from the repo root:

```bash
python3 skills/xagent-tool-layer/scripts/run_xagent_tool.py \
  --mention-text "@OWAIbot hi are you up?" \
  --author-username "phi_ramit"
```

With parent tweet context:

```bash
python3 skills/xagent-tool-layer/scripts/run_xagent_tool.py \
  --mention-text "@OWAIbot can you try again" \
  --parent-text "Analyze 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D on ethereum" \
  --author-username "phi_ramit"
```

To execute the full onchain workflow when the message is confidently onchain:

```bash
python3 skills/xagent-tool-layer/scripts/run_xagent_tool.py \
  --mention-text "@OWAIbot analyze 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D on ethereum" \
  --author-username "phi_ramit" \
  --execute-onchain
```

## Output

The script returns JSON. Important fields:

- `decision`: the parsed `xagent` intent decision
- `route`: `general`, `onchain_analysis`, or `needs_more_info`
- `reply`: drafted final user-facing text when available
- `analysis`: raw onchain payload when `--execute-onchain` succeeds

## Notes

- The script loads persona from `agent.md` by default.
- It uses `OPENAI_API_KEY` for routing and drafting.
- `--execute-onchain` uses the existing async analysis API and may take a few minutes.
- Do not truncate URLs in downstream handling.

