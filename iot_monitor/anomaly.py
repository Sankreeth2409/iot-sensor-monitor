"""Streaming anomaly detection: hard limits, robust z-score, stuck sensor."""
from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass

from .schema import Reading

# metric -> (lower limit, upper limit); None = unchecked. Voltage: 230 V +/-10 %.
LIMITS = {
    "temperature": (None, 90.0),
    "vibration": (None, 7.0),
    "voltage": (207.0, 253.0),
}


@dataclass(frozen=True)
class Alert:
    ts: float
    device: str
    metric: str
    kind: str       # threshold | zscore | trend | stuck | stale
    severity: str   # warning | critical
    message: str
    value: float | None = None


class Detector:
    """One instance per (device, metric) series."""

    def __init__(self, window=50, min_samples=20, z_threshold=5.0, stuck_n=15, cooldown=10,
                 trend_n=15, trend_threshold=9.0):
        self.window = deque(maxlen=window)
        self.recent = deque(maxlen=stuck_n)
        self.trend = deque(maxlen=trend_n)
        self.min_samples, self.z_threshold = min_samples, z_threshold
        self.stuck_n, self.cooldown = stuck_n, cooldown
        self.trend_n, self.trend_threshold = trend_n, trend_threshold
        self._n = 0
        self._last_alert = {}

    def _allowed(self, kind, cooldown=None):
        gap = self.cooldown if cooldown is None else cooldown
        last = self._last_alert.get(kind)
        if last is not None and self._n - last < gap:
            return False
        self._last_alert[kind] = self._n
        return True

    def update(self, r: Reading):
        self._n += 1
        alerts = []
        lo, hi = LIMITS.get(r.metric, (None, None))
        if hi is not None and r.value > hi and self._allowed("threshold"):
            alerts.append(Alert(r.ts, r.device, r.metric, "threshold", "critical",
                                f"{r.metric} {r.value:g} {r.unit} above limit {hi:g}", r.value))
        if lo is not None and r.value < lo and self._allowed("threshold"):
            alerts.append(Alert(r.ts, r.device, r.metric, "threshold", "critical",
                                f"{r.metric} {r.value:g} {r.unit} below limit {lo:g}", r.value))

        self.trend.append(r.value)
        if len(self.window) >= self.min_samples:
            med = statistics.median(self.window)
            mad = statistics.median(abs(v - med) for v in self.window)
            scale = max(1.4826 * mad, 0.001 * abs(med), 1e-6)   # robust sigma estimate
            z = (r.value - med) / scale
            if len(self.trend) == self.trend_n:
                # Least-squares slope over the last trend_n samples, in units of its own standard error.
                # Catches slow drift that the rolling median would otherwise absorb.
                n = self.trend_n
                xm = (n - 1) / 2
                sxx = n * (n * n - 1) / 12
                slope = sum((i - xm) * v for i, v in enumerate(self.trend)) / sxx
                # Noise level from first differences: unaffected by seasonality and by the trend itself.
                w = list(self.window)
                diffs = [b - a for a, b in zip(w, w[1:])]
                dm = statistics.median(diffs)
                noise = max(1.4826 * statistics.median(abs(d - dm) for d in diffs) / 2 ** 0.5,
                            0.001 * abs(med), 1e-6)
                tz = slope / (noise / sxx ** 0.5)
                if abs(tz) >= self.trend_threshold and self._allowed("trend", 30):
                    alerts.append(Alert(r.ts, r.device, r.metric, "trend", "warning",
                                        f"{r.metric} is trending {'up' if slope > 0 else 'down'} "
                                        f"at {slope:+.2f} {r.unit}/sample ({tz:+.1f} sigma)", r.value))
            if abs(z) >= self.z_threshold and self._allowed("zscore"):
                alerts.append(Alert(r.ts, r.device, r.metric, "zscore", "warning",
                                    f"{r.metric} {r.value:g} {r.unit} deviates {z:+.1f} sigma from recent median {med:g}",
                                    r.value))
        self.window.append(r.value)

        self.recent.append(r.value)
        if len(self.recent) == self.stuck_n and len(set(self.recent)) == 1 and self._allowed("stuck", 30):
            alerts.append(Alert(r.ts, r.device, r.metric, "stuck", "warning",
                                f"{r.metric} reported {r.value:g} {r.unit} for {self.stuck_n} samples in a row (sensor stuck?)",
                                r.value))
        return alerts
