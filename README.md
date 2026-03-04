# X Mentions Auto-Reply Agent

This project runs a bot that:
1. Polls mentions of your X account.
2. Sends each mention to your analysis API.
3. Posts the returned text as a reply.

## 1) Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env` with your X credentials, bot user id, and `ANALYSIS_API_URL`.

## 2) Expected Analysis API Contract

Request body sent by the agent:

```json
{
  "mention": {
    "id": "<tweet id>",
    "text": "<mention text>",
    "author_id": "<author id>",
    "created_at": "<iso timestamp>",
    "conversation_id": "<conversation id>"
  }
}
```

Response body expected from your API (either key works):

```json
{
  "reply_text": "Thanks for reaching out!"
}
```

or

```json
{
  "reply": "Thanks for reaching out!"
}
```

## 3) Run

Single run:

```bash
python -m src.x_mentions_agent.main --once
```

Continuous polling:

```bash
python -m src.x_mentions_agent.main
```

## Notes

- `state.json` stores the last seen mention id so the bot only handles new mentions.
- Replies are trimmed to 280 characters.
- If your API requires auth, set `ANALYSIS_API_KEY` and optionally `ANALYSIS_API_KEY_HEADER`.
