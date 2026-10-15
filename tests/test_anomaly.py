import random
import unittest

from iot_monitor.anomaly import Detector
from iot_monitor.schema import Reading


def feed(det, values, metric="temperature", unit="C"):
    out = []
    for i, v in enumerate(values):
        out += det.update(Reading("d", metric, v, 1.7e9 + i, i, unit))
    return out


def noisy(n, mean=70.0, sd=0.5, seed=1):
    rng = random.Random(seed)
    return [round(rng.gauss(mean, sd), 3) for _ in range(n)]


class AnomalyTests(unittest.TestCase):
    def test_quiet_series_no_alerts(self):
        self.assertEqual(feed(Detector(), noisy(300)), [])

    def test_spike_detected(self):
        vals = noisy(60)
        vals[40] += 10
        kinds = [a.kind for a in feed(Detector(), vals)]
        self.assertIn("zscore", kinds)

    def test_no_zscore_before_enough_samples(self):
        vals = noisy(10)
        vals[5] += 50
        self.assertEqual([a for a in feed(Detector(min_samples=20), vals) if a.kind == "zscore"], [])

    def test_hard_limit_is_critical(self):
        alerts = feed(Detector(), noisy(30) + [95.0])
        crit = [a for a in alerts if a.kind == "threshold"]
        self.assertEqual(len(crit), 1)
        self.assertEqual(crit[0].severity, "critical")

    def test_lower_limit_for_voltage(self):
        alerts = feed(Detector(), noisy(30, 230, 1.0) + [200.0], metric="voltage", unit="V")
        self.assertTrue(any(a.kind == "threshold" and "below" in a.message for a in alerts))

    def test_stuck_sensor(self):
        alerts = feed(Detector(), noisy(40) + [70.123] * 20)
        self.assertEqual([a.kind for a in alerts if a.kind == "stuck"], ["stuck"])

    def test_slow_drift_flagged_before_limit(self):
        vals = noisy(60) + [70 + 0.6 * k + random.Random(k).gauss(0, 0.5) for k in range(1, 40)]
        alerts = feed(Detector(), vals)
        trend = [a for a in alerts if a.kind == "trend"]
        limit = [a for a in alerts if a.kind == "threshold"]
        self.assertTrue(trend)
        if limit:
            self.assertLess(trend[0].ts, limit[0].ts)

    def test_cooldown_prevents_alert_storm(self):
        vals = noisy(40) + [95.0] * 5
        self.assertEqual(len([a for a in feed(Detector(cooldown=10), vals) if a.kind == "threshold"]), 1)


if __name__ == "__main__":
    unittest.main()
