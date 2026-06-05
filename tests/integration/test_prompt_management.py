"""Prompt Management Capability tests.

Run:
    venv/bin/python -m pytest tests/test_prompt_management.py -v
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.capabilities.prompt import (  # noqa: E402
    CompositeStore,
    LangfuseStore,
    LocalYamlStore,
    PromptCapability,
    PromptFetchError,
    PromptManager,
    PromptNotFoundError,
    PromptTemplate,
    get_prompt_manager,
    reset_prompt_manager,
)

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _make_settings(**overrides) -> SimpleNamespace:
    """Build a minimal Settings-like object."""
    defaults = dict(
        prompt_enabled=True,
        prompt_backend="yaml",
        prompt_local_dir="prompts",
        prompt_default_label="prod",
        prompt_cache_ttl_sec=300,
        prompt_warmup_names="",
        prompt_fail_open=True,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _write_yaml(dir_: Path, rel: str, body: str) -> Path:
    p = dir_ / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _make_yaml_dir() -> Path:
    """Create a temp dir with two test yaml files, return the dir path."""
    tmp = Path(tempfile.mkdtemp(prefix="prompt_yaml_"))
    _write_yaml(
        tmp,
        "agents/main_chat.yaml",
        'name: agents.main_chat\n'
        'version: "1.0.0"\n'
        'label: prod\n'
        "template: |-\n"
        "  Hello {user_name}, you are {role}.\n"
        "metadata:\n"
        "  description: test\n",
    )
    _write_yaml(
        tmp,
        "capabilities/summary.yaml",
        'name: capabilities.summary\n'
        'version: "1.0.0"\n'
        "template: |-\n"
        "  Summarize concisely. Keep facts.\n",
    )
    return tmp


class _FakeStore:
    """A minimal in-memory PromptStore for manager tests."""

    name = "fake"

    def __init__(self, templates: dict[str, PromptTemplate]) -> None:
        self._tpls = templates
        self.fetch_count = 0

    async def fetch(self, name, *, version=None, label=None) -> PromptTemplate:
        self.fetch_count += 1
        tpl = self._tpls.get(name)
        if tpl is None:
            raise PromptNotFoundError(f"not found: {name}")
        return tpl


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------


def test_disabled_no_op() -> None:
    """prompt_enabled=False -> get_prompt_manager returns None;
    AgentOrchestrator constructed with disabled prompt won't register PromptCapability.
    """
    reset_prompt_manager()
    fake_settings = _make_settings(prompt_enabled=False)
    with patch("src.capabilities.prompt.factory._runtime_settings", fake_settings):
        mgr = get_prompt_manager()
    assert mgr is None
    reset_prompt_manager()


def test_local_yaml_store_load() -> None:
    tmp = _make_yaml_dir()
    store = LocalYamlStore(base_dir=tmp)
    names = store.list_names()
    assert "agents.main_chat" in names
    assert "capabilities.summary" in names

    tpl = asyncio.run(store.fetch("agents.main_chat"))
    assert tpl.name == "agents.main_chat"
    assert tpl.version == "1.0.0"
    assert tpl.label == "prod"
    assert tpl.source == "yaml"
    assert "{user_name}" in tpl.template


def test_local_yaml_store_not_found() -> None:
    tmp = _make_yaml_dir()
    store = LocalYamlStore(base_dir=tmp)

    async def _run():
        await store.fetch("does.not.exist")

    try:
        asyncio.run(_run())
        raise AssertionError("expected PromptNotFoundError")
    except PromptNotFoundError:
        pass


def test_manager_render_with_vars() -> None:
    tpls = {
        "greeting": PromptTemplate(
            name="greeting",
            template="Hello {user_name}, you are {role}.",
            source="fake",
        )
    }
    mgr = PromptManager(_FakeStore(tpls), cache_ttl_sec=300)
    rendered = asyncio.run(mgr.get("greeting", user_name="Alice", role="admin"))

    assert rendered.text == "Hello Alice, you are admin."
    assert rendered.name == "greeting"
    assert rendered.cache_hit is False
    assert rendered.rendered_vars == {"user_name": "Alice", "role": "admin"}
    md = rendered.to_metadata()
    assert "name" in md and "source" in md and "cache_hit" in md
    assert "text" not in md  # text 不应在 metadata 中


def test_manager_missing_var_keeps_placeholder() -> None:
    tpls = {
        "greeting": PromptTemplate(
            name="greeting",
            template="Hello {user_name}, you are {role}.",
            source="fake",
        )
    }
    mgr = PromptManager(_FakeStore(tpls))
    rendered = asyncio.run(mgr.get("greeting", user_name="Bob"))
    # {role} 缺失应保留原样, 不抛错
    assert rendered.text == "Hello Bob, you are {role}."


def test_manager_renders_langfuse_double_brace_template() -> None:
    tpls = {
        "greeting": PromptTemplate(
            name="greeting",
            template="Hello {{ user_name }}, you are {{role}}.",
            version=3,
            label="prod",
            source="langfuse",
            metadata={"langfuse_labels": ["prod"], "langfuse_tags": ["agent"]},
        )
    }
    mgr = PromptManager(_FakeStore(tpls))
    rendered = asyncio.run(mgr.get("greeting", user_name="Alice"))

    assert rendered.text == "Hello Alice, you are {role}."
    md = rendered.to_metadata()
    assert md["label"] == "prod"
    assert md["langfuse_labels"] == ["prod"]
    assert md["langfuse_tags"] == ["agent"]


def test_manager_cache_hit() -> None:
    tpls = {
        "x": PromptTemplate(name="x", template="payload-{n}", source="fake"),
    }
    store = _FakeStore(tpls)
    mgr = PromptManager(store, cache_ttl_sec=300)

    r1 = asyncio.run(mgr.get("x", n="1"))
    r2 = asyncio.run(mgr.get("x", n="2"))

    assert r1.cache_hit is False
    assert r2.cache_hit is True
    assert store.fetch_count == 1, f"store.fetch_count={store.fetch_count}, expected 1"
    # 不同变量但 cache key 相同 (cache key 不含 vars), 验证渲染独立
    assert r1.text == "payload-1"
    assert r2.text == "payload-2"


def test_manager_cache_ttl_expires() -> None:
    tpls = {"x": PromptTemplate(name="x", template="hi", source="fake")}
    store = _FakeStore(tpls)
    mgr = PromptManager(store, cache_ttl_sec=1)

    r1 = asyncio.run(mgr.get("x"))
    assert r1.cache_hit is False
    assert store.fetch_count == 1

    # 模拟过期: 直接改写 cache 内部 expires_at 为过去
    for k, (_expires, tpl) in list(mgr._cache.items()):
        mgr._cache[k] = (time.time() - 10, tpl)

    r2 = asyncio.run(mgr.get("x"))
    assert r2.cache_hit is False
    assert store.fetch_count == 2


def test_composite_falls_back_on_primary_error() -> None:
    tpls = {"x": PromptTemplate(name="x", template="from-yaml", source="yaml")}

    class FailingPrimary:
        name = "langfuse"

        async def fetch(self, name, *, version=None, label=None):
            raise PromptFetchError("network down")

    fallback = _FakeStore(tpls)
    composite = CompositeStore(primary=FailingPrimary(), fallback=fallback)

    tpl = asyncio.run(composite.fetch("x"))
    assert tpl.template == "from-yaml"
    assert "composite:" in tpl.source, f"expected composite:* prefix, got {tpl.source}"
    assert fallback.fetch_count == 1


def test_langfuse_store_reuses_injected_client() -> None:
    class FakePrompt:
        name = "agents.main_chat"
        prompt = "Hello {{name}}"
        version = 7
        labels = ["prod"]
        tags = ["main"]
        config = {"temperature": 0.2}
        is_fallback = False

    class FakeClient:
        def __init__(self) -> None:
            self.calls = []

        def get_prompt(self, name, **kwargs):
            self.calls.append((name, kwargs))
            return FakePrompt()

    client = FakeClient()
    store = LangfuseStore(default_label="prod", client=client)
    tpl = asyncio.run(store.fetch("agents.main_chat"))

    assert tpl.template == "Hello {{name}}"
    assert tpl.version == 7
    assert tpl.label == "prod"
    assert tpl.metadata["langfuse_labels"] == ["prod"]
    assert client.calls == [("agents.main_chat", {"label": "prod"})]


def test_langfuse_store_accepts_chat_prompt_payload() -> None:
    class FakePrompt:
        name = "agents.main_chat"
        prompt = [
            {"role": "system", "content": "You are {{role}}."},
            {"role": "user", "content": {"type": "placeholder", "name": "input"}},
        ]
        version = 8
        labels = ["prod"]
        tags = []
        config = {}
        is_fallback = False

    class FakeClient:
        def get_prompt(self, name, **kwargs):
            return FakePrompt()

    store = LangfuseStore(default_label="prod", client=FakeClient())
    tpl = asyncio.run(store.fetch("agents.main_chat"))

    assert tpl.template.startswith("system: You are {{role}}.")
    assert "user:" in tpl.template
    assert tpl.metadata["langfuse_prompt_type"] == "chat"


def test_composite_propagates_when_both_fail() -> None:
    class FailingPrimary:
        name = "langfuse"

        async def fetch(self, name, *, version=None, label=None):
            raise PromptFetchError("primary down")

    fallback = _FakeStore({})
    composite = CompositeStore(primary=FailingPrimary(), fallback=fallback)

    try:
        asyncio.run(composite.fetch("missing"))
        raise AssertionError("expected PromptNotFoundError")
    except PromptNotFoundError:
        pass


def test_warmup_failure_does_not_crash() -> None:
    """warmup 中部分 prompt 找不到, 不应抛错;
    PromptCapability.setup() 也应吞下错误。
    """
    tpls = {"ok": PromptTemplate(name="ok", template="OK", source="fake")}
    mgr = PromptManager(_FakeStore(tpls))
    cap = PromptCapability(manager=mgr, warmup_names=["ok", "missing"], enabled=True)

    # setup() 不应抛错
    asyncio.run(cap.setup())
    # 其中 "ok" 应已被 warmup 拉取并缓存
    r = asyncio.run(mgr.get("ok"))
    assert r.cache_hit is True


def test_main_chat_fallback_when_get_fails() -> None:
    """集成: agent_runtime 中 prompt 失败时 instructions 走硬编码 fallback,
    主流程不挂。

    通过注入一个会抛错的 mgr, 调用 orchestrator.run()
    并 mock Runner.run, 验证 fallback 文本生效。
    """
    reset_prompt_manager()
    fake_settings = _make_settings(prompt_enabled=True, prompt_fail_open=True)
    # 也 patch agent_runtime 用到的 current_settings (函数内是 module-level import)
    from src.application.orchestration import agent_runtime as ar_mod

    failing_mgr = MagicMock()
    failing_mgr.get = AsyncMock(side_effect=RuntimeError("intentional"))

    fake_run_result = MagicMock()
    fake_run_result.final_output = "ok"
    # parse_tool_calls_from_result 解析 result, 给个空 list 来源
    fake_run_result.new_items = []

    # 重新构造 settings 让 prompt_enabled=True 生效(其余使用默认)
    full_settings = SimpleNamespace(
        openai_api_key="sk-test",
        openai_base_url=None,
        prompt_enabled=True,
        prompt_fail_open=True,
        compression_enabled=False,
        memory_short_term_enabled=False,
        memory_session_summary_enabled=False,
        memory_long_term_enabled=False,
    )
    with patch.object(ar_mod, "current_settings", full_settings), \
         patch.object(ar_mod, "Runner") as MockRunner, \
         patch.object(ar_mod, "Agent") as MockAgent, \
         patch.object(ar_mod, "AsyncOpenAI") as MockClient, \
         patch.object(ar_mod, "OpenAIChatCompletionsModel"), \
         patch.object(ar_mod, "parse_tool_calls_from_result", return_value=[]):
        MockRunner.run = AsyncMock(return_value=fake_run_result)
        MockClient.return_value = MagicMock()
        MockAgent.return_value = MagicMock()

        # 构造 orchestrator
        from src.capabilities.memory.store import MemoryStore
        from src.capabilities.model_routing.router import ModelRouter
        from src.capabilities.tools.registry import ToolRegistry

        orch = ar_mod.AgentOrchestrator(
            tool_registry=ToolRegistry(),
            memory_store=MemoryStore(),
            model_router=ModelRouter(),
            prompt_manager=failing_mgr,
        )
        session = ar_mod.AgentSession(session_id="s1")
        result = asyncio.run(orch.run(session, "hello"))

        # 验证: prompt_enabled=True 但 mgr.get 抛错 → 走 fallback
        # Agent 被构造时 instructions 应是硬编码 fallback (含 "concise assistant")
        agent_call = MockAgent.call_args
        instructions = agent_call.kwargs.get("instructions", "")
        assert "concise assistant" in instructions, (
            f"expected fallback hardcoded instructions, got: {instructions!r}"
        )

        # 主流程应正常返回
        assert result["output"] == "ok"

    reset_prompt_manager()


# ----------------------------------------------------------------------
# Manual runner
# ----------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_disabled_no_op,
        test_local_yaml_store_load,
        test_local_yaml_store_not_found,
        test_manager_render_with_vars,
        test_manager_missing_var_keeps_placeholder,
        test_manager_renders_langfuse_double_brace_template,
        test_manager_cache_hit,
        test_manager_cache_ttl_expires,
        test_composite_falls_back_on_primary_error,
        test_langfuse_store_reuses_injected_client,
        test_langfuse_store_accepts_chat_prompt_payload,
        test_composite_propagates_when_both_fail,
        test_warmup_failure_does_not_crash,
        test_main_chat_fallback_when_get_fails,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  OK  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {type(exc).__name__}: {exc}")
    total = len(tests)
    ok = total - failed
    print(f"\n[ {ok}/{total} ] tests passed")
    sys.exit(1 if failed else 0)
