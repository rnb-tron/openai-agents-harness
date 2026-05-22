from src.capabilities.tools import ToolRegistry, ToolSpec


def _tool() -> str:
    return "ok"


def test_register_keeps_callable_compatibility():
    registry = ToolRegistry()

    registry.register(
        "custom_tool",
        _tool,
        description="A custom test tool.",
        category="test",
        requires_approval=True,
    )

    assert registry.get("custom_tool") is _tool
    assert registry.list_tools() == ["custom_tool"]
    assert registry.list_agent_tools() == [_tool]
    assert registry.list_approval_required() == ["custom_tool"]

    spec = registry.get_spec("custom_tool")
    assert spec is not None
    assert spec.description == "A custom test tool."
    assert spec.category == "test"
    assert spec.requires_approval is True


def test_disabled_tools_are_hidden_from_runtime_lists():
    registry = ToolRegistry()
    registry.register_spec(ToolSpec(name="disabled_tool", handler=_tool, enabled=False))

    assert registry.get("disabled_tool") is None
    assert registry.list_tools() == []
    assert registry.list_agent_tools() == []
    assert registry.get_spec("disabled_tool") is not None


def test_default_tools_include_metadata():
    registry = ToolRegistry()
    registry.register_defaults()

    assert registry.list_tools() == ["add_numbers", "get_weather"]

    add_spec = registry.get_spec("add_numbers")
    assert add_spec is not None
    assert add_spec.category == "builtin"
    assert add_spec.risk_level == "low"
