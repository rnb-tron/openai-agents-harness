from dataclasses import dataclass, is_dataclass, replace
from typing import Any

from agents import function_tool


@dataclass(frozen=True)
class ToolSpec:
    """Metadata wrapper around an Agents SDK-compatible tool callable."""

    name: str
    handler: Any
    description: str = ""
    category: str = "custom"
    enabled: bool = True
    risk_level: str = "low"
    requires_approval: bool = False
    timeout_sec: float | None = None
    audit_enabled: bool = True


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}
        self._approval_required_names: set[str] = set()
        self._auto_approve_names: set[str] = set()

    def register(
        self,
        name: str,
        handler: Any,
        *,
        description: str = "",
        category: str = "custom",
        enabled: bool = True,
        risk_level: str = "low",
        requires_approval: bool = False,
        timeout_sec: float | None = None,
        audit_enabled: bool = True,
    ) -> None:
        self.register_spec(
            ToolSpec(
                name=name,
                handler=handler,
                description=description,
                category=category,
                enabled=enabled,
                risk_level=risk_level,
                requires_approval=requires_approval,
                timeout_sec=timeout_sec,
                audit_enabled=audit_enabled,
            )
        )

    def register_spec(self, spec: ToolSpec) -> None:
        if not spec.name:
            raise ValueError("tool name is required")
        if spec.handler is None:
            raise ValueError("tool handler is required")
        self._tools[spec.name] = self._apply_approval_policy(spec)

    def configure_approval_policy(
        self,
        *,
        require_approval: list[str] | tuple[str, ...] = (),
        auto_approve: list[str] | tuple[str, ...] = (),
    ) -> None:
        """Apply HITL policy to existing tools and any tools registered later."""
        self._approval_required_names = set(require_approval)
        self._auto_approve_names = set(auto_approve)
        self._tools = {
            name: self._apply_approval_policy(spec)
            for name, spec in self._tools.items()
        }

    def _apply_approval_policy(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._auto_approve_names:
            return replace(spec, requires_approval=False)
        if spec.name in self._approval_required_names:
            return replace(spec, requires_approval=True)
        return spec

    def get(self, name: str) -> Any | None:
        spec = self._tools.get(name)
        if spec is None or not spec.enabled:
            return None
        return spec.handler

    def get_spec(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return sorted(name for name, spec in self._tools.items() if spec.enabled)

    def list_specs(self, *, enabled_only: bool = True) -> list[ToolSpec]:
        specs = self._tools.values()
        if enabled_only:
            specs = [spec for spec in specs if spec.enabled]
        return sorted(specs, key=lambda spec: spec.name)

    def list_agent_tools(self) -> list[Any]:
        return [self._to_agent_tool(self._tools[name]) for name in self.list_tools()]

    def list_approval_required(self) -> list[str]:
        return [
            spec.name
            for spec in self.list_specs()
            if spec.requires_approval
        ]

    def _to_agent_tool(self, spec: ToolSpec) -> Any:
        handler = spec.handler
        updates: dict[str, Any] = {}
        if spec.requires_approval:
            updates["needs_approval"] = True
        if spec.timeout_sec is not None:
            updates["timeout_seconds"] = spec.timeout_sec
        if updates and is_dataclass(handler):
            valid_fields = {field.name for field in handler.__dataclass_fields__.values()}
            filtered = {key: value for key, value in updates.items() if key in valid_fields}
            if filtered:
                return replace(handler, **filtered)
        return handler

    def register_defaults(self) -> None:
        """Register minimal SDK tools for demo and extension."""

        @function_tool
        async def get_weather(city: str) -> str:
            """Return a mocked weather report for the given city."""
            city_name = city.strip() or "unknown"
            return f"{city_name} weather: sunny, 26C, light wind."

        @function_tool
        async def add_numbers(a: float, b: float) -> float:
            """Add two numbers and return the result."""
            return a + b

        self.register(
            "add_numbers",
            add_numbers,
            description="Add two numbers and return the result.",
            category="builtin",
            risk_level="low",
        )
        self.register(
            "get_weather",
            get_weather,
            description="Return a mocked weather report for a city.",
            category="builtin",
            risk_level="low",
        )
