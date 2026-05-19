class ModelRouter:
    """Simple runtime model route policy with cheap heuristics."""

    def __init__(self, default_model: str = "gpt-4o-mini", reasoning_model: str = "gpt-4.1-mini"):
        self.default_model = default_model
        self.reasoning_model = reasoning_model

    def select(self, task_type: str | None = None) -> str:
        if task_type == "reasoning":
            return self.reasoning_model
        return self.default_model

    def infer_task_type(self, user_input: str) -> str | None:
        lowered = user_input.lower()
        keywords = ("why", "analyze", "reason", "design", "tradeoff", "explain")
        if any(token in lowered for token in keywords):
            return "reasoning"
        return None
