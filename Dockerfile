FROM node:22-bookworm-slim

ENV OPENCLAW_HOME=/app/.openclaw \
    OPENCLAW_STATE_DIR=/app/.openclaw/state

WORKDIR /app

RUN npm install -g openclaw@latest

COPY . /app

RUN chmod +x /app/scripts/start-openclaw.sh

CMD ["/app/scripts/start-openclaw.sh"]
