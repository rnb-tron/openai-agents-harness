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
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def post_stream(
    url: str,
    payload: dict[str, Any],
    token: str | None,
    timeout: float,
) -> dict[str, Any]:
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
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            content_type = response.headers.get("Content-Type", "")
            events = parse_stream_response(body, content_type)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"无法连接 Harness API: {exc.reason}") from exc
    for event in events:
        if event.get("type") == "error":
            raise RuntimeError(event.get("detail") or "stream returned error")
        if event.get("event") == "error":
            data = event.get("data") or {}
            raise RuntimeError(data.get("msg") or "stream returned error")
    for event in reversed(events):
        if event.get("type") == "done":
            return event["data"]
        if event.get("event") == "end":
            data = event["data"]
            protocol = data.get("protocol") or {}
            if "sessionId" in protocol:
                data["session_id"] = protocol["sessionId"]
            if "turnId" in protocol:
                data["turn_id"] = protocol["turnId"]
            if "runState" in data and "run_state" not in data:
                data["run_state"] = data["runState"]
            return data
    raise RuntimeError("stream did not return done event")


def parse_stream_response(body: str, content_type: str) -> list[dict[str, Any]]:
    if "text/event-stream" not in content_type:
        return [json.loads(line) for line in body.splitlines() if line.strip()]

    events: list[dict[str, Any]] = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        if not block.strip():
            continue
        event: dict[str, Any] = {}
        for line in block.splitlines():
            if line.startswith("event:"):
                event["event"] = line[len("event:") :]
            elif line.startswith("id:"):
                event["id"] = line[len("id:") :]
            elif line.startswith("data:"):
                event["data"] = json.loads(line[len("data:") :])
        if event:
            events.append(event)
    return events


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
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP 请求超时秒数")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--approve", action="store_true", help="直接批准中断")
    choice.add_argument("--reject", action="store_true", help="直接拒绝中断")
    args = parser.parse_args()

    initial = post_stream(
        f"{args.base_url}/chat",
        {
            "query": args.message,
            "sessionId": args.session_id,
            "userId": args.user_id,
        },
        args.token,
        args.timeout,
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
        "turn_id": initial["turn_id"],
        "message": initial["input"],
        "model": initial["model"],
        "user_id": args.user_id,
    }
    if interruption.get("id"):
        resume_payload["approval_request_id"] = interruption["id"]
    if not approved:
        resume_payload["rejection_message"] = "示例调用中人工拒绝了该操作。"

    resumed = post_stream(
        f"{args.base_url}/chat/resume/stream",
        resume_payload,
        args.token,
        args.timeout,
    )
    print("恢复后的响应：")
    print(json.dumps(resumed, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        raise SystemExit(f"调用失败: {exc}") from None
