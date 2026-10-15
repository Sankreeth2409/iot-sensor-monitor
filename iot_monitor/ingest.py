"""Subscribes to the bus, validates, stores, and runs the detectors."""
from __future__ import annotations

import logging
import threading

from .anomaly import Alert, Detector
from .schema import TOPIC_PREFIX, ValidationError, parse_reading

log = logging.getLogger("iot_monitor.ingest")


class Ingestor:
    def __init__(self, bus, store, pattern=f"{TOPIC_PREFIX}/+/+", detector_factory=Detector):
        self.bus, self.store, self.pattern = bus, store, pattern
        self._factory = detector_factory
        self._detectors, self._last_seen, self._stale = {}, {}, set()
        self._lock = threading.Lock()
        self.received = self.accepted = self.rejected = self.alerts_raised = 0

    def start(self):
        self.bus.subscribe(self.pattern, self.on_message)

    def on_message(self, topic, payload):
        with self._lock:
            self.received += 1
            try:
                r = parse_reading(payload, topic)
            except ValidationError as exc:
                self.rejected += 1
                log.warning("rejected message on %s: %s", topic, exc)
                return
            self.accepted += 1
            self.store.add_reading(r)
            key = (r.device, r.metric)
            self._last_seen[key] = r.ts
            self._stale.discard(key)
            det = self._detectors.setdefault(key, self._factory())
            for a in det.update(r):
                self._raise(a)

    def check_stale(self, now, max_age):
        """Raise one 'stale' alert for each series that has not reported for max_age seconds."""
        with self._lock:
            for key, last in self._last_seen.items():
                if now - last > max_age and key not in self._stale:
                    self._stale.add(key)
                    self._raise(Alert(now, key[0], key[1], "stale", "warning",
                                      f"no data from {key[0]}/{key[1]} for {now - last:.1f} s"))

    def _raise(self, alert):
        self.alerts_raised += 1
        self.store.add_alert(alert)
        log.info("ALERT %s %s/%s: %s", alert.kind, alert.device, alert.metric, alert.message)
