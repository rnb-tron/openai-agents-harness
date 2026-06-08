# 高级 Agent 能力指南

本文覆盖 HITL、Checkpoint 与 Handoff 的当前接入方式。

> 状态：当前实现指南。HTTP 应用优先使用 `HarnessBuilder` 配置驱动路径；Manager 级 API 适用于测试和组件理解。

## 能力状态

| 能力 | Runtime 接入 | 存储/边界 |
| --- | --- | --- |
| HITL | SDK 原生 `needs_approval`、`interruptions`、`RunState` 恢复 | 审批请求当前保存在进程内 |
| Checkpoint | capability 在 run 前/后保存 `AgentState` 摘要 | 当前仅进程内；不是 SDK `RunState` 仓库 |
| Handoff | SDK 原生 `Agent.handoffs` | 环境配置提供静态目标，使用当前模型 |

## HITL

启用并指定需要审批的已注册工具：

```env
HITL_ENABLED=true
HITL_APPROVAL_TIMEOUT=300
HITL_REQUIRE_APPROVAL_TOOLS=get_weather
HITL_AUTO_APPROVE_TOOLS=
```

`HarnessBuilder` 将策略应用到 `ToolRegistry`；Runtime 构建 SDK 工具时设置 `needs_approval=True`。

请求示例：

```bash
curl -X POST http://localhost:8080/chat \
  -H 'Content-Type: application/json' \
  -d '{"query":"请查询北京天气。","sessionId":"hitl-demo","userId":"demo-user"}'
```

如果 SDK 中断，SSE 流中的 `end` 事件 `data` 包含：

```json
{
  "protocol": {"sessionId": "hitl-demo", "msgId": "msg_xxx"},
  "interrupted": true,
  "interruptions": [{"id": "approval-id", "sdk_interruption_index": 0}],
  "runState": {},
  "model": "gpt-4o-mini"
}
```

恢复时提交响应中的状态与决定：

```bash
curl -X POST http://localhost:8080/chat/resume/stream \
  -H 'Content-Type: application/json' \
  -d '{
    "session_id":"hitl-demo",
    "message":"请查询北京天气。",
    "model":"gpt-4o-mini",
    "run_state": {},
    "approval_request_id":"approval-id",
    "interruption_index":0,
    "approved":true
  }'
```

实际运行可使用：

```bash
venv/bin/python examples/hitl_resume.py --approve --message "请查询北京天气。"
```

生产限制：当前审批请求和匹配状态由进程内 `ApprovalManager` 保管，调用方回传 SDK state；尚未提供持久化、审计、幂等和跨实例恢复。

## Checkpoint

启用 Runtime 的运行边界快照：

```env
CHECKPOINT_ENABLED=true
CHECKPOINT_AUTO_SAVE=true
CHECKPOINT_MAX_CHECKPOINTS=10
```

当前 capability 在一次完整运行之前与之后保存摘要。它不在每个工具调用后自动创建可恢复的 SDK 执行状态，也不能替代 HITL 的 `run_state` 保存。

组件级调用：

```python
from src.capabilities.advanced_agents import AgentState, CheckpointConfig, CheckpointManager

manager = CheckpointManager(
    CheckpointConfig(enabled=True, max_checkpoints=10, auto_save=True)
)
state = AgentState(
    session_id="session-001",
    conversation_history=[],
    current_model="gpt-4o-mini",
    tool_calls=[],
    context={"user_id": "user-001"},
)
checkpoint_id = await manager.save("session-001", state, "开始")
restored = await manager.restore(checkpoint_id)
```

## Handoff

推荐通过环境配置静态目标：

```env
HANDOFF_ENABLED=true
HANDOFF_AGENTS_JSON={"billing":{"description":"处理账单问题","instructions":"只处理账单相关请求。"},"support":{"description":"处理技术问题","instructions":"只处理技术支持请求。"}}
```

在每次 Runtime 构建主 Agent 时，`HandoffManager.build_configured_handoffs()` 将启用的目标转换为 SDK `Agent`，并作为 `handoffs` 传入主 Agent。当前配置只覆盖目标名称、描述、指令与 `enabled` 标识；不声明目标专属工具和动态路由策略。

组件测试中也可直接使用 manager：

```python
from src.capabilities.advanced_agents import HandoffConfig, HandoffManager

manager = HandoffManager(
    HandoffConfig(
        enabled=True,
        agents={"billing": {"description": "处理账单", "instructions": "只处理账单。"}},
    )
)
targets = manager.build_configured_handoffs(sdk_model)
```

## 测试与示例

```bash
venv/bin/python -m pytest tests/unit/test_hitl_native_sdk.py \
  tests/unit/test_agent_runtime_resume.py \
  tests/unit/test_handoff_native_sdk.py \
  tests/unit/test_checkpoint_capability.py -q

venv/bin/python examples/advanced_agents_components.py
```

## 相关文档

- [架构设计](../design/ARCHITECTURE_DESIGN.md)
- [AgentOrchestrator 使用指南](./AGENT_ORCHESTRATOR_USAGE.md)
