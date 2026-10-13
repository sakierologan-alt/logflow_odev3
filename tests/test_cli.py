# tests/test_cli.py
"""Komut satırı argüman işleme ve uçtan uca çalıştırma testleri."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

import main as cli
from filters import PredicateFilterStage
from projection import ProjectionStage
from sinks import FileSink
from components import ConsoleSink
from tests.helpers import FIXTURES_DIR

FIXTURE = os.path.join(FIXTURES_DIR, "small.log")


def run_cli(*argv):
    """main()'i çalıştırır; (çıkış kodu, stdout, stderr) döndürür."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as exit_:
            code = exit_.code
    return code, out.getvalue(), err.getvalue()


class TestArgumentParsing(unittest.TestCase):

    def parse(self, *argv):
        return cli.build_arg_parser().parse_args(list(argv))

    def test_defaults_are_no_filters_and_no_projection(self):
        args = self.parse("in.log")
        self.assertIsNone(args.min_status)
        self.assertIsNone(args.path_prefix)
        self.assertIsNone(args.fields)
        self.assertIsNone(args.output)

    def test_all_options(self):
        args = self.parse("in.log", "--min-status", "400", "--path-prefix", "/api",
                          "--fields", "timestamp,clientIp,status", "-o", "out.jsonl",
                          "--since", "2000-10-10T20:00:00Z", "--until", "2000-10-11T00:00:00")
        self.assertEqual((args.min_status, args.path_prefix, args.output), (400, "/api", "out.jsonl"))
        self.assertEqual(args.fields, "timestamp,clientIp,status")
        self.assertEqual(args.since, datetime(2000, 10, 10, 20, 0, tzinfo=timezone.utc))
        self.assertEqual(args.until, datetime(2000, 10, 11, 0, 0, tzinfo=timezone.utc))  # naive -> UTC

    def test_invalid_time_is_rejected(self):
        code, _, err = run_cli(FIXTURE, "--since", "dün")
        self.assertEqual(code, 2)
        self.assertIn("geçersiz zaman", err)

    def test_non_integer_min_status_is_rejected(self):
        code, _, _ = run_cli(FIXTURE, "--min-status", "çok")
        self.assertEqual(code, 2)


class TestBuildPipeline(unittest.TestCase):

    def build(self, *argv):
        return cli.build_pipeline(cli.build_arg_parser().parse_args(list(argv)))

    def test_only_requested_stages_are_added_in_documented_order(self):
        pipeline, _, filters, sink = self.build(
            "in.log", "--min-status", "400", "--path-prefix", "/api", "--fields", "status")
        kinds = [type(s).__name__ for s in pipeline.stages]
        self.assertEqual(kinds, ["ParserStage", "PredicateFilterStage", "PredicateFilterStage", "ProjectionStage"])
        self.assertEqual([f.name for f in filters], ["min-status>=400", "path-prefix=/api"])
        self.assertIsInstance(sink, ConsoleSink)

    def test_no_options_means_parser_only(self):
        pipeline, _, filters, _ = self.build("in.log")
        self.assertEqual(len(pipeline.stages), 1)
        self.assertEqual(filters, [])

    def test_output_option_selects_file_sink_and_time_range_adds_one_filter(self):
        pipeline, _, filters, sink = self.build("in.log", "-o", "o.jsonl", "--since", "2000-01-01T00:00:00Z")
        self.assertIsInstance(sink, FileSink)
        self.assertEqual([f.name for f in filters], ["time-range"])


class TestMainEndToEnd(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.output = os.path.join(self._tmp.name, "out.jsonl")

    def test_filter_project_write_and_report(self):
        code, out, _ = run_cli(FIXTURE, "--min-status", "400", "--path-prefix", "/api",
                               "--fields", "timestamp,clientIp,status", "-o", self.output)
        self.assertEqual(code, 0)
        with open(self.output, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f]
        self.assertEqual([r["clientIp"] for r in rows], ["10.0.0.2", "10.0.0.3", "10.0.0.6"])
        self.assertEqual(list(rows[0]), ["timestamp", "clientIp", "status"])
        self.assertIn("Toplam Hatalı/Atlanan Satır Sayısı: 1", out)
        self.assertIn("Filtre min-status>=400: geçen=4, elenen=3", out)
        self.assertIn("Filtre path-prefix=/api: geçen=3, elenen=1", out)
        self.assertIn("3 kayıt yazıldı", out)

    def test_console_output_when_no_output_file(self):
        code, out, _ = run_cli(FIXTURE, "--min-status", "500", "--fields", "clientIp,status")
        self.assertEqual(code, 0)
        self.assertIn("clientIp=10.0.0.3 status=500", out)
        self.assertNotIn("10.0.0.1", out)

    def test_time_range_filter(self):
        code, out, _ = run_cli(FIXTURE, "--since", "2000-10-10T20:57:00Z", "--until", "2000-10-10T21:00:00Z",
                               "--fields", "clientIp", "-o", self.output)
        self.assertEqual(code, 0)
        with open(self.output, encoding="utf-8") as f:
            self.assertEqual([json.loads(l)["clientIp"] for l in f], ["10.0.0.3", "10.0.0.4", "10.0.0.5"])

    def test_unknown_field_exits_with_error_and_writes_nothing(self):
        code, _, err = run_cli(FIXTURE, "--fields", "status,foo", "-o", self.output)
        self.assertEqual(code, 2)
        self.assertIn("Bilinmeyen alan 'foo'", err)
        self.assertFalse(os.path.exists(self.output))

    def test_missing_input_file_reports_error_and_does_not_create_output(self):
        code, _, err = run_cli(os.path.join(self._tmp.name, "yok.log"), "-o", self.output)
        self.assertEqual(code, 1)
        self.assertIn("Hata:", err)
        self.assertFalse(os.path.exists(self.output))  # girdi açılamadan çıktı dosyasına dokunulmadı

    def test_output_equal_to_input_is_refused_and_input_is_preserved(self):
        copy = os.path.join(self._tmp.name, "copy.log")
        with open(FIXTURE, encoding="utf-8") as src, open(copy, "w", encoding="utf-8") as dst:
            dst.write(src.read())
        code, _, err = run_cli(copy, "-o", copy)
        self.assertEqual(code, 2)
        self.assertIn("aynı olamaz", err)
        with open(copy, encoding="utf-8") as f:
            self.assertEqual(len(f.read().splitlines()), 8)  # girdi silinmedi


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
