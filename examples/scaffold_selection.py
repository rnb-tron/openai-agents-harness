"""本地演示脚手架平台如何解析候选 Capability 组合。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.harness.catalog import validate_capability_selection


def main() -> None:
    parser = argparse.ArgumentParser(description="校验脚手架候选能力组合")
    parser.add_argument(
        "capabilities",
        nargs="*",
        default=["vector_search", "hitl"],
        help="候选能力名称，如 vector_search hitl observability",
    )
    args = parser.parse_args()

    result = validate_capability_selection(args.capabilities)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
