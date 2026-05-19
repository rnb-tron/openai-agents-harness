from dataclasses import dataclass, field
from typing import Any

from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, Runner, set_tracing_disabled

from app.capabilities.memory.store import MemoryStore
from app.capabilities.memory.manager import MemoryManager
from app.capabilities.model_routing.router import ModelRouter
from app.capabilities.tools.registry import ToolRegistry
from app.core.agents_result_parser import parse_tool_calls_from_result
from app.settings import current_settings

set_tracing_disabled(True)


@dataclass
class AgentSession:
    session_id: str
    user_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


class AgentOrchestrator:
    """Minimal OpenAI Agents SDK orchestration with pluggable capabilities."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        memory_store: MemoryStore,
        model_router: ModelRouter,
        memory_manager: MemoryManager | None = None,
    ):
        self.tool_registry = tool_registry
        self.memory_store = memory_store
        self.model_router = model_router
        self.memory_manager = memory_manager  # 新的MemoryManager (可选)

    async def run(self, session: AgentSession, user_input: str) -> dict[str, Any]:
        if not current_settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for /chat endpoint")

        task_type = self.model_router.infer_task_type(user_input)
        selected_model = self.model_router.select(task_type=task_type)
        
        # 使用新的MemoryManager构建上下文 (如果可用)
        if self.memory_manager and current_settings.memory_enabled:
            try:
                memory_context = await self.memory_manager.get_context(
                    session_id=session.session_id,
                    user_id=session.user_id or "anonymous",
                    user_input=user_input,
                )
            except Exception as e:
                # 降级到旧版MemoryStore
                memory_context = self.memory_store.render_context(session.session_id)
        else:
            # 使用旧版MemoryStore
            memory_context = self.memory_store.render_context(session.session_id)
        
        enriched_input = user_input
        if memory_context:
            enriched_input = (
                "Conversation memory:\n"
                f"{memory_context}\n\n"
                "User:\n"
                f"{user_input}"
            )

        client_kwargs = {"api_key": current_settings.openai_api_key}
        if current_settings.openai_base_url:
            client_kwargs["base_url"] = current_settings.openai_base_url
        client = AsyncOpenAI(**client_kwargs)

        agent = Agent(
            name="MinimalChatAgent",
            instructions=(
                "You are a concise assistant. Use tools when useful. "
                "If a tool is used, include the final user-facing conclusion in plain text."
            ),
            model=OpenAIChatCompletionsModel(model=selected_model, openai_client=client),
            tools=self.tool_registry.list_agent_tools(),
        )
        run_result = await Runner.run(starting_agent=agent, input=enriched_input)
        assistant_output = str(run_result.final_output)
        tool_calls = parse_tool_calls_from_result(run_result)

        # 存储到记忆 (同时使用新旧系统)
        self.memory_store.append(session.session_id, "user", user_input)
        self.memory_store.append(session.session_id, "assistant", assistant_output)
        
        # 如果启用了MemoryManager,也存储到长期记忆
        if self.memory_manager and current_settings.memory_enabled:
            try:
                await self.memory_manager.add_memory(
                    session_id=session.session_id,
                    user_id=session.user_id or "anonymous",
                    role="user",
                    content=user_input,
                )
                await self.memory_manager.add_memory(
                    session_id=session.session_id,
                    user_id=session.user_id or "anonymous",
                    role="assistant",
                    content=assistant_output,
                )
            except Exception as e:
                # 长期记忆失败不影响主流程
                pass
        
        session.context["last_model"] = selected_model

        return {
            "session_id": session.session_id,
            "input": user_input,
            "output": assistant_output,
            "model": selected_model,
            "tool_calls": tool_calls,
            "memory_size": len(self.memory_store.get(session.session_id)),
        }
