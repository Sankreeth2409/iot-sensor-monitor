import json
import unittest

from iot_monitor.schema import ValidationError, parse_reading

GOOD = {"device": "pump-01", "metric": "temperature", "value": 71.2, "unit": "C", "ts": 1.7e9, "seq": 3}


def msg(**over):
    d = dict(GOOD)
    d.update(over)
    return json.dumps(d)


class SchemaTests(unittest.TestCase):
    def test_valid(self):
        r = parse_reading(msg(), "factory/pump-01/temperature")
        self.assertEqual((r.device, r.metric, r.value, r.seq, r.unit), ("pump-01", "temperature", 71.2, 3, "C"))

    def test_accepts_bytes(self):
        self.assertEqual(parse_reading(msg().encode()).value, 71.2)

    def test_rejects_bad_input(self):
        bad = [
            "not json", "[1,2]", "null", b"\xff\xfe",
            msg(value="71"), msg(value=True), msg(value=float("nan")), msg(value=1e9),
            msg(metric="humidity"), msg(device=""), msg(device="a b"), msg(device="../etc"),
            msg(ts=0), msg(ts="now"), msg(seq=-1), msg(seq=1.5), msg(seq=True),
        ]
        for payload in bad:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    parse_reading(payload)

    def test_missing_field(self):
        d = dict(GOOD)
        del d["seq"]
        with self.assertRaises(ValidationError):
            parse_reading(json.dumps(d))

    def test_topic_must_match_payload(self):
        with self.assertRaises(ValidationError):
            parse_reading(msg(), "factory/pump-02/temperature")


if __name__ == "__main__":
    unittest.main()
