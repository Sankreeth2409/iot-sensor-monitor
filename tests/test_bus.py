import unittest

from iot_monitor.bus import MemoryBus, topic_matches


class BusTests(unittest.TestCase):
    def test_topic_matching(self):
        cases = [
            ("factory/+/+", "factory/pump-01/temperature", True),
            ("factory/+/+", "factory/pump-01", False),
            ("factory/+/+", "factory/a/b/c", False),
            ("factory/#", "factory/a/b/c", True),
            ("factory/pump-01/+", "factory/pump-02/temperature", False),
            ("#", "anything/at/all", True),
        ]
        for pattern, topic, expected in cases:
            with self.subTest(pattern=pattern, topic=topic):
                self.assertEqual(topic_matches(pattern, topic), expected)

    def test_publish_reaches_matching_subscribers_only(self):
        bus, got = MemoryBus(), []
        bus.subscribe("factory/+/temperature", lambda t, p: got.append(t))
        bus.publish("factory/a/temperature", "x")
        bus.publish("factory/a/voltage", "x")
        self.assertEqual(got, ["factory/a/temperature"])


if __name__ == "__main__":
    unittest.main()
