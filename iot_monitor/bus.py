"""Message transport. MemoryBus needs nothing; MqttBus talks to a real MQTT broker."""
from __future__ import annotations

import threading


def topic_matches(pattern: str, topic: str) -> bool:
    """MQTT-style matching: '+' = one level, '#' = everything below (must be last)."""
    p, t = pattern.split("/"), topic.split("/")
    for i, part in enumerate(p):
        if part == "#":
            return i == len(p) - 1
        if i >= len(t):
            return False
        if part != "+" and part != t[i]:
            return False
    return len(p) == len(t)


class MemoryBus:
    """In-process publish/subscribe with MQTT topic semantics. Used for tests and the demo."""

    def __init__(self):
        self._subs = []
        self._lock = threading.Lock()

    def subscribe(self, pattern, callback):
        with self._lock:
            self._subs.append((pattern, callback))

    def publish(self, topic, payload):
        with self._lock:
            subs = list(self._subs)
        for pattern, cb in subs:
            if topic_matches(pattern, topic):
                cb(topic, payload)

    def close(self):
        pass


class MqttBus:
    """Thin wrapper over paho-mqtt (pip install paho-mqtt). Same interface as MemoryBus."""

    def __init__(self, host="localhost", port=1883, client_id=""):
        import paho.mqtt.client as mqtt  # imported lazily so the rest works without it

        try:  # paho-mqtt >= 2.0
            self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id)
        except AttributeError:  # paho-mqtt 1.x
            self._client = mqtt.Client(client_id)
        self._client.connect(host, port, keepalive=30)
        self._client.loop_start()

    def subscribe(self, pattern, callback):
        self._client.message_callback_add(pattern, lambda _c, _u, m: callback(m.topic, m.payload))
        self._client.subscribe(pattern)

    def publish(self, topic, payload):
        self._client.publish(topic, payload)

    def close(self):
        self._client.loop_stop()
        self._client.disconnect()
