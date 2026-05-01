from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol


class Level(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class Event:
    level: Level
    msg: str
    data: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class Handler(Protocol):
    def handle(self, event: Event) -> None: ...


class ConsoleHandler:
    def handle(self, event: Event) -> None:
        ts = event.timestamp.strftime("%H:%M:%S")
        kv = "  ".join(f"{k}={v}" for k, v in event.data.items())
        line = f"{ts} [combfind] {event.level.value.upper():<8} {event.msg}"
        if kv:
            line += f"  {kv}"
        print(line)


_lock = threading.Lock()
_handlers: list[Handler] = [ConsoleHandler()]


def set_handlers(handlers: list[Handler]) -> None:
    with _lock:
        _handlers[:] = handlers


def add_handler(handler: Handler) -> None:
    with _lock:
        _handlers.append(handler)


_LEVEL_ORDER = {Level.DEBUG: 0, Level.INFO: 1, Level.WARNING: 2, Level.ERROR: 3}


def emit(level: Level, msg: str, **data) -> None:
    try:
        min_level = Level(os.environ.get("COMBFIND_LOG_LEVEL", "info").lower())
    except ValueError:
        min_level = Level.INFO
    if _LEVEL_ORDER[level] < _LEVEL_ORDER[min_level]:
        return
    event = Event(level=level, msg=msg, data=data)
    with _lock:
        handlers = list(_handlers)
    for h in handlers:
        h.handle(event)


def info(msg: str, **data) -> None:
    emit(Level.INFO, msg, **data)


def warning(msg: str, **data) -> None:
    emit(Level.WARNING, msg, **data)


def error(msg: str, **data) -> None:
    emit(Level.ERROR, msg, **data)


def debug(msg: str, **data) -> None:
    emit(Level.DEBUG, msg, **data)
