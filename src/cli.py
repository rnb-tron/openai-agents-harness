"""Command line helpers for local harness development."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from src.core.config import get_settings
from src.harness.builder import HarnessBuilder


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openai-agents-harness")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("doctor", help="Validate basic local configuration")
    subcommands.add_parser("list-capabilities", help="Print the configured capability catalog as JSON")
    return parser


def _doctor() -> int:
    settings = get_settings()
    issues: list[str] = []
    if not settings.openai_api_key:
        issues.append("OPENAI_API_KEY is empty; /chat will fail until a model credential is configured.")
    if settings.session_store_enabled and not settings.database_url:
        issues.append("SESSION_STORE_ENABLED=true requires SESSION_STORE_DATABASE_* settings.")
    if settings.rate_limit_enabled and settings.rate_limit_backend == "redis" and not settings.redis_enabled:
        issues.append("RATE_LIMIT_BACKEND=redis requires REDIS_ENABLED=true.")

    if issues:
        print("Configuration issues:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Configuration looks OK.")
    return 0


def _list_capabilities() -> int:
    settings = get_settings()
    catalog = HarnessBuilder(settings).build().context.capability_catalog()
    print(json.dumps(catalog, ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "doctor":
        return _doctor()
    if args.command == "list-capabilities":
        return _list_capabilities()
    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
