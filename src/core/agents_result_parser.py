import json
from typing import Any

from agents import ToolCallItem, ToolCallOutputItem


def parse_tool_calls_from_result(result: Any) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    calls_in_progress: dict[str, dict[str, Any]] = {}
    if not hasattr(result, "new_items"):
        return []

    for item in result.new_items:
        if isinstance(item, ToolCallItem):
            call_id = getattr(item.raw_item, "call_id", None)
            if not call_id:
                continue
            name = getattr(item.raw_item, "name", "unknown")
            args_str = getattr(item.raw_item, "arguments", "{}")
            try:
                calls_in_progress[call_id] = {"name": name, "input": json.loads(args_str)}
            except json.JSONDecodeError:
                calls_in_progress[call_id] = {"name": name, "input": {"raw": args_str}}
        if isinstance(item, ToolCallOutputItem):
            if item.raw_item is None:
                continue
            call_id = (
                item.raw_item.get("call_id")
                if isinstance(item.raw_item, dict)
                else getattr(item.raw_item, "call_id", None)
            )
            if not call_id or call_id not in calls_in_progress:
                continue
            call_data = calls_in_progress.pop(call_id)
            call_data["output"] = item.output
            tool_calls.append(call_data)

    for call_data in calls_in_progress.values():
        call_data["output"] = {"error": "missing output"}
        tool_calls.append(call_data)

    return tool_calls
