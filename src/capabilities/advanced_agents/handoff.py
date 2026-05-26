"""OpenAI Agents SDK 原生 Handoff 的轻量装配器。"""

from typing import Any

from agents import Agent, OpenAIChatCompletionsModel

from src.core.logging import setup_logger

from .config import HandoffConfig

logger = setup_logger("advanced_agents.handoff")


class HandoffManager:
    """根据配置构造可交给主 Agent 的 SDK 原生 handoff 目标。"""

    def __init__(
        self,
        config: HandoffConfig,
        model: OpenAIChatCompletionsModel | None = None,
    ) -> None:
        self.config = config
        self._agents: dict[str, Agent] = {}
        self._agent_registry: dict[str, dict[str, Any]] = {}
        self.model = model

    def is_enabled(self) -> bool:
        return self.config.enabled

    def register_agent(
        self,
        name: str,
        display_name: str,
        description: str,
        instructions: str = "",
    ) -> dict[str, Any]:
        metadata = {
            "name": name,
            "display_name": display_name,
            "description": description,
            "instructions": instructions,
        }
        self._agent_registry[name] = metadata
        logger.info(
            "agent_registered",
            extra={"agent_name": name, "display_name": display_name},
        )
        return metadata

    def create_agent(
        self,
        name: str,
        instructions: str,
        tools: list[Any] | None = None,
        *,
        description: str = "",
        model: OpenAIChatCompletionsModel | None = None,
    ) -> Agent:
        agent_model = model or self.model
        if not agent_model:
            raise ValueError("未提供 Model 实例")

        agent = Agent(
            name=name,
            handoff_description=description or None,
            instructions=instructions,
            model=agent_model,
            tools=tools or [],
        )
        self._agents[name] = agent
        logger.info("agent_created", extra={"agent_name": name})
        return agent

    def build_configured_handoffs(
        self,
        model: OpenAIChatCompletionsModel,
    ) -> list[Agent]:
        """构造主 Agent 的 SDK 原生 handoff 目标列表。"""
        if not self.config.enabled:
            return []

        self.model = model
        handoffs: list[Agent] = []
        for name, spec in self.config.agents.items():
            if not isinstance(spec, dict) or spec.get("enabled", True) is False:
                continue
            handoffs.append(
                self.create_agent(
                    name=name,
                    instructions=str(spec.get("instructions", "")),
                    description=str(spec.get("description", "")),
                    model=model,
                )
            )
        return handoffs

    def create_triage_agent(
        self,
        name: str,
        instructions: str,
        handoff_agents: list[str],
        tools: list[Any] | None = None,
    ) -> Agent:
        if not self.model:
            raise ValueError("未提供 Model 实例")

        targets = [
            agent for agent_name in handoff_agents if (agent := self._agents.get(agent_name))
        ]
        triage_agent = Agent(
            name=name,
            instructions=instructions,
            model=self.model,
            tools=tools or [],
            handoffs=targets,
        )
        self._agents[name] = triage_agent
        logger.info(
            "triage_agent_created",
            extra={"agent_name": name, "handoff_targets": handoff_agents},
        )
        return triage_agent

    def is_agent_available(self, agent_name: str) -> bool:
        return agent_name in self._agents or agent_name in self._agent_registry

    def get_agent(self, agent_name: str) -> Agent | None:
        return self._agents.get(agent_name)

    def get_available_agents(self) -> list[str]:
        return list(self._agents.keys())

    def get_registry(self) -> dict[str, dict[str, Any]]:
        return self._agent_registry.copy()

    def cleanup(self) -> None:
        self._agents.clear()
        self._agent_registry.clear()
        logger.info("handoff_manager_cleaned")
