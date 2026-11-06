import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cluster_probe as p


class TestManifest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(p.main_class_from_manifest("Manifest-Version: 1.0\nMain-Class: a.B\n"), "a.B")

    def test_continued_line(self):
        text = "Manifest-Version: 1.0\nMain-Class: org.example.very.long.\n package.Main\n"
        self.assertEqual(p.main_class_from_manifest(text), "org.example.very.long.package.Main")

    def test_missing(self):
        self.assertIsNone(p.main_class_from_manifest("Manifest-Version: 1.0\n"))
        self.assertIsNone(p.main_class_from_manifest(""))

    def test_crlf_and_case(self):
        self.assertEqual(p.main_class_from_manifest("main-class: x.Y\r\n"), "x.Y")


class TestCommand(unittest.TestCase):
    def test_with_main_class(self):
        self.assertEqual(
            p.build_jar_command("/home/hadoop/jars/A.jar", "org.example.Main", "/in", "/out"),
            "hadoop jar /home/hadoop/jars/A.jar org.example.Main /in /out")

    def test_without_main_class(self):
        self.assertEqual(
            p.build_jar_command("/home/hadoop/jars/A.jar", None, "/in", "/out"),
            "hadoop jar /home/hadoop/jars/A.jar /in /out")


class TestLayout(unittest.TestCase):
    def test_tsv_ok(self):
        got = p.detect_layout(["CA\t446841\n", "TX\t301119\n"], 2)
        self.assertEqual((got["sep"], got["ncols"], got["mismatch"]), ("tsv", 2, False))
        self.assertEqual(got["sample"][0], "CA\t446841")

    def test_csv(self):
        got = p.detect_layout(['"AK",7508'], 2)
        self.assertEqual((got["sep"], got["ncols"]), ("csv", 2))

    def test_mismatch(self):
        got = p.detect_layout(["only-one-col"], 2)
        self.assertTrue(got["ncols"] == 1 and got["mismatch"])
        self.assertEqual(got["sep"], "csv")

    def test_empty(self):
        got = p.detect_layout([], 2)
        self.assertEqual(got["ncols"], 0)
        self.assertTrue(got["mismatch"])


class TestColumns(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(p.diff_columns(["a", "b"], ["a", "b", "c"])["ok"])

    def test_missing(self):
        got = p.diff_columns(["a", "missing"], ["a", "b"])
        self.assertFalse(got["ok"])
        self.assertEqual(got["missing"], ["missing"])

    def test_extra(self):
        self.assertEqual(p.diff_columns(["a"], ["a", "b"])["extra"], ["b"])


class TestInputCheck(unittest.TestCase):
    def test_cmd(self):
        self.assertEqual(p.input_check_cmd("/data/x.csv"),
                         "hdfs dfs -test -e /data/x.csv && echo OK || echo MISSING")

    def test_parse(self):
        self.assertTrue(p.parse_input_check("OK\n"))
        self.assertFalse(p.parse_input_check("MISSING\n"))
        self.assertFalse(p.parse_input_check(""))


class TestGuessPid(unittest.TestCase):
    def test_pick_latest(self):
        out = ("1111 java RunJar /home/hadoop/jars/A.jar /in /out\n"
               "2222 java RunJar /home/hadoop/jars/A.jar /in2 /out2\n"
               "3333 bash pgrep -af RunJar\n")
        self.assertEqual(p.guess_pid(out, "A.jar"), 2222)

    def test_ignore_other_jar(self):
        out = "1111 java RunJar /home/hadoop/jars/B.jar /in /out\n"
        self.assertIsNone(p.guess_pid(out, "A.jar"))

    def test_empty(self):
        self.assertIsNone(p.guess_pid("", "A.jar"))


class TestCsv(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(p.csv_row(["CA", 446841]), "CA,446841\n")

    def test_escape(self):
        self.assertEqual(p.csv_row(['a,b', 'he said "hi"', "x\ny", None]),
                         '"a,b","he said ""hi""","x\ny",\n')


if __name__ == "__main__":
    unittest.main()
