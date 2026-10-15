import json
import threading
import unittest
import urllib.error
import urllib.request

from iot_monitor.dashboard import make_server
from iot_monitor.schema import Reading
from iot_monitor.storage import Store


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = Store()
        for i in range(10):
            cls.store.add_reading(Reading("pump-01", "temperature", 70 + i, 1e9 + i, i, "C"))
        cls.server = make_server(cls.store, "127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_page(self):
        code, body = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn("IoT Sensor Monitor", body)

    def test_api(self):
        self.assertEqual(json.loads(self.get("/api/stats")[1])["readings"], 10)
        self.assertEqual(json.loads(self.get("/api/latest")[1])[0]["value"], 79.0)
        series = json.loads(self.get("/api/series?device=pump-01&metric=temperature&limit=4")[1])
        self.assertEqual([p["value"] for p in series], [76.0, 77.0, 78.0, 79.0])
        self.assertEqual(json.loads(self.get("/api/alerts")[1]), [])

    def test_bad_parameters(self):
        self.assertEqual(self.get("/api/series?device=pump-01")[0], 400)
        self.assertEqual(self.get("/api/series?device=a%27%3B--&metric=temperature")[0], 400)
        self.assertEqual(self.get("/api/series?device=pump-01&metric=temperature&limit=abc")[0], 200)
        self.assertEqual(self.get("/nope")[0], 404)


if __name__ == "__main__":
    unittest.main()
