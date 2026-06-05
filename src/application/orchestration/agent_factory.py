from __future__ import annotations

from typing import Any, Callable

from agents import Agent, AsyncOpenAI, ModelSettings, OpenAIChatCompletionsModel
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
        sdk_model = OpenAIChatCompletionsModel(model=model, openai_client=client)
        handoffs = self.handoff_builder(sdk_model) if self.handoff_builder else []
        if handoffs:
            from agents.extensions.handoff_prompt import prompt_with_handoff_instructions

            instructions = prompt_with_handoff_instructions(instructions)

        model_settings = ModelSettings()
        if getattr(self.settings, "reasoning_summary_enabled", False):
            model_settings = ModelSettings(
                reasoning=Reasoning(
                    summary=getattr(self.settings, "reasoning_summary_mode", "auto")
                )
            )
        return Agent(
            name="MinimalChatAgent",
            instructions=instructions,
            model=sdk_model,
            model_settings=model_settings,
            tools=self.tool_registry.list_agent_tools(),
            handoffs=handoffs,
        )

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
                    "agents.main_chat",
                    task_type=task_type,
                    extra_instructions="",
                )
                instructions = rendered.text
                ctx.metadata["prompt"] = rendered.to_metadata()
            except Exception as exc:
                self.logger.warning(
                    "prompt_get_failed_using_fallback",
                    extra={
                        "prompt_name": "agents.main_chat",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                if not self.settings.prompt_fail_open:
                    raise
        return instructions
