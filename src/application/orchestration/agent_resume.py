from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from agents import Runner, RunState

from src.application.orchestration.stream_events import iter_stream_events
from src.capabilities.plugin import RunContext, RunPhase
from src.core.agents_result_parser import parse_tool_calls_from_result


class AgentResumeRuntime:
    """处理 SDK interruption / HITL 审批恢复流程。

    这块逻辑只服务于 HITL / tool approval。把它从 ``AgentOrchestrator`` 中拆出来，
    是为了让普通 ``run_stream`` 主流程保持轻量；不使用人工审批时，业务编排者
    基本不需要阅读本文件。

    ``AgentOrchestrator.resume_stream_with_approval`` 是对外门面；本类是内部实现。
    这样 API 层仍然只面对一个 runtime 对象，而复杂恢复逻辑可以独立演进。
    """

    def __init__(self, owner: Any) -> None:
        self.owner = owner

    async def resume_stream_with_approval(
        self,
        session: Any,
        *,
        run_state: dict[str, Any],
        interruption_index: int,
        approved: bool,
        approval_request_id: str | None = None,
        reviewer: str = "anonymous",
        model: str | None = None,
        user_input: str = "",
        always: bool = False,
        rejection_message: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """审批后恢复 SDK 中断，并流式返回最终响应。

        外层负责 observation 包装，内部 ``_resume_stream_with_approval`` 负责实际
        恢复。这里保持和普通 ``run_stream`` 类似的事件形态：先 ``start``，中间
        产出 ``delta`` / ``agent_updated``，最后产出 ``done``。
        """
        with self.owner.observer.observe(
            session_id=session.session_id,
            user_id=session.user_id,
            user_input=user_input,
            trace_name="agent.chat.resume.stream",
        ) as observation:
            try:
                async for event in self._resume_stream_with_approval(
                    session,
                    run_state=run_state,
                    interruption_index=interruption_index,
                    approved=approved,
                    approval_request_id=approval_request_id,
                    reviewer=reviewer,
                    model=model,
                    user_input=user_input,
                    always=always,
                    rejection_message=rejection_message,
                ):
                    if event["type"] == "done":
                        self.owner.observer.update(observation, event["data"])
                    yield event
            except Exception as exc:
                self.owner.observer.mark_error(observation, exc)
                raise

    async def _complete_rejected_resume(
        self,
        *,
        session: Any,
        ctx: RunContext,
        selected_model: str,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """把“拒绝审批”直接转成最终响应。

        拒绝时不继续调用模型，避免模型误以为工具已经执行并编造结果。这里仍然
        触发 ``AFTER_RUN``，让 session_store、memory summary 等能力记录这次拒绝。
        """
        ctx.final_output = f"操作已被拒绝，未执行工具 {tool_name}。因此无法基于该工具的查询结果提供信息或建议。"
        ctx.tool_calls = [
            {
                "name": tool_name,
                "input": tool_args or {},
                "output": {"error": "rejected_by_user"},
                "status": "rejected",
            }
        ]
        ctx.metadata["hitl"] = {"decision": "rejected", "tool_executed": False}
        await self.owner.registry.dispatch(RunPhase.AFTER_RUN, ctx)
        session.context["last_model"] = selected_model
        return {
            "session_id": session.session_id,
            "input": ctx.user_input,
            "output": ctx.final_output,
            "model": selected_model,
            "tool_calls": ctx.tool_calls,
            "memory_size": await self.owner._memory_size(session.session_id),
            "metadata": dict(ctx.metadata),
            "interrupted": False,
            "decision": "rejected",
            "tool_executed": False,
        }

    async def _resume_stream_with_approval(
        self,
        session: Any,
        *,
        run_state: dict[str, Any],
        interruption_index: int,
        approved: bool,
        approval_request_id: str | None = None,
        reviewer: str = "anonymous",
        model: str | None = None,
        user_input: str = "",
        always: bool = False,
        rejection_message: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """恢复一次已中断的 SDK run。

        输入给 Runner 的不是用户文本，而是还原后的 SDK ``RunState``。审批通过时
        继续流式执行；审批拒绝时直接返回受控响应；如果恢复后再次触发审批，
        会返回新的 ``run_state`` 给调用方继续处理。
        """
        if not self.owner.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for /chat endpoint")

        run = await self.owner._prepare_agent_run(
            session,
            user_input,
            model=model,
        )
        sdk_state = await RunState.from_json(run.agent, run_state)

        rejected_tool_name, rejected_tool_args = await self._apply_approval(
            session=session,
            sdk_state=sdk_state,
            run_state=run_state,
            interruption_index=interruption_index,
            approved=approved,
            approval_request_id=approval_request_id,
            reviewer=reviewer,
            always=always,
            rejection_message=rejection_message,
        )

        if not approved:
            result = await self._complete_rejected_resume(
                session=session,
                ctx=run.ctx,
                selected_model=run.selected_model,
                tool_name=rejected_tool_name,
                tool_args=rejected_tool_args,
            )
            yield {
                "type": "start",
                "session_id": session.session_id,
                "model": result["model"],
            }
            for delta in (
                "操作已被拒绝，",
                f"未执行工具 {result['tool_calls'][0]['name']}。",
                "因此无法基于该工具的查询结果提供信息或建议。",
            ):
                yield {"type": "delta", "delta": delta}
            yield {"type": "done", "data": result}
            return

        agent_path = ["MinimalChatAgent"]
        yield {
            "type": "start",
            "session_id": session.session_id,
            "model": run.selected_model,
        }
        try:
            result = Runner.run_streamed(starting_agent=run.agent, input=sdk_state)
            async for event in iter_stream_events(result, agent_path=agent_path):
                yield event
        except Exception as exc:
            await self.owner.registry.dispatch(RunPhase.ON_ERROR, run.ctx, error=exc)
            raise

        interruptions = list(getattr(result, "interruptions", []) or [])
        if interruptions:
            yield {
                "type": "done",
                "data": await self.owner._build_interrupted_result(
                    session=session,
                    user_input=user_input,
                    run=run,
                    run_result=result,
                ),
            }
            return

        yield {
            "type": "done",
            "data": await self._complete_successful_resume(
                session=session,
                user_input=user_input,
                run=run,
                run_result=result,
            ),
        }

    async def _apply_approval(
        self,
        *,
        session: Any,
        sdk_state: Any,
        run_state: dict[str, Any],
        interruption_index: int,
        approved: bool,
        approval_request_id: str | None,
        reviewer: str,
        always: bool,
        rejection_message: str | None,
    ) -> tuple[str, dict[str, Any]]:
        """把审批决定应用到 SDK RunState，并返回被拒工具信息。

        启用项目内 HITL manager 时，会先校验并更新本地审批记录，再把决定写入
        SDK state；未启用时，直接使用 SDK interruption 对象 approve/reject，方便
        业务方自己维护审批记录。
        """
        if self.owner.hitl_mgr is not None:
            if not approval_request_id:
                raise ValueError("HITL 已启用，恢复请求必须包含 approval_request_id")
            reviewed_request = await self.owner.hitl_mgr.review_sdk_approval(
                request_id=approval_request_id,
                session_id=session.session_id,
                interruption_index=interruption_index,
                run_state=run_state,
                approved=approved,
                reviewer=reviewer,
                comment=rejection_message or "",
            )
            self.owner.hitl_mgr.apply_approval_to_state(
                sdk_state,
                interruption_index=interruption_index,
                approved=approved,
                always=always,
                rejection_message=rejection_message,
            )
            return reviewed_request.tool_name, reviewed_request.tool_args

        interruptions = sdk_state.get_interruptions()
        if interruption_index < 0 or interruption_index >= len(interruptions):
            raise ValueError(f"审批中断不存在: {interruption_index}")
        interruption = interruptions[interruption_index]
        tool_name = (
            getattr(interruption, "qualified_name", None) or getattr(interruption, "name", None) or "requested_tool"
        )
        if approved:
            sdk_state.approve(interruption, always_approve=always)
        else:
            sdk_state.reject(
                interruption,
                always_reject=always,
                rejection_message=rejection_message,
            )
        return tool_name, {}

    async def _complete_successful_resume(
        self,
        *,
        session: Any,
        user_input: str,
        run: Any,
        run_result: Any,
    ) -> dict[str, Any]:
        """完成审批恢复后的成功路径。

        该路径与普通聊天完成路径一致：解析最终输出和工具调用，触发
        ``AFTER_RUN``，然后返回统一的 done payload。
        """
        run.ctx.final_output = str(run_result.final_output)
        run.ctx.tool_calls = parse_tool_calls_from_result(run_result)
        await self.owner.registry.dispatch(RunPhase.AFTER_RUN, run.ctx)
        session.context["last_model"] = run.selected_model
        return {
            "session_id": session.session_id,
            "input": user_input,
            "output": run.ctx.final_output,
            "model": run.selected_model,
            "tool_calls": run.ctx.tool_calls,
            "memory_size": await self.owner._memory_size(session.session_id),
            "metadata": dict(run.ctx.metadata),
            "interrupted": False,
        }
