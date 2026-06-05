from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from langfuse import propagate_attributes

from src.capabilities.observability import get_tracer_manager


class AgentRunObserver:
    """Langfuse observation wrapper used by streaming runtime methods."""

    @contextmanager
    def observe(
        self,
        *,
        session_id: str,
        user_id: str | None,
        user_input: str,
        trace_name: str,
    ):
        tracer_manager = get_tracer_manager()
        langfuse = tracer_manager.langfuse if tracer_manager is not None and tracer_manager.is_initialized else None
        if langfuse is None:
            yield None
            return

        with langfuse.start_as_current_observation(
            name=trace_name,
            as_type="agent",
            input=user_input,
        ) as observation:
            with propagate_attributes(
                trace_name=trace_name,
                session_id=session_id,
                user_id=user_id,
                tags=["chat"],
            ):
                langfuse.set_current_trace_io(input=user_input)
                yield observation

    def update(self, observation: Any, result: dict[str, Any]) -> None:
        if observation is None:
            return
        output: Any = result.get("output")
        if result.get("interrupted"):
            output = {
                "interrupted": True,
                "interruptions": result.get("interruptions", []),
            }
        observation.update(
            output=output,
            metadata={
                "model": result.get("model", ""),
                "interrupted": bool(result.get("interrupted", False)),
                **dict(result.get("metadata") or {}),
            },
        )
        tracer_manager = get_tracer_manager()
        if tracer_manager is not None and tracer_manager.langfuse is not None:
            tracer_manager.langfuse.set_current_trace_io(output=output)

    @staticmethod
    def mark_error(observation: Any, error: Exception) -> None:
        if observation is not None:
            observation.update(level="ERROR", status_message=str(error))
