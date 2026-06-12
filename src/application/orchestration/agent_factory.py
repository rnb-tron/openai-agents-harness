from __future__ import annotations

from typing import Any, Callable

from agents import Agent, AsyncOpenAI, ModelSettings, OpenAIChatCompletionsModel, OpenAIResponsesModel
from openai.types.shared import Reasoning

from src.capabilities.plugin import RunContext
from src.capabilities.prompt.manager import PromptManager
from src.capabilities.tools.registry import ToolRegistry
from src.core.config import Settings


class AgentFactory:
    """Build SDK clients, models, and the primary chat Agent."""

    def __init__(
        self,
        *,
        settings: Settings,
        tool_registry: ToolRegistry,
        prompt_manager: PromptManager | None = None,
        handoff_builder: Callable[[Any], list[Any]] | None = None,
        logger: Any,
    ) -> None:
        self.settings = settings
        self.tool_registry = tool_registry
        self.prompt_manager = prompt_manager
        self.handoff_builder = handoff_builder
        self.logger = logger

    def create_client(self) -> AsyncOpenAI:
        client_kwargs: dict[str, Any] = {"api_key": self.settings.openai_api_key}
        if self.settings.openai_base_url:
            client_kwargs["base_url"] = self.settings.openai_base_url
        return AsyncOpenAI(**client_kwargs)

    def build_agent(
        self,
        *,
        model: str,
        client: AsyncOpenAI,
        instructions: str,
    ) -> Agent:
        reasoning_summary_enabled = getattr(self.settings, "reasoning_summary_enabled", False)
        model_api = self._resolve_model_api()
        # Responses 是 OpenAI reasoning summary 的标准路径；部分 OpenAI-compatible 服务
        # 只在 Chat Completions 扩展字段 delta.reasoning_content 中返回 thinking。
        if model_api == "responses":
            sdk_model = OpenAIResponsesModel(model=model, openai_client=client)
        else:
            sdk_model = OpenAIChatCompletionsModel(model=model, openai_client=client)
        handoffs = self.handoff_builder(sdk_model) if self.handoff_builder else []
        if handoffs:
            from agents.extensions.handoff_prompt import prompt_with_handoff_instructions

            instructions = prompt_with_handoff_instructions(instructions)

        model_settings = ModelSettings()
        if reasoning_summary_enabled:
            model_settings = ModelSettings(
                reasoning=Reasoning(
                    effort=getattr(self.settings, "reasoning_effort", "low"),
                    summary=getattr(self.settings, "reasoning_summary_mode", "auto"),
                ),
                extra_body=self._chat_reasoning_extra_body(model_api),
            )
        return Agent(
            name="MinimalChatAgent",
            instructions=instructions,
            model=sdk_model,
            model_settings=model_settings,
            tools=self.tool_registry.list_agent_tools(),
            handoffs=handoffs,
        )

    def _resolve_model_api(self) -> str:
        configured = str(getattr(self.settings, "agent_model_api", "auto")).strip().lower()
        if configured in {"responses", "chat_completions"}:
            return configured
        if configured != "auto":
            self.logger.warning(
                "unknown_agent_model_api_using_responses",
                extra={"configured": configured},
            )
        # auto 的默认路径固定为 Responses API，这是 OpenAI reasoning summary 的标准实现。
        # 若目标服务只在 Chat Completions 扩展字段返回 thinking，应显式配置 chat_completions。
        return "responses"

    def _chat_reasoning_extra_body(self, model_api: str) -> dict[str, Any] | None:
        if model_api != "chat_completions":
            return None
        if not getattr(self.settings, "openai_base_url", None):
            return None
        if not getattr(self.settings, "reasoning_chat_enable_thinking", True):
            return None
        # 当前 test 环境的兼容服务需要这个开关才会流式返回 reasoning_content。
        return {"enable_thinking": True}

    def default_instructions(self) -> str:
        return (
            "You are a concise assistant. Use tools when useful. "
            "If a tool is used, include the final user-facing conclusion in plain text."
        )

    async def resolve_instructions(self, task_type: str | None, ctx: RunContext) -> str:
        instructions = self.default_instructions()
        if self.settings.prompt_enabled and self.prompt_manager is not None:
            try:
                rendered = await self.prompt_manager.get(
                    "agents.main_system_chat",
                    task_type=task_type,
                    extra_instructions="",
                )
                instructions = rendered.text
                ctx.metadata["prompt"] = rendered.to_metadata()
            except Exception as exc:
                self.logger.warning(
                    "prompt_get_failed_using_fallback",
                    extra={
                        "prompt_name": "agents.main_system_chat",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                if not self.settings.prompt_fail_open:
                    raise
        return instructions
