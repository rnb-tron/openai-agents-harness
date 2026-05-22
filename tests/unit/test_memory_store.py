from src.capabilities.memory.store import MemoryStore


def test_memory_store_clear_and_stats():
    store = MemoryStore()
    store.append("s1", "user", "hello")
    store.append("s1", "assistant", "hi")
    store.append("s2", "user", "hey")

    assert store.stats() == {"sessions": 2, "messages": 3}

    store.clear("s1")

    assert store.get("s1") == []
    assert store.stats() == {"sessions": 1, "messages": 1}
