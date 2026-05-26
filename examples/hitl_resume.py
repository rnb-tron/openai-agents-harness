"""通过 Chat API 演示 OpenAI Agents SDK 原生中断与恢复流程。

运行前请启动已配置 HITL 和模型服务的 Harness，例如配置:

    HITL_ENABLED=true
    HITL_REQUIRE_APPROVAL_TOOLS=get_weather

并发送会触发该工具的消息。本示例只负责调用已启动的 HTTP 服务。
"""

from __future__ import annotations

import argparse
import json
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def post_json(url: str, payload: dict[str, Any], token: str | None) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    return body["data"]


def decision_from_args(args: argparse.Namespace) -> bool:
    if args.approve:
        return True
    if args.reject:
        return False
    choice = input("是否批准本次工具调用？[y/N] ").strip().lower()
    return choice in {"y", "yes"}


def main() -> None:
    parser = argparse.ArgumentParser(description="演示 HITL 中断与 HTTP 恢复")
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--message", default="请查询北京天气。")
    parser.add_argument("--session-id", default="example-hitl-session")
    parser.add_argument("--user-id", default="example-user")
    parser.add_argument("--token", default=None, help="启用 Auth 时使用的 Bearer Token")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--approve", action="store_true", help="直接批准中断")
    choice.add_argument("--reject", action="store_true", help="直接拒绝中断")
    args = parser.parse_args()

    initial = post_json(
        f"{args.base_url}/chat",
        {
            "message": args.message,
            "session_id": args.session_id,
            "user_id": args.user_id,
        },
        args.token,
    )
    if not initial.get("interrupted"):
        print("本次调用未发生工具审批中断。")
        print(json.dumps(initial, ensure_ascii=False, indent=2))
        return

    interruption = initial["interruptions"][0]
    print("收到待审批工具调用：")
    print(json.dumps(interruption, ensure_ascii=False, indent=2))
    approved = decision_from_args(args)

    resume_payload: dict[str, Any] = {
        "run_state": initial["run_state"],
        "interruption_index": interruption["sdk_interruption_index"],
        "approved": approved,
        "session_id": initial["session_id"],
        "message": initial["input"],
        "model": initial["model"],
        "user_id": args.user_id,
    }
    if interruption.get("id"):
        resume_payload["approval_request_id"] = interruption["id"]
    if not approved:
        resume_payload["rejection_message"] = "示例调用中人工拒绝了该操作。"

    resumed = post_json(
        f"{args.base_url}/chat/resume",
        resume_payload,
        args.token,
    )
    print("恢复后的响应：")
    print(json.dumps(resumed, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
