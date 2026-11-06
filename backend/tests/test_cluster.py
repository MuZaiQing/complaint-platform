import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cluster


class TestValidatePath(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(cluster.validate_path("/data/cfpb_struct/input/complaints_clean.csv"),
                         "/data/cfpb_struct/input/complaints_clean.csv")
        self.assertEqual(cluster.validate_path("/data/output/"), "/data/output")

    def test_reject(self):
        for bad in ["data/out", "", None, "/data/../etc", "/data/out;rm -rf /", "/data/out x", "C:\\data"]:
            with self.assertRaises(ValueError):
                cluster.validate_path(bad)


class TestParse(unittest.TestCase):
    def test_progress(self):
        self.assertEqual(cluster.parse_progress("2026-11-06 10:00:01,234 INFO map 40% reduce 0%"),
                         {"map": 40, "reduce": 0})
        self.assertIsNone(cluster.parse_progress("job is running"))

    def test_app_id(self):
        self.assertEqual(cluster.find_app_id("Submitting tokens ... application_1762300000000_0042"),
                         "application_1762300000000_0042")
        self.assertIsNone(cluster.find_app_id("no app here"))

    def test_clean_ansi(self):
        self.assertEqual(cluster.clean_ansi("\x1b[1;32mINFO\x1b[0m ok"), "INFO ok")

    def test_parse_rows(self):
        rows = list(cluster.parse_rows(["CA\t120\n", "TX\t98\n", "\n"], "tsv", 2))
        self.assertEqual(rows, [("CA", 120), ("TX", 98)])
        with self.assertRaises(ValueError):
            list(cluster.parse_rows(["CA\t120\textra\n"], "tsv", 2))

    def test_parse_rows_csv(self):
        self.assertEqual(list(cluster.parse_rows(["CA,120\n"], "csv", 2)), [("CA", 120)])

    def test_numeric_coerce(self):
        self.assertEqual(cluster.coerce("120"), 120)
        self.assertEqual(cluster.coerce("CA"), "CA")


class TestHistory(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.json"
            cluster.save_history([{"run_id": "r1", "state": "success"}], p)
            self.assertEqual(cluster.load_history(p)[0]["run_id"], "r1")
            p.write_text("{broken", encoding="utf-8")
            self.assertEqual(cluster.load_history(p), [])


class TestConfig(unittest.TestCase):
    def test_load_jobs(self):
        jobs = cluster.load_job_configs()
        self.assertEqual(len(jobs), 10)
        self.assertIn("fcc_state", jobs)
        self.assertEqual(jobs["fcc_state"]["columns"], ["state_code", "complaint_count"])

    def test_target_table_whitelist(self):
        jobs = cluster.load_job_configs()
        for j in jobs.values():
            self.assertIn(j["target_table"], cluster.STATS_TABLES)


if __name__ == "__main__":
    unittest.main()
