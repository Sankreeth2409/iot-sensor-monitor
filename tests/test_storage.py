import unittest

from iot_monitor.anomaly import Alert
from iot_monitor.schema import Reading
from iot_monitor.storage import Store


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.s = Store()
        for i in range(5):
            self.s.add_reading(Reading("a", "temperature", 70 + i, 100 + i, i, "C"))
        self.s.add_reading(Reading("b", "voltage", 230, 100, 0, "V"))

    def test_latest_one_row_per_series(self):
        latest = {(r["device"], r["metric"]): r["value"] for r in self.s.latest()}
        self.assertEqual(latest, {("a", "temperature"): 74.0, ("b", "voltage"): 230.0})

    def test_series_is_chronological_and_limited(self):
        pts = self.s.series("a", "temperature", limit=3)
        self.assertEqual([p["value"] for p in pts], [72.0, 73.0, 74.0])

    def test_alerts_newest_first(self):
        self.s.add_alert(Alert(1, "a", "temperature", "zscore", "warning", "first", 1.0))
        self.s.add_alert(Alert(2, "a", "temperature", "stuck", "warning", "second", 2.0))
        self.assertEqual([a["message"] for a in self.s.alerts(10)], ["second", "first"])

    def test_counts(self):
        self.assertEqual(self.s.counts(), {"readings": 6, "alerts": 0, "series": 2})

    def test_sql_injection_is_inert(self):
        self.assertEqual(self.s.series("a'; DROP TABLE readings;--", "temperature"), [])
        self.assertEqual(self.s.counts()["readings"], 6)


if __name__ == "__main__":
    unittest.main()
