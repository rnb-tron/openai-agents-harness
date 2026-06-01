from src.capabilities.memory.store import MemoryStore


def test_memory_store_is_noop_compatibility_adapter():
    store = MemoryStore()
    store.append("s1", "user", "hello")
    store.append("s1", "assistant", "hi")
    store.append("s2", "user", "hey")

    assert store.stats() == {"sessions": 0, "messages": 0, "backend": "disabled"}

    store.clear("s1")

    assert store.get("s1") == []
    assert store.render_context("s1") == ""
