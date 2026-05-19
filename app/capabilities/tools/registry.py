from collections.abc import Callable

from agents import function_tool


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Callable] = {}

    def register(self, name: str, handler: Callable) -> None:
        self._tools[name] = handler

    def get(self, name: str) -> Callable | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def list_agent_tools(self) -> list[Callable]:
        return [self._tools[name] for name in self.list_tools()]

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

        self.register("add_numbers", add_numbers)
        self.register("get_weather", get_weather)
