"""Sensor simulator with fault injection (spike, drift, stuck, dropout)."""
from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass

from .schema import METRICS, TOPIC_PREFIX


@dataclass(frozen=True)
class Fault:
    kind: str            # spike | drift | stuck | dropout
    start: int           # first affected step
    duration: int = 1
    magnitude: float = 0.0


class SensorSim:
    def __init__(self, device, metric, nominal, noise, amplitude=0.0, period=120, faults=(), seed=0):
        self.device, self.metric = device, metric
        self.nominal, self.noise, self.amplitude, self.period = nominal, noise, amplitude, period
        self.faults = tuple(faults)
        self._rng = random.Random(f"{seed}:{device}:{metric}")
        self._last = nominal
        self._stuck_value = {}

    def reading(self, i):
        """Value at step i, or None when the sensor has dropped out."""
        value = self.nominal + self.amplitude * math.sin(2 * math.pi * i / self.period)
        value += self._rng.gauss(0, self.noise)
        for n, f in enumerate(self.faults):
            if not f.start <= i < f.start + f.duration:
                continue
            if f.kind == "spike":
                value += f.magnitude
            elif f.kind == "drift":
                value += f.magnitude * (i - f.start + 1) / f.duration
            elif f.kind == "stuck":
                value = self._stuck_value.setdefault(n, self._last)
            elif f.kind == "dropout":
                return None
        _, lo, hi = METRICS[self.metric]
        value = min(max(value, lo), hi)
        self._last = value
        return round(value, 3)


_BASE = {  # metric -> (nominal, noise, seasonal amplitude)
    "temperature": (70.0, 0.6, 3.0),
    "vibration": (2.5, 0.15, 0.2),
    "voltage": (230.0, 1.2, 0.0),
}
# (device, metric) -> faults. Chosen so each detector is exercised.
DEFAULT_FAULTS = {
    ("pump-01", "temperature"): [Fault("drift", 150, 60, 35.0)],   # overheating, ramps past the 90 C limit
    ("pump-02", "vibration"): [Fault("spike", 100, 1, 4.0)],       # single shock, still under the hard limit
    ("motor-01", "voltage"): [Fault("stuck", 220, 30)],            # frozen sensor
    ("pump-02", "voltage"): [Fault("dropout", 260, 25)],           # lost connection
}
DEFAULT_DEVICES = ("pump-01", "pump-02", "motor-01")


def default_fleet(seed=7, faults=True):
    fleet = []
    for device in DEFAULT_DEVICES:
        for metric, (nominal, noise, amp) in _BASE.items():
            f = DEFAULT_FAULTS.get((device, metric), []) if faults else []
            fleet.append(SensorSim(device, metric, nominal, noise, amp, faults=f, seed=seed))
    return fleet


def run(bus, sensors, steps, interval=1.0, realtime=False, start_ts=None, stop=None, on_step=None):
    """Publish `steps` readings per sensor. Returns the number of messages published.

    realtime=False generates timestamps instantly (start_ts + i*interval) for tests/benchmarks."""
    start_ts = time.time() if start_ts is None else start_ts
    sent = 0
    for i in range(steps):
        if stop is not None and stop.is_set():
            break
        ts = time.time() if realtime else start_ts + i * interval
        for s in sensors:
            v = s.reading(i)
            if v is None:
                continue
            unit = METRICS[s.metric][0]
            payload = json.dumps({"device": s.device, "metric": s.metric, "value": v,
                                  "unit": unit, "ts": round(ts, 3), "seq": i}, separators=(",", ":"))
            bus.publish(f"{TOPIC_PREFIX}/{s.device}/{s.metric}", payload)
            sent += 1
        if on_step:
            on_step(i, ts)
        if realtime:
            if stop is not None:
                stop.wait(interval)
            else:
                time.sleep(interval)
    return sent
