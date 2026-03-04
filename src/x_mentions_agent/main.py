from __future__ import annotations

import argparse

from dotenv import load_dotenv

from .agent import MentionReplyAgent
from .config import Settings
from .logging_config import configure_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="X mention auto-reply agent")
    parser.add_argument("--once", action="store_true", help="Run one poll cycle and exit")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    agent = MentionReplyAgent(settings)
    if args.once:
        agent.run_once()
    else:
        agent.run_forever()


if __name__ == "__main__":
    main()
