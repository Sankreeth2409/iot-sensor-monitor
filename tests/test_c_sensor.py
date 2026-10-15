import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from iot_monitor.bus import MemoryBus
from iot_monitor.cli import bridge_lines
from iot_monitor.schema import parse_reading

SRC = Path(__file__).resolve().parent.parent / "c" / "sensor.c"
CC = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")


@unittest.skipUnless(CC, "no C compiler found")
class CSensorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.exe = str(Path(cls.tmp.name) / "sensor")
        subprocess.run([CC, "-std=c99", "-O2", "-Wall", "-Wextra", str(SRC), "-o", cls.exe, "-lm"], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_sensor(self, *args):
        return subprocess.run([self.exe, *args], capture_output=True, text=True, check=True).stdout.splitlines()

    def test_every_line_is_valid(self):
        lines = self.run_sensor("c-node-01", "50", "3")
        self.assertEqual(len(lines), 150)
        for line in lines:
            parse_reading(line)

    def test_reproducible_values(self):
        strip = lambda ls: [l.split('"ts"')[0] for l in ls]
        self.assertEqual(strip(self.run_sensor("n", "20", "5")), strip(self.run_sensor("n", "20", "5")))

    def test_bridge_publishes_c_output(self):
        bus, got = MemoryBus(), []
        bus.subscribe("factory/+/+", lambda t, p: got.append(t))
        ok, bad = bridge_lines(self.run_sensor("c-node-01", "10", "1"), bus)
        self.assertEqual((ok, bad, len(got)), (30, 0, 30))

    def test_bridge_skips_bad_lines(self):
        bus = MemoryBus()
        self.assertEqual(bridge_lines(["garbage", "", '{"device":"x"}'], bus), (0, 2))

    def test_bad_arguments_exit_nonzero(self):
        r = subprocess.run([self.exe, "n", "-5"], capture_output=True)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
