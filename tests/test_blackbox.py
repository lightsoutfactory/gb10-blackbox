"""python3 -m unittest discover -s tests"""
import datetime as dt
import importlib.machinery
import importlib.util
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "gb10-blackbox")
loader = importlib.machinery.SourceFileLoader("gb10_blackbox", SCRIPT)
spec = importlib.util.spec_from_loader("gb10_blackbox", loader)
bb = importlib.util.module_from_spec(spec)
loader.exec_module(bb)

T0 = dt.datetime(2026, 11, 14, 10, 0, tzinfo=dt.timezone.utc)


def line(minute, hot, gpu="78C,9.0W,0%,500MHz", used=78000, total=124545, start=T0):
    ts = start + dt.timedelta(minutes=minute)
    return f"{ts:%Y-%m-%dT%H:%M:%SZ} hot={hot} zones={hot},84,{hot - 2} gpu={gpu} load=8.46,7.18,7.54 mem={used}/{total}MB\n"


class Record(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.dir.name, "bb.log")

    def tearDown(self):
        self.dir.cleanup()

    def write(self, lines):
        with open(self.log, "w") as f:
            f.writelines(lines)

    def test_reading_matches_the_format_it_is_read_back_with(self):
        bb.zones = lambda: [92, 84, 90]
        bb.gpu = lambda: {"t": 83, "w": 53.01, "u": 96, "mhz": 1976}
        bb.memory = lambda: (101087, 124545)
        bb.loadavg = lambda: "7.89,5.34,4.75"
        s = bb.reading(T0)
        self.assertEqual(s, "2026-11-14T10:00:00Z hot=92 zones=92,84,90 gpu=83C,53.0W,96%,1976MHz "
                            "load=7.89,5.34,4.75 mem=101087/124545MB")
        row = bb.Row(bb.LINE.match(s))
        self.assertEqual((row.hot, row.gpu["mhz"], row.used), (92, 1976, 101087))
        bb.gpu = lambda: None
        bb.zones = lambda: []
        s = bb.reading(T0)
        self.assertIn("hot=-1 zones=- gpu=-", s)
        self.assertIsNone(bb.Row(bb.LINE.match(s)).gpu)

    def test_record_appends_and_trims_to_whole_lines(self):
        bb.zones = lambda: [70]
        bb.gpu = lambda: None
        bb.memory = lambda: (1000, 2000)
        bb.loadavg = lambda: "0.10,0.20,0.30"
        for _ in range(3):
            bb.record(self.log, 64)
        self.assertEqual(len(bb.read_rows(self.log)), 3)
        self.write([line(m, 80) for m in range(1000)])
        bb.trim(self.log)
        rows = bb.read_rows(self.log)
        with open(self.log) as f:
            self.assertEqual(sum(1 for _ in f), len(rows))
        self.assertTrue(450 < len(rows) < 550)
        self.assertEqual(rows[-1].ts, T0 + dt.timedelta(minutes=999))

    def test_a_hot_power_off_with_the_gpu_idle(self):
        self.write([line(m, 90 + m % 4) for m in range(10)] + [line(m, 98) for m in range(10, 13)]
                   + [line(m, 60) for m in range(45, 50)])
        rows = bb.read_rows(self.log)
        found = bb.gaps(rows, 5)
        self.assertEqual(len(found), 1)
        kind, text, before = bb.verdict(rows, found[0][0], 93, shutdowns=[])
        self.assertEqual(kind, "HEAT")
        self.assertIn("98 C", text)
        self.assertIn("CPU cores", text)
        self.assertEqual(before[-1].ts, T0 + dt.timedelta(minutes=12))

    def test_a_hot_power_off_under_gpu_load(self):
        self.write([line(m, 97, gpu="88C,43.0W,96%,1976MHz") for m in range(5)] + [line(m, 60) for m in range(30, 32)])
        rows = bb.read_rows(self.log)
        kind, text, _ = bb.verdict(rows, bb.gaps(rows, 5)[0][0], 93, shutdowns=[])
        self.assertEqual(kind, "HEAT")
        self.assertIn("GPU was busy (96% at 1976 MHz)", text)

    def test_a_planned_restart_is_not_blamed_on_heat(self):
        self.write([line(m, 97) for m in range(5)] + [line(m, 60) for m in range(20, 22)])
        rows = bb.read_rows(self.log)
        kind, _, _ = bb.verdict(rows, 4, 93, shutdowns=[T0 + dt.timedelta(minutes=5)])
        self.assertEqual(kind, "CLEAN")
        kind, _, _ = bb.verdict(rows, 4, 93, shutdowns=[T0 - dt.timedelta(days=3)])
        self.assertEqual(kind, "HEAT")

    def test_cool_and_memory(self):
        self.write([line(m, 80) for m in range(5)] + [line(m, 60) for m in range(20, 22)])
        rows = bb.read_rows(self.log)
        self.assertEqual(bb.verdict(rows, 4, 93, shutdowns=[])[0], "COOL")
        self.write([line(m, 80, used=123000) for m in range(5)] + [line(m, 60) for m in range(20, 22)])
        rows = bb.read_rows(self.log)
        self.assertEqual(bb.verdict(rows, 4, 93, shutdowns=[])[0], "MEMORY")

    def test_a_clock_that_went_back_after_power_loss_is_a_gap(self):
        old = dt.datetime(2026, 6, 5, 3, 0, tzinfo=dt.timezone.utc)
        self.write([line(m, 96) for m in range(5)] + [line(m, 50, start=old) for m in range(3)])
        rows = bb.read_rows(self.log)
        self.assertEqual(bb.gaps(rows, 5), [(4, 5)])
        out = io.StringIO()
        with redirect_stdout(out):
            bb.clean_shutdowns = lambda: []
            bb.why(self.log, 5, 93, 3)
        self.assertIn("the clock went back", out.getvalue())
        self.assertIn("HEAT 1", out.getvalue())

    def test_bands(self):
        self.write([line(m, 85 + m % 13, gpu="80C,20.0W,96%,1976MHz") for m in range(1300)])
        out = io.StringIO()
        with redirect_stdout(out):
            bb.bands(self.log, 30)
        text = out.getvalue()
        self.assertIn("highest 97 C", text)
        self.assertIn("100 C or more:   0.0%", text)
        self.assertIn("SM clock median 1976 MHz", text)

    def test_other_lines_are_ignored(self):
        self.write(["garbage\n", line(0, 80), "2026-11-14T10:00:28Z xid24h=0\n", line(1, 81)])
        self.assertEqual([r.hot for r in bb.read_rows(self.log)], [80, 81])


if __name__ == "__main__":
    unittest.main()
