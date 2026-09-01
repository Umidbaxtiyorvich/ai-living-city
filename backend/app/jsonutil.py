from __future__ import annotations

import json
from enum import Enum
from typing import Any


def jsonable(value: Any) -> Any:
    """Turns simulation payloads into plain JSON (enums, tuples, etc.)."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k) if isinstance(k, Enum) else k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def dumps(value: Any) -> str:
    return json.dumps(jsonable(value), ensure_ascii=False, separators=(",", ":"))
