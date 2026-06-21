from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from typing import Any, Callable
from uuid import uuid4


EventHandler = Callable[["YingmingEvent"], None]


@dataclass(frozen=True)
class YingmingEvent:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "system"
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "source": self.source,
            "created_at": self.created_at,
            "payload": self.payload,
        }


class EventBus:
    def __init__(self, max_events: int = 200) -> None:
        self._events: deque[YingmingEvent] = deque(maxlen=max_events)
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._lock = RLock()

    def emit(self, event_type: str, payload: dict[str, Any] | None = None, source: str = "system") -> YingmingEvent:
        event = YingmingEvent(type=event_type, payload=payload or {}, source=source)
        with self._lock:
            self._events.append(event)
            handlers = [*self._subscribers.get(event_type, []), *self._subscribers.get("*", [])]
        for handler in handlers:
            handler(event)
        return event

    def subscribe(self, event_type: str, handler: EventHandler) -> Callable[[], None]:
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(handler)

        def unsubscribe() -> None:
            with self._lock:
                handlers = self._subscribers.get(event_type, [])
                if handler in handlers:
                    handlers.remove(handler)

        return unsubscribe

    def recent(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._events)[-limit:]
        return [event.as_dict() for event in events]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
