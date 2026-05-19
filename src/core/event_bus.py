import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable


@dataclass
class Event:
    event_type: str
    data: dict[str, Any]
    timestamp: datetime | None = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class EventBus:
    _instance = None
    _subscribers: dict[str, list[Callable]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._subscribers = {}
        return cls._instance

    @classmethod
    def subscribe(cls, event_type: str, handler: Callable) -> None:
        if event_type not in cls._subscribers:
            cls._subscribers[event_type] = []
        if handler not in cls._subscribers[event_type]:
            cls._subscribers[event_type].append(handler)

    @classmethod
    def unsubscribe(cls, event_type: str, handler: Callable) -> None:
        if event_type in cls._subscribers and handler in cls._subscribers[event_type]:
            cls._subscribers[event_type].remove(handler)

    @classmethod
    def publish(cls, event_type: str, data: dict[str, Any] | None = None) -> None:
        event = Event(event_type=event_type, data=data or {})
        for handler in cls._subscribers.get(event_type, []):
            asyncio.create_task(cls._invoke_handler(handler, event))

    @classmethod
    async def _invoke_handler(cls, handler: Callable, event: Event) -> None:
        if asyncio.iscoroutinefunction(handler):
            await handler(event)
        else:
            handler(event)


event_bus = EventBus()
