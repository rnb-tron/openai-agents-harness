"""
Handoff Agent 协作管理器

提供:
- 注册专业 Agent
- 创建 Triage Agent (带 Handoff 能力)
- 执行 Handoff 路由
- Agent 可用性检查
"""

from typing import Optional, Any

try:
    from openai_agents import Agent
    from openai_agents.models import OpenAIChatCompletionsModel
except ImportError:
    # 如果 openai_agents 未安装,使用占位符
    Agent = Any
    OpenAIChatCompletionsModel = Any

from src.core.logging import setup_logger

from .config import HandoffConfig

logger = setup_logger("advanced_agents.handoff")


class HandoffManager:
    """Handoff Agent 协作管理器"""
    
    def __init__(
        self,
        config: HandoffConfig,
        model: Optional[OpenAIChatCompletionsModel] = None,
    ):
        self.config = config
        self._agents: dict[str, Agent] = {}
        self._agent_registry: dict[str, dict] = {}  # 存储 Agent 元信息
        self.model = model
    
    def is_enabled(self) -> bool:
        """是否启用 Handoff"""
        return self.config.enabled
    
    def register_agent(
        self,
        name: str,
        display_name: str,
        description: str,
        instructions: str = "",
    ) -> dict:
        """注册一个 Agent"""
        self._agent_registry[name] = {
            "name": name,
            "display_name": display_name,
            "description": description,
            "instructions": instructions,
        }
        logger.info(
            "agent_registered",
            extra={"agent_name": name, "display_name": display_name},
        )
        return self._agent_registry[name]
    
    def create_agent(
        self,
        name: str,
        instructions: str,
        tools: Optional[list] = None,
    ) -> Agent:
        """创建 Agent 实例"""
        if not self.model:
            raise ValueError("未提供 Model 实例")
        
        agent = Agent(
            name=name,
            instructions=instructions,
            model=self.model,
            tools=tools or [],
        )
        
        self._agents[name] = agent
        logger.info("agent_created", extra={"agent_name": name})
        return agent
    
    def create_triage_agent(
        self,
        name: str,
        instructions: str,
        handoff_agents: list[str],
        tools: Optional[list] = None,
    ) -> Agent:
        """创建 Triage Agent (带 Handoff 能力)"""
        if not self.model:
            raise ValueError("未提供 Model 实例")
        
        # 获取要 Handoff 的 Agent
        agents_to_handoff = []
        for agent_name in handoff_agents:
            agent = self._agents.get(agent_name)
            if agent:
                agents_to_handoff.append(agent)
        
        triage_agent = Agent(
            name=name,
            instructions=instructions,
            model=self.model,
            tools=tools or [],
            handoffs=agents_to_handoff,  # 设置 Handoff
        )
        
        self._agents[name] = triage_agent
        logger.info(
            "triage_agent_created",
            extra={"agent_name": name, "handoff_targets": handoff_agents},
        )

        return triage_agent
    
    def is_agent_available(self, agent_name: str) -> bool:
        """检查 Agent 是否可用"""
        return agent_name in self._agents or agent_name in self._agent_registry
    
    def get_agent(self, agent_name: str) -> Optional[Agent]:
        """获取 Agent 实例"""
        return self._agents.get(agent_name)
    
    def get_available_agents(self) -> list[str]:
        """获取所有可用的 Agent"""
        return list(self._agents.keys())
    
    def get_registry(self) -> dict[str, dict]:
        """获取 Agent 注册表"""
        return self._agent_registry.copy()
    
    def cleanup(self):
        """清理所有 Agent"""
        self._agents.clear()
        self._agent_registry.clear()
        logger.info("handoff_manager_cleaned")
