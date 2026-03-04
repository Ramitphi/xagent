FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STATE_FILE=/app/state/state.json \
    PERSONA_FILE=/app/agent.md

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY agent.md ./agent.md

CMD ["python", "-m", "src.x_mentions_agent.main"]
