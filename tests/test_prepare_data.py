import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_data import prepare


class ServiceStartTests(unittest.TestCase):
    def test_stale_doktor_file_does_not_extend_wp_series(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            logs = root / "data" / "202304"
            logs.mkdir(parents=True)
            template = 'IP000001 - - [{} +0900] "GET / HTTP/1.1" 200 1 "-" "test"\n'
            (logs / "access.wp.log.1").write_text(template.format("02/Apr/2023:00:00:44"))
            stale_log = template.format("29/Mar/2023:01:13:53")
            (logs / "access.doktor.log.1").write_text(stale_log)
            (logs / "access.doktor.log.2").write_text(stale_log)

            with contextlib.redirect_stdout(io.StringIO()):
                audit, hourly, daily = prepare(root / "data", root / "outputs")
            wp = hourly[hourly["service"] == "wp"]
            doktor = hourly[hourly["service"] == "doktor"]
            self.assertEqual(wp.iloc[0]["time_local"], "2023-04-02T00:00:00+09:00")
            self.assertTrue(doktor.iloc[0]["time_local"].startswith("2023-03-29"))
            self.assertEqual(wp["requests"].sum(), 1)
            self.assertEqual(audit["records_used"].sum(), 2)
            self.assertEqual(daily[daily["service"] == "wp"].iloc[0]["unknown_hours"], 23)

            with contextlib.redirect_stdout(io.StringIO()):
                _, hourly, _ = prepare(root / "data", root / "explicit", start_date="2023-03-29")
            wp = hourly[hourly["service"] == "wp"]
            self.assertEqual(wp.iloc[0]["time_local"], "2023-03-29T00:00:00+09:00")


if __name__ == "__main__":
    unittest.main()
