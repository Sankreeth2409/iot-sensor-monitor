import json
import unittest

from iot_monitor.bus import MemoryBus
from iot_monitor.ingest import Ingestor
from iot_monitor.simulator import DEFAULT_FAULTS, default_fleet, run
from iot_monitor.storage import Store

START, STEPS = 1_700_000_000.0, 400


def run_fleet(seed=7, faults=True):
    bus, store = MemoryBus(), Store()
    ing = Ingestor(bus, store)
    ing.start()
    run(bus, default_fleet(seed, faults), STEPS, 1.0, start_ts=START,
        on_step=lambda i, ts: ing.check_stale(ts, 8.0))
    return ing, store


class PipelineTests(unittest.TestCase):
    def test_every_injected_fault_is_detected(self):
        _, store = run_fleet()
        alerts = store.all_alerts()
        for (device, metric), faults in DEFAULT_FAULTS.items():
            t0 = START + faults[0].start
            hits = [a for a in alerts if a["device"] == device and a["metric"] == metric and a["ts"] >= t0]
            with self.subTest(fault=f"{faults[0].kind} {device}/{metric}"):
                self.assertTrue(hits, "fault was not detected")

    def test_expected_alert_kinds(self):
        _, store = run_fleet()
        kinds = {(a["device"], a["metric"], a["kind"]) for a in store.all_alerts()}
        self.assertIn(("pump-02", "vibration", "zscore"), kinds)
        self.assertIn(("motor-01", "voltage", "stuck"), kinds)
        self.assertIn(("pump-02", "voltage", "stale"), kinds)
        self.assertTrue({("pump-01", "temperature", "trend"), ("pump-01", "temperature", "threshold")} & kinds)

    def test_drift_flagged_before_hard_limit(self):
        _, store = run_fleet()
        a = [x for x in store.all_alerts() if x["device"] == "pump-01" and x["metric"] == "temperature"]
        first = {}
        for x in a:
            first.setdefault(x["kind"], x["ts"])
        self.assertIn("trend", first)
        self.assertLess(first["trend"], first["threshold"])

    def test_no_false_alarms_without_faults(self):
        _, store = run_fleet(faults=False)
        self.assertEqual(store.all_alerts(), [])

    def test_no_false_alarms_on_clean_series_with_faults_elsewhere(self):
        _, store = run_fleet()
        faulted = set(DEFAULT_FAULTS)
        self.assertEqual([a for a in store.all_alerts() if (a["device"], a["metric"]) not in faulted], [])

    def test_garbage_is_rejected_not_stored(self):
        bus, store = MemoryBus(), Store()
        ing = Ingestor(bus, store)
        ing.start()
        bus.publish("factory/x/temperature", "not json")
        bus.publish("factory/x/temperature", json.dumps({"device": "x", "metric": "temperature", "value": 1e6,
                                                          "unit": "C", "ts": 1, "seq": 0}))
        bus.publish("factory/other/temperature", json.dumps({"device": "x", "metric": "temperature", "value": 5,
                                                              "unit": "C", "ts": 1, "seq": 0}))
        self.assertEqual((ing.received, ing.accepted, ing.rejected), (3, 0, 3))
        self.assertEqual(store.counts()["readings"], 0)

    def test_simulation_is_reproducible(self):
        a = [r["value"] for r in run_fleet(3)[1].series("pump-01", "voltage", 2000)]
        b = [r["value"] for r in run_fleet(3)[1].series("pump-01", "voltage", 2000)]
        self.assertEqual(a, b)

    def test_dropout_produces_gap(self):
        _, store = run_fleet()
        self.assertEqual(len(store.series("pump-02", "voltage", 2000)), STEPS - 25)


if __name__ == "__main__":
    unittest.main()
