"""Message schema and validation. Everything that comes off the wire is untrusted."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

TOPIC_PREFIX = "factory"
# metric -> (unit, minimum plausible value, maximum plausible value)
METRICS = {
    "temperature": ("C", -50.0, 200.0),
    "vibration": ("mm/s", 0.0, 50.0),
    "voltage": ("V", 0.0, 500.0),
}
_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Reading:
    device: str
    metric: str
    value: float
    ts: float
    seq: int
    unit: str


def _number(x, name):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValidationError(f"{name} must be a number")
    if not math.isfinite(x):
        raise ValidationError(f"{name} must be finite")
    return float(x)


def parse_reading(payload, topic: str | None = None) -> Reading:
    """Parse and validate one message. Raises ValidationError on anything unexpected."""
    try:
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode("utf-8")
        data = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise ValidationError(f"payload is not valid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise ValidationError("payload must be a JSON object")
    for key in ("device", "metric", "value", "ts", "seq"):
        if key not in data:
            raise ValidationError(f"missing field: {key}")

    device, metric = data["device"], data["metric"]
    if not isinstance(device, str) or not _NAME.match(device):
        raise ValidationError("device must be 1-64 chars of letters, digits, '-' or '_'")
    if metric not in METRICS:
        raise ValidationError(f"unknown metric: {metric!r}")
    unit, lo, hi = METRICS[metric]
    value = _number(data["value"], "value")
    if not lo <= value <= hi:
        raise ValidationError(f"value {value} outside plausible range [{lo}, {hi}] for {metric}")
    ts = _number(data["ts"], "ts")
    if ts <= 0:
        raise ValidationError("ts must be positive")
    seq = data["seq"]
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        raise ValidationError("seq must be a non-negative integer")
    if topic is not None and topic != f"{TOPIC_PREFIX}/{device}/{metric}":
        raise ValidationError("topic does not match device/metric in payload")
    return Reading(device, metric, value, ts, seq, unit)
